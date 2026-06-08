{
    'name': 'ใบสำคัญจ่าย (สด) (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Cash Payment Voucher (ใบสำคัญจ่าย (สด))',
    'description': """
        ใบสำคัญจ่าย (สด) (Cash Payment Voucher) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_npd_journal_voucher_qweb.payment_voucher_cash_pdf) to Odoo 18 Jasper.
        Model: account.move.

        Reuses the computed fields (jasper_jv_*) from pfb_npd_journal_voucher_jasper.
        Differences from ใบสำคัญจ่าย:
        - หัวเรื่อง "ใบสำคัญจ่าย (สด)"
        - ตัวเลขเดบิต/เครดิต แสดง 4 ตำแหน่งทศนิยม
        - ลายเซ็น 3 คอลัมน์ (ผู้รับเงิน / ผู้จัดทำ / ผู้มีอำนาจอนุมัติ)
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'account',
        'jasper_reports',
        'pfb_npd_journal_voucher_jasper',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
