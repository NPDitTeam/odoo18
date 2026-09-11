{
    'name': 'จองคิวรถขนส่ง',
    'version': '18.0.2.8.0',  # คลิกรูปก่อนขนส่ง/หลักฐานการส่ง เพื่อดูรูปเต็ม (widget image_popup)
    'category': 'Operations/Inventory',
    'summary': 'ระบบจองคิวรถขนส่ง พร้อมแสดงเส้นทางบน Google Maps และติดตามรถ Real-time',
    'depends': [
        'base',
        'fleet',
        'transport_sync',
        'vehicle_registration',
        'vehicle_tracking',  # เชื่อมโยงกับระบบติดตามรถ GPS
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/vehicle_booking_views.xml',
        'views/res_users_settings_views.xml',
        'views/tracking_settings_views.xml',
        'views/vehicle_tracking_views.xml',
        'views/delivery_history_views.xml',
        'views/delivery_rating_views.xml',
        'views/rating_templates.xml',
        'views/tracking_map_template.xml',
        'views/tracking_map_food_delivery.xml',  # 🍔 Food Delivery Style Template
        'views/res_users_views.xml'
        # 'views/tracking_map_realtime_views.xml',  # ปิดการใช้งานแผนที่ Real-time
    ],
    'assets': {
        'web.assets_backend': [
            'transport_booking/static/src/css/google_maps.css',
            'transport_booking/static/src/css/vehicle_tracking.css',
            'transport_booking/static/src/css/image_popup_field.css',
            'transport_booking/static/src/js/location_autocomplete_widget.js',
            'transport_booking/static/src/js/google_maps_widget.js',
            'transport_booking/static/src/js/image_popup_field.js',
            'transport_booking/static/src/js/vehicle_tracking_widget.js',
            'transport_booking/static/src/js/copyable_url_field.js',
            'transport_booking/static/src/js/vehicle_tracking_auto_refresh.js',  # ✅ Auto-refresh tracking list จากฐานข้อมูล
            'transport_booking/static/src/xml/google_maps_templates.xml',
            'transport_booking/static/src/xml/image_popup_field.xml',
            'transport_booking/static/src/xml/vehicle_tracking_templates.xml',
            'transport_booking/static/src/xml/copyable_url_field.xml',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'license': 'LGPL-3',
}
