from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    type = fields.Selection(
        selection_add=[
            ('receivable', 'Receivable'),
            ('payable', 'Payable'),
        ],
        ondelete={
            'receivable': 'cascade',
            'payable': 'cascade',
        },
    )
