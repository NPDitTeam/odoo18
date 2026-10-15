from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import UserError


class NpdPaymentWhtFileWizard(models.TransientModel):
    _name = 'npd.payment.wht.file.wizard'
    _description = 'เพิ่มใบหัก ณ ที่จ่าย'

    payment_id = fields.Many2one('account.payment', required=True, readonly=True)
    amount = fields.Monetary(related='payment_id.npd_other_receivable_amount', string='ยอดลูกหนี้อื่น')
    currency_id = fields.Many2one(related='payment_id.currency_id')
    reclassed = fields.Boolean(related='payment_id.npd_wht_reclassed')
    attachment_ids = fields.Many2many('ir.attachment', string='ไฟล์ใบหัก ณ ที่จ่าย')
    note = fields.Char(string='หมายเหตุ')

    def action_confirm(self):
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError(_('กรุณาแนบไฟล์อย่างน้อย 1 ไฟล์'))
        pay = self.payment_id
        Files = self.env['npd.payment.wht.file'].sudo()
        names = []
        for att in self.attachment_ids:
            Files.create({
                'payment_id': pay.id,
                'file': att.datas,
                'file_name': att.name,
                'note': self.note,
            })
            names.append(att.name)
        # ไฟล์ชั่วคราวของหน้าต่างนี้ คัดลอกไปแล้ว
        self.attachment_ids.sudo().unlink()
        posted = pay._npd_apply_wht_reclass()
        body = Markup('%s<ul>%s</ul>') % (
            _('แนบใบหัก ณ ที่จ่าย %s ไฟล์') % len(names),
            Markup('').join(Markup('<li>%s</li>') % escape(n) for n in names))
        if posted:
            body += Markup('<p>%s</p>') % (
                _('ลงบัญชีใน %s: Dr ภาษีเงินได้ถูกหัก ณ ที่จ่าย / Cr ลูกหนี้อื่น %s') % (
                    pay.move_id.name, '{:,.2f}'.format(pay.npd_other_receivable_amount)))
        pay.message_post(body=body)
        return {'type': 'ir.actions.act_window_close'}
