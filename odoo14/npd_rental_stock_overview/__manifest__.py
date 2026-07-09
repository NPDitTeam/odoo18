# -*- coding: utf-8 -*-
{
    'name': 'NPD Rental Stock Overview',
    'version': '18.0.1.0.0',
    'summary': 'รายงานภาพรวมสต็อก เช่า แยกบริษัท/สาขา พร้อมจำนวนที่ถูกเช่า (ตัดสต๊อกเสร็จสิ้น ยังไม่คืน)',
    'description': """
รายงานภาพรวมสต็อก เช่า (Odoo 18)
================================
แสดงรายการสินค้าเช่าทั้งหมดแยกตาม บริษัท (res.company) + สาขา (res.branch) พร้อมคอลัมน์:
  * ปริมาณคงคลัง (on-hand) ของสาขา
  * จำนวนที่ถูกเช่า = จำนวนที่ตัดสต๊อกออก (ใบส่งออกสถานะ 'เสร็จสิ้น') ของบิลเช่า
    ที่ 'ยังไม่ได้คืนครบ' (หักจำนวนที่คืนกลับผ่านใบคืนที่เสร็จสิ้นแล้ว)
  * สินค้าหาย / สินค้าชำรุด (จากใบ Scrap)
  * ย้ายสต็อกเข้า/ออก (จาก stock.api.transfer)

หมายเหตุ Odoo 18: เดิม (Odoo 14) แต่ละบริษัทเป็นคนละฐานข้อมูล รายงานจึงไม่ต้องมีคอลัมน์บริษัท
เวอร์ชันนี้ทุกบริษัทอยู่ DB เดียวกัน จึงเพิ่มคอลัมน์ 'บริษัท' (อ้างอิงบริษัทเจ้าของคลัง)
และปรับ CTE ย้ายสต็อกให้ตรง schema ใหม่ของ stock.api.transfer (โอนภายใน DB)
""",
    'author': 'NPD',
    'category': 'Inventory/Reporting',
    'license': 'LGPL-3',
    # branch -> multi_branch_management_aagam (ให้ res.branch + branch_id บนคลัง/บิล/ใบส่ง)
    # stock_api_transfer -> ตาราง stock_api_transfer_line ที่ SQL view อ้างถึงต้องมีก่อน
    'depends': ['stock', 'sale_stock', 'multi_branch_management_aagam', 'stock_api_transfer'],
    'data': [
        'security/ir.model.access.csv',
        'views/rental_stock_overview_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
