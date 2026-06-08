{
    'name': 'ใบแจ้งหนี้ขาย/ใบกำกับภาษี (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Sales Tax Invoice (ใบแจ้งหนี้ขาย/ใบกำกับภาษี)',
    'description': """
        ใบแจ้งหนี้ขาย/ใบกำกับภาษี (Sales Tax Invoice / Delivery) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_std_accounting_qweb.report_tax_invoice) to Odoo 18 Jasper.
        Model: account.move.

        รูปแบบเหมือนใบแจ้งหนี้ค่าเช่าส่วนต่าง (pfb_npd_rental_difference_jasper):
        - logo / ชื่อบริษัท / ที่อยู่ ดึงจากสาขา (branch_id) ก่อน fallback บริษัท
        - QR + ชื่อบริษัทสำหรับสั่งจ่ายเช็ค เลือกตาม company_registry
        - ไม่มีคอลัมน์รหัสสินค้า, ตัด [รหัส] หน้าชื่อสินค้า
        Reuses computed fields (jasper_rd_*) from pfb_npd_rental_difference_jasper.
        ต่างจากใบค่าเช่าส่วนต่าง: หัวเรื่อง "ใบส่งสินค้า", ชื่อบริษัทไม่มี (สำนักงานใหญ่),
        ยอดรวมไม่มีภาษีหัก ณ ที่จ่าย.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'account',
        'jasper_reports',
        'pfb_npd_rental_difference_jasper',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
