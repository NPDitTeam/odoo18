{
    'name': 'Payment Slip Date AI',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'AI-powered date extraction from payment slips',
    'description': 'ใช้ AI (Gemini) อ่านวันที่จากสลิปการโอนเงินที่แนบในเอกสารแนบ แล้วเติมค่าลงในฟิลด์วันที่ '
                   '(พอร์ตจาก Odoo 14 รุ่นล่าสุดใน git — รวมแก้ thinking กินโควตาจนอ่านสลิปไม่ได้)',
    'author': 'NPD Dev',
    'license': 'AGPL-3',
    'depends': ['base', 'account', 'account_payment_invoice'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'views/account_payment_view.xml',
        'views/res_users_view.xml',
        'views/res_company_view.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
