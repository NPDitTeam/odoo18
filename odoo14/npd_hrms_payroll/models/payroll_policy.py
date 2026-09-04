# -*- coding: utf-8 -*-
"""นโยบายการคำนวณเงินเดือน — ตัวเลขทุกตัวในสูตรอยู่ที่นี่

เหตุผลที่ต้องมีโมเดลนี้: ระบบจะถูกปล่อยเช่าให้บริษัทอื่นใช้ และแต่ละบริษัท
คิดเงินเดือนไม่เหมือนกัน (ตัวหารวัน/ชั่วโมง อัตรา OT เพดานลดหย่อน ขั้นภาษี
วิธีปัดเศษ) ถ้าฝังไว้ในโค้ดเหมือน Odoo 14 จะต้องแก้โค้ดทุกครั้งที่รับลูกค้าใหม่

ค่าเริ่มต้นทุกตัวตั้งไว้ตรงกับที่ NPD ใช้อยู่เดิม → ติดตั้งแล้วได้ผลลัพธ์เท่าเดิม

มี ``effective_from`` เพื่อรองรับกรณีกฎหมายภาษีเปลี่ยน — สร้างนโยบายใหม่
โดยไม่แตะของเก่า สลิปย้อนหลังจึงยังคำนวณด้วยกติกาของปีนั้น
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ค่าเริ่มต้น = กติกาที่ NPD ใช้อยู่ (อัตราภาษีเงินได้บุคคลธรรมดาของไทย)
DEFAULT_TAX_BRACKETS = [
    (1, 0, 150000, 0, 0),
    (2, 150001, 300000, 5, 7500),
    (3, 300001, 500000, 10, 22500),
    (4, 500001, 750000, 15, 47500),
    (5, 750001, 1000000, 20, 85000),
    (6, 1000001, 2000000, 25, 135000),
    (7, 2000001, 5000000, 30, 235000),
    (8, 5000001, 999999999, 35, 485000),
]


class PayrollPolicy(models.Model):
    _name = 'payroll.policy'
    _description = 'นโยบายการคำนวณเงินเดือน'
    _order = 'company_id, effective_from desc'

    name = fields.Char(string='ชื่อนโยบาย', required=True, default='นโยบายมาตรฐาน')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)
    effective_from = fields.Date(
        string='เริ่มใช้ตั้งแต่', required=True,
        default=lambda self: fields.Date.to_date('2000-01-01'),
        help='ระบบเลือกนโยบายที่ "เริ่มใช้" ล่าสุดแต่ไม่เกินวันตัดรอบของสลิปนั้น')
    active = fields.Boolean(string='ใช้งาน', default=True)
    note = fields.Text(string='หมายเหตุ')

    # ------------------------------------------------------------------
    # ตัวหารพื้นฐาน
    # ------------------------------------------------------------------
    salary_days_divisor = fields.Float(
        string='ตัวหารวันต่อเดือน', default=30.0, required=True,
        help='ค่าจ้างต่อวัน = เงินเดือน ÷ ค่านี้ (ค่ามาตรฐานของไทยคือ 30)')
    ot_hours_per_day = fields.Float(
        string='ชั่วโมงทำงานต่อวัน (ฐานคิด OT)', default=8.0, required=True,
        help='ค่าจ้างต่อชั่วโมงสำหรับคิด OT = ค่าจ้างต่อวัน ÷ ค่านี้')
    use_schedule_hours_for_deduction = fields.Boolean(
        string='ใช้ชั่วโมงจากตารางงานคิดยอดหักสาย', default=True,
        help='ติ๊ก = คิดค่าจ้างต่อชั่วโมงจากกะจริงของพนักงาน (ค่าเฉลี่ยต่อวัน) '
             'ไม่ติ๊ก = ใช้ "ชั่วโมงทำงานต่อวัน" ด้านบนเหมือน OT')

    # ------------------------------------------------------------------
    # พักเที่ยง
    # ------------------------------------------------------------------
    lunch_enabled = fields.Boolean(string='หักช่วงพักเที่ยง', default=True)
    lunch_start = fields.Float(string='พักเที่ยงเริ่ม', default=12.0)
    lunch_end = fields.Float(string='พักเที่ยงสิ้นสุด', default=13.0)
    lunch_min_shift_hours = fields.Float(
        string='กะยาวกี่ชั่วโมงจึงหักพักเที่ยง', default=8.0,
        help='ใช้ตอนหาชั่วโมงทำงานเฉลี่ยต่อวัน')

    # ------------------------------------------------------------------
    # การปัดเศษ
    # ------------------------------------------------------------------
    late_rounding = fields.Selection([
        ('floor', 'ปัดลง (เข้าข้างพนักงาน)'),
        ('ceil', 'ปัดขึ้น'),
        ('none', 'ไม่ปัด (ตามจริง)'),
    ], string='ปัดเศษนาทีสาย', default='floor', required=True)
    early_rounding = fields.Selection([
        ('floor', 'ปัดลง'),
        ('ceil', 'ปัดขึ้น (เข้าข้างบริษัท)'),
        ('none', 'ไม่ปัด (ตามจริง)'),
    ], string='ปัดเศษนาทีออกก่อนเวลา', default='ceil', required=True)

    # ------------------------------------------------------------------
    # กฎการหัก
    # ------------------------------------------------------------------
    absent_includes_early = fields.Boolean(
        string='รวมยอดออกก่อนเวลาไว้ในยอดหักขาดงาน', default=True,
        help='ตรงกับระบบเดิม — ถ้าไม่ติ๊ก ยอดออกก่อนเวลาจะแยกเป็นอีกบรรทัด')
    leave_full_shift_as_full_day = fields.Boolean(
        string='ลาคลุมทั้งกะ = หักเต็มวัน', default=True)
    skip_late_on_first_workday = fields.Boolean(
        string='วันแรกที่เริ่มงานไม่นับสาย', default=True)
    exclude_leave_overlap = fields.Boolean(
        string='ไม่นับสาย/ออกก่อน ที่ทับกับช่วงลา', default=True,
        help='กันหักซ้ำ — ลาช่วงเช้าแล้วเข้าสายเพราะลา จะไม่ถูกหักทั้งสองทาง')

    # ------------------------------------------------------------------
    # ค่าล่วงเวลา
    # ------------------------------------------------------------------
    ot_rate_weekday = fields.Float(
        string='อัตรา OT วันทำงาน (เท่า)', default=1.5, required=True)
    ot_rate_sunday = fields.Float(
        string='อัตรา OT วันหยุดประจำสัปดาห์ (เท่า)', default=1.0, required=True)
    ot_rate_holiday = fields.Float(
        string='อัตรา OT วันหยุดนักขัตฤกษ์ (เท่า)', default=2.0, required=True)
    ot_min_hours = fields.Float(
        string='OT ขั้นต่ำ (ชั่วโมง)', default=1.0,
        help='ต่ำกว่านี้ไม่คิด OT — ใช้เฉพาะเมื่อเลือกวิธี "ปัดเศษเป็นชั่วโมงเต็ม"')

    # ------------------------------------------------------------------
    # ประกันสังคม
    # ------------------------------------------------------------------
    sso_enabled = fields.Boolean(string='คิดประกันสังคม', default=True)
    sso_rate = fields.Float(string='อัตราประกันสังคม (%)', default=5.0)
    sso_min_wage = fields.Float(string='ฐานค่าจ้างต่ำสุด', default=1650.0)
    sso_max_wage = fields.Float(string='ฐานค่าจ้างสูงสุด', default=17500.0)
    sso_prorate_with_salary = fields.Boolean(
        string='คิดจากเงินเดือนที่ได้จริง (prorate)', default=True,
        help='คนเข้า/ออกกลางเดือนจะหักตามยอดที่ได้จริง ไม่ใช่ฐานเต็ม')
    sso_tax_deduction_cap = fields.Float(
        string='เพดานลดหย่อนภาษีของ ปกส. (ต่อปี)', default=9000.0,
        help='กฎหมายให้ลดหย่อนได้จากฐาน 15,000 × 5% × 12 = 9,000 '
             'ซึ่งน้อยกว่ายอดที่หักจริง (ฐาน 17,500)')

    # ------------------------------------------------------------------
    # ภาษี — ค่าลดหย่อนและเพดาน
    # ------------------------------------------------------------------
    tax_enabled = fields.Boolean(string='คิดภาษีหัก ณ ที่จ่าย', default=True)
    tax_personal_deduction = fields.Float(
        string='ค่าลดหย่อนส่วนตัว', default=60000.0)
    tax_expense_rate = fields.Float(
        string='หักค่าใช้จ่าย (% ของเงินได้)', default=50.0)
    tax_expense_max = fields.Float(
        string='หักค่าใช้จ่ายสูงสุด', default=100000.0)

    ded_spouse_max = fields.Float(string='เพดานคู่สมรส', default=60000.0)
    ded_parents_max = fields.Float(string='เพดานอุปการะบิดามารดา', default=120000.0)
    ded_health_self_max = fields.Float(
        string='เพดานประกันสุขภาพตนเอง', default=25000.0)
    ded_life_health_max = fields.Float(
        string='เพดานประกันชีวิต + สุขภาพตนเอง (รวม)', default=100000.0)
    ded_parents_health_max = fields.Float(
        string='เพดานประกันสุขภาพบิดามารดา', default=15000.0)
    ded_pension_ins_rate = fields.Float(
        string='ประกันบำนาญ (% ของเงินได้)', default=15.0)
    ded_pension_ins_max = fields.Float(string='เพดานประกันบำนาญ', default=200000.0)
    ded_rmf_rate = fields.Float(string='RMF (% ของเงินได้)', default=30.0)
    ded_rmf_max = fields.Float(string='เพดาน RMF', default=500000.0)
    ded_ssf_rate = fields.Float(string='SSF (% ของเงินได้)', default=30.0)
    ded_ssf_max = fields.Float(string='เพดาน SSF', default=200000.0)
    ded_thaiesg_rate = fields.Float(string='ThaiESG (% ของเงินได้)', default=30.0)
    ded_thaiesg_max = fields.Float(string='เพดาน ThaiESG', default=300000.0)
    ded_pension_fund_rate = fields.Float(
        string='กองทุนสำรองเลี้ยงชีพ (% ของเงินได้)', default=15.0)
    ded_pension_fund_max = fields.Float(
        string='เพดานกองทุนสำรองเลี้ยงชีพ', default=500000.0)
    ded_retire_group_max = fields.Float(
        string='เพดานรวมกลุ่มเกษียณ', default=500000.0,
        help='บำนาญ + RMF + SSF + กองทุนสำรองฯ รวมกันไม่เกินค่านี้ (ThaiESG แยกต่างหาก)')
    ded_home_loan_max = fields.Float(
        string='เพดานดอกเบี้ยกู้ซื้อที่อยู่อาศัย', default=100000.0)
    ded_shopping_max = fields.Float(
        string='เพดานช้อปดีมีคืน / Easy E-Receipt', default=50000.0)
    ded_donation_rate = fields.Float(
        string='เงินบริจาคหักได้ (% ของเงินได้หลังลดหย่อน)', default=10.0)

    tax_bracket_ids = fields.One2many(
        'payroll.policy.tax.bracket', 'policy_id', string='ขั้นบันไดอัตราภาษี')

    _sql_constraints = [
        ('company_effective_uniq', 'unique(company_id, effective_from)',
         'มีนโยบายที่เริ่มใช้วันเดียวกันในบริษัทนี้อยู่แล้ว'),
    ]

    @api.constrains('salary_days_divisor', 'ot_hours_per_day')
    def _check_divisors(self):
        for rec in self:
            if rec.salary_days_divisor <= 0:
                raise ValidationError('ตัวหารวันต่อเดือนต้องมากกว่า 0')
            if rec.ot_hours_per_day <= 0:
                raise ValidationError('ชั่วโมงทำงานต่อวันต้องมากกว่า 0')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tax_bracket_ids'):
                vals['tax_bracket_ids'] = [
                    (0, 0, {
                        'sequence': seq, 'income_from': income_from,
                        'income_to': income_to, 'rate': rate, 'deduction': deduction,
                    })
                    for seq, income_from, income_to, rate, deduction
                    in DEFAULT_TAX_BRACKETS
                ]
        return super().create(vals_list)

    def action_reset_tax_brackets(self):
        """คืนขั้นบันไดภาษีเป็นอัตรามาตรฐานของไทย"""
        for rec in self:
            rec.tax_bracket_ids.unlink()
            rec.tax_bracket_ids = [
                (0, 0, {
                    'sequence': seq, 'income_from': income_from,
                    'income_to': income_to, 'rate': rate, 'deduction': deduction,
                })
                for seq, income_from, income_to, rate, deduction in DEFAULT_TAX_BRACKETS
            ]
        return True

    # ------------------------------------------------------------------
    @api.model
    def get_for(self, company, on_date=None):
        """นโยบายที่ใช้กับบริษัทนี้ ณ วันที่ระบุ

        ไม่พบ → สร้างนโยบายมาตรฐานให้อัตโนมัติ เพื่อให้ระบบใช้งานได้ทันที
        หลังติดตั้งโดยไม่ต้องตั้งค่าอะไรก่อน
        """
        company = company or self.env.company
        on_date = on_date or fields.Date.context_today(self)
        policy = self.sudo().search([
            ('company_id', '=', company.id),
            ('effective_from', '<=', on_date),
        ], order='effective_from desc', limit=1)
        if policy:
            return policy
        policy = self.sudo().search(
            [('company_id', '=', company.id)], order='effective_from asc', limit=1)
        if policy:
            return policy
        _logger.info('[PAYROLL POLICY] สร้างนโยบายมาตรฐานให้บริษัท %s', company.name)
        return self.sudo().create({
            'name': 'นโยบายมาตรฐาน',
            'company_id': company.id,
            # ค่าเริ่มต้นดึงจาก res.company เพื่อไม่ให้ตั้งค่าซ้ำสองที่
            'sso_enabled': company.hrms_sso_enabled,
            'sso_rate': company.hrms_sso_rate or 5.0,
            'sso_min_wage': company.hrms_sso_min_wage or 1650.0,
            'sso_max_wage': company.hrms_sso_max_wage or 17500.0,
            'ot_rate_weekday': company.hrms_ot_rate_weekday or 1.5,
            'ot_rate_sunday': company.hrms_ot_rate_sunday or 1.0,
            'ot_rate_holiday': company.hrms_ot_rate_holiday or 2.0,
        })

    def action_duplicate_for_new_year(self):
        """คัดลอกนโยบายไปเป็นฉบับใหม่ — ใช้เมื่อกฎหมายภาษีเปลี่ยน

        ของเดิมไม่ถูกแตะ สลิปย้อนหลังจึงยังคำนวณด้วยกติกาเดิม
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        new_policy = self.copy({
            'name': '%s (แก้ไข %s)' % (self.name, today.year),
            'effective_from': today,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'payroll.policy',
            'res_id': new_policy.id,
            'view_mode': 'form',
            'target': 'current',
        }


class PayrollPolicyTaxBracket(models.Model):
    _name = 'payroll.policy.tax.bracket'
    _description = 'ขั้นบันไดอัตราภาษี (นโยบาย)'
    _order = 'sequence'

    policy_id = fields.Many2one(
        'payroll.policy', string='นโยบาย', required=True, ondelete='cascade')
    sequence = fields.Integer(string='ลำดับ', required=True, default=1)
    income_from = fields.Float(string='เงินได้ตั้งแต่', required=True)
    income_to = fields.Float(string='ถึง', required=True)
    rate = fields.Float(string='อัตราภาษี (%)', required=True)
    deduction = fields.Float(
        string='ค่าลดหย่อนของขั้น',
        help='ใช้ในสูตรย่อ: (เงินได้สุทธิ × อัตรา) − ค่านี้')
