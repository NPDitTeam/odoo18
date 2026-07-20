# -*- coding: utf-8 -*-
def migrate(cr, version):
    """เคลียร์ตัวย่อบริษัท (rental_contract_prefix) ที่ค้างจาก default เดิม
    (เวอร์ชันก่อนหน้า default = env.company ทำให้ได้ prefix ตามบริษัทที่ active
     ไม่ใช่บริษัทของใบขาย เช่น ได้ 'lg-' ทั้งที่ใบขายเป็นบริษัทกรุงเทพ)

    ตั้งเป็น NULL ให้ไป fallback คำนวณตาม company ของใบขาย (company_registry) แทน
    ทำเฉพาะใบที่ยังไม่มีเลขที่สัญญา (rental_contract_no) เพื่อไม่กระทบเลขที่ออกไปแล้ว
    """
    cr.execute("""
        UPDATE sale_order
           SET rental_contract_prefix = NULL
         WHERE rental_contract_prefix IS NOT NULL
           AND (rental_contract_no IS NULL OR rental_contract_no = '')
    """)
