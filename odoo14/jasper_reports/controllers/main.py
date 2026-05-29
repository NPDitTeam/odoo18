# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright (C) 2019-Today Serpent Consulting Services Pvt. Ltd.
#                         (<http://www.serpentcs.com>)
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# guarantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

import json
import logging

import werkzeug.exceptions
from werkzeug.urls import url_parse

from odoo import http
from odoo.addons.web.controllers.report import ReportController as WebReportController
from odoo.http import content_disposition, route, request
from odoo.tools.misc import html_escape
from odoo.tools.safe_eval import safe_eval, time

_logger = logging.getLogger(__name__)

class ReportController(WebReportController):

    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        if converter == 'jasper':
            report_jas = request.env[
                'ir.actions.report']._get_report_from_name(reportname)
            context = dict(request.env.context)
            # Force English so XML field labels match JRXML fieldDescriptions
            context['lang'] = 'en_US'
            if docids:
                docids = [int(i) for i in docids.split(',') if i.isdigit()]
            if data.get('options'):
                data.update(json.loads(data.pop('options')))
            if data.get('context'):
                data['context'] = json.loads(data['context'])
                if data['context'].get('lang'):
                    del data['context']['lang']
                context.update(data['context'])
            # Force English again after context merge
            context['lang'] = 'en_US'
            # Get the report and output type
            jasper, output_type = report_jas.with_context(
                context).render_jasper(docids, data=data)
            content_dict = {
                'pdf': 'application/pdf',
                'html': 'application/html',
                'csv': 'text/csv',
                'xls': 'application/xls',
                'rtf': 'application/octet-stream',
                'odt': 'application/vnd.oasis.opendocument.text',
                'ods': 'application/vnd.oasis.opendocument.spreadsheet',
                'txt': 'text/plain',
            }
            # Build filename from document name
            filename = "%s.%s" % (report_jas.name, output_type)
            if docids and report_jas.print_report_name:
                obj = request.env[report_jas.model].browse(docids)
                if len(obj) == 1:
                    try:
                        filename = "%s.%s" % (safe_eval(report_jas.print_report_name, {'object': obj, 'time': time}), output_type)
                    except Exception:
                        pass
            pdfhttpheaders = [
                ('Content-Type', content_dict.get(output_type)),
                ('Content-Length', len(jasper)),
                ('Content-Disposition', "inline; filename=\"%s\"; filename*=UTF-8''%s" % (
                    filename.encode('ascii', 'replace').decode('ascii'),
                    werkzeug.urls.url_quote(filename),
                )),
            ]
            return request.make_response(jasper, headers=pdfhttpheaders)
        return super(ReportController, self).report_routes(
            reportname, docids, converter, **data)


    @route()
    def report_download(self, data, context=None, token=None, readonly=True):
        """This function is used by 'action_manager_report.js' in order to trigger the download of
        a pdf/controller report.

        :param data: a javascript array JSON.stringified containg report internal url ([0]) and
        type [1]
        :returns: Response with a filetoken cookie and an attachment header
        """
        requestcontent = json.loads(data)
        url, type = requestcontent[0], requestcontent[1]
        if type == 'jasper':
            try:
                converter = 'jasper'
                extension = 'pdf'
                pattern = '/report/jasper/'
                    
                reportname = url.split(pattern)[1].split('?')[0]

                docids = None
                if '/' in reportname:
                    reportname, docids = reportname.split('/')

                if docids:
                    # Generic report:
                    response = self.report_routes(reportname, docids=docids, converter=converter, context=context)
                else:
                    # Particular report:
                    data = url_parse(url).decode_query(cls=dict)  # decoding the args represented in JSON
                    if 'context' in data:
                        context, data_context = json.loads(context or '{}'), json.loads(data.pop('context'))
                        context = json.dumps({**context, **data_context})
                    response = self.report_routes(reportname, converter=converter, context=context, **data)

                report = request.env['ir.actions.report']._get_report_from_name(reportname)
                extension = report.jasper_output or "pdf"
                filename = "%s.%s" % (report.name, extension)

                if docids:
                    ids = [int(x) for x in docids.split(",")]
                    obj = request.env[report.model].browse(ids)
                    if report.print_report_name and not len(obj) > 1:
                        report_name = safe_eval(report.print_report_name, {'object': obj, 'time': time})
                        filename = "%s.%s" % (report_name, extension)
                response.headers.add('Content-Disposition', content_disposition(filename))
                return response
            except Exception as e:
                _logger.warning("Error while generating jasper report %s", reportname, exc_info=True)
                se = http.serialize_exception(e)
                error = {
                    'code': 200,
                    'message': "Odoo Server Error",
                    'data': se
                }
                res = request.make_response(html_escape(json.dumps(error)))
                raise werkzeug.exceptions.InternalServerError(response=res) from e
        else:
            return super(ReportController, self).report_download(data, context=context, token=token)

