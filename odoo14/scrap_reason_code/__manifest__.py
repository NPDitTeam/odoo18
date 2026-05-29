{
    "name": "Scrap Reason Code",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "summary": "Reason code for scrapping",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "category": "Warehouse Management",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/reason_code_view.xml",
        "views/stock_scrap_views.xml",
        "views/stock_move_views.xml",
    ],
    "installable": True,
}
