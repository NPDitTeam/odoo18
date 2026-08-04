# -*- coding: utf-8 -*-
{
    'name': 'สถานะต่ออายุบิล (Sale Order)',
    'version': '18.0.1.0.0',
    'summary': 'เพิ่มฟิลด์ "สถานะต่ออายุบิล" ใน Sale Order คำนวณจาก "เลขอ้างอิงเงินประกัน"',
    'description': '''
        เพิ่มฟิลด์ "สถานะต่ออายุบิล" (renewal_bill_status) ใน Sale Order
        ต่อจากฟิลด์ "เลขอ้างอิงเงินประกัน" (deposit_ref)

        เงื่อนไข:
        - deposit_ref มีค่า (อย่างน้อย 1 เลขอ้างอิง) -> สถานะ = "ต่ออายุบิล"
        - deposit_ref ไม่มีค่า                        -> สถานะ = ว่าง

        หมายเหตุ: deposit_ref เก็บเป็นข้อความคั่นด้วยจุลภาค (,) เช่น "SO001,SO002"
        โดยเอกสารที่ถูกกดซ้ำ (ต่ออายุ) ครั้งแรกจะมีเลขอ้างอิง 1 ค่า

        ข้อควรทราบ (Odoo 18): บริษัทที่ company_registry เป็น '4' (เอ็นพีดี สตีลเทค)
        และ '5' (เอ็นพีดี โลจิสติกส์) ถูกยกเว้นการสะสม deposit_ref ตอนกดซ้ำเอกสาร
        (ดู sale.order.copy_data ใน pfb_npd_add_date_quatation_order)
        บิลต่ออายุของ 2 บริษัทนี้จึงไม่มี deposit_ref และสถานะจะเป็นค่าว่าง
    ''',
    'category': 'Sales',
    'author': 'NPD IT',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['sale', 'pfb_npd_add_date_quatation_order'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
