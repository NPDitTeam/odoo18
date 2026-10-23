# -*- coding: utf-8 -*-
{
    'name': 'NPD คอลัมน์ส่วนลดรายการสินค้าแบบ o14',
    'version': '18.0.1.7.0',
    'summary': 'น้ำหนักต่อหน่วย / ประเภทการลดราคา / ยอดส่วนลด / วันที่จัดส่งสินค้า / ยอดหลังหักส่วนลด ในรายการใบเสนอราคา + ส่วนลดเกิน 50% ต้องขออนุมัติ',
    'description': """
ให้คอลัมน์รายการสินค้าใบเสนอราคา/ใบสั่งขาย o18 ตรงกับ o14 (ผู้ใช้สั่ง 22 ต.ค. 2569)
=====================================================
o14 ได้คอลัมน์เหล่านี้จาก bi_sale_purchase_discount_with_tax ซึ่ง o18 ไม่ได้ติดตั้ง
(ติดตั้งแล้วสูตรราคา/VAT/ลงบัญชีเปลี่ยนทุกบริษัท) — ผู้ใช้ต้องการแค่เกณฑ์ขออนุมัติ:

* ประเภทส่วนลด = Product และยอดส่วนลด > 50% ของยอดรายการ (price_subtotal_without_discount)
  → ซ่อน Convert to Order แสดง Send for Approval (โค้ดเดิมใน sale_isolated_quotation)
* ยอดส่วนลดไม่หักออกจากยอดรวม/ใบแจ้งหนี้ (เหมือน o18 เดิม: รวมไปที่ - Line Discount / - Rental Discount)
    """,
    'category': 'Sales',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['sale_isolated_quotation', 'pfb_npd_all_customs', 'product'],
    'data': [
        'data/decimal_precision.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'npd_sale_line_discount_o14/static/src/xml/tax_totals_discount.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
