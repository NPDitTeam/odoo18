# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - Mobile API',
    'version': '18.0.1.0.0',
    'summary': 'REST API ให้แอป HR คุยกับ Odoo โดยตรง (แทน PHP npdhrms.com ทั้งหมด)',
    'description': """
NPD HRMS - Mobile API
=====================
แทนไฟล์ PHP ทั้งชุดบน npdhrms.com/api ด้วย controller ของ Odoo

หลักการออกแบบ
-------------
* **รูปแบบ JSON ที่ตอบกลับเหมือนเดิมทุกคีย์** — ฝั่งแอปแก้แค่ base URL
  กับการแนบ token ไม่ต้องรื้อ parser (คีย์ที่สะกดผิดมาแต่เดิมอย่าง
  ``leave_statr_time`` ก็คงไว้ด้วยเหตุผลนี้)
* **ตรรกะไม่อยู่ใน controller** — controller ทำหน้าที่แค่ตรวจสิทธิ์ แปลงพารามิเตอร์
  แล้วเรียกเมธอด ``api_*`` บนโมเดล กฎธุรกิจจึงมีชุดเดียวที่หน้าเว็บกับแอปใช้ร่วมกัน
* **มี token จริง** — ของเดิมยิงตรงถึงฐานข้อมูลโดยไม่มีการยืนยันตัวตนใด ๆ
  (บาง endpoint ใช้ HTTP Basic ที่ฝัง user/pass ไว้ในโค้ดแอป)
  ตอนนี้ล็อกอินแล้วได้ token ผูกกับอุปกรณ์ มีวันหมดอายุ และเพิกถอนได้

ทุก endpoint อยู่ใต้ ``/api/hrms/v1/``
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'npd_hrms_attendance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/api_cron.xml',
        'views/hrms_api_token_views.xml',
        'views/hrms_tenant_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
