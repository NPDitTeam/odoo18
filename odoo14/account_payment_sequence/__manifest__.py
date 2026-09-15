{
    "name": "Account Payment Sequence",
    "version": "18.0.1.2.0",
    "license": "LGPL-3",
    "category": "Accounting",
    "summary": "Custom sequence for payments",
    # account_journal_sequences เป็นตัวเพิ่มประเภทสมุดรายวัน receivable/payable
    # ที่โมดูลนี้เปิดให้ใช้กับ account.payment
    # psn_journal_sequence ออกเลขรายการบันทึกบัญชีตาม sequence ของสมุดรายวัน (RV-/PV-)
    # npd_sequence_auto_year_range สร้างช่วงรายวันรูปแบบเดิมให้เอกสารย้อนหลัง/ปีใหม่
    "depends": ["account", "account_journal_sequences", "psn_journal_sequence",
                "npd_sequence_auto_year_range"],
    "data": [
        "data/ir_sequence_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
