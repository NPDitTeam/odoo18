# -*- coding: utf-8 -*-
{
    'name': "account_lvm",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
        Install this module to use list view manager functionality in  account,purchase,stock and expense module.
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '18.0.1.0.1',

    # any module necessary for this one to work correctly
    'depends': ['ks_list_view_manager','account','purchase','hr_expense','stock','sale'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],

    'assets': {'web.assets_backend':
		[
			'account_lvm/static/src/js/account_lvm_render.js',
			'account_lvm/static/src/xml/**/*',


	  ]
    },

    'post_init_hook': 'post_init_hook',
}

