from odoo import fields, models


class ReceiptAmountCorrection(models.Model):
    _name = 'advance.clear.receipt.correction'
    _description = 'Receipt Amount Correction'
    _order = 'id'

    advance_clear_id = fields.Many2one(
        'account.advance.clear',
        string='Advance Clear',
        required=True,
        ondelete='cascade',
    )
    filename = fields.Char(
        string='ชื่อไฟล์',
        required=True,
        readonly=True,
    )
    original_amount = fields.Float(
        string='ยอดที่ AI อ่านได้',
        default=0,
        readonly=True,
        digits='Product Price',
    )
    corrected_amount = fields.Float(
        string='ยอดที่ถูกต้อง',
        required=True,
        digits='Product Price',
    )
