{
    'name': 'ใบเพิ่มหนี้ขาย (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Sales Debit Note (ใบเพิ่มหนี้ขาย)',
    'description': """
        ใบเพิ่มหนี้/ใบกำกับภาษี (Sales Debit Note) using JasperReports.
        Converted from Odoo 14 QWeb report
        (pfb_std_accounting_qweb.report_debit_invoice) to Odoo 18 Jasper.
        Model: account.move.

        - โลโก้ / ชื่อบริษัท / ที่อยู่ ดึงแบบเดียวกับใบสำคัญจ่าย
          (company_id, ที่อยู่ดึงจากสาขา branch_id ก่อน fallback บริษัท).
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
