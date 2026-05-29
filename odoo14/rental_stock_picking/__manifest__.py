{
    'name': 'Rental Stock Picking Extension',
    'version': '18.0.1.0.0',
    'category': 'Stock',
    'summary': 'Add user permission for editing force date in stock picking',
    'license': 'LGPL-3',
    'depends': ['stock', 'base'],
    'data': [
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
}
