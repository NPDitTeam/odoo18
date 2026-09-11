# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - Medical Expense',
    'version': '18.0.1.0.0',
    'summary': 'เบิกค่ารักษาพยาบาลผ่านแอป — วงเงินต่อปี ยอดยกมา และส่งเข้าใบสำคัญจ่ายอัตโนมัติ',
    'description': """
NPD HRMS - Medical Expense
==========================
พอร์ตฟีเจอร์ "ค่ารักษาพยาบาล" จาก Odoo 14 (employee_salary / medical.expense)

ความต่างจาก Odoo 14
-------------------
* ไม่มีโมเดลแยก — ใช้คำขอเพิ่มเวลา (``hr.manual.time.log``) ที่แอปส่งเข้ามาอยู่แล้ว
  ประเภทที่ติ๊ก "เบิกค่ารักษาพยาบาล" จะได้บัญชีธนาคาร / ไฟล์แนบหลายไฟล์ /
  วงเงินต่อปี / ใบสำคัญจ่าย เพิ่มเข้ามา
* Odoo 14 แยก DB ต่อบริษัท ต้องเปิด cursor ข้าม DB ไปสร้างใบการรับ —
  Odoo 18 อยู่ DB เดียว สร้างใบสำคัญจ่ายในบริษัทของพนักงานด้วย ``with_company``
  ใน transaction เดียวกับการอนุมัติ (ล้มก็ย้อนทั้งคู่ ไม่มีใบค้างครึ่งทาง)
* ค่าตั้งต้นของใบสำคัญจ่าย (บัญชี วิธีจ่ายเงิน สาขา เลขเอกสาร) อยู่บน ``res.company``
  แท็บ "นโยบายระบบบุคคล" แทนตาราง config ที่อ้าง id ข้าม DB
* ค่ารักษาพยาบาลจ่ายผ่านใบสำคัญจ่ายแล้ว จึงห้ามเข้าสลิปเงินเดือนซ้ำ
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'npd_hrms_api',
        'account_voucher_npd',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/medical_security.xml',
        'data/medical_cron.xml',
        'views/res_company_views.xml',
        'views/medical_limit_views.xml',
        'views/manual_time_views.xml',
        'views/account_voucher_views.xml',
        'views/employee_salary_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
