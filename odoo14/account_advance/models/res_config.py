from odoo import models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    advance_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Advance Account",
    )
    advance_journal_id = fields.Many2one(
        "account.journal",
        index=True,
        string="Advance Journal",
        required=False,
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    advance_account_id = fields.Many2one(
        comodel_name="account.account",
        related="company_id.advance_account_id",
        string="Advance Account",
        readonly=False,
    )
    advance_journal_id = fields.Many2one(
        comodel_name="account.journal",
        related="company_id.advance_journal_id",
        string="Advance Journal",
        readonly=False,
    )
