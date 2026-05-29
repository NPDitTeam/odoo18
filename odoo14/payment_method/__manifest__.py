{
    "name": "Payment Method",
    "version": "18.0.1.0.0",
    "author": "Perfect Blending",
    "website": "https://www.perfectblending.com",
    "license": "AGPL-3",
    "category": "Accounting",
    "summary": "Custom Payment Method for voucher and payment",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "security/payment_method_security.xml",
        "views/payment_method_view.xml",
    ],
    "installable": True,
}
