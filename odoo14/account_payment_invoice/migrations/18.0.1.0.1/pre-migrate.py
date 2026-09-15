# -*- coding: utf-8 -*-
"""Day of Rent บนใบรับชำระ: วันที่ -> จำนวนวัน (ตัวเลข) ให้ตรงกับ Odoo 14

Odoo แปลงคอลัมน์ date เป็น numeric เองไม่ได้ จะเปลี่ยนชื่อคอลัมน์เดิมเป็น *_moved0 ค้างไว้
ถ้าคอลัมน์ยังว่างทั้งหมดให้ลบทิ้งก่อน แล้ว ORM สร้างคอลัมน์ตัวเลขใหม่ให้
มีข้อมูลแล้วไม่ลบ (ปล่อยให้ Odoo ย้ายไป *_moved0 แทน ข้อมูลไม่หาย)
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'account_payment' AND column_name = 'pfb_date_of_rent'
    """)
    row = cr.fetchone()
    if not row or row[0] != 'date':
        return
    cr.execute("SELECT count(*) FROM account_payment WHERE pfb_date_of_rent IS NOT NULL")
    filled = cr.fetchone()[0]
    if filled:
        _logger.warning("account_payment.pfb_date_of_rent (date) มีข้อมูล %s ใบ ไม่ลบคอลัมน์", filled)
        return
    cr.execute("ALTER TABLE account_payment DROP COLUMN pfb_date_of_rent")
    _logger.info("account_payment.pfb_date_of_rent: ลบคอลัมน์วันที่ (ว่าง) เพื่อสร้างเป็นตัวเลข")
