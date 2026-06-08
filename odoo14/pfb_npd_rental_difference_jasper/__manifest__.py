{
    'name': 'ใบแจ้งหนี้ค่าเช่าส่วนต่าง (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Rental Difference Invoice',
    'description': """
        ใบแจ้งหนี้ค่าเช่าส่วนต่าง (Rental Difference Invoice) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_npd_rental_difference_qweb.report_tax_invoice) to Odoo 18 Jasper.
        Model: account.move.

        - โลโก้ / ชื่อบริษัท / ที่อยู่สาขา ดึงแบบเดียวกับ jasper ใบลดหนี้
          (pfb_npd_debt_reduction_jasper).
        - รูป QR และชื่อบริษัทสำหรับสั่งจ่ายเช็ค เลือกตาม company_registry
          (ID บริษัท) แทนการเช็คจากชื่อ database แบบ odoo14.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'base',
        'account',
        'jasper_reports',
        'l10n_th_partner',
        'multi_branch_management_aagam',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
