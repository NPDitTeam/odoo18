# -*- coding: utf-8 -*-
"""ให้รายงาน ภ.ง.ด.1 ตามทันทุกครั้งที่สลิปถูกแก้

แยกเป็นไฟล์ของตัวเองเพราะต้องโหลดหลัง ``payroll_salary`` — โมเดลที่ขยายด้วย
``_inherit`` ต้องมีตัวจริงอยู่ในทะเบียนก่อน ไม่งั้น Odoo โหลดโมดูลไม่ผ่านทั้งตัว
(ไฟล์ ``pnd1_report`` ถูก import ก่อน ``payroll_salary`` ในโมดูลนี้)
"""
from odoo import models


class PayrollSalaryPnd1(models.Model):
    """ให้รายงาน ภ.ง.ด.1 ตามทันทุกครั้งที่สลิปถูกแก้

    เดิมรายงานถูกสร้างตอนอนุมัติรอบครั้งเดียว การแก้ยอดทีหลังจึงไม่สะท้อนในรายงาน
    และไม่มีสัญญาณอะไรบอกว่าตัวเลขสองฝั่งไม่ตรงกันแล้ว
    """
    _inherit = 'payroll.salary'

    # ฟิลด์ที่กระทบยอดในรายงาน (line_ids → รายรับเปลี่ยนตามบรรทัดในสลิป)
    PND1_WATCH_FIELDS = {
        'line_ids', 'total_gross', 'net_salary', 'tax_monthly',
        'payment_date', 'employee_id', 'year', 'month', 'period_id',
    }

    def write(self, vals):
        res = super().write(vals)
        if (res and not self.env.context.get('skip_pnd1_sync')
                and set(vals) & self.PND1_WATCH_FIELDS):
            self.env['pnd1.line']._sync_payrolls_safe(self)
        return res
