{
    'name': 'PFB NPD : Shipment Information',
    'version': '18.0.1.0.0',
    'author': 'PP',
    'license': 'AGPL-3',
    'category': 'Sale',
    'depends': ['sale', 'web', 'shipping_cost', 'fleet_license_plate'],
    'data': [
        'views/sale_order.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pfb_npd_tap_shipment_information/static/src/js/autocomplete.js',
            'pfb_npd_tap_shipment_information/static/src/js/autocomplete.xml',
        ],
    },
    'installable': True,
}
