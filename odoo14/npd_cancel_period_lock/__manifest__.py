# -*- coding: utf-8 -*-
{
    'name': 'NPD Cancel Period Lock',
    'version': '18.0.1.0.0',
    'summary': 'ล็อกไม่ให้ยกเลิกใบแจ้งหนี้ / ใบรับชำระ ของเดือนก่อนหน้า (ยกเว้นฝ่ายการเงิน)',
    'description': """
NPD Cancel Period Lock (พอร์ตจาก Odoo 14)
==========================================
เพิ่มฟิลด์ "สถานะการยกเลิก" ให้

* ใบแจ้งหนี้ (account.move ประเภท out_invoice) ตัดสินจาก "วันที่ใบแจ้งหนี้"
* ใบรับชำระ (account.payment ประเภทรับเงิน inbound) ตัดสินจาก "วันที่รับชำระ"

เอกสารที่วันที่อยู่ก่อน "วันตัดงวด" จะขึ้นสถานะ "ไม่สามารถยกเลิกได้ โปรดติดต่อฝ่ายการเงิน"
และกดยกเลิก / รีเซ็ตเป็นแบบร่าง จะขึ้นแจ้งเตือนข้อความเดียวกัน

วันตัดงวด: Scheduled Action รันทุกวันที่ 15 เวลา 00:05 (เวลาไทย) -> วันที่ 1 ของเดือนปัจจุบัน
เก็บไว้ที่ System Parameter npd_cancel_period_lock.cutoff_date

สิทธิ์ยกเลิกได้ไม่สนเงื่อนไข: กลุ่ม "Cancel Period Lock - ยกเลิกเอกสารย้อนหลังได้ (ฝ่ายการเงิน)"
เปิดให้ผู้ใช้ได้ที่ ตั้งค่า > ผู้ใช้ > แท็บ Preferences

ต่างจาก Odoo 14
---------------
* ใบรับชำระ Odoo 18 สถานะยกเลิกคือ canceled (ไม่ใช่ cancel) และไม่ได้สืบทอดจาก account.move
* ดักเพิ่มที่ action_cancel_payment (ปุ่มยกเลิกของ account_payment_invoice)
* สมุดรายวันของใบรับชำระลิงก์ผ่าน origin_payment_id (core) และ payment_id (account_payment_invoice)
""",
    'category': 'Accounting',
    'author': 'NPD Dev',
    'license': 'AGPL-3',
    # โหลดหลัง account_payment_invoice เพื่อให้ด่านตรวจทำงานก่อนโค้ดยกเลิก/รีเซ็ตของมัน
    'depends': [
        'account',
        'account_payment_invoice',
    ],
    'data': [
        'security/security.xml',
        'data/ir_cron.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/res_users_views.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': False,
}
