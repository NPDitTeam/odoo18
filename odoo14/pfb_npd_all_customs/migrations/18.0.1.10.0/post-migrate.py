# -*- coding: utf-8 -*-
"""ตั้งบัญชีรายได้ของแต่ละกรณี ให้ได้ผลเหมือน Odoo 14

Odoo 14 ไม่ได้เขียนโค้ดกำหนดบัญชีจากประเภทใบเสนอราคาเลย บัญชีมาจาก
default_account_id ของสมุดรายวัน แล้วสมุดรายวันมาจากประเภทใบเสนอราคาอีกที
(ตรวจกับฐานข้อมูล O14 แล้ว: สินค้าเช่าไม่มีบัญชีรายได้ทั้งที่ตัวสินค้าและประเภทสินค้า
 จึงตกมาใช้บัญชีของสมุดรายวัน)

Odoo 18 ใช้ลำดับต่างออกไป — account_move_line._compute_account_id ให้
บัญชีของสินค้า/ประเภทสินค้าชนะก่อน แล้วค่อยตกมาที่สมุดรายวันเป็นตัวสุดท้าย
ผลคือบรรทัดใบแจ้งหนี้ไปลง 410000 Income แทนที่จะเป็น 4100-01

migration นี้คัดลอกบัญชีเริ่มต้นของสมุดรายวันที่ตั้งไว้ในแต่ละแถว
มาเป็นบัญชีรายได้ของแถวนั้น เพื่อให้โค้ดกำหนดบัญชีตรง ๆ ไม่ต้องพึ่งลำดับของ Odoo
"""
import logging

_logger = logging.getLogger(__name__)

KS_MODELS = ['npd.invoice.journal.config']


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE npd_invoice_journal_config
        ADD COLUMN IF NOT EXISTS income_account_id integer
    """)

    # ใบสำคัญรับ/จ่ายไม่ได้ออกบรรทัดสินค้า จึงไม่ต้องมีบัญชีรายได้
    cr.execute("""
        UPDATE npd_invoice_journal_config c
           SET income_account_id = j.default_account_id, write_date = now()
          FROM account_journal j
         WHERE j.id = c.journal_id
           AND j.default_account_id IS NOT NULL
           AND c.income_account_id IS NULL
           AND c.usage NOT IN ('voucher_sale', 'voucher_purchase')
    """)
    _logger.info("ตั้งบัญชีรายได้จากบัญชีเริ่มต้นของสมุดรายวัน %s แถว", cr.rowcount)

    cr.execute("""
        SELECT co.name, c.usage
          FROM npd_invoice_journal_config c JOIN res_company co ON co.id=c.company_id
         WHERE c.income_account_id IS NULL
           AND c.usage NOT IN ('voucher_sale', 'voucher_purchase')
    """)
    for company_name, usage in cr.fetchall():
        _logger.warning(
            "%s กรณี '%s': สมุดรายวันไม่ได้ตั้งบัญชีเริ่มต้นไว้ "
            "บรรทัดใบแจ้งหนี้จะใช้บัญชีที่ Odoo เลือกเอง "
            "ถ้าไม่ถูกต้องให้ตั้งบัญชีรายได้เองที่เมนู",
            company_name, usage,
        )

    # ล้าง cache คอลัมน์ของ ks_list_view_manager ไม่งั้นเมนูจะเปิดไม่ได้
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name='user_specific'")
    if cr.fetchone():
        cr.execute("""
            DELETE FROM user_fields
             WHERE fields_list IN (SELECT id FROM user_specific WHERE model_name = ANY(%s))
        """, (KS_MODELS,))
        cr.execute("DELETE FROM user_specific WHERE model_name = ANY(%s)", (KS_MODELS,))
