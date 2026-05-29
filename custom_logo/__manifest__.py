# -*- coding: utf-8 -*-
{
    'name': 'Custom Logo',
    'version': '18.0.1.0.0',
    'summary': 'เปลี่ยนโลโก้หน้า Database Selector และ Login',
    'category': 'Customization',
    'author': 'Custom',
    'depends': ['web'],
    'data': [],
    'assets': {
        'web.assets_frontend': [
            'custom_logo/static/src/css/custom_logo.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}