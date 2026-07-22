{
    'name': u'ใบสั่งซื้อ (Jasper)',
    'version': '18.0.1.0.0',
    'summary': u'Jasper Report สำหรับใบสั่งซื้อ (Purchase Order)',
    'description': """
        Purchase Order report using JasperReports.
        Ported from Odoo 14 QWeb module (npd_npd_po_qweb).
        - หัวข้อ font 16, รายละเอียดอื่น ๆ font 13
        - ตาราง 7 คอลัมน์ (ลำดับ/รายการ/จำนวน/หน่วย/ราคาต่อหน่วย/ส่วนลด%/ราคารวม)
        - ยอดรวม + จำนวนเงินเป็นตัวอักษร (baht text) + ลายเซ็น 3 ช่อง (ผู้จัดทำ/ผู้ตรวจสอบ/ผู้อนุมัติ)
    """,
    'author': 'NPD',
    'category': 'Purchases',
    'depends': [
        'base',
        'purchase',
        'jasper_reports',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
