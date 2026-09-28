{
    "name": "Custom Payment Popup",
    "version": "18.0.1.1.0",
    "license": "LGPL-3",
    "category": "Accounting",
    "summary": "ปุ่มชำระเงินบนใบแจ้งหนี้ + กฎเลือกสมุดรายวันฝั่งรับชำระ",
    "depends": ["account", "account_payment_invoice", "account_payment_sequence"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_move_view.xml",
        "views/payment_journal_rule_views.xml",
    ],
    "installable": True,
}
