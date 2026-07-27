# -*- coding: utf-8 -*-
"""ตั้งค่าเริ่มต้นคอลัมน์ "สมุดรายวันรับเงิน (Payment)" ให้เหมือน Odoo 14

รอบก่อนตั้งเป็น "ธนาคาร" ทุกแถว เพราะ Odoo 18 รับเฉพาะ bank/cash/credit
ผู้ใช้ยืนยันให้กลับไปใช้คู่เดิมของ Odoo 14 (สมุดรายวันรับชำระ*) จึงเขียนทับให้

หมายเหตุที่ต้องรู้: สมุดรายวัน "รับชำระ*" เป็นประเภท receivable ซึ่ง Odoo 18
ไม่ยอมให้ account.payment ใช้ (ดูคอมเมนต์ใน models/invoice_journal_config.py)
คอลัมน์นี้จึงมีผลเฉพาะจุดที่โค้ดเราเลือกสมุดรายวันเอง ส่วนหน้า
"ลงทะเบียนการชำระเงิน" มาตรฐานของ Odoo จะข้ามไปใช้ค่าเริ่มต้นของมันเอง
"""
import logging

_logger = logging.getLogger(__name__)

# สมุดรายวันใบแจ้งหนี้ -> สมุดรายวันรับชำระ (ยกมาจาก dict ที่ฝังในโค้ด Odoo 14)
PAYMENT_MAP_NAMES = [
    ('สมุดรายวันค่าประกัน', 'สมุดรายวันรับชำระค่าประกัน'),
    ('สมุดรายวันค่าปรับชำรุด', 'สมุดรายวันรับชำระค่าปรับชำรุด'),
    ('สมุดรายวันค่าปรับหาย', 'สมุดรายวันรับชำระค่าปรับหาย'),
    ('สมุดรายวันลดหนี้การขาย', 'สมุดรายวันรับชำระลดหนี้'),
    ('สมุดรายวันการขาย', 'สมุดรายวันรับชำระ'),
    ('สมุดรายวันการขาย(สาขา)', 'สมุดรายวันรับชำระ'),
    ('สมุดรายวันเช่า(สาขา)', 'สมุดรายวันรับชำระ'),
    ('สมุดรายวันเช่า', 'สมุดรายวันรับชำระ'),
]

KS_MODELS = ['npd.invoice.journal.config']


def _find_journal(cr, company_id, name, types):
    cr.execute(
        "SELECT id FROM account_journal "
        " WHERE company_id = %s AND type = ANY(%s) "
        "   AND COALESCE(name->>'th_TH', name->>'en_US') = %s "
        " ORDER BY id LIMIT 1",
        (company_id, list(types), name),
    )
    row = cr.fetchone()
    return row[0] if row else None


def migrate(cr, version):
    cr.execute("SELECT id, name FROM res_company ORDER BY id")
    companies = cr.fetchall()

    updated = 0
    for company_id, company_name in companies:
        for invoice_name, payment_name in PAYMENT_MAP_NAMES:
            invoice_journal_id = _find_journal(
                cr, company_id, invoice_name, ['sale', 'purchase'])
            payment_journal_id = _find_journal(
                cr, company_id, payment_name,
                ['receivable', 'payable', 'bank', 'cash', 'credit'])
            if not invoice_journal_id or not payment_journal_id:
                continue

            # เขียนทับค่า "ธนาคาร" ที่ migration 18.0.1.8.0 ใส่ไว้
            cr.execute("""
                UPDATE npd_invoice_journal_config
                   SET payment_bank_journal_id = %s, write_date = now()
                 WHERE company_id = %s
                   AND journal_id = %s
            """, (payment_journal_id, company_id, invoice_journal_id))
            updated += cr.rowcount

    _logger.info("ตั้งสมุดรายวันรับเงิน (Payment) แบบ Odoo 14 ให้ %s แถว", updated)

    # ล้าง cache คอลัมน์ของ ks_list_view_manager ไม่งั้นเมนูจะเพี้ยน/เปิดไม่ได้
    cr.execute("""
        SELECT 1 FROM information_schema.tables WHERE table_name = 'user_specific'
    """)
    if cr.fetchone():
        cr.execute("""
            DELETE FROM user_fields
             WHERE fields_list IN (SELECT id FROM user_specific WHERE model_name = ANY(%s))
        """, (KS_MODELS,))
        cr.execute("DELETE FROM user_specific WHERE model_name = ANY(%s)", (KS_MODELS,))
