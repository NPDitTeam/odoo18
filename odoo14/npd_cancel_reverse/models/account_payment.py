from odoo import _, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _npd_has_posted_move(self):
        return any(p.move_id and (p.move_id.state == 'posted' or p.move_id.reversal_move_ids) for p in self)

    def action_draft(self):
        if self._npd_has_posted_move():
            raise UserError(_('ใบรับ/จ่ายชำระที่ลงบัญชีแล้วรีเซตเป็นฉบับร่างไม่ได้ (เลขรายการบัญชีจะข้าม)\n'
                              'ให้กด "ยกเลิกการชำระ" ระบบจะกลับขาบัญชีให้ แล้วทำใบใหม่'))
        return super().action_draft()

    def action_cancel(self):
        # ปุ่มยกเลิกมาตรฐานกับใบที่ลงบัญชีแล้ว -> ยกเลิกด้วยการกลับรายการ
        posted = self.filtered(lambda p: p.move_id.state == 'posted')
        if posted:
            posted.action_cancel_payment()
        rest = self - posted
        return super(AccountPayment, rest).action_cancel() if rest else True

    def action_cancel_payment(self):
        """ยกเลิกการชำระ: ถอนการกระทบยอด แล้วกลับขาบัญชี (แทนการรีเซต/ยกเลิกรายการเดิม)

        แทนที่ของ account_payment_invoice / account_payment_sequence ทั้งหมด (ไม่เรียก super)
        เพราะของเดิมรีเซตรายการบัญชีแล้วบังคับยกเลิกด้วย SQL
        """
        if hasattr(self, '_check_cancel_lock'):
            self._check_cancel_lock()
        for rec in self:
            if rec.state not in ('paid', 'in_process'):
                raise UserError(_('ยกเลิกได้เฉพาะใบที่ลงบัญชีแล้ว (%s)') % (rec.name or rec.id))
        if hasattr(self, '_unreconcile_all'):
            self._unreconcile_all()
        else:
            self.move_id.line_ids.filtered('reconciled').remove_move_reconcile()
        for rec in self:
            if rec.move_id:
                rec.move_id._npd_cancel_by_reverse(_('ยกเลิกการชำระ %s') % (rec.name or ''))
        self.write({'state': 'canceled'})
        if hasattr(self, '_reset_invoice_payment_states'):
            self._reset_invoice_payment_states()
        self.env['account.move'].invalidate_model(['state', 'payment_state', 'amount_residual'])
        self.invalidate_recordset()
        for rec in self:
            rec.message_post(body=_('ยกเลิกการชำระด้วยการกลับรายการบัญชี'))
        return True
