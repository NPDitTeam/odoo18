from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    campaign_id = fields.Many2one('utm.campaign', string='แคมเปญ')
    medium_id = fields.Many2one('utm.medium', string='สื่อ')
    source_id = fields.Many2one('utm.source', string='แหล่งที่มา')
    customer_channel_id = fields.Many2one(
        'customer.channel',
        string='ช่องทางลูกค้า',
        required=True,
    )
    freelance_salesperson_id = fields.Many2one(
        'res.partner',
        string='Freelance Salesperson',
    )

    @api.constrains('customer_channel_id')
    def _check_customer_channel(self):
        for order in self:
            if not order.customer_channel_id:
                raise ValidationError("กรุณาเลือกช่องทางลูกค้า!")
