{
    'name': 'ใบกำกับภาษี/ใบเสร็จรับเงิน ค่าเช่า (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper rent receipts: tools rental, scaffold rental, place rental',
    'description': """
แปลงจาก Odoo 14 QWeb เป็น Jasper พิมพ์จากหน้ารับชำระ 3 แบบฟอร์ม

* ใบกำกับภาษี/ใบเสร็จรับเงิน (pfb_npd_payment_form_receipt) — ค่าเช่าเครื่องมือก่อสร้าง
* ใบกำกับภาษี/ใบเสร็จรับเงิน ค่าเช่าทรัพย์สิน (pfb_npd_payment_form_receipt_scaffold) — ค่าเช่านั่งร้าน (เอกสารออกเป็นชุด)
* ใบเสร็จรับเงินค่าเช่าที่ (pfb_npd_payment_form_receipt_place_rent) — ค่าเช่าสถานที่

หัวกระดาษ / ข้อมูลลูกค้า / ช่องวิธีชำระเงิน ใช้ฟิลด์ร่วมกับใบเสร็จรับเงินค่าขนส่ง (npd_payment_receipt_jasper)
ยอดเงินแยก VAT ตามสัดส่วนใบแจ้งหนี้ที่ตัดชำระ และภาษีหัก ณ ที่จ่าย 5% เฉพาะลูกค้านิติบุคคลที่ยังไม่ได้รับใบหัก
""",
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'npd_payment_receipt_jasper',   # หัวกระดาษ/ลูกค้า/วิธีชำระเงิน/ลายเซ็น (jasper_*)
        'account_payment_wht_flag',     # wht_has_slip
        'l10n_th_amount_to_text',       # จำนวนเงินตัวอักษรภาษาไทย
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
