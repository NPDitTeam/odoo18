{
    "name": "Chatter Position (Bottom/Side)",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "category": "Technical",
    "summary": "Allow users to choose chatter position: bottom or side",
    "depends": ["mail", "web"],
    "data": [
        "views/res_users_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_chatter_position/static/src/js/chatter_position.js",
            "web_chatter_position/static/src/xml/chatter_position.xml",
        ],
    },
    "installable": True,
    "auto_install": False,
}
