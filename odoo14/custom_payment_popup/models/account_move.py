from odoo import models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_open_payment_form(self):
        """Open payment form pre-filled from invoice + auto search invoice"""
        self.ensure_one()

        # Auto-select journal from the invoice journal
        # จับคู่ได้ที่เมนู การขาย > การกำหนดค่า > สมุดรายวันรับชำระ
        journal = self.env['npd.invoice.journal.config']._get_payment_journal(
            self.company_id, self.journal_id,
        )

        if not journal:
            # ต้องล็อกบริษัทด้วย ไม่งั้นจะคว้าสมุดรายวันธนาคารของบริษัทอื่น
            # เวลาผู้ใช้เปิดหลายบริษัทพร้อมกัน
            journal = self.env['account.journal'].search([
                ('type', '=', 'bank'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)

        # Determine payment type
        if self.move_type in ('out_invoice', 'in_refund'):
            payment_type = 'inbound'
            partner_type = 'customer'
        else:
            payment_type = 'outbound'
            partner_type = 'supplier'

        ctx = {
            'default_partner_id': self.partner_id.id,
            'default_date': self.invoice_date or False,
            'default_ref': self.name,
            'default_search_invoice_name': self.name,
            'default_payment_type': payment_type,
            'default_partner_type': partner_type,
            'default_currency_id': self.currency_id.id,
        }
        if journal:
            ctx['default_journal_id'] = journal.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('ชำระเงิน'),
            'res_model': 'account.payment',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }
