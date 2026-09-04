# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - Attendance & Leave',
    'version': '18.0.1.0.0',
    'summary': 'ลงเวลาเข้า-ออก การลา และการขอเพิ่มเวลา (แทนฐานข้อมูล MySQL/PHP เดิม)',
    'description': """
NPD HRMS - Attendance & Leave
=============================
พอร์ตโมดูล ``hr_attendance_branch`` จาก Odoo 14 พร้อม "ย้ายเจ้าของข้อมูล"

เดิม (Odoo 14 + PHP)
--------------------
แอป → PHP (npdhrms.com) → MySQL คือแหล่งข้อมูลจริง
Odoo ดึงมาทีหลังด้วย cron (json_checkin.php / json_leave_requests.php / ...)
แล้ว push กลับตอนแก้ไข — ข้อมูลสองชุด ชนกันได้ และ Odoo เห็นข้อมูลช้า

ตอนนี้ (Odoo 18)
----------------
แอป → Odoo โดยตรง — Odoo เป็นแหล่งข้อมูลจริงชุดเดียว ไม่มี MySQL ไม่มี cron sync
ตรรกะทั้งหมด (หักสิทธิ์วันลา / คืนสิทธิ์ / กันลงเวลาซ้ำ / ตรวจรัศมี) อยู่ในโมเดล
ทั้งหน้าเว็บ Odoo และแอปจึงใช้กฎชุดเดียวกันเสมอ

ประเภทการลาเปลี่ยนเป็นข้อมูลหลัก (``hrms.leave.type``) แทนคอลัมน์ตายตัว 8 ประเภท
→ บริษัทที่เช่าระบบไปใช้ตั้งประเภทการลาของตัวเองได้
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'npd_hrms_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/attendance_security.xml',
        'data/hrms_leave_type_data.xml',
        'data/attendance_cron.xml',
        'views/hrms_leave_type_views.xml',
        'views/attendance_views.xml',
        'views/leave_request_views.xml',
        'views/manual_time_views.xml',
        'views/npd_hrms_attendance_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
