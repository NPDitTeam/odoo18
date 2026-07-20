{
    'name': 'ใบส่ง/รับ/ตรวจคุณภาพสินค้า (QC Checklist) - Jasper',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report สำหรับใบส่ง/รับ/ตรวจคุณภาพสินค้า (QC Checklist) บน vehicle.booking',
    'description': """
        ใบส่ง/รับ/ตรวจคุณภาพสินค้า (QC Checklist)
        - พิมพ์จากเอกสารจองคิวรถขนส่ง (vehicle.booking)
        - รายการสินค้าดึงจาก transport.order.line (แท็บ "รายการสินค้า")
        - เที่ยวส่งเลขที่ ใช้เลขรันเอกสารของใบจองรถ (vehicle.booking.name)
        - รองรับการพิมพ์หลายหน้าเมื่อรายการสินค้ามีจำนวนมาก
    """,
    'author': 'NPD',
    'category': 'Inventory',
    'depends': [
        'base',
        'jasper_reports',
        'transport_booking',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
