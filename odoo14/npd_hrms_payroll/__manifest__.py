# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - Payroll',
    'version': '18.0.1.0.0',
    'summary': 'คำนวณเงินเดือน ภาษี ประกันสังคม OT และเงินประกันการทำงาน',
    'description': """
NPD HRMS - Payroll
==================
พอร์ตเอนจินเงินเดือนจาก Odoo 14 (``payroll_salary`` ~3,300 บรรทัด)

สิ่งที่เปลี่ยน
--------------
1. **ตัด PHP ออกทั้งหมด** — สาย/ขาด/ลา/OT คำนวณเองใน ``payroll.attendance.engine``
   (เดิมยิง calculate_lateness.php + get_ot_data.php ไปอ่าน MySQL)
2. **ค่าเที่ยว/เบี้ยเลี้ยงคนขับอ่านผ่าน ORM** จาก ``vehicle.booking``
   (เดิม login ข้ามเซิร์ฟเวอร์ไป npd-solution.com แล้วดึง JSON มาเทียบเอง)
   ยึด ``delivery_date`` = วันส่งจริงเวลาไทย และไม่กรองสาขา
3. **สูตรทุกตัวตั้งค่าได้** ผ่าน ``payroll.policy`` — ตัวหารวัน/ชั่วโมง อัตรา OT
   เพดานลดหย่อนภาษีทุกช่อง ขั้นบันไดภาษี วิธีปัดเศษ พักเที่ยง
   ค่าเริ่มต้นตรงกับที่ NPD ใช้อยู่ → ติดตั้งแล้วได้ผลเท่าเดิม
   มี ``effective_from`` รองรับกฎหมายเปลี่ยนโดยไม่กระทบสลิปย้อนหลัง
4. **บุคคลพิเศษตั้งค่าบนบัตรพนักงาน** — เดิมฝังรหัสผู้บริหารไว้ใน
   ``EXECUTIVE_TAX_CONFIG`` ในโค้ด ต้องแก้โปรแกรมทุกครั้งที่เปลี่ยนคน
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'npd_hrms_attendance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/payroll_security.xml',
        'data/payroll_policy_data.xml',
        'views/payroll_policy_views.xml',
        'views/lateness_rule_views.xml',
        'views/pnd1_report_views.xml',
        'views/payroll_period_views.xml',
        'views/payroll_salary_views.xml',
        'views/other_income_views.xml',
        'views/work_security_deposit_views.xml',
        'views/employee_salary_views.xml',
        'views/employee_warning_auto_views.xml',
        'views/npd_hrms_payroll_menus.xml',
        'reports/employee_warning_report.xml',
        'data/employee_warning_auto_cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
