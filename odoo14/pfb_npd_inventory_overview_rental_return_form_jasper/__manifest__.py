{
    'name': 'ใบคืนการเช่า (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Rental Return Form',
    'description': """
        Rental Return Form Report using JasperReports.
        Converted from Odoo 14 QWeb report (pfb_npd_inventory_overview_rental_return_form)
        to Odoo 18 Jasper format.
    """,
    'author': 'NPD',
    'category': 'Inventory',
    'depends': [
        'base',
        'stock',
        'sale',
        'sale_stock',
        'jasper_reports',
        'pfb_npd_all_customs',
        'pfb_npd_add_date_quatation_order',
        'pfb_npd_add_date_stock_picking',
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
