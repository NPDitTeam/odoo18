# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrmsManualTimeReason(models.Model):
    _inherit = 'hrms.manual.time.reason'

    hrms_is_medical = fields.Boolean(
        string='เบิกค่ารักษาพยาบาล',
        help='คำขอประเภทนี้มีวงเงินต่อปี ต้องระบุบัญชีธนาคารที่ให้โอนเข้า '
             'และเมื่ออนุมัติจะสร้างใบสำคัญจ่ายให้อัตโนมัติ\n'
             'จ่ายผ่านฝ่ายบัญชี — ไม่เข้าสลิปเงินเดือน')

    @api.constrains('hrms_is_medical', 'payroll_income_field')
    def _check_medical_not_in_payroll(self):
        for rec in self:
            if rec.hrms_is_medical and rec.payroll_income_field:
                raise ValidationError(
                    'ประเภท "%s" จ่ายผ่านใบสำคัญจ่ายแล้ว ห้ามตั้ง "ฟิลด์รายได้ในสลิป" ซ้ำ '
                    '— พนักงานจะได้เงินสองรอบ' % rec.name)
