{
    'name': 'Stock Picking Rent Discount & Approval',
    'version': '18.0.1.0.0',
    'summary': 'Add rental discount and approval process in Stock Picking',
    'category': 'Stock',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/rent_discount_wizard_view.xml',
        'views/approval_picking_wizard_view.xml',
        'views/request_picking_approval_wizard_view.xml',
        'views/stock_picking_view.xml',
    ],
    'installable': True,
    'application': False,
}
