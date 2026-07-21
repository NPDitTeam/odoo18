{
    'name': u'ใบส่งมอบสินค้า (Jasper)',
    'version': '18.0.1.0.0',
    'summary': u'Jasper Report สำหรับใบส่งมอบสินค้า (Delivery Note)',
    'description': """
        Delivery Note report using JasperReports.
        Ported from Odoo 14 QWeb module (pfb_npd_sale_form_delivery_note).
        ใช้โครงและฟิลด์ jasper_* ร่วมกับใบกำกับการเช่า (pfb_npd_rent_invoice_jasper)
        - เลขที่ใบส่งมอบสินค้า RDO-yymmdd+ลำดับ (ir.sequence) สร้างเมื่อยืนยันใบขายเช่า
        - เงื่อนไข 3 ข้อ (ผู้ตรวจรับสินค้า) และลายเซ็น 3 ช่อง
    """,
    'author': 'NPD',
    'category': 'Sales',
    'depends': [
        'base',
        'sale',
        'jasper_reports',
        'pfb_npd_rent_invoice_jasper',
        'pfb_npd_rental_equipment_contract_jasper',
    ],
    'data': [
        'data/ir_sequence.xml',
        'views/sale_order_view.xml',
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
