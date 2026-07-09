{
    'name': 'SO Auto Stock Cut',
    'version': '18.0.1.0.0',
    'summary': 'Auto reserve and validate stock picking (cut/return) from sale order using pfb_quantity.',
    'category': 'Sales',
    'author': 'ChatGPT',
    'license': 'LGPL-3',
    'depends': ['sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_view.xml',
        'views/stock_confirm_wizard_view.xml',
        'views/stock_picking_view.xml',
    ],
    'installable': True,
    'auto_install': False,
}
