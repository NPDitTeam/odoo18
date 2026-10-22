# -*- coding: utf-8 -*-
{
    'name': 'NPD Logistics ใบสั่งขายแบบ o14',
    'version': '18.0.1.2.0',
    'summary': 'บริษัท เอ็นพีดี โลจิสติกส์: ซ่อนปุ่มงานเช่า และปิดสูตรเช่าของบริษัทอื่น (จำนวน×วัน, ค่าประกัน, ราคารวม VAT) ให้ลงข้อมูลตรงแบบ o14',
    'description': """
ใบสั่งขายของ บริษัท เอ็นพีดี โลจิสติกส์ จำกัด
* ซ่อนปุ่ม "ยกเลิกรายการอ้างอิงบิลเช่า" และ "ตัดสต๊อก Auto"
* ไม่คำนวณจำนวน = Quantity Rent x วันเช่า
* ไม่ดึงค่าประกันอัตโนมัติ
* ไม่ใช้ราคารวม VAT แบบใบเช่า (ใช้ราคาที่กรอกตรง)
* ไม่มีภาษีรายบรรทัด (แบบ o14)
* ซ่อนช่องสูตรเช่า/ค่าประกัน/ถอด VAT ที่บริษัทอื่นใช้

บริษัทอื่นทำงานเหมือนเดิม
    """,
    'category': 'Sales',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['transport_sync', 'so_auto_stock_cut', 'sale_order_cancel_wizard',
                'pfb_npd_all_customs', 'npd_rent_price_round', 'sale_api_rent',
                'pfb_npd_delivery_note_jasper', 'npd_sale_renewal_status'],
    'data': [
        'views/sale_order_views.xml',
        'views/sale_order_fields_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
