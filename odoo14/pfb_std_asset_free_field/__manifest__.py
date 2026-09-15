{
    "name": "PFB Standard : Asset Free Field And Sequences",
    "summary": """Asset Sequences""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "development_status": "Beta",
    "author": "Thatsawan",
    'website': 'https://www.perfectblending.com/',
    # o14 ใช้ hr.employee / stock.location โดยไม่ได้ประกาศ depends ไว้ (บังเอิญติดตั้งอยู่แล้ว)
    "depends": ["account_asset_management", "pfb_asset_qrcode", 'product',
                'purchase', 'hr', 'stock',
                ],
    "data": [
        "security/ir.model.access.csv",
        "views/account_asset_free_field_view.xml",
        "views/account_condition_type.xml",
        'views/product.xml',
    ],
    "installable": True,
}
