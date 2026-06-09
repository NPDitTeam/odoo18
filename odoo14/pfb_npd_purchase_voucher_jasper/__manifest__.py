{
    'name': 'ใบสำคัญซื้อ (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Purchase Voucher (ใบสำคัญซื้อ)',
    'description': """
        ใบสำคัญซื้อ (Purchase Voucher) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_npd_journal_voucher_qweb.vendors_bills_pdf) to Odoo 18 Jasper.
        Model: account.move.

        รูปแบบเหมือนใบสำคัญจ่าย (pfb_npd_journal_voucher_jasper) ต่างที่:
        - หัวเรื่อง "ใบสำคัญซื้อ"
        - ตัด section รายการจ่ายชำระ / payment method / ภาษีหัก ณ ที่จ่าย ออก
        - เพิ่ม section รายละเอียดภาษี (จาก tax_invoice_ids)
        logo/company name/address ดึงแบบเดียวกับใบสำคัญจ่าย (company_id, branch-first).
        Reuses computed fields (jasper_jv_*) from pfb_npd_journal_voucher_jasper.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'account',
        'jasper_reports',
        'l10n_th_account_tax',
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
