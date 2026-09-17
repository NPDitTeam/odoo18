# -*- coding: utf-8 -*-
{
    'name': 'NPD Rental Status Update',
    'version': '18.0.1.1.0',
    'summary': 'Update rental status with permission control',
    'description': """
        อัพเดทสถานะ rental_status ของใบสั่งเช่า (เมนู ⚙ "ปิดบิล" ในหน้ารายการ) — พอร์ตจาก Odoo 14
        - ผู้ใช้ทั่วไป: ปิดบิลได้เฉพาะรายการที่ "ครบกำหนด" หรือ "เกินกำหนด"
        - ผู้ใช้ที่ติ๊ก "อนุญาตปรับสถานะการเช่าได้ทุกสถานะ": เลือกสถานะใดก็ได้
    """,
    'author': 'NPD Dev',
    'category': 'Sales',
    'license': 'LGPL-3',
    'depends': ['sale', 'sale_management', 'pfb_npd_add_date_quatation_order'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'wizard/update_rental_status_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
