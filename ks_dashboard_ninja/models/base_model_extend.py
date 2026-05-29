# -*- coding: utf-8 -*-

from odoo import models, api


class BaseExtend(models.AbstractModel):
    _inherit = 'base'

    # TODO: add condition to check if the any DN channel is active or not

    @api.model_create_multi
    def create(self, vals):
        recs = super(BaseExtend, self).create(vals)
        if 'ir.' not in self._name and 'bus.' not in self._name and self.env.user and self.env.user.has_group('base.group_user'):
            self.env['bus.bus']._sendone('ks_notification', 'Update: Dashboard Items', {'model': self._name})
        return recs

    def write(self, vals):
        recs = super(BaseExtend, self).write(vals)
        if 'ir.' not in self._name and 'bus.' not in self._name and self.env.user and self.env.user.has_group('base.group_user') and 'res.partner' not in self._name:
            self.env['bus.bus']._sendone('ks_notification', 'Update: Dashboard Items', {'model': self._name})
        return recs