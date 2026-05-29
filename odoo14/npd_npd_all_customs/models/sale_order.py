from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    npd_so_type = fields.Selection([
        ('sale', 'Sales'),
        ('rent', 'Rent')],
        string="Sale Type",
        index=True, default='sale', required=True)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    npd_so_rent_ok = fields.Boolean('Can be Rent', compute="_compute_so_rent_ok", store=True)

    @api.depends('order_id', 'order_id.npd_so_type')
    def _compute_so_rent_ok(self):
        for so_line in self:
            so_line.npd_so_rent_ok = so_line.order_id.npd_so_type == 'rent'
