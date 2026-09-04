# -*- coding: utf-8 -*-
"""นโยบาย HR ระดับบริษัท

ค่าที่เดิม hardcode อยู่ในโค้ดฝั่ง Odoo 14 (รหัสพนักงานเริ่มที่ 1352, อัตราประกันสังคม
5% ช่วง 1,650–17,500, วันตัดรอบ 25, สิทธิ์วันลาแต่ละประเภท, สิทธิหยุดวันเสาร์ 2/1)
ย้ายมาเป็นฟิลด์บน res.company ทั้งหมด

เหตุผล: Odoo 14 แยก DB ต่อบริษัท ค่าคงที่จึงฝังในโค้ดได้ — Odoo 18 ใช้ DB เดียว
หลายบริษัท ค่าพวกนี้ต้องแยกตามบริษัท และต้องแก้ได้จากหน้า Settings เพื่อให้
ปล่อยเช่าระบบให้บริษัทอื่นใช้ได้โดยไม่ต้องแก้โค้ด
"""
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ------------------------------------------------------------------
    # รหัสพนักงาน
    # ------------------------------------------------------------------
    hrms_employee_code_prefix = fields.Char(
        string='คำนำหน้ารหัสพนักงาน',
        help='เว้นว่างได้ — ถ้ากรอก "NPD" รหัสจะออกเป็น NPD1352')
    hrms_employee_code_start = fields.Integer(
        string='รหัสพนักงานเริ่มต้นที่', default=1000,
        help='ระบบจะไล่หาเลขว่างตัวแรกตั้งแต่เลขนี้ขึ้นไป')
    hrms_employee_code_padding = fields.Integer(
        string='จำนวนหลักรหัสพนักงาน', default=0,
        help='0 = ไม่เติมศูนย์นำหน้า, 5 = 01352')

    # ------------------------------------------------------------------
    # รอบตัดเงินเดือน
    # ------------------------------------------------------------------
    hrms_cutoff_start_day = fields.Integer(
        string='วันเริ่มรอบตัดเงินเดือน', default=25,
        help='รอบเงินเดือนเริ่มวันที่นี้ของเดือนก่อนหน้า ถึงวันก่อนหน้าวันนี้ของเดือนปัจจุบัน '
             '(ค่า 25 = รอบ 25 ถึง 24)')

    # ------------------------------------------------------------------
    # ประกันสังคม
    # ------------------------------------------------------------------
    hrms_sso_enabled = fields.Boolean(string='คิดประกันสังคม', default=True)
    hrms_sso_rate = fields.Float(
        string='อัตราประกันสังคม (%)', default=5.0, digits=(5, 2))
    hrms_sso_min_wage = fields.Float(
        string='ฐานค่าจ้างต่ำสุด (ประกันสังคม)', default=1650.0)
    hrms_sso_max_wage = fields.Float(
        string='ฐานค่าจ้างสูงสุด (ประกันสังคม)', default=17500.0)

    # ------------------------------------------------------------------
    # สิทธิ์วันลาตั้งต้น (ใช้ตอนสร้างพนักงานใหม่ / รีเซ็ตขึ้นปีใหม่)
    # ------------------------------------------------------------------
    hrms_leave_personal_paid_days = fields.Integer(
        string='ลากิจได้รับค่าจ้าง (วัน/ปี)', default=3)
    hrms_leave_personal_paid_after_months = fields.Integer(
        string='ได้สิทธิ์ลากิจเมื่อทำงานครบ (เดือน)', default=3)
    hrms_leave_personal_unpaid_days = fields.Integer(
        string='ลากิจไม่ได้รับค่าจ้าง (วัน/ปี)', default=30)
    hrms_leave_sick_days = fields.Integer(
        string='ลาป่วยมีใบรับรองแพทย์ (วัน/ปี)', default=30)
    hrms_leave_maternity_paid_days = fields.Integer(
        string='ลาคลอดได้รับค่าจ้าง (วัน)', default=45)
    hrms_leave_maternity_unpaid_days = fields.Integer(
        string='ลาคลอดไม่ได้รับค่าจ้าง (วัน)', default=45)
    hrms_leave_vacation_days = fields.Integer(
        string='ลาพักร้อน (วัน/ปี)', default=7)
    hrms_leave_vacation_after_years = fields.Integer(
        string='ได้สิทธิ์ลาพักร้อนเมื่อทำงานครบ (ปี)', default=1)
    hrms_leave_saturday_days = fields.Integer(
        string='สิทธิหยุดวันเสาร์ (ครั้ง/ปี)', default=24)
    hrms_leave_emergency_days = fields.Integer(
        string='ลาฉุกเฉิน (วัน/ปี)', default=3)

    # ------------------------------------------------------------------
    # สิทธิหยุดวันเสาร์ — ค่าเริ่มต้นตอน seed config รายสาขา
    # ------------------------------------------------------------------
    hrms_saturday_days_hq = fields.Integer(
        string='สิทธิหยุดเสาร์/เดือน (สำนักงานใหญ่)', default=2)
    hrms_saturday_days_branch = fields.Integer(
        string='สิทธิหยุดเสาร์/เดือน (สาขา)', default=1)

    # ------------------------------------------------------------------
    # ค่าล่วงเวลา (OT)
    # ------------------------------------------------------------------
    hrms_ot_rate_weekday = fields.Float(
        string='อัตรา OT วันทำงาน (เท่า)', default=1.5, digits=(5, 2),
        help='ชั่วโมงที่ทำนอกกะของวันทำงานปกติ')
    hrms_ot_rate_sunday = fields.Float(
        string='อัตรา OT วันหยุดประจำสัปดาห์ (เท่า)', default=1.0, digits=(5, 2),
        help='ทำงานในวันที่ตารางงานไม่ได้กำหนดให้ทำ')
    hrms_ot_rate_holiday = fields.Float(
        string='อัตรา OT วันหยุดนักขัตฤกษ์ (เท่า)', default=2.0, digits=(5, 2))
    hrms_ot_grace_period = fields.Integer(
        string='ผ่อนผันเวลาสาย (นาที)', default=15,
        help='เข้าสายไม่เกินกี่นาทีถึงจะยังไม่ถูกหัก')

    # ------------------------------------------------------------------
    # การลงเวลา
    # ------------------------------------------------------------------
    hrms_checkin_default_radius = fields.Integer(
        string='รัศมีเช็คอินเริ่มต้น (เมตร)', default=50,
        help='ใช้เมื่อสาขายังไม่ได้ตั้งค่ารัศมีของตัวเอง')
    hrms_checkin_require_gps = fields.Boolean(
        string='บังคับส่งพิกัด GPS ตอนลงเวลา', default=True)
    hrms_allow_multi_login = fields.Boolean(
        string='อนุญาตให้ล็อกอินหลายเครื่องพร้อมกัน', default=False,
        help='ค่าเริ่มต้นระดับบริษัท — ตั้งรายบุคคลได้ที่บัตรพนักงาน')

    def _hrms_policy(self):
        """คืนค่านโยบาย HR ของบริษัทนี้เป็น dict — ใช้ในโค้ดคำนวณเพื่อไม่ต้อง
        อ้างชื่อฟิลด์ยาว ๆ กระจายทั่วโมดูล"""
        self.ensure_one()
        return {
            'code_prefix': self.hrms_employee_code_prefix or '',
            'code_start': self.hrms_employee_code_start or 1000,
            'code_padding': self.hrms_employee_code_padding or 0,
            'cutoff_start_day': self.hrms_cutoff_start_day or 25,
            'sso_enabled': self.hrms_sso_enabled,
            'sso_rate': (self.hrms_sso_rate or 0.0) / 100.0,
            'sso_min': self.hrms_sso_min_wage or 0.0,
            'sso_max': self.hrms_sso_max_wage or 0.0,
            'checkin_radius': self.hrms_checkin_default_radius or 50,
        }

    def _hrms_leave_defaults(self):
        """ค่าตั้งต้นสิทธิ์วันลาทุกประเภทของบริษัทนี้

        คีย์ตรงกับชื่อฟิลด์ใน hr.leave.type.custom เพื่อ write() ได้ตรง ๆ
        """
        self.ensure_one()
        return {
            'leave_personal_paid_total_remaining': self.hrms_leave_personal_paid_days,
            'leave_personal_paid_total': self.hrms_leave_personal_paid_days,
            'leave_personal_unpaid_total_remaining': self.hrms_leave_personal_unpaid_days,
            'leave_personal_unpaid_total': self.hrms_leave_personal_unpaid_days,
            'leave_sick_total_remaining': self.hrms_leave_sick_days,
            'leave_sick_total': self.hrms_leave_sick_days,
            'leave_maternity_paid_total_remaining': self.hrms_leave_maternity_paid_days,
            'leave_maternity_paid_total': self.hrms_leave_maternity_paid_days,
            'leave_maternity_unpaid_total_remaining': self.hrms_leave_maternity_unpaid_days,
            'leave_maternity_unpaid_total': self.hrms_leave_maternity_unpaid_days,
            'leave_vacation_total_remaining': self.hrms_leave_vacation_days,
            'leave_vacation_total': self.hrms_leave_vacation_days,
            'leave_saturday_total_remaining': self.hrms_leave_saturday_days,
            'leave_saturday_total': self.hrms_leave_saturday_days,
            'leave_emergency_total_remaining': self.hrms_leave_emergency_days,
            'leave_emergency_total': self.hrms_leave_emergency_days,
        }
