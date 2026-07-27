# -*- coding: utf-8 -*-
"""เติมค่าเริ่มต้นของกรณีใหม่ในเมนู "สมุดรายวันออกใบแจ้งหนี้"

เพิ่ม 3 กรณี: ใบลดหนี้ / ค่าปรับหาย / ค่าปรับชำรุด
บริษัทไหนไม่มีสมุดรายวันชื่อนั้นจะไม่ถูกสร้างแถว ไปตั้งเองได้ที่เมนู

ส่วนเมนู "สมุดรายวันรับชำระ" ตั้งใจปล่อยว่าง เพราะสมุดรายวันปลายทางที่โค้ด
Odoo 14 เดิมอ้างถึง (สมุดรายวันรับชำระ / รับชำระค่าประกัน / รับชำระค่าปรับ*)
ไม่มีอยู่จริงในฐานข้อมูล Odoo 18 นี้เลย จับคู่ให้เองไม่ได้ ต้องให้ผู้ใช้เลือก
"""
import logging

_logger = logging.getLogger(__name__)

USAGE_NAMES = {
    'credit_note': ['สมุดรายวันลดหนี้การขาย', 'สมุดรายวันลดหนี้ขาย'],
    'penalty_lost': ['สมุดรายวันค่าปรับหาย'],
    'penalty_damaged': ['สมุดรายวันค่าปรับชำรุด'],
}


def migrate(cr, version):
    cr.execute("SELECT id, name FROM res_company ORDER BY id")
    companies = cr.fetchall()

    created = 0
    for company_id, company_name in companies:
        for usage, names in USAGE_NAMES.items():
            cr.execute(
                "SELECT 1 FROM npd_invoice_journal_config "
                " WHERE company_id = %s AND usage = %s",
                (company_id, usage),
            )
            if cr.fetchone():
                continue

            journal_id = None
            for name in names:
                # name เป็น jsonb (translate=True) ตั้งแต่ Odoo 16
                cr.execute(
                    "SELECT id FROM account_journal "
                    " WHERE company_id = %s AND type = 'sale' "
                    "   AND COALESCE(name->>'th_TH', name->>'en_US') = %s "
                    " ORDER BY id LIMIT 1",
                    (company_id, name),
                )
                row = cr.fetchone()
                if row:
                    journal_id = row[0]
                    break

            if not journal_id:
                _logger.info(
                    "ข้ามการตั้งค่า '%s' ของบริษัท %s: ไม่พบสมุดรายวันชื่อ %s",
                    usage, company_name, names,
                )
                continue

            cr.execute(
                "INSERT INTO npd_invoice_journal_config "
                "       (company_id, usage, journal_id, note, "
                "        create_uid, write_uid, create_date, write_date) "
                "VALUES (%s, %s, %s, %s, 1, 1, now(), now())",
                (company_id, usage, journal_id, 'ตั้งค่าอัตโนมัติตอนอัปเกรดโมดูล'),
            )
            created += 1

    _logger.info("สร้างค่าตั้งต้นสมุดรายวันออกใบแจ้งหนี้เพิ่ม %s แถว", created)
