# -*- coding: utf-8 -*-
u"""เปลี่ยนไฟล์แนบของใบรับชำระ = ต้องตรวจสอบการโอนใหม่

พนักงานที่ได้ผล "แนบสลิปผิดใบ" จะแก้ด้วยการลบสลิปเดิมแล้วแนบสลิปที่ถูก
ถ้าไม่รีเซ็ตสถานะ ใบนั้นจะค้าง "ไม่สำเร็จ" ต่อไป (cron ลองซ้ำให้แค่ตามเพดาน
ที่ตั้งไว้ และใบที่เคยผ่านแล้วไม่ถูกตรวจซ้ำเลย) พนักงานต้องไปตามฝ่ายบัญชี
ให้กดตรวจใหม่ทุกครั้ง

จึงดักตอนเพิ่ม/ลบ/ย้ายไฟล์ที่เป็นสลิปได้ (รูปภาพ/PDF) ของใบรับชำระที่
ลงบันทึกแล้ว -> กลับเป็น "รอตรวจสอบ" + ล้างตัวนับ แล้ว cron ตรวจให้เองรอบถัดไป
"""
from odoo import api, models

from .account_payment import POSTED_STATES, SLIP_MIMETYPES


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _scb_touched_payments(self):
        u"""ใบรับชำระที่ไฟล์เหล่านี้แนบอยู่ (ทั้งแนบตรง และแนบผ่าน chatter)"""
        slips = self.filtered(lambda a: a.mimetype in SLIP_MIMETYPES)
        if not slips:
            return self.env['account.payment']
        ids = set(slips.filtered(
            lambda a: a.res_model == 'account.payment' and a.res_id).mapped('res_id'))
        message_ids = slips.filtered(
            lambda a: a.res_model == 'mail.message' and a.res_id).mapped('res_id')
        if message_ids:
            messages = self.env['mail.message'].sudo().browse(message_ids).exists()
            ids |= set(messages.filtered(
                lambda m: m.model == 'account.payment' and m.res_id).mapped('res_id'))
        return self.env['account.payment'].sudo().browse(list(ids)).exists()

    @api.model
    def _scb_reset_payments(self, payments):
        payments = payments.filtered(
            lambda p: p.state in POSTED_STATES and p.payment_type == 'inbound'
            and p.partner_type == 'customer'
            and p.scb_verify_state not in ('to_check', 'skipped', False))
        if payments:
            payments.write({
                'scb_verify_state': 'to_check',
                'scb_verify_summary': payments._scb_public_summary('to_check'),
                'scb_verify_attempts': 0,
                'scb_issue_type': False,
            })

    @api.model_create_multi
    def create(self, vals_list):
        records = super(IrAttachment, self).create(vals_list)
        if any(v.get('res_model') in ('account.payment', 'mail.message')
               for v in vals_list):
            self._scb_reset_payments(records._scb_touched_payments())
        return records

    def write(self, vals):
        # message_post ย้ายไฟล์จากหน้าต่างเขียนข้อความมาผูกกับใบ ด้วยการ write
        watch = 'res_model' in vals or 'res_id' in vals
        before = self._scb_touched_payments() if watch else None
        res = super(IrAttachment, self).write(vals)
        if watch:
            self._scb_reset_payments(before | self._scb_touched_payments())
        return res

    def unlink(self):
        payments = self._scb_touched_payments()
        res = super(IrAttachment, self).unlink()
        self._scb_reset_payments(payments)
        return res
