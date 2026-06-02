{
    'name': 'Custom Shipping Invoice',
    'version': '18.0.1.0.0',
    'summary': 'Add shipping cost button and invoice integration',
    'author': 'NPD',
    'category': 'Sales',
    'license': 'AGPL-3',
    'depends': [
        'sale',
        'account',
        'base',
        'pfb_npd_tap_shipment_information',
        'sale_api_rent',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/popup_shipping_invoice_rules.xml',
        'views/sale_order_view.xml',
        'views/popup_shipping_invoice.xml',
    ],
    'installable': True,
    'application': False,
}
