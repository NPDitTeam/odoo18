from odoo import models, fields


class StockCutConfirmLine(models.TransientModel):
    _name = 'stock.cut.confirm.line'
    _description = 'Stock Cut Confirm Line'

    wizard_id = fields.Many2one('stock.cut.confirm.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product')
    quantity = fields.Float(string='Quantity')
    location_name = fields.Char(string='Location')
    stock_remain = fields.Float(string='สต็อกคงเหลือ (บ้านเขียว)', readonly=True)
    need_manual_input = fields.Boolean(string='ต้องกรอกสต็อกจริง', default=False)
    manual_stock_input = fields.Float(string='จำนวนสต็อกจริง')
