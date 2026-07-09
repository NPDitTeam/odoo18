from odoo import models, fields

class StockCutConfirmLine(models.TransientModel):
    _name = 'stock.cut.confirm.line'
    _description = 'Stock Cut Confirm Line'

    wizard_id = fields.Many2one('stock.cut.confirm.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product')
    odoo_stock_qty = fields.Float(string='สต๊อกคงเหลือ', readonly=True)
    quantity = fields.Float(string='Quantity')
    location_name = fields.Char(string='Location')
