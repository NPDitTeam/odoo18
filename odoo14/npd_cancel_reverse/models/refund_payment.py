from odoo import _, models
from odoo.exceptions import UserError

STATUS_FIELD = {
    'overpaid_refund': 'overpaid_refund_status',
    'wtax_refund': 'wtax_refund_status',
    'rental_difference': 'rental_difference_status',
}


class RefundPayment(models.Model):
    _inherit = 'refund.payment'

    def action_cancel(self):
        """ยกเลิกด้วยการกลับรายการ (เดิมรีเซตรายการบัญชีค้างเป็นร่าง)"""
        for rec in self:
            if not rec.env.user.can_confirm_refund_payment:
                raise UserError(_("คุณไม่มีสิทธิ์ยกเลิกเอกสารนี้"))
            if rec.state not in ('draft', 'confirmed'):
                raise UserError(_("ไม่สามารถยกเลิกเอกสารที่ถูกยกเลิกแล้ว"))
            moves = rec.move_id
            if 'reversed_wtax_move_id' in rec._fields:
                moves |= rec.reversed_wtax_move_id
            moves._npd_cancel_by_reverse(_('ยกเลิก %s') % (rec.name or ''))
            rec.state = 'cancelled'
            rec.show_state = False
            field = STATUS_FIELD.get(rec.transfer_type)
            for p in rec.payment_ids:
                if field and field in p._fields:
                    p[field] = 'none'
            rec.message_post(body=_('ยกเลิกเอกสารด้วยการกลับรายการบัญชีเรียบร้อยแล้ว'))
        return True

    def action_reset_to_draft(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                raise UserError(_('%s ลงบัญชีแล้ว รีเซตเป็นฉบับร่างไม่ได้ (เลขรายการบัญชีจะข้าม)\n'
                                  'ให้กด "ยกเลิก" ระบบจะกลับขาบัญชีให้ แล้วทำใบใหม่') % (rec.name or ''))
        return super().action_reset_to_draft()
