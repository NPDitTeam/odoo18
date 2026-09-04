# -*- coding: utf-8 -*-
"""สูตรคิด "สาย" ที่ตั้งเองได้ พร้อมวันเริ่มใช้

เดิมค่าผ่อนผันเป็นตัวเลขเดียวต่อสลิป (``payroll.salary.lateness_grace_period``)
ใช้ทั้งรอบเหมือนกันหมด พอเปลี่ยนนโยบายกลางรอบจึงทำไม่ได้ — ต้องรอรอบถัดไป
หรือยอมให้ยอดที่คำนวณไปแล้วเปลี่ยนตาม

โมเดลนี้ให้ตั้งสูตรพร้อม **วันเริ่มใช้** ได้ เอนจินเลือกสูตรรายวัน รอบที่คร่อม
วันเริ่มใช้ (เช่นตัดรอบ 25 ส.ค. - 24 ก.ย. แต่เริ่มใช้ 1 ก.ย.) จึงคิดถูกทั้งสองช่วง
ในใบเดียว และเอกสารของวันก่อนหน้าไม่ถูกกระทบ

ตั้งใจไม่มีฟิลด์ ``active`` — ถ้าจะกลับไปใช้สูตรเดิมให้เพิ่มสูตรใหม่ที่มีวันเริ่มใช้
ถัดไป จะได้ไม่ไปเปลี่ยนผลการคำนวณของวันที่ผ่านมาแล้ว
"""
import calendar
import logging
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# ค่าที่ระบบใช้มาแต่เดิมถ้ายังไม่เคยตั้งสูตรอะไรเลย
LEGACY_GRACE_MINUTES = 15

MODE_GRACE = 'grace'
MODE_DEADLINE = 'deadline'


class PayrollLatenessRule(models.Model):
    _name = 'payroll.lateness.rule'
    _description = 'สูตรคิดสาย (ผ่อนผันเข้างาน)'
    _order = 'effective_date desc, id desc'
    _rec_name = 'display_summary'

    effective_date = fields.Date(
        string='เริ่มใช้ตั้งแต่วันที่', required=True,
        default=fields.Date.context_today,
        help='สูตรนี้ใช้กับการลงเวลาตั้งแต่วันที่นี้เป็นต้นไป\n'
             'วันก่อนหน้ายังคิดด้วยสูตรเดิม จึงไม่กระทบยอดที่คำนวณไปแล้ว')
    mode = fields.Selection([
        (MODE_GRACE, 'ผ่อนผันเป็นนาที (เลทได้)'),
        (MODE_DEADLINE, 'ไม่ผ่อนผัน — กำหนดเวลาเข้างานล่าสุด'),
    ], string='รูปแบบ', required=True, default=MODE_GRACE)
    grace_minutes = fields.Integer(
        string='ผ่อนผันได้ (นาที)', default=LEGACY_GRACE_MINUTES,
        help='เข้างานช้าไม่เกินกี่นาทีถึงจะยังไม่ถือว่าสาย\n'
             'ใส่ 0 = ไม่ผ่อนผันเลย สายทันทีที่เลยเวลาเข้ากะ\n'
             'ถ้าเกินที่ผ่อนผัน จะนับสายตั้งแต่นาทีแรกรวมนาทีที่ผ่อนผันด้วย')
    deadline_hour = fields.Float(
        string='เข้างานไม่เกินเวลา', default=8.0,
        help='เข้างานได้ช้าที่สุดถึงเวลานี้ เลยจากนี้ถือว่าสาย (ปกติ 08:00)')
    branch_ids = fields.Many2many(
        'res.branch', 'payroll_lateness_rule_branch_rel', 'rule_id', 'branch_id',
        string='ใช้กับสาขา',
        help='เว้นว่าง = ใช้กับทุกสาขา\n'
             'สาขาที่ระบุจะชนะสูตร "ทุกสาขา" ที่เริ่มใช้วันเดียวกัน')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)
    note = fields.Char(string='หมายเหตุ')

    branch_scope = fields.Char(
        string='ขอบเขต', compute='_compute_display_summary', store=True)
    display_summary = fields.Char(
        string='สูตร', compute='_compute_display_summary', store=True)

    # ------------------------------------------------------------------
    @api.depends('mode', 'grace_minutes', 'deadline_hour', 'effective_date',
                 'branch_ids')
    def _compute_display_summary(self):
        for rule in self:
            if rule.mode == MODE_DEADLINE:
                detail = _('เข้างานไม่เกิน %s') % rule._deadline_text()
            elif rule.grace_minutes > 0:
                detail = _('ผ่อนผัน %s นาที') % rule.grace_minutes
            else:
                detail = _('ไม่ผ่อนผัน')
            scope = (', '.join(rule.branch_ids.mapped('name'))
                     if rule.branch_ids else _('ทุกสาขา'))
            rule.branch_scope = scope
            rule.display_summary = '%s — %s (เริ่ม %s)' % (
                detail, scope, fields.Date.to_string(rule.effective_date) or '-')

    def _deadline_text(self):
        self.ensure_one()
        total = int(round((self.deadline_hour or 0.0) * 60))
        return '%02d:%02d' % (total // 60, total % 60)

    @api.constrains('grace_minutes', 'deadline_hour', 'mode')
    def _check_values(self):
        for rule in self:
            if rule.mode == MODE_GRACE and rule.grace_minutes < 0:
                raise ValidationError(_('นาทีผ่อนผันต้องไม่ติดลบ'))
            if rule.mode == MODE_DEADLINE and not (0.0 <= rule.deadline_hour < 24.0):
                raise ValidationError(
                    _('เวลาเข้างานล่าสุดต้องอยู่ระหว่าง 00:00 - 23:59'))

    @api.constrains('effective_date', 'branch_ids', 'company_id')
    def _check_no_overlap(self):
        """วันเริ่มใช้เดียวกัน ห้ามมีสูตรที่ขอบเขตสาขาทับกัน ไม่งั้นไม่รู้จะใช้อันไหน

        อนุญาต: 01/09 "ทุกสาขา" + 01/09 "ภูเก็ต"  (ภูเก็ตชนะเฉพาะสาขาตัวเอง)
        ห้าม:    01/09 "ภูเก็ต"   + 01/09 "ภูเก็ต, ชะอำ"
        """
        for rule in self:
            others = self.search([
                ('effective_date', '=', rule.effective_date),
                ('company_id', '=', rule.company_id.id),
                ('id', '!=', rule.id),
            ])
            for other in others:
                if not rule.branch_ids and not other.branch_ids:
                    raise ValidationError(_(
                        'มีสูตร "ทุกสาขา" ที่เริ่มใช้วันที่ %s อยู่แล้ว '
                        '— แก้ไขรายการเดิม หรือระบุสาขาให้ต่างกัน'
                    ) % fields.Date.to_string(rule.effective_date))
                overlap = rule.branch_ids & other.branch_ids
                if overlap:
                    raise ValidationError(_(
                        'สาขา %s ถูกกำหนดไว้ 2 สูตรในวันเริ่มใช้เดียวกัน (%s)'
                    ) % (', '.join(overlap.mapped('name')),
                         fields.Date.to_string(rule.effective_date)))

    # ------------------------------------------------------------------
    # ใช้จากเอนจินคำนวณ
    # ------------------------------------------------------------------
    @api.model
    def _rules_for_branch(self, branch=None, company=None):
        """สูตรที่ใช้ได้กับสาขานี้ เรียงตามวันเริ่มใช้ (เก่า -> ใหม่)

        วันเริ่มใช้เดียวกัน "สาขาที่ระบุ" ชนะ "ทุกสาขา"
        """
        domain = []
        if company:
            domain.append(('company_id', '=', company.id))
        rules = self.sudo().search(domain, order='effective_date asc')
        by_date = {}
        for rule in rules:
            if rule.branch_ids and (not branch or branch not in rule.branch_ids):
                continue  # สูตรของสาขาอื่น
            current = by_date.get(rule.effective_date)
            if current is None or (rule.branch_ids and not current.branch_ids):
                by_date[rule.effective_date] = rule
        return [by_date[d] for d in sorted(by_date)]

    @api.model
    def _rule_for_date(self, date_value, branch=None, company=None):
        """สูตรที่มีผลกับวันที่นี้ (คืน None ถ้ายังไม่มีสูตรครอบคลุม)"""
        if not date_value:
            return None
        picked = None
        for rule in self._rules_for_branch(branch, company):
            if rule.effective_date <= date_value:
                picked = rule
            else:
                break
        return picked

    @api.model
    def rules_for_engine(self, branch=None, company=None):
        """โหลดสูตรทั้งชุดครั้งเดียวไว้ให้เอนจินวนใช้รายวัน

        เอนจินวนหลายสิบวันต่อพนักงานหนึ่งคน ถ้าค้นสูตรใหม่ทุกวันจะยิง search
        ซ้ำเป็นร้อยครั้งต่อสลิป — โหลดทีเดียวแล้วเลือกในหน่วยความจำแทน
        """
        return self._rules_for_branch(branch, company)

    @api.model
    def resolve_for_day(self, rules, day, default_grace):
        """คืน (นาทีผ่อนผัน, เวลาเข้างานล่าสุด) ที่ใช้กับวันนั้น

        ``rules`` คือผลจาก :meth:`rules_for_engine` — ถ้ายังไม่มีสูตรครอบคลุม
        วันนั้น ให้ใช้ค่าผ่อนผันเดิมของสลิป เพื่อไม่ให้ผลของวันเก่าเปลี่ยน
        """
        picked = None
        for rule in rules:
            if rule.effective_date <= day:
                picked = rule
            else:
                break
        if picked is None:
            return default_grace, None
        if picked.mode == MODE_DEADLINE:
            return 0, picked.deadline_hour
        return picked.grace_minutes, None

    # ------------------------------------------------------------------
    # API สำหรับแอปพนักงาน
    # ------------------------------------------------------------------
    @api.model
    def api_get_late_minutes(self, employee_code, month, year):
        """นาทีที่ "สาย" รายวันของเดือนนั้น ให้แอปแสดงใต้เวลาเข้างาน

        ใช้เอนจินตัวเดียวกับตอนคิดเงินเดือน ตัวเลขที่แอปโชว์จึงเป็น
        "นาทีเดียวกับที่ payroll หักจริง" ไม่ได้คำนวณซ้ำในแอป
        เปลี่ยนสูตรใน Odoo เมื่อไหร่ แอปตามทันทีโดยไม่ต้อง build ใหม่

        :return: {'YYYY-MM-DD': {'minutes': int, 'checkin': 'HH:MM'}}
                 เฉพาะวันที่สายจริง (ไม่สาย = ไม่มี key)

                 ที่ต้องคืน ``checkin`` มาด้วย เพราะวันหนึ่งสแกนเข้าได้หลายครั้ง
                 แต่ระบบคิดสายจากครั้งแรกของวันครั้งเดียว แอปจะได้เอาไปจับคู่ว่า
                 ควรแสดงข้อความสายที่แถวไหน ไม่ใช่แปะทุกแถวของวันนั้น
        """
        empty = {}
        if not employee_code:
            return empty
        try:
            month, year = int(month), int(year)
        except (TypeError, ValueError):
            return empty
        if not (1 <= month <= 12) or year < 2000:
            return empty

        employee = self.env['employee.salary'].sudo().search(
            [('employee_code', '=', str(employee_code))], limit=1)
        if not employee:
            return empty
        if not self.env['hr.work.schedule'].sudo().search_count(
                [('employee_id', '=', employee.id)]):
            # ยังไม่ได้ตั้งตารางกะ = คิดสายไม่ได้ ปล่อยว่างดีกว่าเดามั่ว
            _logger.info('[APP LATE] ไม่พบตารางกะของ %s', employee_code)
            return empty

        date_from = date(year, month, 1)
        date_to = date(year, month, calendar.monthrange(year, month)[1])
        company = employee.company_id or self.env.company
        policy = self.env['payroll.policy'].sudo().get_for(company, date_to)
        if not policy:
            _logger.warning('[APP LATE] ไม่พบนโยบายเงินเดือนของ %s', company.name)
            return empty

        result = self.env['payroll.attendance.engine'].compute_attendance_deductions(
            employee, date_from, date_to, policy,
            grace_period=LEGACY_GRACE_MINUTES, base_salary=employee.salary)

        return {
            entry['date']: {
                'minutes': int(round(entry['minutes'])),
                'checkin': entry.get('checkin') or '',
            }
            for entry in (result.get('late_log') or [])
            if entry.get('minutes')
        }
