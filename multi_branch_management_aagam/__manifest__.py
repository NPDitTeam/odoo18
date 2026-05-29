# -*- coding: utf-8 -*-
{
    'name' : 'Multiple Branch Operations Management, Branchwise Sales, Orders, Quotations, Purchase, Inventory Management',
    'version' : '18.0.0.0.4',
    'summary': 'Multiple Branch Management POS Multi Branch Sales Multi branch management CRM Multiple location manage multiple operating unit multiple warehouse branch multi branch app multiple Unit Operations Account cashflow Reports',
    'sequence': 15,
    'description': """
Multiple Branches
====================
The specific and easy-to-use multi branch system that allows you to keep track of your branches, even when you are not an admin. It provides an easy way to follow up on your vendors and customers.

    """,
    'category': 'Branch Management',   
    'images' : [],
    'depends' : ['base_setup','base', 'point_of_sale', 'stock', 'account', 'purchase', 'sale_management', ],
    'data': [
        'data/ir_module_category.xml',
        # 'security/branch_security.xml',
        'security/ir.model.access.csv',
        'wizard/view_branch_warehouse.xml',
        'views/branch_view.xml',
        'security/branch_group_security.xml',
        'views/res_users_inherite.xml',
        'views/customer_inherit_view.xml',
        'views/product_template_inherit_view.xml',
        'views/sale_order_inherit_view.xml',
        'views/stock_picking_inherit.xml',
        'views/invoice_view_inherit.xml',
        'views/purchase_order_inherit_view.xml',
        'views/stock_warehouse_inherite_view.xml',
        'views/stock_location_inherit_view.xml',
        # 'views/stock_inventory_view_inherit.xml', stock invery not exist in odoo 17
        'views/pos_config_view_inherit.xml',
        'views/pos_session_view_inherit.xml',
        'views/pos_order_view_inherit.xml',
        'views/pos_payment_view_inherit.xml',

        'views/account_move_line.xml',
        'views/account_view.xml',

        'report/cash_flow_pdf_template.xml',
        'report/cash_flow_print_report.xml',

        'wizard/cash_flow_account_wizard.xml',



        # 'report/report_account_cashflow_report.xml',
        # 'report/report_menu.xml',
        # 'wizard/account_cashflow_report.xml',
         #seperate menu not needed

    ],
    'demo': [],
    'post_init_hook': 'post_init_hook',


    'auto_install': False,    
    'license': 'OPL-1',
    'price': 88,
    'currency': 'USD',
    'support': 'business@aagaminfotech.com',
    'author': 'Aagam Infotech',
    'website': 'https://www.aagaminfotech.com',
    'images': ['static/description/images/Multiple_Branch_Management.gif'],
    'installable': True,    
}
