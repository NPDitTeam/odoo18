{
    'name': 'ใบเสร็จรับเงิน ค่าประกัน/ค่าปรับชำรุด/ค่าปรับหาย (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper receipts for deposit, damaged penalty and lost penalty payments',
    'description': """
แปลงจาก Odoo 14 QWeb เป็น Jasper พิมพ์จากหน้ารับชำระ 3 แบบฟอร์ม

* ใบเสร็จรับเงิน(ค่าประกัน)               = pfb_npd_receipt (A5 นอน)
* ใบเสร็จรับเงิน(ค่าปรับชำรุด)             = pfb_npd_payment_damaged (A5 นอน)
* ใบกำกับภาษี/ใบเสร็จรับเงิน(ค่าปรับหาย)   = pfb_npd_payment_disappeared (A4 ตั้ง ไล่รายการสินค้า)

หัวกระดาษ / ข้อมูลลูกค้า / ช่องวิธีชำระเงิน / ลายเซ็น ใช้ฟิลด์ร่วมกับใบเสร็จรับเงินค่าขนส่ง
(npd_payment_receipt_jasper) ส่วนเลขที่ใบกำกับการเช่า ยอดเงิน และรายการสินค้าคำนวณในโมดูลนี้
""",
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'npd_payment_receipt_jasper',
        'l10n_th_amount_to_text',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
