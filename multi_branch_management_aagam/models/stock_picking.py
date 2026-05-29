# -*- coding: utf-8 -*-

from odoo import  fields, models,api


class StockPicking(models.Model):
    _inherit = "stock.picking"

    branch_id = fields.Many2one("res.branch", string='Branch', help='The default branch for this user.',
                                context={'user_preference': True}, default=lambda self: self.env.user.branch_id.id)

    branch_loc_ids = fields.Many2many('stock.location',compute="get_branch_locations")

class StockLocation(models.Model):
    _inherit = "stock.location"
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if 'branch_axis' in self._context:
            branchid = self._context.get('branch_axis')
            branch = self.env['res.branch'].browse(branchid)
            loc_list=[]
            for warehouse in branch.warehouse_ids:
                context = dict(self._context)
                if 'branch_axis' in self._context:
                    context.pop('branch_axis')
                self = self.with_context(context)
                locids = self.env['stock.location'].search([('warehouse_id','=',warehouse.id)]).ids
                loc_list.extend(locids)
                args=[('id','in',loc_list)]
        # return super()._search(args, offset, limit, order, count, access_rights_uid)
        return super()._search(args, offset, limit, order)


class ProcurementGroup(models.Model):
    _inherit = 'procurement.group'

    branch_id = fields.Many2one('res.branch', 'Branch',  default=lambda self: self.env.user.branch_id.id)

