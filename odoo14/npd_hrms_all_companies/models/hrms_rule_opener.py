# -*- coding: utf-8 -*-
"""เปิดกฎการมองเห็นของระบบบุคคลให้ข้ามบริษัทได้

ทำไมต้องเขียนด้วยโค้ดแทนที่จะประกาศในไฟล์ข้อมูล
------------------------------------------------
กฎพวกนี้ถูกสร้างครั้งแรกในบล็อก ``noupdate="1"`` ของโมดูลต้นทาง ซึ่งบอก Odoo
ว่า "สร้างครั้งเดียวแล้วอย่าไปยุ่งอีก" การประกาศทับในไฟล์ข้อมูลของโมดูลนี้
จึงไม่มีผล ต่อให้สั่งอัปเดตโมดูลกี่ครั้งก็ตาม (ลองมาแล้ว กฎยังเป็นค่าเดิม)

เขียนเป็นเมธอดแล้วเรียกจากไฟล์ข้อมูลด้วย ``<function>`` แทน วิธีนี้ทำงานทุกครั้ง
ที่อัปเดตโมดูล และถ้าวันหน้าอยากกลับไปกรองตามบริษัท ก็แค่ถอนโมดูลนี้ออก
โดยไม่ต้องไปไล่แก้กฎทีละข้อ

ทำไมต้องเปิดข้ามบริษัท
---------------------
ระบบเดิมฝั่ง Odoo 14 ไม่มีการแยกบริษัทในงานบุคคลเลย (ทั้งระบบมีบริษัทเดียว
ชื่อบริษัทของพนักงานเป็นแค่ข้อความไว้พิมพ์ในรายงาน) คนที่ทำงานบุคคลจึงเห็น
พนักงานทุกคนทุกบริษัทมาตลอด

ฝั่งนี้พอร์ตมาเป็นระบบหลายบริษัทจริง ซึ่งดีกว่าเรื่องการแยกงบและแยกเงินเดือน
แต่กฎการมองเห็นที่ติดมาทำให้ใช้งานจริงไม่ได้ เช่นพนักงาน 217 จาก 239 คน
ยื่นใบลาไม่ได้เพราะประเภทการลาถูกสร้างไว้ในบริษัทเดียว

ข้อมูลยังบันทึกว่าเป็นของบริษัทไหนครบทุกรายการ รายงานแยกบริษัทจึงยังทำได้
เปลี่ยนแค่ว่าไม่ต้องอยู่บริษัทนั้นถึงจะเห็น ส่วนการเข้าถึงยังคุมด้วยสิทธิ์กลุ่ม
ตามเดิม คนที่ไม่มีสิทธิ์งานบุคคลก็ยังไม่เห็นอะไรอยู่ดี
"""
import logging

from odoo import models, api

_logger = logging.getLogger(__name__)

# กฎที่ต้องเปิด — ชื่ออ้างอิงเต็มของแต่ละข้อ
HRMS_COMPANY_RULES = [
    'npd_hrms_base.rule_employee_salary_company',
    'npd_hrms_base.rule_employee_warning_company',
    'npd_hrms_base.rule_allowance_management_company',
    'npd_hrms_base.rule_payroll_holiday_company',
    'npd_hrms_base.rule_saturday_leave_config_company',
    'npd_hrms_attendance.rule_attendance_branch_company',
    'npd_hrms_attendance.rule_leave_request_company',
    'npd_hrms_attendance.rule_manual_time_log_company',
    'npd_hrms_attendance.rule_leave_balance_company',
    'npd_hrms_attendance.rule_hrms_leave_type_company',
    'npd_hrms_attendance.rule_manual_time_reason_company',
    'npd_hrms_medical.rule_hrms_medical_limit_company',
    'npd_hrms_medical.rule_hrms_medical_opening_company',
    'npd_hrms_payroll.rule_payroll_salary_company',
    'npd_hrms_payroll.rule_payroll_period_company',
    'npd_hrms_payroll.rule_payroll_policy_company',
    'npd_hrms_payroll.rule_other_income_company',
    'npd_hrms_payroll.rule_welfare_fund_config_company',
    'npd_hrms_payroll.rule_welfare_fund_report_company',
    'npd_hrms_payroll.rule_work_security_deposit_company',
]

# เงื่อนไขที่แปลว่า "เห็นได้ทุกแถว"
OPEN_DOMAIN = "[(1, '=', 1)]"


class IrRuleHrmsOpener(models.Model):
    _inherit = 'ir.rule'

    @api.model
    def npd_open_hrms_company_rules(self):
        """ปรับกฎของระบบบุคคลให้ไม่กรองตามบริษัท

        เรียกจากไฟล์ข้อมูลตอนติดตั้งและตอนอัปเดตโมดูล
        """
        opened, missing = 0, []
        for xmlid in HRMS_COMPANY_RULES:
            rule = self.env.ref(xmlid, raise_if_not_found=False)
            if not rule:
                missing.append(xmlid)
                continue
            if rule.domain_force != OPEN_DOMAIN:
                rule.sudo().write({'domain_force': OPEN_DOMAIN})
                opened += 1
        # ล้างแคชสิทธิ์ ไม่งั้นคนที่เปิดหน้าจอค้างไว้จะยังโดนกฎเดิมจนกว่าจะรีเฟรช
        self.env.registry.clear_cache()
        _logger.info('[HRMS-ALL-CO] เปิดกฎข้ามบริษัทแล้ว %s ข้อ%s', opened,
                     ' (ไม่พบ %s)' % ', '.join(missing) if missing else '')
        return True
