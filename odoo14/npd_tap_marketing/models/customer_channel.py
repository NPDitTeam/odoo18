from odoo import fields, models


class CustomerChannel(models.Model):
    _name = 'customer.channel'
    _description = 'ช่องทางลูกค้า'
    _order = 'sequence, id'

    name = fields.Char(string='ชื่อช่องทาง', required=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    active = fields.Boolean(string='ใช้งาน', default=True)
