# -*- coding: utf-8 -*-
{
    "name": "Account Payment WHT Flag",
    "summary": "เพิ่มช่องติ๊ก 'ใบหัก ณ ที่จ่าย' ในแบบฟอร์ม account.payment (ค่าเริ่มต้นไม่ติ๊ก)",
    "version": "18.0.1.0.0",
    "author": "NPD Dev",
    "website": "",
    "license": "AGPL-3",
    "depends": ["account", "account_payment_invoice"],
    "data": [
        "views/account_payment_view.xml",
    ],
    "installable": True,
    "application": False,
}
