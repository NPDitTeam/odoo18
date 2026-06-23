from odoo import fields, models, api, _


class AIVerifyWizard(models.TransientModel):
    _name = 'ai.verify.wizard'
    _description = 'AI Verification Result Wizard'

    advance_clear_id = fields.Many2one(
        'account.advance.clear',
        string='Advance Clear',
        readonly=True,
    )
    result_html = fields.Html(
        string='Verification Result',
        readonly=True,
        sanitize=False,
    )
    is_pass = fields.Boolean(
        string='Passed',
        default=False,
        readonly=True,
    )
    raw_response = fields.Text(
        string='Raw AI Response',
        readonly=True,
    )

    def action_close(self):
        """Close the wizard."""
        return {'type': 'ir.actions.act_window_close'}
