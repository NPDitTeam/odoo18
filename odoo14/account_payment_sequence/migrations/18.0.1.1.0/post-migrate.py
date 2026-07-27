# -*- coding: utf-8 -*-
"""สร้างวิธีการชำระเงิน (manual) ให้สมุดรายวัน รับชำระ/จ่ายชำระ

Odoo 18 สร้าง account.payment.method.line ให้อัตโนมัติเฉพาะสมุดรายวัน
bank/cash/credit เท่านั้น สมุดรายวัน receivable/payable จึงมี 0 แถว
ทำให้ช่อง "วิธีการชำระเงิน" (required) บนหน้ารับชำระว่างเปล่า บันทึกไม่ได้

Odoo 14 ไม่มีปัญหานี้เพราะ payment_method_id ชี้ไปที่ account.payment.method
ตรง ๆ ไม่ต้องมี line ต่อสมุดรายวัน (โมดูลตัวเดิมยังบังคับ payment_method_id = 1
ไว้ด้วยถ้าคำนวณไม่ได้)

ไม่ตั้ง payment_account_id (บัญชีพัก) ให้ เพราะโมดูล account_payment_invoice
override _prepare_move_line_default_vals สร้าง move line เองจากบัญชีของ
custom.payment.method อยู่แล้ว (แบบเดียวกับที่ Odoo 14 ทำ) จึงไม่ต้องใช้บัญชีพัก
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # หา manual method ทั้งขาเข้า/ขาออก
    cr.execute("""
        SELECT id, payment_type, COALESCE(name->>'th_TH', name->>'en_US')
          FROM account_payment_method
         WHERE code = 'manual'
    """)
    methods = cr.fetchall()
    if not methods:
        _logger.warning("ไม่พบ account.payment.method code='manual' ข้ามการสร้าง")
        return

    cr.execute("""
        SELECT id, COALESCE(name->>'th_TH', name->>'en_US'), type
          FROM account_journal
         WHERE type IN ('receivable', 'payable')
         ORDER BY id
    """)
    journals = cr.fetchall()

    created = 0
    for journal_id, journal_name, journal_type in journals:
        for method_id, payment_type, method_name in methods:
            # receivable = รับเงิน (inbound), payable = จ่ายเงิน (outbound)
            wanted = 'inbound' if journal_type == 'receivable' else 'outbound'
            if payment_type != wanted:
                continue

            cr.execute("""
                SELECT 1 FROM account_payment_method_line
                 WHERE journal_id = %s AND payment_method_id = %s
            """, (journal_id, method_id))
            if cr.fetchone():
                continue

            cr.execute("""
                INSERT INTO account_payment_method_line
                       (name, sequence, payment_method_id, journal_id,
                        create_uid, write_uid, create_date, write_date)
                VALUES (%s, 10, %s, %s, 1, 1, now(), now())
            """, (method_name, method_id, journal_id))
            created += 1
            _logger.info("สร้างวิธีการชำระเงิน '%s' ให้สมุดรายวัน %s",
                         method_name, journal_name)

    _logger.info("สร้าง account.payment.method.line ทั้งหมด %s แถว", created)
