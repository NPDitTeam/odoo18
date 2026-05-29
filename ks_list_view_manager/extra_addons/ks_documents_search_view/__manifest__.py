# -*- coding: utf-8 -*-
{
    'name': "ks_documents_search_view",

    'summary': "Search View addition for documents module",

    'description': """
        Install this module to use list view manager functionality in documents module.
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '18.0.1.0.0',

    # any module necessary for this one to work correctly
    'depends': ['ks_list_view_manager','account_lvm','accountant_reconsile','documents'],

    # always loaded
    'data': [
    ],
    'demo': [
    ],

    'assets': {'web.assets_backend':
		[
			'ks_documents_search_view/static/src/js/ks_documents_search_view.js',
			'ks_documents_search_view/static/src/xml/ks_documents_search_view.xml',
	  ]
    },

}

