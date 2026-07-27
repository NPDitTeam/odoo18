# -*- coding: utf-8 -*-
"""เติมสมุดรายวันรับชำระให้แถวที่ยังว่างอยู่

pre-migrate ย้ายข้อมูลจากโมเดลเดิม (npd.payment.journal.map) มาแล้ว
รอบนี้เติมให้แถวที่เหลือตามคู่ที่โค้ด Odoo 14 เดิมฝังไว้ เพื่อให้ผู้ที่
อัปเกรดข้ามเวอร์ชันมาได้ค่าตั้งต้นเหมือนกัน

กรณีใบสำคัญรับ/จ่าย (voucher_*) ไม่ต้องมีสมุดรายวันรับชำระ เพราะตัวมันเอง
เป็นเอกสารรับ/จ่ายเงินอยู่แล้ว จึงไม่อยู่ในตารางนี้
"""
import logging

_logger = logging.getLogger(__name__)

# usage -> ชื่อสมุดรายวันรับชำระ
USAGE_PAYMENT_NAMES = {
    'so_sale': 'สมุดรายวันรับชำระ',
    'so_rent': 'สมุดรายวันรับชำระ',
    'insurance': 'สมุดรายวันรับชำระค่าประกัน',
    'penalty_lost': 'สมุดรายวันรับชำระค่าปรับหาย',
    'penalty_damaged': 'สมุดรายวันรับชำระค่าปรับชำรุด',
    'credit_note': 'สมุดรายวันรับชำระลดหนี้',
}


def migrate(cr, version):
    filled = 0
    for usage, journal_name in USAGE_PAYMENT_NAMES.items():
        cr.execute("""
            UPDATE npd_invoice_journal_config c
               SET payment_journal_id = j.id, write_date = now()
              FROM account_journal j
             WHERE j.company_id = c.company_id
               AND j.type IN ('receivable', 'payable', 'bank', 'cash')
               AND COALESCE(j.name->>'th_TH', j.name->>'en_US') = %s
               AND c.usage = %s
               AND c.payment_journal_id IS NULL
        """, (journal_name, usage))
        filled += cr.rowcount

    _logger.info("เติมสมุดรายวันรับชำระให้ %s แถว", filled)
