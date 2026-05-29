{
    'name': 'Custom Cash Payment',
    'version': '18.0.1.0.0',
    'summary': 'ชำระเงินสด',
    'category': 'Accounting',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['account', 'mail', 'multi_branch_management_aagam'],
    'data': [
        'security/ir.model.access.csv',
        'views/cash_payment_views.xml',
        'data/cash_payment_sequence.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
