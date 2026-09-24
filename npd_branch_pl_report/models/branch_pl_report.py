# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date
import json
import logging
import math

_logger = logging.getLogger(__name__)

# ชื่อย่อเดือนภาษาไทยสำหรับหัวคอลัมน์ (m01..m12)
MONTH_TH = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
            'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']

# ชื่อภาษีซื้อ (ให้ตรงกับที่ commission total_expense ใช้)
VAT_INCL_NAME = 'ภาษีซื้อรวม Vat 7%'      # ราคารวมภาษีแล้ว
VAT_EXCL_NAME = 'ภาษีซื้อไม่รวม Vat 7%'   # ราคายังไม่รวมภาษี


def truncate_decimal(value, decimals=2):
    """ตัดทศนิยมไม่ปัดเศษ ให้แนวเดียวกับรายงาน commission"""
    multiplier = 10 ** decimals
    return math.trunc((value or 0.0) * multiplier) / multiplier


class BranchPLReport(models.TransientModel):
    _name = 'npd.branch.pl.report'
    _description = 'งบรายรับ-รายจ่ายรายสาขา'

    @api.model
    def _get_year_selection(self):
        current_year = fields.Date.today().year
        return [(str(y), str(y)) for y in range(current_year - 5, current_year + 2)]

    year = fields.Selection(
        selection='_get_year_selection',
        string='ปี',
        required=True,
        default=lambda self: str(fields.Date.today().year),
    )
    branch_id = fields.Many2one('res.branch', string='สาขา', required=True)
    line_ids = fields.One2many('npd.branch.pl.report.line', 'report_id', string='บรรทัด')

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def action_generate_report(self):
        self.ensure_one()
        self.line_ids.unlink()
        self._compute_lines()
        return {
            'name': 'งบรายรับ-รายจ่าย %s ปี %s' % (self.branch_id.name or '', self.year),
            'type': 'ir.actions.act_window',
            'res_model': 'npd.branch.pl.report.line',
            'view_mode': 'tree',
            'domain': [('report_id', '=', self.id)],
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _input_vat_account(self):
        """บัญชีภาษีซื้อ (1154-00) — ใช้เป็นปลายทางของส่วน VAT ที่แยกออกจากฐาน
        หาแบบไดนามิกจาก repartition line ของภาษีซื้อ 7% ก่อน แล้วค่อย fallback รหัส"""
        tax = self.env['account.tax'].search(
            [('name', 'in', [VAT_INCL_NAME, VAT_EXCL_NAME])], limit=1)
        if tax:
            rl = tax.invoice_repartition_line_ids.filtered(
                lambda l: l.repartition_type == 'tax' and l.account_id)[:1]
            if rl:
                return rl.account_id
        return self.env['account.account'].search([('code', '=', '1154-00')], limit=1)

    def _compute_lines(self):
        self.ensure_one()
        branch = self.branch_id
        if not branch:
            raise UserError(_('กรุณาเลือกสาขา'))

        year_int = int(self.year)
        date_from = date(year_int, 1, 1)
        date_to = date(year_int, 12, 31)

        vat_account = self._input_vat_account()
        vat_account_id = vat_account.id if vat_account else False

        # {account_id: [m1..m12]} — ยอดรายจ่าย (บวก)
        expense_acc = {}
        income_months = [0.0] * 12   # รายได้ค่าเช่า
        salary_months = [0.0] * 12   # เงินเดือน

        def add_exp(account_id, m_idx, amount):
            if not amount:
                return
            expense_acc.setdefault(account_id, [0.0] * 12)[m_idx] += amount

        def add_vat(base_account_id, m_idx, vat_amount):
            """VAT ไป 1154-00 ถ้าหาเจอ ไม่งั้นทบเข้าบัญชีฐาน (ให้ยอดรวมยังตรง)"""
            if not vat_amount:
                return
            target = vat_account_id or base_account_id
            expense_acc.setdefault(target, [0.0] * 12)[m_idx] += vat_amount

        # ==============================================================
        # รายได้ค่าเช่า — เฉพาะสมุด "เช่า(สาขา)" หักใบลดหนี้ขาย (= ยอดเช่า ใน commission)
        # ==============================================================
        # o18 มีสมุดชื่อเดียวกันหลายตัว (ตัวละบริษัท) ถ้าเอาแค่ limit=1
        # จะได้ของบริษัทเดียวแล้วยอดหาย จึงใช้ทุกตัวที่ชื่อตรง
        # การกรองสาขายังคุมให้ได้เฉพาะของสาขานั้นอยู่แล้ว
        rent_journal = self.env['account.journal'].search(
            [('name', '=', 'สมุดรายวันเช่า(สาขา)')])
        if rent_journal:
            rent_invoices = self.env['account.move'].sudo().search([
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('journal_id', 'in', rent_journal.ids),
                ('branch_id', '=', branch.id),
                ('state', '=', 'posted'),
                ('move_type', '=', 'out_invoice'),
                ('contact_type', '=', 'branch'),
            ])
            for inv in rent_invoices:
                if inv.invoice_date:
                    income_months[inv.invoice_date.month - 1] += inv.amount_untaxed or 0.0

        cn_journal = self.env['account.journal'].search(
            [('name', '=', 'สมุดรายวันลดหนี้ขาย')])
        if cn_journal:
            rental_cns = self.env['account.move'].sudo().search([
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('journal_id', 'in', cn_journal.ids),
                ('branch_id', '=', branch.id),
                ('state', '=', 'posted'),
                ('move_type', '=', 'out_refund'),
                ('contact_type', '=', 'branch'),
            ])
            for cn in rental_cns:
                if cn.invoice_date:
                    income_months[cn.invoice_date.month - 1] -= cn.amount_untaxed or 0.0

        # ==============================================================
        # (1) Vendor Bills — ยอดที่จ่ายแล้ว (cash) เฉลี่ยลงบรรทัดบัญชีของบิลตามสัดส่วน
        #     -> ฐานไป 5xxx, VAT ไป 1154-00 โดยอัตโนมัติ (ตามบัญชีของบรรทัดในบิล)
        #     branch = หัวบิล (branch_id), งวด = date (วันที่ลงบัญชี = วันที่รับชำระ)
        # ==============================================================
        vendor_bills = self.env['account.move'].sudo().search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', '=', 'posted'),
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('branch_id', '=', branch.id),
        ])
        for bill in vendor_bills:
            if not bill.invoice_payments_widget or not bill.date:
                continue
            try:
                data = json.loads(bill.invoice_payments_widget)
            except (json.JSONDecodeError, TypeError):
                continue
            content = (data or {}).get('content') or []
            paid = sum(p.get('amount', 0.0) for p in content)
            if not paid:
                continue
            m_idx = bill.date.month - 1
            # บรรทัดที่ไม่ใช่ลูกหนี้/เจ้าหนี้ = บรรทัดค่าใช้จ่าย + บรรทัดภาษี
            alloc_lines = bill.line_ids.filtered(
                lambda l: l.account_id
                and l.account_id.account_type not in ('asset_receivable', 'liability_payable')
                and (l.debit or l.credit))
            total = sum(alloc_lines.mapped('balance'))
            if not total:
                continue
            for l in alloc_lines:
                add_exp(l.account_id.id, m_idx, paid * (l.balance / total))

        # ==============================================================
        # (2) Advance Clear — branch ตาม analytic, งวด = doc_date  (เหมือน commission)
        # ==============================================================
        advance_clears = self.env['account.advance.clear'].sudo().search([
            ('doc_date', '>=', date_from),
            ('doc_date', '<=', date_to),
            ('state', '=', 'post'),
        ])
        for adv in advance_clears:
            if not adv.doc_date:
                continue
            m_idx = adv.doc_date.month - 1
            for line in adv.clear_ids:
                aa = line.account_analytic_id
                if not (aa and aa.branch_id and aa.branch_id.id == branch.id):
                    continue
                base, vat = self._advance_line_amounts(line)
                add_exp(line.account_id.id, m_idx, base)
                add_vat(line.account_id.id, m_idx, vat)

        # ==============================================================
        # (3) Voucher Lines — branch ตาม analytic, งวด = payment_date  (เหมือน commission)
        # ==============================================================
        voucher_lines = self.env['account.voucher.line'].sudo().search([
            ('payment_date', '>=', date_from),
            ('payment_date', '<=', date_to),
            ('voucher_id.state', 'in', ['posted', 'transferred']),
            ('voucher_id.voucher_type', '=', 'purchase'),
            ('voucher_id.check_show', '=', False),
            ('account_analytic_id.branch_id', '=', branch.id),
        ])
        for line in voucher_lines:
            if not line.payment_date:
                continue
            m_idx = line.payment_date.month - 1
            base = line.price_subtotal or 0.0
            vat = base * 0.07 if any(
                t.name in (VAT_INCL_NAME, VAT_EXCL_NAME) for t in line.tax_ids) else 0.0
            add_exp(line.account_id.id, m_idx, base)
            add_vat(line.account_id.id, m_idx, vat)

        # ==============================================================
        # (4) JV — สมุดทั่วไป (JV-%), branch หัวเอกสาร, งวด = date, ยอด = debit ทุกบรรทัด
        # ==============================================================
        jv_moves = self.env['account.move'].sudo().search([
            ('name', '=like', 'JV-%'),
            ('branch_id', '=', branch.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', '=', 'posted'),
        ])
        for mv in jv_moves:
            if not mv.date:
                continue
            m_idx = mv.date.month - 1
            for l in mv.line_ids:
                if l.debit and l.debit > 0 and l.account_id:
                    add_exp(l.account_id.id, m_idx, l.debit)

        # ==============================================================
        # (5) เงินเดือน — เฉพาะเดือนที่มีรายจ่าย (1)-(4) > 0  (เหมือน commission)
        #     ดึงจาก npd.salary.branch.report.line (ต้องรีเฟรชรายงานเงินเดือนของเดือนนั้นก่อน)
        # ==============================================================
        month_subtotal = [
            sum(months[i] for months in expense_acc.values()) for i in range(12)
        ]
        # รายงานเงินเดือนรายสาขายังไม่ได้พอร์ตมา o18 ถ้ายังไม่มีให้ข้ามส่วนนี้
        # ตัวเลขอื่นยังออกครบ พอพอร์ตมาแล้วส่วนนี้จะทำงานเองโดยไม่ต้องแก้โค้ด
        if 'npd.salary.branch.report.line' not in self.env:
            _logger.info('npd_branch_pl_report: ยังไม่มีรายงานเงินเดือนรายสาขา '
                         'ข้ามส่วนเงินเดือน')
            return self._finalize_lines(income_months, expense_acc, salary_months, branch)

        SalaryLine = self.env['npd.salary.branch.report.line'].sudo()
        for i in range(12):
            if month_subtotal[i] > 0:
                sl = SalaryLine.search([
                    ('branch_name', '=', branch.name),
                    ('month', '=', i + 1),
                    ('year', '=', str(year_int)),
                ])
                stot = sum(sl.mapped('total_income'))
                if stot > 0:
                    salary_months[i] = stot

        return self._finalize_lines(income_months, expense_acc, salary_months, branch)

    def _finalize_lines(self, income_months, expense_acc, salary_months, branch):
        """ตัดบัญชีที่ไม่ต้องแสดงออก แล้วสร้างบรรทัดรายงาน"""
        self.ensure_one()
        # ==============================================================
        # ตัดบัญชีที่สาขานี้สั่งไม่ให้แสดงออกก่อนสร้างบรรทัด
        #
        # ตัดออกทั้งแถวและไม่นับใน "รวมรายจ่าย" กับ "คงเหลือ" ด้วย เพราะถ้าซ่อน
        # แต่แถวแล้วยังนับในยอดรวม ตัวเลขบนจอจะบวกกันไม่ลง อ่านแล้วงงกว่าเดิม
        # สาขาที่ไม่ได้ตั้งค่าไว้จะได้ชุดว่าง รายงานออกเหมือนเดิมทุกประการ
        # ==============================================================
        excluded = self.env['npd.branch.pl.exclusion'].excluded_account_ids_for(branch)
        if excluded:
            removed = [a for a in expense_acc if a in excluded]
            for acc_id in removed:
                expense_acc.pop(acc_id, None)

        # ==============================================================
        # สร้างบรรทัดรายงาน
        # ==============================================================
        Line = self.env['npd.branch.pl.report.line']
        accounts = {a.id: a for a in self.env['account.account'].browse(list(expense_acc.keys()))}
        seq = 10

        # รายได้ค่าเช่า
        Line.create(self._line_vals(seq, 'รายได้ค่าเช่า', 'income', income_months))
        seq += 10

        # รายจ่ายรายบัญชี (เรียงตามรหัสบัญชี)
        expense_total = [0.0] * 12
        for acc_id in sorted(expense_acc, key=lambda a: accounts[a].code or ''):
            months = expense_acc[acc_id]
            acc = accounts[acc_id]
            label = '%s %s' % (acc.code or '', acc.name or '')
            Line.create(self._line_vals(seq, label, 'expense', months))
            expense_total = [expense_total[i] + months[i] for i in range(12)]
            seq += 10

        # เงินเดือน (ถ้ามี)
        if any(salary_months):
            Line.create(self._line_vals(seq, 'เงินเดือน', 'expense', salary_months))
            expense_total = [expense_total[i] + salary_months[i] for i in range(12)]
            seq += 10

        # รวมรายจ่าย
        Line.create(self._line_vals(seq, 'รวมรายจ่าย', 'total_expense', expense_total))
        seq += 10

        # คงเหลือ = รายได้ - รวมรายจ่าย
        net = [income_months[i] - expense_total[i] for i in range(12)]
        Line.create(self._line_vals(seq, 'คงเหลือ', 'net', net))

    def _advance_line_amounts(self, line):
        """คืน (ฐาน, VAT) ของบรรทัด advance clear ให้ ฐาน+VAT = line_amount ตาม commission:
           - ภาษีซื้อรวม 7%  -> line_amount = price_unit (รวม VAT) => ฐาน=incl/1.07, VAT=ส่วนต่าง
           - ภาษีซื้อไม่รวม 7% -> line_amount = price_unit*1.07     => ฐาน=price_unit, VAT=price_unit*0.07
           - ภาษีอื่น        -> line_amount = 0
           - ไม่มีภาษี        -> line_amount = price_subtotal (ฐานล้วน)"""
        if line.tax_ids:
            names = ', '.join(t.name for t in line.tax_ids)
            if VAT_INCL_NAME in names:
                incl = line.price_unit or 0.0
                base = incl / 1.07
                return base, incl - base
            elif VAT_EXCL_NAME in names:
                base = line.price_unit or 0.0
                return base, base * 0.07
            return 0.0, 0.0
        return (line.price_subtotal or 0.0), 0.0

    def _line_vals(self, seq, name, row_type, months):
        vals = {
            'report_id': self.id,
            'sequence': seq,
            'name': name,
            'row_type': row_type,
        }
        total = 0.0
        for i in range(12):
            v = truncate_decimal(months[i], 2)
            vals['m%02d' % (i + 1)] = v
            total += v
        vals['total'] = truncate_decimal(total, 2)
        return vals


class BranchPLReportLine(models.TransientModel):
    _name = 'npd.branch.pl.report.line'
    _description = 'บรรทัดงบรายรับ-รายจ่ายรายสาขา'
    _order = 'sequence, id'

    report_id = fields.Many2one('npd.branch.pl.report', ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='รายการ', readonly=True)
    row_type = fields.Selection([
        ('income', 'รายได้'),
        ('expense', 'รายจ่าย'),
        ('total_expense', 'รวมรายจ่าย'),
        ('net', 'คงเหลือ'),
    ], string='ประเภท', readonly=True)

    m01 = fields.Float(string=MONTH_TH[0], readonly=True, digits=(16, 2))
    m02 = fields.Float(string=MONTH_TH[1], readonly=True, digits=(16, 2))
    m03 = fields.Float(string=MONTH_TH[2], readonly=True, digits=(16, 2))
    m04 = fields.Float(string=MONTH_TH[3], readonly=True, digits=(16, 2))
    m05 = fields.Float(string=MONTH_TH[4], readonly=True, digits=(16, 2))
    m06 = fields.Float(string=MONTH_TH[5], readonly=True, digits=(16, 2))
    m07 = fields.Float(string=MONTH_TH[6], readonly=True, digits=(16, 2))
    m08 = fields.Float(string=MONTH_TH[7], readonly=True, digits=(16, 2))
    m09 = fields.Float(string=MONTH_TH[8], readonly=True, digits=(16, 2))
    m10 = fields.Float(string=MONTH_TH[9], readonly=True, digits=(16, 2))
    m11 = fields.Float(string=MONTH_TH[10], readonly=True, digits=(16, 2))
    m12 = fields.Float(string=MONTH_TH[11], readonly=True, digits=(16, 2))
    total = fields.Float(string='รวม', readonly=True, digits=(16, 2))
