# -*- coding: utf-8 -*-
{
    'name': 'NPD Rental Return Tracking',
    'version': '18.0.1.0.0',
    'summary': 'ตรวจสอบใบตัดสต๊อก (ใบส่งออกเช่า) ที่ยังคืนไม่ครบ แยกบริษัท/สาขา/สินค้า',
    'description': """
ตรวจสอบการตัดสต๊อกที่ยังไม่คืน (Odoo 18)
========================================
เมนูตรวจสอบระดับ 'เอกสาร' ว่า 'ใบตัดสต๊อกใบไหน' (ใบส่งออก outgoing เสร็จสิ้น
ของบิลเช่า) ที่ยัง 'คืนไม่ครบ' โดยดูจากใบตัด/ใบคืนใน stock.picking

แต่ละแถว = 1 ใบตัด (stock.move ที่เป็นใบส่งออก done ไม่ใช่ใบคืน) พร้อม:
  * บริษัท  * สาขา (res.branch)  * สินค้า  * ลูกค้า  * ใบตัด/ใบสั่งขาย
  * วันที่ตัด/กำหนดคืน  * จำนวนที่ตัด  * จำนวนที่คืนแล้ว  * จำนวนค้างคืน  * สถานะการคืน

นิยาม 'ตัด/คืน' ใช้ตรรกะเดียวกับ so_auto_stock_cut และ npd_rental_stock_overview:
  ใบตัด   = move state=done, picking outgoing, origin_returned_move_id IS NULL
  จำนวนคืน = move state=done ที่อ้างอิงกลับผ่าน origin_returned_move_id
  ค้างคืน  = GREATEST(จำนวนตัด - จำนวนคืน, 0)
  สาขา     = branch ของคลังต้นทาง (fallback: branch ของ picking -> ของบิลขาย)

ยอด 'ค้างคืน' รวมต่อ (สินค้า x สาขา) จะตรงกับคอลัมน์ 'จำนวนที่ถูกเช่า'
ในรายงาน npd_rental_stock_overview (เป็นการเจาะลึกว่ายอดนั้นมาจากเอกสารใดบ้าง)

ต่างจาก Odoo 14: ทุกบริษัทอยู่ฐานเดียวกัน จึงเพิ่มคอลัมน์ 'บริษัท'
และชื่อสินค้าเป็น jsonb ต้อง cast ::text ก่อนค้น '(R)'
""",
    'author': 'NPD',
    'category': 'Inventory/Reporting',
    'license': 'LGPL-3',
    # multi_branch_management_aagam -> res.branch + branch_id บนคลัง/ใบส่ง/บิลขาย
    'depends': ['stock', 'sale_stock', 'multi_branch_management_aagam'],
    'data': [
        'security/ir.model.access.csv',
        'views/rental_return_tracking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
