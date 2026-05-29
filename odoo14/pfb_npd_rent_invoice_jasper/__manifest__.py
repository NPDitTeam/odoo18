{
    'name': 'ใบกำกับการเช่า (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Rental Invoice Form',
    'description': """
        Rental Invoice Report using JasperReports.
        Converted from Odoo 14 QWeb report (pfb_npd_sale_form_rent_invoice)
        to Odoo 18 Jasper format.
    """,
    'author': 'NPD',
    'category': 'Sales',
    'depends': [
        'base',
        'sale',
        'jasper_reports',
        'pfb_npd_all_customs',
        'pfb_npd_add_date_quatation_order',
        'pfb_npd_tap_shipment_information',
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
