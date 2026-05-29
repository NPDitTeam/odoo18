{
    'name': 'ใบเสนอราคาเช่าสินค้า (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Rental Quotation Form',
    'description': """
        Rental Quotation Report using JasperReports.
        Converted from Odoo 14 QWeb report (pfb_npd_sale_form_rental_quatation)
        to Odoo 18 Jasper format.
    """,
    'author': 'NPD',
    'category': 'Sales',
    'depends': [
        'base',
        'sale',
        'jasper_reports',
        'pfb_npd_all_customs',              # pfb_amount, pfb_amount_insurance, pfb_dis_amount_insurance, pfb_date_of_rent, pfb_quantity, pfb_insurance_price, second_uom_qty
        'pfb_npd_add_date_quatation_order',  # on_site
        'pfb_npd_tap_shipment_information',  # shipping_cost
        'multi_branch_management_aagam',     # branch_id (res.users)
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
