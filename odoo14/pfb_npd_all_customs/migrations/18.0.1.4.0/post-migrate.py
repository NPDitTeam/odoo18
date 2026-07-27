# -*- coding: utf-8 -*-
"""เติมค่าเริ่มต้นของ

1. กรณี "ใบสำคัญรับ" / "ใบสำคัญจ่าย" ในเมนูสมุดรายวันออกใบแจ้งหนี้
(ส่วนจับคู่สมุดรายวันรับชำระย้ายไปอยู่ใน migration 18.0.1.5.0 แล้ว)

สมุดรายวัน "รับชำระ*" / "จ่ายชำระ" เป็นประเภท receivable/payable
ที่โมดูล account_journal_sequences เพิ่มเข้ามา ไม่ใช่ bank/cash
"""
import logging

_logger = logging.getLogger(__name__)

# usage -> (ประเภทสมุดรายวัน, ชื่อที่ไล่หา)
USAGE_NAMES = {
    'voucher_sale': ('receivable', ['สมุดรายวันรับชำระ']),
    'voucher_purchase': ('payable', ['สมุดรายวันจ่ายชำระ']),
}

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

    created_config = 0

    for company_id, company_name in companies:
        # --- 1. ใบสำคัญรับ / ใบสำคัญจ่าย ---
        for usage, (journal_type, names) in USAGE_NAMES.items():
            cr.execute(
                "SELECT 1 FROM npd_invoice_journal_config "
                " WHERE company_id = %s AND usage = %s",
                (company_id, usage),
            )
            if cr.fetchone():
                continue

            journal_id = None
            for name in names:
                journal_id = _find_journal(cr, company_id, name, [journal_type])
                if journal_id:
                    break
            if not journal_id:
                _logger.info("ข้าม '%s' ของบริษัท %s: ไม่พบสมุดรายวัน %s",
                             usage, company_name, names)
                continue

            cr.execute(
                "INSERT INTO npd_invoice_journal_config "
                "       (company_id, usage, journal_id, note, "
                "        create_uid, write_uid, create_date, write_date) "
                "VALUES (%s, %s, %s, %s, 1, 1, now(), now())",
                (company_id, usage, journal_id, 'ตั้งค่าอัตโนมัติตอนอัปเกรดโมดูล'),
            )
            created_config += 1

    _logger.info("สร้างค่าตั้งต้นสมุดรายวันออกใบแจ้งหนี้ %s แถว", created_config)
