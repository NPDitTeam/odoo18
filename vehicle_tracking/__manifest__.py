# -*- coding: utf-8 -*-
{
    'name': 'Vehicle Tracking',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Real-time Vehicle GPS Tracking System',
    'description': """
        Vehicle Tracking Module
        =======================
        * Track vehicles in real-time using GPS data
        * Display vehicle locations on interactive map
        * Monitor vehicle status, speed, mileage
        * Integration with DistarGPS API
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/vehicle_tracking_views.xml',
        'views/vehicle_map_template.xml',
        'views/menu_views.xml',
    ],
    # 'assets': {
    #     'web.assets_backend': [
    #         'vehicle_tracking/static/src/js/map_widget.js',
    #     ],
    # },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
