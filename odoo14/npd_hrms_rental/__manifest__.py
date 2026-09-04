# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - Rental & Transport',
    'version': '18.0.1.0.0',
    'summary': 'ผูกพนักงานกับคนขับ ค่าเที่ยว/เบี้ยเลี้ยงจากงานขนส่งและงานเช่า',
    'description': """
NPD HRMS - Rental & Transport
=============================
ต่อระบบบุคคลเข้ากับงานขนส่ง/ปล่อยเช่า

สิ่งที่เปลี่ยนจาก Odoo 14
--------------------------
เดิมเงินเดือนต้อง login ข้ามเซิร์ฟเวอร์ไป npd-solution.com (DB NPD_Logistics)
แล้วยิง JSON API ดึงงานมาทีละเดือน 2 รอบ เอามาเทียบรอบตัดเองใน Python
พร้อมบวกเวลา +7 ชม. แปลง UTC เป็นเวลาไทยเอง

ตอนนี้อยู่ฐานเดียวกันแล้ว → อ่าน ``vehicle.booking`` ผ่าน ORM ตรง ๆ
และใช้ฟิลด์ ``delivery_date`` ที่เป็นวันส่งจริงเวลาไทยซึ่ง store ไว้แล้ว
จึงไม่ต้องแปลงเวลาเอง และไม่พลาดงานที่คาบรอยต่อรอบ

โมดูลนี้เพิ่ม
--------------
* ผูกบัตรพนักงานกับคนขับ (``vehicle.driver``) แบบสองทาง
* ปุ่มดูงานขนส่งของพนักงานในรอบเงินเดือน เพื่อตรวจว่าค่าเที่ยวมาจากงานไหน
* แยกยอดค่าเที่ยว/เบี้ยเลี้ยงให้เห็นในสลิป
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'npd_hrms_payroll',
        'transport_booking',
        'vehicle_registration',
    ],
    'data': [
        'views/employee_driver_views.xml',
        'views/payroll_salary_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
