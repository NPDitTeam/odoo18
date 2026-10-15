{
    "name": "NPD รับชำระ: ลูกหนี้อื่น แทนภาษีถูกหัก ณ ที่จ่าย + แนบใบหัก ณ ที่จ่าย",
    "version": "18.0.1.0.3",
    "license": "LGPL-3",
    "category": "Accounting",
    "summary": "ลูกค้าหัก ณ ที่จ่ายแต่ยังไม่ส่งใบ → บันทึกเป็นลูกหนี้อื่น แนบใบแล้วโอนเป็นภาษีถูกหัก ณ ที่จ่าย",
    "description": """
หน้ารับชำระ (Payment Information)
- ซ่อนวิธีชำระ "ภาษีเงินได้ถูกหัก ณ ที่จ่าย" ไม่ให้พนักงานเลือก ใช้ "ลูกหนี้อื่น" แทน
- ใบที่ลงบันทึกแล้วและมีลูกหนี้อื่น มีปุ่ม "เพิ่มใบหัก ณ ที่จ่าย" แนบได้หลายไฟล์ ไฟล์แก้ได้แต่ลบไม่ได้ (ลงบัญชีไปแล้ว)
- แนบครั้งแรก รายการบันทึกบัญชี (RV) เพิ่ม Dr ภาษีเงินได้ถูกหัก ณ ที่จ่าย / Cr ลูกหนี้อื่น
- สถานะ ยังไม่บันทึกไฟล์หัก ณ ที่จ่าย / บันทึกไฟล์หัก ณ ที่จ่ายแล้ว (เฉพาะใบที่มีลูกหนี้อื่น)
""",
    "author": "NPD",
    "depends": ["account_payment_invoice", "payment_method"],
    "data": [
        "security/ir.model.access.csv",
        "data/payment_method_data.xml",
        "views/account_payment_views.xml",
        "wizard/wht_file_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
