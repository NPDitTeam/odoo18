from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    is_payment_multi = fields.Boolean(
        string='Multi Payment', default=False,
    )
    pfb_so_type = fields.Selection([
        ('sale', 'Sale'),
        ('rent', 'Rent'),
        ('other', 'Other'),
    ], string='SO Type')

    pfb_objective_id = fields.Many2one(
        'sale.objective', string='Objective',
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        """Override to pass custom fields to payment creation."""
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals.update({
            'is_payment_multi': self.is_payment_multi,
            'pfb_so_type': self.pfb_so_type,
            'pfb_objective_id': self.pfb_objective_id.id if self.pfb_objective_id else False,
        })
        return vals
