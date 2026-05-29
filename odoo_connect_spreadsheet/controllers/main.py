# -*- coding: utf-8 -*-
from odoo.addons.web.controllers.dataset import DataSet

from odoo import http
from odoo.http import request


class DataSetInherit(DataSet):
    def _call_kw_readonly(self):
        params = request.get_json_data()['params']
        try:
            model_class = request.registry[params['model']]
        except KeyError as e:
            raise NotFound() from e
        method_name = params['method']
        for cls in model_class.mro():
            method = getattr(cls, method_name, None)
            if method is not None and hasattr(method, '_readonly'):
                return method._readonly
        return False

    @http.route(['/web/dataset/call_kw', '/web/dataset/call_kw/<path:path>'], type='json', auth="user",
                readonly=_call_kw_readonly)
    def call_kw(self, model, method, args, kwargs, path=None):
        res = super(DataSetInherit, self).call_kw(model, method, args, kwargs, path=None)
        for spreadsheet in request.env['connect.spreadsheet'].search([('state', '=', 'active')]):
            if spreadsheet.update_type == 'realtime' and spreadsheet.model_id.model == model \
                    and method in ['web_save', 'unlink']:
                spreadsheet.sync_spreadsheet()
        return res

    @http.route(['/web/dataset/call_button', '/web/dataset/call_button/<path:path>'], type='json', auth="user",
                readonly=_call_kw_readonly)
    def call_button(self, model, method, args, kwargs, path=None):
        res = super(DataSetInherit, self).call_button(model, method, args, kwargs, path=None)
        for spreadsheet in request.env['connect.spreadsheet'].search([('state', '=', 'active')]):
            if spreadsheet.update_type == 'realtime' and spreadsheet.model_id.model == model:
                spreadsheet.sync_spreadsheet()
        return res
