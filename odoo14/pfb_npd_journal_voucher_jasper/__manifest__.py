{
    'name': 'ใบสำคัญจ่าย (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Payment Voucher (ใบสำคัญจ่าย)',
    'description': """
        ใบสำคัญจ่าย (Payment Voucher) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_std_journal_voucher_qweb.payment_voucher_pdf) to Odoo 18 Jasper.
        Model: account.move.

        - โลโก้ / ชื่อบริษัท / ที่อยู่ ดึงตามบริษัทที่เลือก (company_id) แบบ odoo18.
        - ตารางหลัก: รายการบันทึกบัญชี (วน line_ids แสดง รหัส/ชื่อบัญชี/เดบิต/เครดิต).
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'base',
        'account',
        'jasper_reports',
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
