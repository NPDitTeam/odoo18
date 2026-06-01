# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Sale Api Rent",
    "version": "18.0.1.0.0",
    "author": "NPD",
    "category": "Sales",
    "summary": "ดึงข้อมูลการเช่าจากบริษัทอื่น (popup) มายังใบสั่งขายของบริษัท เอ็นพีดี โลจิสติกส์ ภายในฐานข้อมูลเดียวกัน",
    "license": "AGPL-3",
    "depends": [
        "sale",
        "base",
        "pfb_npd_tap_shipment_information",
        "pfb_npd_all_customs",
        "sale_isolated_quotation",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/fetch_rental_wizard_views.xml",
        "views/sale_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
