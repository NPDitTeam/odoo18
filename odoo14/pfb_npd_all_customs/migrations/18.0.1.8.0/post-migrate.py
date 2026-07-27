# -*- coding: utf-8 -*-
"""แยกสมุดรายวันฝั่งรับชำระเป็น 2 คอลัมน์

payment_journal_id       = เอกสารใบสำคัญ (account.voucher) -> receivable/payable
payment_bank_journal_id  = หน้ารับชำระเงิน (account.payment) -> bank/cash/credit  [ใหม่]

Odoo 18 ฮาร์ดโค้ดใน account.payment._compute_available_journal_ids ว่าสมุดรายวัน
ต้องเป็น bank/cash/credit เท่านั้น สมุดรายวัน "รับชำระ*" ที่ seed ไว้รอบก่อน
เป็นประเภท receivable จึงใช้กับ account.payment ไม่ได้เลย (และไม่มี
payment_method_line สักแถว ทำให้โพสต์ไม่ผ่าน)

migration นี้เติมคอลัมน์ใหม่ด้วยสมุดรายวันธนาคารที่ใช้งานได้จริงของแต่ละบริษัท
เลือกเล่มที่มี payment_method_line อยู่แล้วเท่านั้น ผู้ใช้เปลี่ยนเองทีหลังได้
"""
import logging

_logger = logging.getLogger(__name__)

# ชื่อสมุดรายวันรับเงินที่อยากได้เป็นค่าเริ่มต้น ไล่ตามลำดับ
PREFERRED_BANK_NAMES = ['ธนาคาร', 'เงินสด']


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE npd_invoice_journal_config
        ADD COLUMN IF NOT EXISTS payment_bank_journal_id integer
    """)

    cr.execute("SELECT id, name FROM res_company ORDER BY id")
    companies = cr.fetchall()

    filled = 0
    for company_id, company_name in companies:
        journal_id = None
        for name in PREFERRED_BANK_NAMES:
            cr.execute("""
                SELECT j.id FROM account_journal j
                 WHERE j.company_id = %s
                   AND j.type IN ('bank', 'cash', 'credit')
                   AND COALESCE(j.name->>'th_TH', j.name->>'en_US') = %s
                   AND EXISTS (SELECT 1 FROM account_payment_method_line l
                                WHERE l.journal_id = j.id)
                 ORDER BY j.id LIMIT 1
            """, (company_id, name))
            row = cr.fetchone()
            if row:
                journal_id = row[0]
                break

        if not journal_id:
            # ไม่เจอชื่อที่ต้องการ เอาเล่มแรกที่ใช้ได้จริง
            cr.execute("""
                SELECT j.id FROM account_journal j
                 WHERE j.company_id = %s
                   AND j.type IN ('bank', 'cash', 'credit')
                   AND EXISTS (SELECT 1 FROM account_payment_method_line l
                                WHERE l.journal_id = j.id)
                 ORDER BY j.id LIMIT 1
            """, (company_id,))
            row = cr.fetchone()
            journal_id = row[0] if row else None

        if not journal_id:
            _logger.warning(
                "บริษัท %s ไม่มีสมุดรายวันธนาคาร/เงินสดที่ตั้ง payment method ไว้ "
                "หน้ารับชำระจะใช้ค่าเริ่มต้นของ Odoo",
                company_name,
            )
            continue

        # เติมเฉพาะแถวที่ผูกสมุดรายวันใบสำคัญไว้แล้ว (คือแถวที่ใช้รับชำระจริง)
        # แถวใบสำคัญรับ/จ่าย (voucher_*) ไม่ต้องมี เพราะตัวมันเองคือเอกสารรับเงิน
        cr.execute("""
            UPDATE npd_invoice_journal_config
               SET payment_bank_journal_id = %s, write_date = now()
             WHERE company_id = %s
               AND payment_bank_journal_id IS NULL
               AND payment_journal_id IS NOT NULL
        """, (journal_id, company_id))
        filled += cr.rowcount

    _logger.info("เติมสมุดรายวันรับเงิน (Payment) ให้ %s แถว", filled)
