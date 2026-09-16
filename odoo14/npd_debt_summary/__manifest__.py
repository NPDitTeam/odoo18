# -*- coding: utf-8 -*-
{
    'name': 'รวมหนี้ลูกค้า (NPD Debt Summary)',
    'version': '18.0.1.0.0',
    'summary': 'สรุปหนี้ลูกค้า - สแกนลูกค้าที่มีใบแจ้งหนี้ค้างชำระอัตโนมัติ + หนังสือทวงถาม',
    'description': """
        รวมหนี้ลูกค้า (Customer Debt Summary) - พอร์ตจาก Odoo 14 (14.0.1.13.0)
        - กดปุ่มอัพเดท ระบบจะสแกนลูกค้าที่มีใบแจ้งหนี้ค้างชำระให้อัตโนมัติ
        - แยกเป็นแท็บ: ค่าเช่า / ค่าประกัน / ค่าเช่าส่วนต่าง / ค่าปรับหาย / ค่าปรับชำรุด /
          ค่าขนส่ง / ค่าหัก ณ ที่จ่าย
        - กำหนดสถานะติดตามหนี้ตามช่วงจำนวนวันค้างชำระได้เอง
        - พิมพ์ "หนังสือขอให้ชำระหนี้ค้างตามสัญญาเช่า" จากหน้ารวมหนี้ลูกค้า
    """,
    'author': 'NPD',
    'category': 'Sales',
    # โมดูลที่ให้ฟิลด์ซึ่งใช้ใน domain ของการค้นหา (ฟิลด์อื่นที่ไม่บังคับใช้ getattr กันไว้แล้ว
    # เช่น ส่วนลดของ bi_sale_purchase_discount_with_tax ที่ยังไม่ได้ติดตั้งบน prod)
    #   scrap_reason_code + npd_commission_fields : ประเภทเอกสาร (reason_code_id) + เซลล์
    #   sale_api_rent                             : so_number / source_company_id (แท็บค่าขนส่ง)
    #   account_payment_invoice                   : ใบรับชำระหลายใบแจ้งหนี้ (แท็บหัก ณ ที่จ่าย)
    #   pfb_npd_all_customs                       : rent_check (แยกใบแจ้งหนี้ค่าประกัน)
    'depends': [
        'sale', 'sale_management', 'account',
        'scrap_reason_code', 'npd_commission_fields', 'sale_api_rent',
        'account_payment_invoice', 'pfb_npd_all_customs',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/debt_collection_status_data.xml',
        'views/debt_summary_views.xml',
        'views/debt_collection_status_views.xml',
        'report/debt_collection_letter.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
