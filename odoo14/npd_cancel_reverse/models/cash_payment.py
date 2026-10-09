from odoo import _, fields, models


class CashPayment(models.Model):
    _inherit = 'cash.payment'

    state = fields.Selection(selection_add=[('cancel', 'ยกเลิก')], ondelete={'cancel': 'set default'})

    def action_reset_to_draft(self):
        """ลงบัญชีแล้ว -> ยกเลิกด้วยการกลับรายการ (เดิมทิ้งรายการค้างเป็นร่าง ยืนยันใหม่ได้เลขใหม่)"""
        posted = self.filtered(lambda r: r.move_id and r.move_id.state == 'posted')
        for rec in posted:
            rec.move_id._npd_cancel_by_reverse(_('ยกเลิก %s') % (rec.name or ''))
            rec.state = 'cancel'
            for p in rec.payment_ids:
                p.cash_status = ''
                if hasattr(p, 'cash_invoice_id'):
                    p.cash_invoice_id = False
            rec.message_post(body=_('ยกเลิกรายการด้วยการกลับรายการบัญชีเรียบร้อยแล้ว'))
        rest = self - posted
        return super(CashPayment, rest).action_reset_to_draft() if rest else True
