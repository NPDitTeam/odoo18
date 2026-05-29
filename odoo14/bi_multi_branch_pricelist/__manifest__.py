# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Multi Branch for Pricelists Odoo App',
    'version': '18.0.0.0.1',
    'license': 'LGPL-3',
    'category': 'Sales',
    'summary': 'Multi Branch for pricelist',
    'author': 'BrowseInfo',
    'website': 'https://www.browseinfo.in',
    'depends': ['multi_branch_management_aagam', 'product'],
    'data': [
        'views/product_pricelist_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
