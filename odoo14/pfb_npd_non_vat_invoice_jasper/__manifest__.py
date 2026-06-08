{
    'name': 'ใบแจ้งหนี้ขาย (Non Vat) (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Sales Invoice Non-VAT (ใบแจ้งหนี้ขาย Non Vat)',
    'description': """
        ใบแจ้งหนี้ขาย (Non Vat) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_std_accounting_qweb.report_non_vat_invoice) to Odoo 18 Jasper.
        Model: account.move.

        รูปแบบเหมือนใบเพิ่มหนี้ขาย (pfb_npd_debit_invoice_jasper) ต่างที่หัวเรื่อง "ใบส่งสินค้า".
        Reuses the computed fields (jasper_dn_*) from pfb_npd_debit_invoice_jasper.
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'account',
        'jasper_reports',
        'pfb_npd_debit_invoice_jasper',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
