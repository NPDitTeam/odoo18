from datetime import datetime

from odoo import _, models
from odoo.exceptions import UserError


class AccountVoucher(models.Model):
    _inherit = 'account.voucher'

    def cancel_voucher(self):
        """ยกเลิกใบสำคัญ (รวมคืนเงินประกัน) ด้วยการกลับรายการ ไม่ลบรายการบัญชีแบบเดิม"""
        for voucher in self:
            if voucher.move_id:
                voucher.move_id._npd_cancel_by_reverse(_('ยกเลิกใบสำคัญ %s') % (voucher.number or ''))
            # ใบรับ/จ่ายชำระที่ใบสำคัญสร้างไว้ ยกเลิกด้วยการกลับรายการเหมือนกัน
            pays = voucher.payment_t_ids.filtered(lambda p: p.exists() and p.state in ('paid', 'in_process'))
            if pays:
                pays.action_cancel_payment()
            voucher.message_post(body="<p><b>Cancel Receipts</b> (กลับรายการบัญชี)</p>"
                                      "<p><b>Cancel Date:</b> %s </p><p><b>Total:</b> %s </p>" % (
                                          datetime.today().strftime('%d/%m/%Y'), voucher.amount))
        self._sync_wht_cert_state('cancel')
        self.write({'state': 'cancel'})
        return True

    def action_cancel_draft(self):
        for voucher in self:
            if voucher.move_id:
                raise UserError(_('ใบสำคัญ %s เคยลงบัญชีแล้ว (ยกเลิกด้วยการกลับรายการ) '
                                  'กลับเป็นฉบับร่างไม่ได้ ให้ทำใบใหม่') % (voucher.number or ''))
        return super().action_cancel_draft()
