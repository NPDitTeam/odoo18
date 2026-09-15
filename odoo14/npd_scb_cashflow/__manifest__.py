# -*- coding: utf-8 -*-
{
    'name': 'NPD Bank Cash Flow Report',
    'summary': 'รายงานกระแสเงินสดธนาคาร (SCB / Kbank / กรุงไทย) ดึงจาก Google Sheet',
    'description': """
NPD SCB Cash Flow Report
========================
เพิ่มเมนู "กระแสเงินสด ธนาคาร SCB" ในโมดูลการออกใบแจ้งหนี้/บัญชี (Reporting)
โดยดึงข้อมูลจาก Google Spreadsheet (แท็บ SCB) มาแสดงเป็นตารางใน Odoo

- ใช้ Google Service Account (ชีตเป็นส่วนตัวได้ ไม่ต้องเปิดสาธารณะ)
- ปุ่ม "ดึงข้อมูลจาก Google Sheet" ในเมนู Action ของตาราง
- Scheduled Action (cron) ดึงอัตโนมัติทุก 15 นาที (เปิด/ปิดได้)
- ไม่ต้องใช้ Google Apps Script

พอร์ตจาก Odoo 14 (14.0.2.6.0): เรียก Google Sheets API ตรงด้วย requests + cryptography
(ไลบรารีที่ Odoo มีอยู่แล้ว) ไม่ต้อง pip install google-api-python-client ใน container
""",
    'version': '18.0.1.0.0',
    'author': 'PP',
    'category': 'Accounting',
    'license': 'AGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'data/server_action.xml',
        'data/cron.xml',
        'wizard/cashflow_summary_views.xml',
        'views/scb_cashflow_views.xml',
        'views/scb_bank_statement_views.xml',
        'views/scb_cashflow_config_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
}
