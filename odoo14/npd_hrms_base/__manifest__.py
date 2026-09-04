# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - Base',
    'version': '18.0.1.0.0',
    'summary': 'ข้อมูลหลักระบบบุคคล — พนักงาน สาขา แผนก ตำแหน่ง ตารางงาน วันหยุด เบี้ยเลี้ยง',
    'description': """
NPD HRMS - Base
===============
ข้อมูลหลักของระบบบุคคล พอร์ตจาก Odoo 14 (employee_salary) มาที่ Odoo 18

ความแตกต่างจากของเดิมบน Odoo 14
--------------------------------
1. **ตัดการเชื่อมต่อ PHP API (npdhrms.com) ออกทั้งหมด** — Odoo เป็นเจ้าของข้อมูลจริง
   ไม่มี ``_sync_to_api`` / ``import_from_php`` / ``get_device_id.php`` อีกต่อไป
2. สาขาใช้ ``res.branch`` (multi_branch_management_aagam) แทน ``hr.branch.custom``
   → สาขาชุดเดียวกับฝั่งขาย/บัญชี/สต๊อก คิดค่าคอมสาขาได้ตรงโดยไม่ต้อง map ชื่อ
3. แยกบริษัทด้วย ``res.company`` ใน DB เดียว แทนการแยก DB ต่อบริษัทแบบเดิม
   (``company`` ที่เคยเป็น Selection ชื่อบริษัท 5 ค่า → ``company_id``)
4. ค่าที่เคย hardcode เป็นของ NPD (รหัสพนักงานเริ่มที่ 1352, ประกันสังคม 5%
   ช่วง 1,650–17,500, วันตัดรอบ 25, สิทธิ์วันลา, สิทธิหยุดวันเสาร์ 2/1)
   ย้ายมาอยู่ที่ ``res.company`` → ตั้งค่าแยกรายบริษัทได้จากหน้า Settings
   รองรับการปล่อยเช่าระบบให้บริษัทอื่นใช้โดยไม่ต้องแก้โค้ด
5. ``age`` เปลี่ยนเป็นฟิลด์คำนวณจากวันเกิด (เดิมกรอกมือแล้วค้างไม่อัปเดต)
6. เพิ่ม ``hr_employee_id`` ผูกกับ ``hr.employee`` มาตรฐานของ Odoo
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'multi_branch_management_aagam',
    ],
    'data': [
        'security/npd_hrms_security.xml',
        'security/ir.model.access.csv',
        'security/employee_security.xml',
        'data/employee_cron.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_branch_views.xml',
        'views/hr_org_master_views.xml',
        'views/employee_salary_views.xml',
        'views/employee_warning_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_work_schedule_views.xml',
        'views/payroll_holiday_views.xml',
        'views/saturday_leave_config_views.xml',
        'views/allowance_management_views.xml',
        'views/approver_relations_views.xml',
        'views/hrms_app_release_views.xml',
        'views/npd_hrms_menus.xml',
        'views/employee_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
