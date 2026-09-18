{
    'name': 'กรอกปริมาณสินค้าคงคลังจากฟอร์มได้ (NPD)',
    'version': '18.0.1.0.0',
    'summary': 'Allow entering counted quantity on the stock.quant form, not only in the list',
    'description': """
ฟอร์ม stock.quant ของ Odoo 18 (stock.view_stock_quant_form_editable) ถูกตั้งมาเป็น
create="false" edit="false" delete="false" ทุกช่องจึงล็อกหมด Odoo ตั้งใจให้ปรับจำนวน
ในหน้า "รายการ" เท่านั้น แต่ผู้ใช้ที่กดเปิดฟอร์มจากแถว (ไอคอนเปิดฟอร์ม) จะเจอทางตัน
กรอกจำนวนไม่ได้เลย

โมดูลนี้

* ปลดล็อกฟอร์ม (create/edit) ให้พิมพ์ได้
* เพิ่มช่อง "จำนวนปริมาณ" (inventory_quantity_auto_apply) ที่บันทึกแล้วปรับสต็อกทันที พร้อมสร้างรายการเคลื่อนไหวสต็อกให้ตามมาตรฐาน Odoo
* บังคับช่องบริษัทเป็นอ่านอย่างเดียว เพราะ Odoo ไม่อนุญาตให้ส่ง company_id ตอนสร้าง quant ในโหมดปรับสต็อก (_get_inventory_fields_create)
""",
    'author': 'NPD',
    'category': 'Inventory',
    'depends': [
        'stock',
    ],
    'data': [
        'views/stock_quant_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
