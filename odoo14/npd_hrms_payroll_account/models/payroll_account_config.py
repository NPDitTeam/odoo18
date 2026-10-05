# -*- coding: utf-8 -*-
"""การตั้งค่าลงบัญชีเงินเดือนรายบริษัท + เครื่องคำนวณรายการบัญชี

ทำเป็นโมเดลแยกแทนการเพิ่มฟิลด์บน res.company เพราะผู้ดูแลบัญชีแก้ res.company
ไม่ได้ (แบบ npd_hrms_medical ใช้ได้เฉพาะแอดมิน)

ยึดบรรทัดสลิป (payroll.salary.line) เป็นหลัก ไม่ใช่ฟิลด์บนสลิป: ข้อมูลจริงทุกบริษัท
ผลรวมบรรทัด = total_gross / total_deduction / net_salary พอดี แต่ฟิลด์รวมบางตัว
(income_other, expense_other) ไม่ตรงกับบรรทัดในสลิปที่ซิงก์มาจาก o14
"""
import logging
import re
from collections import defaultdict

import psycopg2
from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError

from .constants import (
    CONFIG_DEFAULTS, DEFAULT_CANDIDATES, DEFAULT_JOURNAL_NAME, DEFAULT_SPLIT_ROWS,
    EMPLOYER_SSO_LINE, KNOWN_LINES, LINE_TYPE_LABELS, SALARY_LINE, SPLIT_KEY_PARENT,
    SPLIT_KEYS, STATUS_DUPLICATE, STATUS_FOUND, STATUS_KEEP, STATUS_MANUAL,
    STATUS_MISSING, STATUS_REDUCE, STATUS_REVIEW,
)
from .payroll_account_move import slip_fingerprint

_logger = logging.getLogger(__name__)

EMPLOYER_SSO_LABEL = 'ประกันสังคมส่วนนายจ้าง'
PAYABLE_LABEL = 'เงินเดือนค้างจ่าย'
# เศษจากการปัดรายบรรทัดต่ำกว่านี้ปรับเข้าเงินเดือนค้างจ่ายได้ เกินนี้แปลว่าสลิปผิดจริง
MAX_RESIDUE = 1.0


def _norm(text):
    return re.sub(r'\s+', ' ', (text or '').strip())


def _fmt(amount):
    return '{:,.2f}'.format(amount or 0.0)


def _fmt_date(value):
    return value.strftime('%d/%m/%Y') if value else '-'


class NpdPayrollAccountConfig(models.Model):
    _name = 'npd.payroll.account.config'
    _description = 'ตั้งค่าลงบัญชีเงินเดือน'
    _inherit = ['mail.thread']
    _rec_name = 'company_id'
    _order = 'company_id'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True,
        default=lambda self: self.env.company, tracking=True)
    journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันเงินเดือน', check_company=True,
        domain=[('type', '=', 'general')], tracking=True,
        help='สมุดรายวันทั่วไปที่ใช้ลงรายการเงินเดือน')
    payable_account_id = fields.Many2one(
        'account.account', string='บัญชีเงินเดือนค้างจ่าย', check_company=True,
        domain=[('deprecated', '=', False)], tracking=True,
        help='เครดิตด้วยเงินสุทธิที่ต้องโอนให้พนักงาน (รวมเศษสตางค์ที่ปรับให้)')
    employer_sso_enabled = fields.Boolean(
        string='ตั้งค้างจ่ายประกันสังคมส่วนนายจ้าง', default=True, tracking=True,
        help='นายจ้างสมทบเท่ากับยอดหักประกันสังคมของลูกจ้างในแต่ละสลิป '
             'ปิดไว้ถ้าฝ่ายบัญชีบันทึกส่วนนายจ้างตอนนำส่งเอง (ไม่งั้นจะซ้ำ)')
    employer_sso_expense_account_id = fields.Many2one(
        'account.account', string='บัญชีค่าใช้จ่ายประกันสังคมส่วนนายจ้าง',
        check_company=True, domain=[('deprecated', '=', False)], tracking=True)
    employer_sso_payable_account_id = fields.Many2one(
        'account.account', string='บัญชีประกันสังคมรอนำส่ง (ส่วนนายจ้าง)',
        check_company=True, domain=[('deprecated', '=', False)], tracking=True)
    date_policy = fields.Selection([
        ('payment_date', 'วันที่จ่ายเงินของรอบ'),
        ('date_to', 'วันสิ้นสุดรอบ (วันตัดรอบ)'),
    ], string='วันที่ลงบัญชี', default='payment_date', required=True, tracking=True,
        help='วันที่จ่ายเงิน = ตรงกับเดือนที่ยื่น ภ.ง.ด.1 ของภาษีหัก ณ ที่จ่าย '
             'แก้วันที่ได้อีกครั้งในหน้าลงบัญชีก่อนกดยืนยัน')
    map_ids = fields.One2many(
        'npd.payroll.account.map', 'config_id', string='ผังบัญชีเงินเดือน', copy=True)
    map_missing_count = fields.Integer(
        string='แถวที่ยังไม่ได้เลือกบัญชี', compute='_compute_map_missing_count')
    default_report = fields.Html(
        string='ผลการสร้างค่าเริ่มต้น', readonly=True, sanitize=True, copy=False)

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)', 'บริษัทนี้มีการตั้งค่าลงบัญชีเงินเดือนแล้ว'),
    ]

    @api.depends('map_ids.account_id', 'map_ids.reduce_expense')
    def _compute_map_missing_count(self):
        for rec in self:
            rec.map_missing_count = len(rec.map_ids.filtered(
                lambda row: not row.account_id and not row.reduce_expense))

    # ==================================================================
    # สิทธิ์
    # ==================================================================
    @api.model
    def _npd_check_poster(self):
        """ต้องเป็นผู้ดูแลบัญชี และ ได้รับสิทธิ์ลงบัญชีเงินเดือน

        สิทธิ์ผู้ดูแลบัญชีอย่างเดียวไม่พอ เพราะบน prod มีถึง 83 คน (รวมพนักงานสาขา)
        ถ้าใช้ได้หมดทุกคนจะเห็นเงินเดือนรายสาขาของทุกบริษัท
        """
        if self.env.su:
            return True
        user = self.env.user
        if not (user.has_group('account.group_account_manager')
                and user.has_group('npd_hrms_payroll_account.group_payroll_account')):
            raise AccessError('ต้องเป็นผู้ดูแลบัญชีที่ได้รับสิทธิ์ลงบัญชีเงินเดือน')
        return True

    @api.model
    def _npd_allowed_companies(self):
        # ยึดบริษัทที่ผู้ใช้มีสิทธิ์ทั้งหมด ไม่ใช่เฉพาะที่ติ๊กในตัวสลับบริษัท
        # รอบเดียวมีสลิปหลายบริษัท ถ้ายึดตัวสลับ ผู้ใช้ต้องติ๊กครบทุกบริษัททุกครั้ง
        if self.env.su:
            return self.env['res.company'].sudo().search([])
        return self.env.user.company_ids

    @api.model
    def _npd_lock_message(self, company, date, action='ลงบัญชีเงินเดือน'):
        """ข้อความไทยเมื่อวันที่ติดล็อกงวด

        เช็คเองก่อนเพราะข้อความของ Odoo เป็นภาษาอังกฤษและโผล่ตอนสร้างรายการไปแล้ว
        """
        date = fields.Date.to_date(date)
        if not date:
            return False
        violations = company._get_lock_date_violations(
            date, fiscalyear=True, sale=False, purchase=False, tax=False, hard=True)
        if not violations:
            return False
        lock_date = max(violation[0] for violation in violations)
        return ('บริษัท %s ล็อกงวดบัญชีถึงวันที่ %s แล้ว %sวันที่ %s ไม่ได้ '
                'ให้ผู้ดูแลบัญชีเปิดงวดหรือเปลี่ยนวันที่ลงบัญชี' % (
                    company.name, _fmt_date(lock_date), action, _fmt_date(date)))

    # ==================================================================
    # หาบัญชีจากชื่อ
    # ==================================================================
    def _npd_company_accounts(self):
        self.ensure_one()
        return self.env['account.account'].sudo().with_company(self.company_id).search([
            ('company_ids', 'in', self.company_id.id),
            ('deprecated', '=', False),
        ])

    def _npd_account_name_index(self, accounts=None):
        """ชื่อบัญชี (ตัดช่องว่างซ้ำแล้ว) -> id ทั้งชื่อไทยและชื่ออังกฤษ

        ผังที่โหลดเข้ามาบางบริษัทเก็บชื่อไทยไว้ในช่องภาษาอังกฤษ จึงต้องเทียบทั้งสองภาษา
        """
        self.ensure_one()
        if accounts is None:
            accounts = self._npd_company_accounts()
        ids_by_name = defaultdict(set)
        for lang in ('th_TH', 'en_US'):
            for account in accounts.with_context(lang=lang):
                key = _norm(account.name)
                if key:
                    ids_by_name[key].add(account.id)
        return {'accounts': accounts, 'ids': ids_by_name}

    def _npd_find_account(self, candidates, name_index=None):
        """(บัญชี|None, 'found'|'duplicate'|'missing') — จับคู่จากชื่อ + ประเภทบัญชีเท่านั้น

        ไม่เดาจากรหัสเด็ดขาด: ฝ่ายบัญชีเปลี่ยนรหัสไปแล้วครั้งหนึ่ง และรหัสของ
        แต่ละผังไม่ตรงกัน (ค่าคอมมิชชั่น 5200-02 ในผังเช่า/ผลิต แต่ 5200-01 ในผังขนส่ง)
        เจอหลายบัญชีชื่อซ้ำก็ไม่เลือกให้ ปล่อยว่างดีกว่าลงผิดบัญชี
        """
        self.ensure_one()
        if name_index is None:
            name_index = self._npd_account_name_index()
        accounts = name_index['accounts']
        types = tuple(candidates.get('types') or ())
        for name in candidates.get('names') or ():
            ids = name_index['ids'].get(_norm(name)) or set()
            matches = accounts.browse(sorted(ids)).filtered(
                lambda account: not types or account.account_type in types)
            if len(matches) == 1:
                return matches, 'found'
            if len(matches) > 1:
                return None, 'duplicate'
        return None, 'missing'

    def _npd_account_display(self, account):
        self.ensure_one()
        if not account:
            return ''
        account = account.sudo().with_company(self.company_id)
        return ('%s %s' % (account.code or '', account.name or '')).strip()

    # ==================================================================
    # ผังบัญชีเงินเดือน
    # ==================================================================
    def _npd_map_index(self):
        self.ensure_one()
        return {
            (row.line_type, (row.line_name or '').strip(), row.department_id.id or False): row
            for row in self.sudo().map_ids
        }

    def _npd_resolve_account(self, line_type, key, department=None, index=None):
        """บัญชีของรายการ — แถวเฉพาะแผนกชนะแถวทั้งบริษัท"""
        self.ensure_one()
        if index is None:
            index = self._npd_map_index()
        dept_id = department.id if department else False
        row = (dept_id and index.get((line_type, key, dept_id))) \
            or index.get((line_type, key, False))
        if row:
            if row.account_id:
                return row.account_id
            if row.reduce_expense:
                # เครดิตบัญชีเดียวกับเงินเดือนของแผนกนั้น จะได้หักลดตรงตัว
                return self._npd_resolve_account('income', SALARY_LINE, department, index)
            return None
        if line_type == 'employer' and key == EMPLOYER_SSO_LINE:
            return self.sudo().employer_sso_expense_account_id or None
        return None

    @api.model
    def _npd_line_label(self, line_type, key, short=False):
        Salary = self.env['payroll.salary']
        parent = SPLIT_KEY_PARENT.get(key)
        if parent and key in Salary._fields:
            label = Salary._fields[key].string
            return label if short else '%s (แยกจาก %s)' % (label, parent[1])
        if line_type == 'employer':
            return '%s (ส่วนนายจ้าง)' % key
        return key

    @api.model
    def _npd_split_value(self, slip, key):
        if key == 'income_bonus':
            # ตรงกับ _compute_income_other: โบนัสนับเฉพาะเดือนที่ติ๊กใช้
            return (slip.income_bonus or 0.0) if slip.bonus_active else 0.0
        return slip[key] or 0.0

    def _npd_split_parts(self, slip, line_type, name, amount, index, mismatches):
        """แตกบรรทัดรวมเป็นส่วนย่อย [(key, ยอด, ป้าย)]

        แยกเฉพาะเมื่อยอดบรรทัด = ฟิลด์ยอดรวมบนสลิป ถ้าไม่ตรง (สลิปที่ซิงก์จาก o14
        หรือ HR แก้ด้วยมือ) ลงทั้งก้อนเข้าบัญชีของบรรทัดแม่ แล้วเตือน
        ส่วนย่อยที่ยังไม่ได้เลือกบัญชีถือว่า "ไม่แยก" ไม่งั้นบรรทัดรวมจะบล็อกทุกรอบ
        """
        self.ensure_one()
        spec = SPLIT_KEYS.get((line_type, name))
        if not spec:
            return [(name, amount, name)]
        cur = self.company_id.currency_id
        total_field, keys = spec
        department = slip.department_id
        carve = []
        for key in keys:
            if not self._npd_resolve_account(line_type, key, department, index):
                continue
            value = cur.round(self._npd_split_value(slip, key))
            if not cur.is_zero(value):
                carve.append((key, value))
        if not carve:
            return [(name, amount, name)]
        if cur.compare_amounts(cur.round(slip[total_field] or 0.0), amount) != 0:
            info = mismatches.setdefault(
                (line_type, name), {'count': 0, 'amount': 0.0, 'keys': set()})
            info['count'] += 1
            info['amount'] += amount
            info['keys'].update(self._npd_line_label(line_type, key, short=True)
                                for key, _value in carve)
            return [(name, amount, name)]
        parts = [(key, value, self._npd_line_label(line_type, key, short=True))
                 for key, value in carve]
        rest = cur.round(amount - sum(value for _key, value in carve))
        if not cur.is_zero(rest):
            parts.append((name, rest, name))
        return parts

    # ==================================================================
    # เครื่องคำนวณ
    # ==================================================================
    def _npd_get_slips(self, period):
        # อ่านด้วย sudo เสมอ: ฝ่ายบัญชีไม่มีสิทธิ์สลิป และรอบที่ซิงก์จาก o14
        # เป็นของบริษัท 1 แต่มีสลิปทุกบริษัท กฎแยกบริษัทจะซ่อนสลิปไปบางส่วน
        self.ensure_one()
        return self.env['payroll.salary'].sudo().search([
            ('period_id', '=', period.id),
            ('company_id', '=', self.company_id.id),
        ])

    def _npd_posting_date(self, period, slips):
        self.ensure_one()
        period = period.sudo()
        if self.date_policy == 'date_to':
            return period.date_to
        dates = [value for value in slips.sudo().mapped('payment_date') if value]
        return period.payment_date or (max(dates) if dates else False) or period.date_to

    def _npd_prepare_entries(self, period, slips, date):
        """คำนวณรายการบัญชีของ (รอบ, บริษัทนี้) — คำนวณล้วน ไม่เขียนลงฐานข้อมูล

        ไม่สร้างรายการร่างไว้ดูตัวอย่าง เพราะ psn_journal_sequence ออกเลขจาก
        ir.sequence ทำแล้วยกเลิกก็เสียเลขไปแล้ว

        คืนค่า dict(lines, issues, totals, fingerprint, date)
        """
        self.ensure_one()
        config = self.sudo()
        company = config.company_id
        cur = company.currency_id
        period = period.sudo()
        slips = slips.sudo()
        date = fields.Date.to_date(date)
        issues = []

        def block(message, amount=0.0):
            issues.append({'severity': 'block', 'message': message, 'amount': amount})

        def warn(message, amount=0.0):
            issues.append({'severity': 'warn', 'message': message, 'amount': amount})

        # ---------- รอบ / การตั้งค่า ----------
        if period.state not in ('approved', 'paid'):
            block('ลงบัญชีได้เฉพาะรอบที่อนุมัติแล้วหรือจ่ายแล้ว')
        journal = config.journal_id
        if not journal:
            block('บริษัท %s ยังไม่ได้เลือกสมุดรายวันเงินเดือน' % company.name)
        elif not journal.active or journal.type != 'general' or journal.company_id != company:
            block('สมุดรายวัน %s ใช้ลงบัญชีเงินเดือนของบริษัท %s ไม่ได้ '
                  '(ต้องเป็นสมุดรายวันทั่วไปของบริษัทนี้ที่ยังใช้งานอยู่)'
                  % (journal.display_name, company.name))
        if not config.payable_account_id:
            block('บริษัท %s ยังไม่ได้เลือกบัญชีเงินเดือนค้างจ่าย' % company.name)
        if config.employer_sso_enabled and not (
                config.employer_sso_expense_account_id
                and config.employer_sso_payable_account_id):
            block('เปิดตั้งค้างจ่ายประกันสังคมส่วนนายจ้างไว้ แต่ยังเลือกบัญชีค่าใช้จ่าย'
                  'หรือบัญชีรอนำส่งไม่ครบ')
        if not date:
            block('ยังไม่ได้ระบุวันที่ลงบัญชี')
        else:
            lock_message = self._npd_lock_message(company, date)
            if lock_message:
                block(lock_message)
        existing = self.env['npd.payroll.account.move'].sudo().search([
            ('period_id', '=', period.id),
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
        ], limit=1)
        if existing:
            block('รอบนี้ของบริษัท %s ลงบัญชีไปแล้ว (%s) ต้องกลับรายการก่อนจึงจะลงใหม่ได้'
                  % (company.name, existing.move_id.name or ''))

        # ---------- บรรทัดสลิป ----------
        index = config._npd_map_index()
        buckets = defaultdict(float)
        labels = defaultdict(set)
        unmapped = {}
        mismatches = {}
        slip_diffs = []
        draft_codes = []
        negative = {'count': 0, 'amount': 0.0}
        no_branch_codes = set()
        totals = defaultdict(float)

        def add(account, slip, amount, debit_side, label):
            # สาขาเฉพาะบรรทัดกำไรขาดทุน หนี้สินเป็นของบริษัท ไม่ใช่ของสาขา
            branch_id = False
            if account.internal_group in ('income', 'expense'):
                branch_id = slip.branch_id.id or False
                if not branch_id:
                    no_branch_codes.add(slip.employee_code or str(slip.id))
            if amount < 0:
                # ยอดติดลบ (เรียกคืน) กลับข้างเดบิต/เครดิต
                debit_side = not debit_side
            key = (account.id, branch_id, 'debit' if debit_side else 'credit')
            buckets[key] += abs(amount)
            labels[key].add(label)

        def add_unmapped(line_type, key, amount, slip):
            entry = unmapped.setdefault((line_type, key), {'amount': 0.0, 'slips': set()})
            entry['amount'] += amount
            entry['slips'].add(slip.id)

        for slip in slips:
            # ปัดรายบรรทัดก่อนรวม: ภาษีในบัญชี = ผลรวมภาษีรายคนที่ปัดแล้ว
            # และเงินเดือนค้างจ่าย = ยอดโอนธนาคารจริง
            sums = defaultdict(float)
            for line in slip.line_ids:
                sums[(line.type, (line.name or '').strip())] += cur.round(line.amount or 0.0)
            nonzero = {key: cur.round(value) for key, value in sums.items()
                       if not cur.is_zero(value)}
            if slip.state == 'draft' and nonzero:
                draft_codes.append(slip.employee_code or str(slip.id))
            income = sum(value for (kind, _n), value in nonzero.items() if kind == 'income')
            deduction = sum(value for (kind, _n), value in nonzero.items()
                            if kind == 'deduction')
            net = cur.round(slip.net_salary or 0.0)
            totals['gross'] += income
            totals['deduction'] += deduction
            totals['net'] += net
            diff = cur.round(cur.round(income - deduction) - net)
            if not cur.is_zero(diff):
                slip_diffs.append((slip, diff))
            if net < 0:
                negative['count'] += 1
                negative['amount'] += net

            department = slip.department_id
            for (line_type, name), amount in nonzero.items():
                if line_type not in ('income', 'deduction'):
                    continue
                for key, part, label in config._npd_split_parts(
                        slip, line_type, name, amount, index, mismatches):
                    account = config._npd_resolve_account(line_type, key, department, index)
                    if not account:
                        add_unmapped(line_type, key, part, slip)
                        continue
                    add(account, slip, part, line_type == 'income', label)

            if config.employer_sso_enabled:
                # ระบบเงินเดือนไม่มีส่วนนายจ้างเลย จึงใช้ยอดหักลูกจ้างในสลิปเดียวกัน
                sso = nonzero.get(('deduction', EMPLOYER_SSO_LINE), 0.0)
                if sso:
                    expense = config._npd_resolve_account(
                        'employer', EMPLOYER_SSO_LINE, department, index)
                    payable = config.employer_sso_payable_account_id
                    if not expense:
                        add_unmapped('employer', EMPLOYER_SSO_LINE, sso, slip)
                    elif payable:
                        add(expense, slip, sso, True, EMPLOYER_SSO_LABEL)
                        add(payable, slip, sso, False, EMPLOYER_SSO_LABEL)
                    totals['employer_sso'] += sso

        # ---------- ปัญหา / คำเตือน ----------
        for (line_type, key), entry in sorted(unmapped.items()):
            block('ยังไม่ได้ผูกบัญชี: %s "%s" ยอดรวม %s บาท (%d สลิป) — '
                  'ไปที่ ผังบัญชีเงินเดือน ของ %s' % (
                      LINE_TYPE_LABELS.get(line_type, line_type),
                      self._npd_line_label(line_type, key), _fmt(entry['amount']),
                      len(entry['slips']), company.name),
                  cur.round(entry['amount']))
        if draft_codes:
            block('มีสลิปที่ยังเป็นร่างแต่มียอด %d ใบ ให้ฝ่ายบุคคลยืนยันสลิปก่อน: %s' % (
                len(draft_codes), ', '.join(sorted(draft_codes)[:20])))
        for (_line_type, name), info in sorted(mismatches.items()):
            warn('บรรทัด %s ไม่ตรงกับรายละเอียดในสลิป %d ใบ จึงไม่แยก %s '
                 '(ลงทั้งก้อนเข้าบัญชีของ %s)' % (
                     name, info['count'], ', '.join(sorted(info['keys'])), name),
                 cur.round(info['amount']))
        if negative['count']:
            warn('มีสลิปที่เงินสุทธิติดลบ %d ใบ รวม %s บาท' % (
                negative['count'], _fmt(negative['amount'])), cur.round(negative['amount']))
        if no_branch_codes:
            warn('สลิป %d ใบไม่มีสาขา รายการค่าใช้จ่ายของสลิปเหล่านี้จะไม่ระบุสาขา: %s' % (
                len(no_branch_codes), ', '.join(sorted(no_branch_codes)[:20])))

        # ---------- รวมเป็นบรรทัดรายการบัญชี ----------
        Branch = self.env['res.branch'].sudo()
        lines = []
        total_debit = total_credit = 0.0
        for (account_id, branch_id, side), amount in buckets.items():
            amount = cur.round(amount)
            if cur.is_zero(amount):
                continue
            lines.append({
                'account': self.env['account.account'].sudo().browse(account_id),
                'branch': Branch.browse(branch_id) if branch_id else Branch,
                'debit': amount if side == 'debit' else 0.0,
                'credit': amount if side == 'credit' else 0.0,
                'labels': sorted(labels[(account_id, branch_id, side)]),
                'is_payable': False,
            })
            if side == 'debit':
                total_debit += amount
            else:
                total_credit += amount
        total_debit = cur.round(total_debit)
        total_credit = cur.round(total_credit)
        net_check = cur.round(totals['net'])

        if unmapped:
            # ยังผูกบัญชีไม่ครบ ผลต่างเดบิต/เครดิตไม่มีความหมาย ใช้ผลต่างรายสลิปแทน
            residue = cur.round(sum(diff for _slip, diff in slip_diffs))
        else:
            residue = cur.round(total_debit - total_credit - net_check)
        if abs(residue) >= MAX_RESIDUE:
            top = sorted(slip_diffs, key=lambda item: -abs(item[1]))[:20]
            block('เงินสุทธิในสลิปไม่ตรงกับผลรวมบรรทัด ต่างกัน %s บาท '
                  '(ตั้งแต่ 1 บาทขึ้นไประบบไม่ปรับให้) สลิปที่ต่าง: %s' % (
                      _fmt(residue),
                      ', '.join('%s (%s)' % (slip.employee_code or slip.id, _fmt(diff))
                                for slip, diff in top) or '-'),
                  residue)
        elif not cur.is_zero(residue):
            warn('ปรับเศษสตางค์ %s บาท เข้าบัญชีเงินเดือนค้างจ่าย' % _fmt(residue), residue)

        payable_amount = cur.round(net_check + residue)
        if config.payable_account_id and not cur.is_zero(payable_amount):
            lines.append({
                'account': config.payable_account_id,
                'branch': Branch,
                'debit': -payable_amount if payable_amount < 0 else 0.0,
                'credit': payable_amount if payable_amount > 0 else 0.0,
                'labels': [PAYABLE_LABEL],
                'is_payable': True,
            })
            if payable_amount > 0:
                total_credit = cur.round(total_credit + payable_amount)
            else:
                total_debit = cur.round(total_debit - payable_amount)

        def sort_key(line):
            account = line['account'].with_company(company)
            return (line['is_payable'], 0 if line['debit'] else 1,
                    account.code or '', line['branch'].name or '')
        lines.sort(key=sort_key)

        # ---------- ตรวจบัญชีที่จะใช้ ----------
        check_policy = 'analytic_policy' in self.env['account.account']._fields
        seen = set()
        for line in lines:
            account = line['account']
            if account.id in seen:
                continue
            seen.add(account.id)
            display = self._npd_account_display(account)
            if account.deprecated:
                block('บัญชี %s ถูกปิดใช้งานแล้ว ให้เลือกบัญชีใหม่ในผังบัญชีเงินเดือน' % display)
            if not (account.company_ids & company.parent_ids):
                block('บัญชี %s ไม่ได้อยู่ในผังบัญชีของบริษัท %s' % (display, company.name))
            if check_policy:
                getter = getattr(account, '_get_analytic_policy', None)
                policy = getter() if getter else account.analytic_policy
                # ลงบัญชีเงินเดือนไม่ใส่บัญชีวิเคราะห์ ทั้ง always และ posted
                # จะล้มตอนผ่านรายการด้วยข้อความภาษาอังกฤษ
                if policy in ('always', 'posted'):
                    block('บัญชี %s ตั้งให้ต้องระบุบัญชีวิเคราะห์ แต่การลงบัญชีเงินเดือน'
                          'ไม่ใส่บัญชีวิเคราะห์ ให้แก้นโยบายของบัญชีนี้หรือเลือกบัญชีอื่น'
                          % display)
        if not lines:
            block('ไม่มีรายการที่มียอดให้ลงบัญชี')

        return {
            'lines': lines,
            'issues': issues,
            'totals': {
                'slip_count': len(slips),
                'total_gross': cur.round(totals['gross']),
                'total_deduction': cur.round(totals['deduction']),
                'total_net': net_check,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'employer_sso': cur.round(totals['employer_sso']),
                'rounding_residue': residue,
            },
            'fingerprint': slip_fingerprint(slips),
            'date': date,
        }

    def _npd_move_vals(self, period, result, date):
        self.ensure_one()
        period = period.sudo()
        totals = result['totals']
        line_commands = []
        for line in result['lines']:
            label = '%s: %s' % (period.display_name, ', '.join(line['labels']))
            line_commands.append(Command.create({
                'name': label[:256],
                'account_id': line['account'].id,
                'debit': line['debit'],
                'credit': line['credit'],
                # ส่งสาขาทุกบรรทัดเสมอ ไม่งั้น multi-branch ใส่สาขาของคนกดให้
                'branch_id': line['branch'].id or False,
            }))
        return {
            'move_type': 'entry',
            'company_id': self.company_id.id,
            'journal_id': self.journal_id.id,
            'date': date,
            'ref': 'เงินเดือน %s' % period.display_name,
            'narration': 'ลงบัญชีจากรอบเงินเดือน %s สลิป %d ใบ เงินสุทธิรวม %s บาท' % (
                period.display_name, totals['slip_count'], _fmt(totals['total_net'])),
            # หัวรายการไม่มีสาขา: รายงานงบรายสาขาอ่านสาขาจากหัวรายการ JV
            # ถ้าปล่อยค่าเริ่มต้น เงินเดือนทั้งบริษัทจะไปกองที่สาขาของคนกด
            'branch_id': False,
            'line_ids': line_commands,
        }

    def _npd_post_period(self, period, date, result=None):
        """สร้างและผ่านรายการบัญชีของ (รอบ, บริษัทนี้) — คำนวณใหม่เสมอถ้าไม่ได้ส่งผลมา"""
        self.ensure_one()
        config = self.sudo()
        company = config.company_id
        period = period.sudo()
        date = fields.Date.to_date(date)
        if result is None:
            result = config._npd_prepare_entries(period, config._npd_get_slips(period), date)
        blocks = [issue['message'] for issue in result['issues']
                  if issue['severity'] == 'block']
        if blocks:
            raise UserError('ลงบัญชีเงินเดือนของบริษัท %s ไม่ได้\n- %s' % (
                company.name, '\n- '.join(blocks)))
        # sudo หลังผ่านการตรวจสิทธิ์แล้ว: กฎสาขาบน account.move.line ทำให้คนที่ไม่มี
        # ทุกสาขาสร้างบรรทัดของสาขาอื่นไม่ได้ (create_uid ยังเป็นผู้ใช้จริง)
        move = self.env['account.move'].sudo().with_company(company).create(
            config._npd_move_vals(period, result, date))
        move.action_post()
        totals = result['totals']
        try:
            with self.env.cr.savepoint():
                link = self.env['npd.payroll.account.move'].sudo().with_company(company).create({
                    'period_id': period.id,
                    'company_id': company.id,
                    'move_id': move.id,
                    'state': 'posted',
                    'date': date,
                    'slip_count': totals['slip_count'],
                    'amount_gross': totals['total_gross'],
                    'amount_deduction': totals['total_deduction'],
                    'amount_net': totals['total_net'],
                    'amount_employer_sso': totals['employer_sso'],
                    'rounding_residue': totals['rounding_residue'],
                    'fingerprint': result['fingerprint'],
                })
        except psycopg2.IntegrityError:
            raise UserError('รอบนี้ของบริษัทนี้ถูกลงบัญชีไปแล้ว') from None
        period._message_log(body='ลงบัญชีเงินเดือนบริษัท %s รายการ %s วันที่ %s '
                                 'สลิป %d ใบ เงินสุทธิรวม %s บาท' % (
                                     company.name, move.name, _fmt_date(date),
                                     totals['slip_count'], _fmt(totals['total_net'])))
        _logger.info('[PAYROLL ACCOUNT] %s %s -> %s', period.display_name,
                     company.name, move.name)
        return link

    # ==================================================================
    # ค่าเริ่มต้นจากผังบัญชี
    # ==================================================================
    def action_generate_defaults(self):
        self._npd_check_poster()
        results = [(config.company_id.name, config._npd_generate_defaults())
                   for config in self]
        return self._npd_defaults_notification(results)

    @api.model
    def action_create_missing_configs(self):
        self._npd_check_poster()
        allowed = self._npd_allowed_companies()
        # สร้างให้ทุกบริษัทที่มีสิทธิ์ ไม่ใช่เฉพาะที่ติ๊กในตัวสลับบริษัท
        Config = self.with_context(allowed_company_ids=allowed.ids)
        have = self.sudo().search([]).company_id
        created = Config.browse()
        for company in (allowed - have).sorted('id'):
            created |= Config.create({'company_id': company.id})
        results = [(config.company_id.name, config._npd_generate_defaults())
                   for config in created]
        if not results:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'ไม่มีบริษัทที่ต้องสร้างเพิ่ม',
                    'message': 'ทุกบริษัทที่คุณมีสิทธิ์มีการตั้งค่าลงบัญชีเงินเดือนแล้ว',
                    'type': 'info',
                    'sticky': False,
                },
            }
        return self._npd_defaults_notification(results)

    @api.model
    def _npd_defaults_notification(self, results):
        todo = sum(stats['todo'] for _name, stats in results)
        message = '\n'.join(
            '%s: จับคู่ได้ %d, ต้องเลือก/ตรวจเอง %d, มีอยู่แล้ว %d' % (
                name, stats['matched'], stats['todo'], stats['kept'])
            for name, stats in results)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'สร้างค่าเริ่มต้นจากผังบัญชีแล้ว',
                'message': message + ('\nดูรายละเอียดที่แท็บ "ผลการสร้างค่าเริ่มต้น"'
                                      if todo else ''),
                'type': 'warning' if todo else 'success',
                'sticky': bool(todo),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _npd_generate_defaults(self):
        """เติมเฉพาะช่องที่ว่าง + สร้างแถวผังที่ยังไม่มี ไม่ทับของที่ฝ่ายบัญชีตั้งไว้"""
        self.ensure_one()
        company = self.company_id
        name_index = self._npd_account_name_index()
        report = []
        stats = {'matched': 0, 'todo': 0, 'kept': 0}
        status_by_code = {'duplicate': STATUS_DUPLICATE, 'missing': STATUS_MISSING}

        def record(kind, item, target, status):
            report.append((kind, item, target or '', status))
            if status == STATUS_KEEP:
                stats['kept'] += 1
            elif status in (STATUS_FOUND, STATUS_REDUCE):
                stats['matched'] += 1
            else:
                stats['todo'] += 1

        def found_status(code, candidates):
            if code == 'found':
                return STATUS_REVIEW if candidates.get('review') else STATUS_FOUND
            return status_by_code[code]

        vals = {}
        # ---------- สมุดรายวัน ----------
        journal_label = self._fields['journal_id'].string
        if self.journal_id:
            record('ตั้งค่า', journal_label, self.journal_id.sudo().display_name, STATUS_KEEP)
        else:
            journals = self.env['account.journal'].sudo().search([
                ('company_id', '=', company.id), ('type', '=', 'general')])
            matches = journals.filtered(lambda journal: DEFAULT_JOURNAL_NAME in {
                _norm(journal.with_context(lang='th_TH').name),
                _norm(journal.with_context(lang='en_US').name)})
            if len(matches) == 1:
                vals['journal_id'] = matches.id
                record('ตั้งค่า', journal_label, matches.display_name, STATUS_FOUND)
            else:
                record('ตั้งค่า', journal_label, '',
                       STATUS_DUPLICATE if matches else STATUS_MISSING)

        # ---------- บัญชีบนการตั้งค่า ----------
        for fname, candidates in CONFIG_DEFAULTS.items():
            label = self._fields[fname].string
            if self[fname]:
                record('ตั้งค่า', label, self._npd_account_display(self[fname]), STATUS_KEEP)
                continue
            account, code = self._npd_find_account(candidates, name_index)
            if account:
                vals[fname] = account.id
            record('ตั้งค่า', label, self._npd_account_display(account),
                   found_status(code, candidates))

        # ---------- แถวผัง ----------
        existing = self._npd_map_index()
        wanted = ([('income', name) for name in KNOWN_LINES['income']]
                  + [('deduction', name) for name in KNOWN_LINES['deduction']]
                  + list(DEFAULT_SPLIT_ROWS))
        sequence = max(self.map_ids.mapped('sequence') or [0])
        commands = []
        for line_type, key in wanted:
            kind = LINE_TYPE_LABELS[line_type]
            item = self._npd_line_label(line_type, key)
            row = existing.get((line_type, key, False))
            if row:
                target = self._npd_account_display(row.account_id) if row.account_id else (
                    'ตามบัญชีของบรรทัด "เงินเดือน"' if row.reduce_expense else '')
                record(kind, item, target, STATUS_KEEP)
                continue
            sequence += 10
            row_vals = {'line_type': line_type, 'line_name': key, 'sequence': sequence}
            candidates = DEFAULT_CANDIDATES.get((line_type, key))
            if candidates is None:
                record(kind, item, '', STATUS_MANUAL)
            elif candidates.get('reduce_expense'):
                row_vals['reduce_expense'] = True
                record(kind, item, 'ตามบัญชีของบรรทัด "เงินเดือน"', STATUS_REDUCE)
            else:
                account, code = self._npd_find_account(candidates, name_index)
                if account:
                    row_vals['account_id'] = account.id
                record(kind, item, self._npd_account_display(account),
                       found_status(code, candidates))
            commands.append(Command.create(row_vals))
        if commands:
            vals['map_ids'] = commands
        vals['default_report'] = self._npd_render_report(report)
        self.write(vals)
        _logger.info('[PAYROLL ACCOUNT] ค่าเริ่มต้น %s: %s', company.name, stats)
        return stats

    def _npd_render_report(self, report):
        todo = {STATUS_MISSING, STATUS_DUPLICATE, STATUS_MANUAL, STATUS_REVIEW}
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        rows = Markup('').join(
            Markup('<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (
                'table-warning' if status in todo else '', kind, item, target or '-', status)
            for kind, item, target, status in report)
        return Markup(
            '<p>สร้างเมื่อ %s โดย %s — จับคู่จาก<b>ชื่อบัญชี</b>ในผังของบริษัทนี้เท่านั้น '
            'แถวสีเหลืองต้องเลือก/ตรวจทานเอง</p>'
            '<table class="table table-sm table-bordered">'
            '<thead><tr><th>ประเภท</th><th>รายการ</th><th>บัญชีที่ได้</th><th>สถานะ</th></tr>'
            '</thead><tbody>%s</tbody></table>') % (
                now.strftime('%d/%m/%Y %H:%M'), self.env.user.name, rows)
