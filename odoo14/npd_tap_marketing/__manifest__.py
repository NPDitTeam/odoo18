{
    'name': 'เพิ่มแท็บการตลาดในใบสั่งขาย',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'summary': 'เพิ่มแท็บ Marketing ใน Sale Order พร้อมช่องทางลูกค้า',
    'category': 'Sales',
    'author': 'NPD',
    'depends': ['sale', 'utm'],
    'data': [
        'security/ir.model.access.csv',
        'data/customer_channel_data.xml',
        'views/customer_channel.xml',
        'views/sale_order.xml',
    ],
    'installable': True,
    'application': False,
}
