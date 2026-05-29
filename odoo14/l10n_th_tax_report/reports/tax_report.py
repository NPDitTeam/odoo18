# Copyright 2019 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models
from odoo import http
from odoo.http import request
import base64
import json
import werkzeug


class TaxReportView(models.TransientModel):
    _name = "tax.report.view"
    _description = "Tax Report View"
    _order = "id"

    name = fields.Char()
    company_id = fields.Many2one("res.company")
    account_id = fields.Many2one("account.account")
    partner_id = fields.Many2one("res.partner")
    tax_id = fields.Many2one("account.tax")
    tax_base_amount = fields.Float()
    tax_amount = fields.Float()
    tax_date = fields.Char()
    tax_invoice_number = fields.Char()
    move_id = fields.Many2one("account.move", string="Journal Entry")
    branch_id = fields.Many2one("res.branch")


class TaxReport(models.TransientModel):
    _name = "report.tax.report"
    _description = "Report Tax Report"

    # Filters fields, used for data computation
    company_id = fields.Many2one(comodel_name="res.company")
    tax_id = fields.Many2many(comodel_name="account.tax")
    date_range_id = fields.Many2one(comodel_name="date.range")
    date_from = fields.Date()
    date_to = fields.Date()
    branch_id = fields.Many2one("res.branch", store=False)

    # Data fields, used to browse report data
    results = fields.Many2many(
        comodel_name="tax.report.view",
        compute="_compute_results",
        help="Use compute fields, so there is nothing store in database",
    )

    def _compute_results(self):
        self.ensure_one()
        print('taxxxxxxxxxxxxx')
        print(tuple(self.tax_id.ids))
        print(tuple(self.tax_id.ids))
        print(self.date_from)
        print(self.date_to)
        print(self.company_id.id)
        self._cr.execute(
            """
            select company_id, account_id, partner_id,
                tax_invoice_number, tax_date, name,
                sum(tax_base_amount) tax_base_amount, sum(tax_amount) tax_amount ,tax_id
            from (
            select t.id, t.company_id, ml.account_id, t.partner_id,
              case when ml.parent_state = 'posted' and t.reversing_id is null
                then t.tax_invoice_number else
                t.tax_invoice_number || ' (VOID)' end as tax_invoice_number,
              t.tax_invoice_date as tax_date,
              case when ml.parent_state = 'posted' and t.reversing_id is null
                then t.tax_base_amount else 0.0 end as tax_base_amount,
              case when ml.parent_state = 'posted' and t.reversing_id is null
                then t.balance else 0.0 end as tax_amount,
              case when m.ref is not null
                then m.ref else ml.move_name end as name,
                ml.tax_line_id as tax_id
            from account_move_tax_invoice t
              join account_move_line ml on ml.id = t.move_line_id
              join account_move m on m.id = ml.move_id
            where ml.parent_state in ('posted', 'cancel')
              and t.tax_invoice_number is not null
              and ml.account_id in (select distinct account_id
                                    from account_tax_repartition_line
                                    where account_id is not null
                                    and invoice_tax_id in %s or refund_tax_id in %s)
              and t.report_date >= %s and t.report_date <= %s
              and ml.company_id = %s
              and t.reversed_id is null
            ) a
            group by company_id, account_id, partner_id,
                tax_invoice_number, tax_date, name, tax_id
            order by tax_date, tax_invoice_number
        """,
            (
                tuple(self.tax_id.ids),
                tuple(self.tax_id.ids),
                self.date_from,
                self.date_to,
                self.company_id.id,
            ),
        )
        tax_report_results = self._cr.dictfetchall()
        ReportLine = self.env["tax.report.view"]
        self.results = False
        for line in tax_report_results:
            self.results += ReportLine.new(line)

    def print_report(self, report_type="qweb"):
        self.ensure_one()
        action = (
                report_type == "xlsx"
                and self.env.ref("l10n_th_tax_report.action_tax_report_xlsx")
                or self.env.ref("l10n_th_tax_report.action_tax_report_pdf")
        )
        return action.report_action(self, config=False)

    def _get_html(self):
        result = {}
        rcontext = {}
        context = dict(self.env.context)
        report = self.browse(context.get("active_id"))
        if report:
            rcontext["o"] = report
            result["html"] = self.env.ref(
                "l10n_th_tax_report.report_tax_report_html"
            )._render(rcontext)
        return result

    @api.model
    def get_html(self, given_context=None):
        return self.with_context(given_context)._get_html()


# NEW: สร้าง Controller สำหรับดาวน์โหลดไฟล์ Binary
class BinaryDownloadController(http.Controller):
    # เปลี่ยน methods เป็น GET เพื่อให้รองรับ ir.actions.act_url ที่ส่ง query parameters มา
    # หรือ ถ้ายังต้องการ POST ก็ต้องรับค่าจาก request.params หรือ request.httprequest.form
    # แต่ ir.actions.act_url จะใช้ GET หรือ POST ก็ได้ตามที่ระบุใน URL pattern
    @http.route('/l10n_th_tax_report/download_binary_file', type='http', auth="user", methods=["GET", "POST"])
    def download_binary_file(self, filename, data, **kw):
        # เมื่อใช้ ir.actions.act_url ข้อมูลจะมาใน query string (สำหรับ GET)
        # หรือ form data (สำหรับ POST)
        # เราสามารถเข้าถึงได้จาก request.params
        filename = request.params.get('filename')
        data = request.params.get('data')

        if not filename or not data:
            # จัดการกรณีไม่มีพารามิเตอร์ที่จำเป็น
            return request.not_found()

        try:
            decoded_data = base64.b64decode(data)
            headers = [
                ('Content-Type', 'application/octet-stream'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
                ('Content-Length', len(decoded_data)),
            ]
            response = request.make_response(decoded_data, headers)
            return response
        except Exception as e:
            # บันทึกข้อผิดพลาดและส่งการตอบกลับที่เหมาะสม
            request.env['ir.logging'].sudo().log(
                'l10n_th_tax_report', 'error', 'Error in download_binary_file: %s' % e,
                'tax_report_controller'
            )
            return request.not_found() # หรือการตอบกลับข้อผิดพลาดที่เฉพาะเจาะจงมากขึ้น