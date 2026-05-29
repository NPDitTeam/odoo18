{
    'name': 'User Branch Filter Setting',
    'version': '18.0.1.0.0',
    'category': 'Settings',
    'summary': 'Add user setting to bypass branch filter in account.move',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'multi_branch_management_aagam'],
    'data': [
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
}
