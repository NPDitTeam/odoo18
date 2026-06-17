from odoo import fields, models


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    # ใช้แยกชุดเลขรันเอกสาร cash.payment ออกตามสาขา
    branch_id = fields.Many2one('res.branch', string='Branch', index=True)
