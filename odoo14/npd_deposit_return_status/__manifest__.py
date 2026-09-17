# -*- coding: utf-8 -*-
{
    'name': 'NPD Deposit Return Status',
    'version': '18.0.1.0.0',
    'summary': 'ติดตามสถานะการคืนเงินประกันในใบสั่งขาย (พอร์ตจาก Odoo 14)',
    'description': """
        สถานะคืนเงินประกันของใบสั่งเช่าที่ "เกินกำหนด"
        - ลูกค้ายังไม่คืนสินค้า         : ใบส่งสินค้าออก (done) มากกว่าใบรับคืน (done)
        - สาขายังไม่สร้างการคืนเงินประกัน : คืนสินค้าครบแล้ว แต่ยังไม่มีใบคืนเงินประกัน (account.voucher reference = SO)
        - รอคืนเงินประกันจากการเงิน     : มีใบคืนเงินประกันแต่ยังไม่ยืนยัน
        - เสร็จสิ้น                     : ใบคืนเงินประกันยืนยันแล้ว -> ใบสั่งเช่า "ปิดบิล"
        อัปเดตทันทีเมื่อสถานะการเช่าเปลี่ยน / รับคืนสินค้า / สร้าง-ยืนยันใบคืนเงินประกัน และ cron ทุก 15 นาที
    """,
    'author': 'NPD Dev',
    'category': 'Sales',
    'depends': ['sale', 'stock', 'account_voucher_npd', 'pfb_npd_add_date_quatation_order',
                'pfb_npd_all_customs', 'pfb_npd_add_date_stock_picking'],
    'data': [
        'views/sale_order_views.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
