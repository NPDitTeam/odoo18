{
    "name": "SO Add Product by Category with Stock",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "summary": "Add products from category with stock info to Sale Order Line",
    "category": "Sales",
    "depends": ["sale", "product", "stock", "pfb_npd_add_date_quatation_order"],
    "data": [
        'security/ir.model.access.csv',
        "views/sale_order_view.xml",
        "views/product_category_wizard_view.xml",
    ],
    "installable": True,
    "application": False,
}
