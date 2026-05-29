{
    'name': 'ใบกำกับภาษี - ใบรับเงิน (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Tax Invoice from Payment',
    'description': """
        Tax Invoice Report using JasperReports, printed from account.payment.
        Converted from Odoo 14 QWeb report
        (pfb_npd_payment_tax_invoice.tax_invoice_payment_npd_pfb)
        to Odoo 18 Jasper format.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'base',
        'account',
        'jasper_reports',
        'multi_branch_management_aagam',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
