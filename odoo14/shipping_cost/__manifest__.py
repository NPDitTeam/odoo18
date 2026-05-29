{
    'name': 'Shipping cost ค่าขนส่ง',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'summary': 'ระบบเก็บข้อมูลค่าขนส่ง',
    'category': 'Sales',
    'depends': ['sale', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/shipping_cost_views.xml',
        'views/shipping_cost_menu.xml',
    ],
    'installable': True,
    'application': True,
}
