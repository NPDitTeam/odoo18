from odoo import _, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_open_overpaid_refund(self):
        """ปุ่ม "คืนเงินโอนเกิน" ในหน้ารับชำระ (ขาบัญชีการเงินข้อ 1.4-1.6)

        เปิดเอกสารโอนคืนเงินลูกค้า ประเภทคืนเงินโอนเกิน ผูกใบรับชำระนี้ไว้ให้
        พนักงานกรอกยอดที่โอนเกิน แล้วกดยืนยัน (Dr ออมทรัพย์ / Cr หนี้สินอื่นๆ)
        จากนั้นการเงินกด "คืนเงินโอนเกิน" ในเอกสารนั้น (Dr หนี้สินอื่นๆ / Cr กระแสรายวัน)
        """
        self.ensure_one()
        existing = self.env['refund.payment'].search([
            ('transfer_type', '=', 'overpaid_refund'), ('payment_ids', 'in', self.ids),
            ('state', '!=', 'cancelled')], limit=1)
        action = {
            'type': 'ir.actions.act_window',
            'name': _('คืนเงินโอนเกิน'),
            'res_model': 'refund.payment',
            'view_mode': 'form',
            'target': 'current',
        }
        if existing:
            action['res_id'] = existing.id
            return action
        action['context'] = {
            'default_transfer_type': 'overpaid_refund',
            'default_company_id': self.company_id.id,
            'default_payment_ids': [(6, 0, self.ids)],
        }
        return action
