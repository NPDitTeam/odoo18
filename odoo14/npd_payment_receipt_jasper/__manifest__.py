{
    'name': 'ใบเสร็จรับเงินค่าขนส่ง (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Payment Receipt (Transport)',
    'description': """
        Payment Receipt Report using JasperReports.
        Converted from Odoo 14 QWeb report
        (npd_payment_receipt.form_payment_npd_pfb)
        to Odoo 18 Jasper format.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'base',
        'account',
        'jasper_reports',
        'multi_branch_management_aagam',
        'account_payment_invoice',
        'account_cheque',
        'payment_method',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
