# -*- coding: utf-8 -*-
{
    'name': 'NPD Convert to Order - Partner Check',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'ห้าม Convert to Order ถ้าข้อมูลลูกค้าไม่ครบ หรือเลขผู้เสียภาษียังเป็น 0000000000000',
    'description': """
ก่อนกด "Convert to Order" (sale_isolated_quotation) จะตรวจข้อมูลลูกค้าในใบเสนอราคา
(ใช้บริษัทแม่ของลูกค้า = commercial partner): ที่อยู่, เขต/อำเภอ, จังหวัด, รหัสไปรษณีย์,
โทรศัพท์หรือมือถือ, อีเมล, เลขประจำตัวผู้เสียภาษี (ตัวเลข 13 หลักขึ้นไป และห้ามเป็น 0 ล้วน)
ถ้าขาดอย่างใดอย่างหนึ่ง จะแจ้งรายการที่ขาดและไม่ให้แปลงเป็นใบสั่งขาย
    """,
    'author': 'NPD Dev',
    'license': 'LGPL-3',
    'depends': ['sale', 'sale_isolated_quotation'],
    'data': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
