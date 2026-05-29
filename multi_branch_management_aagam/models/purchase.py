# -*- coding: utf-8 -*-

from odoo import api, fields, _, models
import datetime
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True},  default=lambda self: self.env.user.branch_id.id)

    @api.onchange('user_id')
    def branch_ids_onchange(self):
        return {'domain': {'branch_id': [('id', 'in', self.user_id.multi_branch_id.ids)]}}

    @api.model
    def _prepare_picking(self):
        if not self.group_id:
            self.group_id = self.group_id.create({
                'name': self.name,
                'partner_id': self.partner_id.id
            })
        if not self.partner_id.property_stock_supplier.id:
            raise UserError(_("You must set a Vendor Location for this partner %s") % self.partner_id.name)
        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'user_id': False,
            'date': self.date_order,
            'origin': self.name,
            'location_dest_id': self._get_destination_location(),
            'location_id': self.partner_id.property_stock_supplier.id,
            'company_id': self.company_id.id,
            'branch_id': self.branch_id.id
        }

class PurchaseOrderLine(models.Model):
    """inherited purchase order line"""
    _inherit = 'purchase.order.line'

    branch_id = fields.Many2one(related='order_id.branch_id', string='Branch',
                                store=True)

class PurchaseReport(models.Model):
    """inherited purchase report"""
    _inherit = "purchase.report"

    branch_id = fields.Many2one('res.branch', 'Branch', readonly=True)

    def _select(self):
        """select"""
        return super(PurchaseReport, self)._select() + \
               ", spt.branch_id as branch_id"

    def _group_by(self):
        """group by"""
        return super(PurchaseReport, self)._group_by() + \
               ", spt.branch_id"
