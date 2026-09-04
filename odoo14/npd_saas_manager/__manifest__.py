# -*- coding: utf-8 -*-
{
    'name': 'NPD SaaS - Manager',
    'version': '18.0.1.0.0',
    'summary': 'ศูนย์ควบคุมการปล่อยเช่าระบบ — สร้าง/ต่ออายุ/ระงับ ฐานข้อมูลลูกค้า',
    'description': """
NPD SaaS - Manager
==================
ติดตั้งบนฐานข้อมูลศูนย์ควบคุม (NPD_Logistics) เท่านั้น

* ลูกค้าหนึ่งราย = หนึ่งฐานข้อมูล = หนึ่งโดเมนย่อย
* สร้างระบบให้ลูกค้าใหม่ด้วยการโคลน DB ต้นแบบที่สะอาด (ตั้งค่าที่พารามิเตอร์ระบบ
  npd_saas.template_db) — ไม่โคลนจากฐานข้อมูลที่มีข้อมูลจริง เพราะข้อมูลพนักงาน
  เงินเดือน และลูกค้าจะหลุดไปอยู่กับผู้เช่า และติดไปกับ backup ของเขาด้วย
* สัญญาถูกเขียนลงฐานข้อมูลลูกค้า แล้วโมดูล npd_saas_client ฝั่งนั้นบังคับใช้เอง
  ระบบลูกค้าจึงคุมสัญญาได้แม้ตัดขาดจากศูนย์ควบคุม
* cron ตรวจวันหมดอายุทุกวัน เลื่อนเป็นผ่อนผัน แล้วจึงหมดอายุ ให้อัตโนมัติ

ก่อนใช้งานจริงต้องตั้งค่า
------------------------
1. npd_saas.template_db  = ชื่อ DB ต้นแบบที่สะอาด
2. npd_saas.root_domain  = โดเมนหลัก (ค่าเริ่มต้น npd-solution.com)
3. dbfilter = ^%d$ ใน odoo.conf พร้อม DNS และใบรับรอง SSL แบบ wildcard
    """,
    'category': 'Administration',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': ['npd_hrms_api'],
    'data': [
        'security/ir.model.access.csv',
        'data/saas_cron.xml',
        'views/saas_tenant_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
