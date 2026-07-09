{
    "name": "Stock API Transfer",
    "version": "18.0.1.0.0",
    "category": "Inventory",
    "summary": "Internal multi-company stock transfer (cut source, add destination) with approval workflow",
    "description": """
Odoo 14 เดิมโยกสต๊อกข้ามบริษัทที่อยู่คนละฐานข้อมูล ผ่าน HTTP API (npderp.com).
Odoo 18 เปลี่ยนมาใช้หลายบริษัทใน DB เดียวกัน จึงโอนสต๊อกภายในตรงๆ ด้วยการปรับ stock.quant
(ตัดคลังต้นทาง + เติมคลังปลายทาง) โดยยังคง workflow อนุมัติเดิมไว้ครบ (ไม่ใช้ API ภายนอกแล้ว)
""",
    "depends": ["stock", "base"],
    "data": [
        "security/stock_transfer_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/stock_transfer_form.xml",
        "views/stock_transfer_menu.xml",
        "views/res_users_view.xml",
        "wizard/stock_transfer_approval_wizard_view.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
