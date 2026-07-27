# -*- coding: utf-8 -*-
"""เติมค่าเริ่มต้นให้เมนู "สมุดรายวันออกใบแจ้งหนี้" ตอนอัปเกรดโมดูล

ก่อนหน้านี้สมุดรายวันถูกเดาจากชื่อในโค้ด ตอนนี้ย้ายมาตั้งค่าในเมนูแทน
migration นี้จะสร้างแถวตั้งค่าให้ทุกบริษัทที่หาสมุดรายวันตามชื่อเจอ
เพื่อให้เปิดเมนูมาแล้วเห็นค่าที่ระบบใช้อยู่จริง ไม่ใช่หน้าว่าง

บริษัทที่หาไม่เจอจะไม่ถูกสร้างแถว และยังทำงานได้ปกติผ่าน fallback ในโค้ด
"""
import logging

_logger = logging.getLogger(__name__)

USAGE_NAMES = {
    'so_sale': ['สมุดรายวันการขาย(สาขา)', 'สมุดรายวันการขาย'],
    'so_rent': ['สมุดรายวันเช่า(สาขา)', 'สมุดรายวันเช่า'],
    'insurance': ['สมุดรายวันค่าประกัน'],
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
                # เทียบทั้ง th_TH และ en_US เผื่อ DB ไหนเก็บภาษาเดียว
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

    _logger.info("สร้างค่าตั้งต้นสมุดรายวันออกใบแจ้งหนี้ %s แถว", created)
