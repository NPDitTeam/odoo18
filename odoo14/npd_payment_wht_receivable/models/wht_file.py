from odoo import _, fields, models
from odoo.exceptions import UserError


class NpdPaymentWhtFile(models.Model):
    _name = 'npd.payment.wht.file'
    _description = 'ไฟล์ใบหัก ณ ที่จ่ายของใบรับชำระ'
    _order = 'id'

    payment_id = fields.Many2one('account.payment', string='ใบรับชำระ', required=True,
                                 ondelete='restrict', index=True)
    company_id = fields.Many2one(related='payment_id.company_id', store=True)
    file = fields.Binary(string='ไฟล์', attachment=True, required=True)
    file_name = fields.Char(string='ชื่อไฟล์')
    note = fields.Char(string='หมายเหตุ')

    def unlink(self):
        # ลงบัญชีโอนลูกหนี้อื่น → ภาษีถูกหัก ณ ที่จ่ายไปแล้ว ไฟล์คือหลักฐานของรายการนั้น
        raise UserError(_('ลบไฟล์ใบหัก ณ ที่จ่ายไม่ได้ เพราะลงบัญชีไปแล้ว (แก้ไข/เปลี่ยนไฟล์ได้)'))
