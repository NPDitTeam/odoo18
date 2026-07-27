{
    "name": "Account Payment Sequence",
    "version": "18.0.1.1.0",
    "license": "LGPL-3",
    "category": "Accounting",
    "summary": "Custom sequence for payments",
    # account_journal_sequences เป็นตัวเพิ่มประเภทสมุดรายวัน receivable/payable
    # ที่โมดูลนี้เปิดให้ใช้กับ account.payment
    "depends": ["account", "account_journal_sequences"],
    "data": [
        "data/ir_sequence_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
