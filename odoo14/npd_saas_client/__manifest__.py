# -*- coding: utf-8 -*-
{
    'name': 'NPD SaaS - Client',
    'version': '18.0.1.0.0',
    'summary': 'บังคับใช้สัญญาการเช่าระบบในฐานข้อมูลของลูกค้า',
    'description': """
NPD SaaS - Client
=================
ติดตั้งใน DB ของลูกค้าแต่ละราย (มากับ DB ต้นแบบ) ทำหน้าที่อ่านและบังคับใช้สัญญา
ที่ศูนย์ควบคุมเขียนลงมา — ไม่มีหน้าจอให้แก้สัญญาเองโดยเจตนา

* หมดอายุ/ถูกระงับ → ล็อกทั้งหน้าเว็บและ REST API ของแอป (ข้อมูลยังอยู่ครบ)
* ช่วงผ่อนผัน → ใช้งานได้ตามปกติ แต่แนบข้อความเตือนไปกับหน้าแรกของแอป
* ปลดล็อกได้จากศูนย์ควบคุมเท่านั้น
    """,
    'category': 'Administration',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': ['npd_hrms_api'],
    'data': [
        'views/saas_license_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
