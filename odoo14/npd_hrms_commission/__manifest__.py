# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - Commission',
    'version': '18.0.1.0.0',
    'summary': 'ค่าคอมมิชชั่นสาขาและ Sales เข้าสลิปเงินเดือน',
    'description': """
NPD HRMS - Commission
=====================
ต่อยอดค่าคอมมิชชั่นจากรายงานฝั่ง ERP เข้าสลิปเงินเดือน

สิ่งที่เปลี่ยนจาก Odoo 14
--------------------------
เดิม HR อยู่คนละฐานกับ ERP (แยก DB ต่อบริษัท) โมดูล ``cross_db_commission``
จึงเปิด psycopg2 ต่อตรงเข้าไปอีก 4 ฐาน แล้วยิง SQL ดิบ ~840 บรรทัด
พร้อมต้อง push รายชื่อ Sales สำนักงานใหญ่และ snapshot เงินเดือนข้ามฐานกลับไป

Odoo 18 ใช้ฐานเดียวหลายบริษัทแล้ว → อ่านผ่าน ORM ตรง ๆ
ไม่มี psycopg2 ไม่มี SQL ดิบ ไม่มี credential ฝังในโค้ด ไม่ต้อง push อะไรกลับ

ข้อควรทราบ
-----------
โมดูลต้นทาง ``npd_commission_report`` (npd.commission.report / .sales)
**ยังไม่ถูกพอร์ตมา Odoo 18** — โมดูลนี้ตรวจก่อนเสมอ ถ้ายังไม่มีจะคิดค่าคอมเป็น 0
และเขียน log บอก แทนที่จะพัง ทำให้เงินเดือนส่วนอื่นยังทำงานได้ครบ
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'npd_hrms_payroll',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/commission_config_views.xml',
        'views/payroll_salary_views.xml',
        'views/npd_hrms_commission_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
