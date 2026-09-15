from odoo import fields, models


class AccountConditionType(models.Model):
    _name = 'account.condition.type'
    _description = 'Asset Condition Type'

    name = fields.Char('name')
    asset_id = fields.One2many(
        comodel_name='account.asset',
        inverse_name='std_condition_type_id',
        string='Asset',
    )
