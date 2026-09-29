# -*- coding: utf-8 -*-
u"""อัปเดตตามกติกา 3 กลุ่ม (พอร์ตจาก o14 14.0.5.7.0 + 14.0.5.8.0)

1. ปล่อยเงินก้อนที่ใบรับชำระ "ที่ยกเลิก/กลับเป็นร่างไปแล้ว" ยังจับค้างไว้
   โค้ดเดิมไม่ปล่อยผลจับคู่ของสลิปตอนยกเลิกใบ ใบที่ยกเลิกแล้วจึงยังถูกนับว่า
   "ใช้เงินก้อนนี้อยู่" ใบจริงที่ทำใหม่แทนจะตก "ตัดเกิน" ทุกครั้งที่กดตรวจ

2. ให้ใบที่ตัดสินด้วยกติกาเก่าถูกตรวจใหม่
   - สลิปจ่ายบิลที่เคยขึ้น "ไม่ต้องตรวจสอบ" (ยังไม่มีรายการรายคน) -> ตรวจใหม่
   - ใบ "ไม่สำเร็จ" ทั้งหมด -> ตรวจใหม่ 1 รอบ เพื่อแยกว่าเป็นเพราะธนาคารส่ง
     ข้อมูลไม่ครบ / แนบสลิปผิด / ยอด-ชื่อไม่ตรงจริง
     ตั้งตัวนับไว้ที่ 2 -> ถ้ายังไม่สำเร็จจะครบเพดาน 3 แล้วหยุด

ไม่อ่านสลิปใหม่ (ใช้ค่าที่ AI อ่านไว้แล้ว) ไม่แตะใบรับชำระ/รายการบัญชี
o18: ใบที่ลงบันทึกแล้วคือ state in_process/paid ไม่ใช่ posted
"""
import logging

from odoo import api, SUPERUSER_ID

from odoo.addons.npd_scb_auto_payment.models.account_payment import POSTED_STATES

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # ---- 1) ปล่อยเงินก้อนของใบที่ไม่ได้ลงบันทึกแล้ว
    lines = env['npd.scb.payment.slip'].search([('state', '=', 'matched')])
    stale = lines.mapped('payment_id').filtered(
        lambda p: p.state not in POSTED_STATES)
    if stale:
        stale._scb_release_on_cancel()
    _logger.info("npd_scb_auto_payment: ปล่อยเงินก้อนจากใบรับชำระที่ไม่ได้ลงบันทึก %s ใบ: %s",
                 len(stale), ', '.join(stale.mapped('name'))[:2000])

    # ---- 2) ตั้งให้ตรวจใหม่ด้วยกติกา 3 กลุ่ม
    Payment = env['account.payment']
    base = [('payment_type', '=', 'inbound'), ('partner_type', '=', 'customer'),
            ('state', 'in', POSTED_STATES)]
    bill = Payment.search(base + [('scb_verify_state', '=', 'skipped'),
                                  ('scb_verify_reason', 'ilike', '"จ่ายบิล"')])
    failed = Payment.search(base + [('scb_verify_state', '=', 'failed')])
    if bill:
        bill.write({'scb_verify_state': 'to_check', 'scb_verify_attempts': 0,
                    'scb_issue_type': False,
                    'scb_verify_summary': Payment._scb_public_summary('to_check')})
    if failed:
        failed.write({'scb_verify_state': 'to_check', 'scb_verify_attempts': 2,
                      'scb_issue_type': False,
                      'scb_verify_summary': Payment._scb_public_summary('to_check')})
    _logger.info("npd_scb_auto_payment 18.0.1.1.0: ตั้งให้ตรวจใหม่ — สลิปจ่ายบิล %s ใบ, "
                 "ใบไม่สำเร็จ %s ใบ", len(bill), len(failed))
