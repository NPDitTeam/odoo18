# -*- coding: utf-8 -*-
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    id_card = fields.Char(string='เลขบัตรประชาชน', size=13)
