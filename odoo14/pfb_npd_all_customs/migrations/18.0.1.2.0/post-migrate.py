# -*- coding: utf-8 -*-
"""ผูกสินค้าเงินประกันเข้ากับแถวตั้งค่ากรณี "ใบแจ้งหนี้รับเงินประกัน"

เดิมสินค้าเงินประกันเก็บเป็นพารามิเตอร์กลางตัวเดียว (sale.deposit_default_npd_id)
ใช้ร่วมกันทุกบริษัท และในฐานข้อมูลนี้ไม่เคยถูกตั้งค่าเลย ทำให้กดปุ่ม "รับเงินประกัน"
แล้วขึ้น "ไม่พบสินค้า..." ตอนนี้ย้ายมาตั้งแยกรายบริษัทในเมนูแทน

migration นี้เติมสินค้าให้แถวที่ยังว่างอยู่ โดยใช้ค่าเดิมจากพารามิเตอร์กลางก่อน
ถ้าไม่มีจึงใช้สินค้า "ค่าประกันสินค้า" ที่โมดูลสร้างให้
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # สินค้าที่โหลดมาจาก data/insurance_product.xml (XML โหลดก่อน post-migrate)
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = 'pfb_npd_all_customs'
           AND name = 'product_product_insurance_deposit'
           AND model = 'product.product'
    """)
    row = cr.fetchone()
    default_product_id = row[0] if row else None

    # ถ้าเคยตั้งพารามิเตอร์กลางไว้ ให้ค่านั้นชนะ จะได้ไม่เปลี่ยนพฤติกรรมเดิม
    cr.execute("""
        SELECT value FROM ir_config_parameter
         WHERE key = 'sale.deposit_default_npd_id'
    """)
    row = cr.fetchone()
    if row and row[0]:
        try:
            legacy_id = int(row[0])
        except (TypeError, ValueError):
            legacy_id = None
        if legacy_id:
            cr.execute(
                "SELECT id FROM product_product WHERE id = %s AND active", (legacy_id,)
            )
            if cr.fetchone():
                default_product_id = legacy_id

    if not default_product_id:
        _logger.warning(
            "ไม่พบสินค้าเงินประกันที่จะใช้เป็นค่าเริ่มต้น "
            "ต้องไปตั้งเองที่เมนู สมุดรายวันออกใบแจ้งหนี้"
        )
        return

    cr.execute("""
        UPDATE npd_invoice_journal_config
           SET product_id = %s, write_date = now()
         WHERE usage = 'insurance'
           AND product_id IS NULL
    """, (default_product_id,))
    _logger.info("ตั้งสินค้าเงินประกันให้ %s แถว (product_id=%s)",
                 cr.rowcount, default_product_id)
