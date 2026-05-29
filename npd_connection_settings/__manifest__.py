{
    'name': 'NPD Connection Settings',
    'version': '1.0',
    'category': 'Settings',
    'description': 'Manage Odoo connection settings for external applications',
    'author': 'NPD Solutions',
    'depends': ['base', 'web'],
    'data': [
        'security/ir_model_access.xml',
        'views/connection_views.xml',
        'views/menu_items.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}