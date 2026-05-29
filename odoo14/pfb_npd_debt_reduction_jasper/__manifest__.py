{
    'name': 'ใบลดหนี้ (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Credit Note (Debt Reduction)',
    'description': """
        Credit Note (ใบลดหนี้) Report using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_npd_debt_reduction.form_debt_reduction_npd_pfb)
        to Odoo 18 Jasper format.
        Model: account.move (move_type=out_refund/in_refund).
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
