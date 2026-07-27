# -*- coding: utf-8 -*-
"""ยุบเมนู "สมุดรายวันรับชำระ" เข้ามาเป็นคอลัมน์ในเมนู "สมุดรายวันออกใบแจ้งหนี้"

เดิมแยกเป็นอีกโมเดล (npd.payment.journal.map) จับคู่ สมุดรายวันใบแจ้งหนี้ -> สมุดรายวันรับชำระ
ตอนนี้ย้ายมาเป็นคอลัมน์ payment_journal_id บนแถวเดียวกัน เพราะแต่ละแถวก็ระบุ
สมุดรายวันใบแจ้งหนี้อยู่แล้ว ดูทีเดียวจบ ไม่ต้องเปิดสองหน้า

ต้องทำใน pre-migrate เพราะพอ Odoo โหลดโมดูลเสร็จแล้วจะลบโมเดลที่หายไปจากโค้ด
พร้อม DROP TABLE ทิ้ง ถ้าย้ายข้อมูลใน post-migrate จะไม่เหลืออะไรให้ย้าย
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # pre-migrate ทำงานก่อน ORM สร้างตาราง ถ้าอัปเกรดข้ามจากเวอร์ชันเก่า
    # (ก่อน 18.0.1.1.0) ตารางยังไม่มี ให้ข้ามไปเลย — ไม่มีข้อมูลเก่าให้ย้ายอยู่แล้ว
    # และ post-migrate รอบถัดไปจะสร้างค่าตั้งต้นให้เองหลังตารางถูกสร้าง
    cr.execute("""
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'npd_invoice_journal_config'
    """)
    if not cr.fetchone():
        _logger.info(
            "ยังไม่มีตาราง npd_invoice_journal_config (อัปเกรดข้ามเวอร์ชัน) "
            "ข้ามการย้ายข้อมูลสมุดรายวันรับชำระ"
        )
        return

    # สร้างคอลัมน์เองก่อน ORM จะสร้างให้ เพื่อเติมข้อมูลได้ทันในรอบนี้
    cr.execute("""
        ALTER TABLE npd_invoice_journal_config
        ADD COLUMN IF NOT EXISTS payment_journal_id integer
    """)

    cr.execute("""
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'npd_payment_journal_map'
    """)
    if not cr.fetchone():
        _logger.info("ไม่พบตาราง npd_payment_journal_map ข้ามการย้ายข้อมูล")
        return

    cr.execute("""
        UPDATE npd_invoice_journal_config c
           SET payment_journal_id = m.payment_journal_id
          FROM npd_payment_journal_map m
         WHERE m.company_id = c.company_id
           AND m.invoice_journal_id = c.journal_id
           AND c.payment_journal_id IS NULL
    """)
    moved = cr.rowcount

    # แถวที่จับคู่ไว้แต่สมุดรายวันนั้นไม่ได้ถูกใช้เป็นค่าตั้งต้นของกรณีไหนเลย
    # จะไม่มีที่ไป แจ้งไว้ใน log ให้ตรวจสอบเอง
    cr.execute("""
        SELECT c.name AS company,
               COALESCE(ij.name->>'th_TH', ij.name->>'en_US') AS invoice_journal,
               COALESCE(pj.name->>'th_TH', pj.name->>'en_US') AS payment_journal
          FROM npd_payment_journal_map m
          JOIN res_company c ON c.id = m.company_id
          JOIN account_journal ij ON ij.id = m.invoice_journal_id
          JOIN account_journal pj ON pj.id = m.payment_journal_id
         WHERE NOT EXISTS (
                   SELECT 1 FROM npd_invoice_journal_config k
                    WHERE k.company_id = m.company_id
                      AND k.journal_id = m.invoice_journal_id
               )
    """)
    orphans = cr.fetchall()
    for company, invoice_journal, payment_journal in orphans:
        _logger.warning(
            "ย้ายไม่ได้: %s | %s -> %s "
            "(ไม่มีแถวกรณีไหนใช้สมุดรายวันใบแจ้งหนี้เล่มนี้) "
            "ถ้ายังต้องใช้ ให้เพิ่มแถวเองที่เมนูสมุดรายวันออกใบแจ้งหนี้",
            company, invoice_journal, payment_journal,
        )

    _logger.info("ย้ายสมุดรายวันรับชำระเข้าคอลัมน์ใหม่ %s แถว, ย้ายไม่ได้ %s แถว",
                 moved, len(orphans))
