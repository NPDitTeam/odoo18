from odoo import fields, models


class AdvanceClearCashBill(models.Model):
    _name = 'advance.clear.cash.bill'
    _description = 'Cash Bill Entry for Advance Clear'
    _order = 'sequence, id'

    advance_clear_id = fields.Many2one(
        'account.advance.clear',
        string='Advance Clear',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(
        string='ลำดับ',
        default=10,
    )
    description = fields.Char(
        string='รายการสินค้า',
        required=True,
    )
    amount = fields.Float(
        string='จำนวนเงิน',
        required=True,
        digits='Product Price',
    )
    vat_amount = fields.Float(
        string='VAT',
        digits='Product Price',
        default=0,
    )
