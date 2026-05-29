from odoo import models, fields, api, _


class SaleObjective(models.Model):
    _name = 'sale.objective'
    _description = 'Sale Objective'

    name = fields.Char('Name')
