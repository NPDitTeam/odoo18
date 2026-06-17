{
    'name': 'Custom Cash Payment',
    'version': '18.0.1.0.0',
    'summary': 'ชำระเงินสด',
    'category': 'Accounting',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['account', 'mail', 'account_payment_invoice', 'multi_branch_management_aagam'],
    'data': [
        'security/ir.model.access.csv',
        'security/cash_payment_security.xml',
        'views/cash_payment_views.xml',
        'views/res_users_view.xml',
        'data/cash_payment_sequence.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
