{
    'name': 'ใบลดหนี้ขาย (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Sales Credit Note (ใบลดหนี้ขาย)',
    'description': """
        ใบลดหนี้/ใบกำกับภาษี (Sales Credit Note) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_std_accounting_qweb.report_credit_invoice) to Odoo 18 Jasper.
        Model: account.move.

        รูปแบบเหมือนใบเพิ่มหนี้ขาย ต่างที่หัวเรื่อง "ใบลดหนี้/ใบกำกับภาษี".
        Reuses the computed fields (jasper_dn_*) from pfb_npd_debit_invoice_jasper.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'account',
        'jasper_reports',
        'pfb_npd_debit_invoice_jasper',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
