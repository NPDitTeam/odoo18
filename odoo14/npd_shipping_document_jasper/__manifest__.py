{
    'name': 'ใบขนส่งสินค้า (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper Report for Shipping Document on stock.picking',
    'description': """
        ใบขนส่งสินค้า (Shipping Document) using JasperReports on stock.picking.
        Converted from Odoo 14 QWeb report (npd_shipping_document_form)
        to Odoo 18 Jasper format. Footer prints on the LAST page only
        (lastPageFooter). Same font as npd_payment_receipt_jasper (Sarabun).
    """,
    'author': 'NPD',
    'category': 'Inventory',
    'depends': [
        'base',
        'stock',
        'sale',
        'jasper_reports',
        'pfb_npd_tap_shipment_information',
        'pfb_npd_all_customs',
        'sale_api_rent',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
