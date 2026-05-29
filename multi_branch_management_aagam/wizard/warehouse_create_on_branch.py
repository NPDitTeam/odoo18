# -*- coding: utf-8 -*-
import datetime
from datetime import timedelta
import calendar
from odoo import models, fields, api


class WarehouseBranch(models.TransientModel):
    _name = "wizard.warehouse.branch"
    _description = "Branch Warehouses"

    name = fields.Char(string="Name",required=1)
    code = fields.Char(string="Code",required=1)

    def action_confirm(self):
        active_ids = self.env.context.get('active_ids', [])
        branch_id = self.env['res.branch'].browse(active_ids)
        warehouse_id = self.env['stock.warehouse'].create({
            'name': self.name,
            'code': self.code,
            'branch_id': branch_id.id,
        })