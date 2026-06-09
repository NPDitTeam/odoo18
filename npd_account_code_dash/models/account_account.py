# -*- coding: utf-8 -*-
import re

from odoo import api, models, _
from odoo.exceptions import ValidationError

# Same as the core regex (odoo.addons.account.models.account_account.ACCOUNT_CODE_REGEX)
# but also allows the dash "-", so codes migrated from Odoo 14 such as "1111-00"
# remain valid.
ACCOUNT_CODE_REGEX_WITH_DASH = re.compile(r'^[A-Za-z0-9.\-]+$')


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.constrains('code')
    def _check_account_code(self):
        # Overrides the core constraint of the same name. Because Odoo keys
        # @api.constrains methods by name, this fully replaces the stricter core
        # check rather than running in addition to it.
        for account in self:
            if account.code and not ACCOUNT_CODE_REGEX_WITH_DASH.match(account.code):
                raise ValidationError(_(
                    "The account code can only contain alphanumeric characters, "
                    "dots and dashes."
                ))
