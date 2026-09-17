{
    'name': 'ใบแจ้งหนี้/ใบวางบิล (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Invoice / Billing Note',
    'description': """
        Invoice / Billing Note report using JasperReports.
        Converted from Odoo 14 QWeb report (pfb_npd_sale_form_Billing_sheet)
        to Odoo 18 Jasper format (สูตรตาม o14 commit a30b9d59).
    """,
    'author': 'NPD',
    'category': 'Sales',
    'depends': [
        'base',
        'sale',
        'jasper_reports',
        # pfb_amount, deposit_ref, pfb_date_of_rent
        'pfb_npd_all_customs',
        # start_rent_date, end_rent_date
        'pfb_npd_add_date_quatation_order',
        'multi_branch_management_aagam',
        # จำนวนเงินเป็นตัวอักษรไทย (เครื่อง o18 ไม่มีไลบรารี bahttext)
        'l10n_th_amount_to_text',
        # ช่องติ๊ก "ใช้ภาษีหัก ณ ที่จ่ายใบแจ้งหนี้/ใบวางบิล หัก 5%" (use_wht_billing_sheet)
        'custom_invoice_date',
    ],
    'data': [
        'views/res_company_views.xml',
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
