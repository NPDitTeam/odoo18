{
    'name': 'NPD: ยกเลิกเอกสารด้วยการกลับรายการบัญชี',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'category': 'Accounting',
    'summary': 'เอกสารที่ลงบัญชีแล้วรีเซตเป็นฉบับร่างไม่ได้ ยกเลิกแล้วกลับขาบัญชี (Reverse) แทน เลขรายการบัญชีไม่ข้าม',
    'description': """
เดิมหลายโมดูลยกเลิก/รีเซตเอกสารด้วยการลบรายการบัญชี หรือทิ้งรายการเดิมค้างเป็นร่าง
แล้วยืนยันใหม่ได้เลขใหม่ ทำให้เลข JV ข้าม

โมดูลนี้

* ยกเลิกเอกสาร = สร้างรายการกลับขาบัญชีในสมุดเดียวกัน ผูกกับรายการเดิม รายการเดิมยังลงบัญชีอยู่
* เอกสารที่ลงบัญชีแล้วรีเซตเป็นฉบับร่างไม่ได้ ต้องทำใบใหม่
* รายการบัญชีของเอกสารเหล่านี้ กดรีเซต/ยกเลิกที่หน้ารายการบัญชีไม่ได้

ครอบคลุม ใบรับชำระ, ใบสำคัญ/คืนเงินประกัน, Advance Clear, รับชำระเงินสด, โอนคืนเงินลูกค้า, รายการค่าเสื่อม
""",
    'depends': [
        'account',
        'account_payment_invoice',
        'account_payment_sequence',
        'npd_cancel_period_lock',
        'account_voucher_npd',
        'account_advance',
        'advance_clear_ai_check',
        'custom_cash_payment',
        'custom_refund_payment',
        'account_asset_management',
    ],
    'data': ['views/views.xml'],
    'installable': True,
}
