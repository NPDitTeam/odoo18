{
    'name': 'ใบเสร็จรับเงิน (ยังไม่ได้รับเงิน) (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Receipt - Not Yet Received (Pre-Receipt)',
    'description': """
        Pre-Receipt (RV) Report using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_npd_accounting_qweb.report_no_receipt_invoice)
        to Odoo 18 Jasper format.
        Iterates account.payment.custom_invoice_ids → move_id → invoice_line_ids.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'base',
        'account',
        'jasper_reports',
        'multi_branch_management_aagam',
        'account_payment_invoice',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
