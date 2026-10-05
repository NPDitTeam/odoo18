# -*- coding: utf-8 -*-
"""กันดึงสลิปที่ลงบัญชีแล้วกลับเป็นร่าง

ไม่กันการเขียน/ลบสลิป เพราะตัวซิงก์ o14 (sync_deletes) เขียนและลบตรง ๆ
ถ้ากันไว้การซิงก์จะพัง — กรณีนั้นให้ฝ่ายบัญชีเห็นผ่านธง "สลิปเปลี่ยนหลังลงบัญชี" แทน
"""
from odoo import models
from odoo.exceptions import UserError


class PayrollSalary(models.Model):
    _inherit = 'payroll.salary'

    def action_reset_draft(self):
        Link = self.env['npd.payroll.account.move'].sudo()
        for slip in self.sudo():
            if slip.period_id and Link.search_count([
                    ('period_id', '=', slip.period_id.id),
                    ('company_id', '=', slip.company_id.id),
                    ('state', '=', 'posted')]):
                raise UserError('สลิปนี้ลงบัญชีแล้ว ให้ฝ่ายบัญชีกลับรายการก่อน (%s)'
                                % (slip.display_name or slip.employee_code or ''))
        return super().action_reset_draft()
