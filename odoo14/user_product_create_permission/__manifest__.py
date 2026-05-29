{
    'name': 'User Product Create Permission',
    'version': '18.0.1.0.1',
    'category': 'Administration',
    'summary': 'Control user permission to create products',
    'license': 'LGPL-3',
    'depends': ['base', 'product'],
    'data': [
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
}
