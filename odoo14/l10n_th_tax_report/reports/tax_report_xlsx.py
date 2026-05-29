# Copyright 2019 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

import logging

from odoo import models

from odoo.addons.report_xlsx_helper.report.report_xlsx_format import (
    FORMATS,
    XLS_HEADERS,
)

_logger = logging.getLogger(__name__)


class ReportTaxReportXlsx(models.TransientModel):
    _name = "report.l10n_th_tax_report.report_tax_report_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Tax Report Excel"

    def _get_ws_params(self, wb, data, objects):
        tax_template = {
            "1_index": {
                "header": {"value": "#"},
                "data": {"value": self._render("row_pos")},
                "width": 3,
            },
            "2_tax_date": {
                "header": {"value": "Date"},
                "data": {"value": self._render("tax_date")},
                "width": 12,
            },
            "3_tax_date": {
                "header": {"value": "Invoice"},
                "data": {"value": self._render("invoice")},
                "width": 12,
            },
            "4_tax_date": {
                "header": {"value": "Payment"},
                "data": {"value": self._render("payment")},
                "width": 18,
            },
            "5_tax_invoice": {
                "header": {"value": "Number"},
                "data": {"value": self._render("tax_invoice_number")},
                "width": 18,
            },
            "6_partner_name": {
                "header": {"value": "Cust./Sup."},
                "data": {"value": self._render("partner_name")},
                "width": 30,
            },
            "7_partner_vat": {
                "header": {"value": "Tax ID"},
                "data": {"value": self._render("partner_vat")},
                "width": 15,
            },
            "8_partner_branch": {
                "header": {"value": "Branch ID"},
                "data": {"value": self._render("partner_branch")},
                "width": 12,
            },
            "9_tax_base_amount": {
                "header": {"value": "Base Amount"},
                "data": {
                    "value": self._render("tax_base_amount"),
                    "format": FORMATS["format_tcell_amount_right"],
                },
                "width": 21,
            },
            "10_tax_amount": {
                "header": {"value": "Tax Amount"},
                "data": {
                    "value": self._render("tax_amount"),
                    "format": FORMATS["format_tcell_amount_right"],
                },
                "width": 21,
            },
            "11_doc_ref": {
                "header": {"value": "Doc Ref."},
                "data": {"value": self._render("doc_ref")},
                "width": 18,
            },
            "12_branch_name": {
                "header": {"value": "Branch"},
                "data": {"value": self._render("branch_name")},
                "width": 20,
            },
        }
        ws_params = {
            "ws_name": "TAX Report",
            "generate_ws_method": "_vat_report",
            "title": "TAX Report",
            "wanted_list": [k for k in sorted(tax_template.keys())],
            "col_specs": tax_template,
        }
        if any(tax.type_tax_use == "sale" for tax in objects.tax_id):

            ws_params["ws_name"] = "Sale TAX Report"
            ws_params["title"] = "Sale TAX Report"
        elif any(tax.type_tax_use == "purchase" for tax in objects.tax_id):

            ws_params["ws_name"] = "Purchase TAX Report"
            ws_params["title"] = "Purchase TAX Report"

        return [ws_params]

    def _vat_report(self, wb, ws, ws_params, data, objects):
        ws.set_portrait()
        ws.fit_to_pages(1, 0)
        ws.set_header(XLS_HEADERS["xls_headers"]["standard"])
        ws.set_footer(XLS_HEADERS["xls_footers"]["standard"])
        self._set_column_width(ws, ws_params)
        row_pos = 0
        # title
        row_pos = self._write_ws_title(ws, row_pos, ws_params, True)
        # company data
        ws.write_column(
            row_pos, 1, ["Period :", "Partner :"], FORMATS["format_left_bold"]
        )
        ws.write_column(
            row_pos,
            2,
            [
                (objects.date_range_id.display_name) or "",
                (objects.company_id.display_name) or "",
            ],
        )
        ws.write_column(
            row_pos, 5, ["Tax ID :", "Branch ID :"], FORMATS["format_left_bold"]
        )
        ws.write_column(
            row_pos,
            6,
            [
                (objects.company_id.partner_id.vat) or "",
                (objects.company_id.partner_id.branch) or "",
            ],
        )
        row_pos += 3
        # vat report table
        row_pos = self._write_line(
            ws,
            row_pos,
            ws_params,
            col_specs_section="header",
            default_format=FORMATS["format_theader_blue_left"],
        )
        ws.freeze_panes(row_pos, 0)
        for obj in objects:
            total_base = 0.00
            total_tax = 0.00
            for line in obj.results:
                total_base += line.tax_base_amount
                total_tax += line.tax_amount


                # 🔍 ดึง branch จาก account.move.ref ด้วยค่าใน line.name
                move_invoice = ''
                move_payment = ''
                move_branch = ''  # ค่าเริ่มต้นเป็นว่าง

                if line.tax_invoice_number:
                    move = self.env["account.move.tax.invoice"].search([("tax_invoice_number", "=", line.tax_invoice_number)], limit=1)
                    if move:
                        move_payment = move.payment_id.name
                        move_invoice = move.payment_id.search_invoice_name
                        move_branch = move.payment_id.branch_id.name


                if not move_branch:

                    if line.name:
                        move = self.env["account.move"].search([("ref", "=", line.name)], limit=1)
                        if move and move.branch_id:
                            move_branch = move.branch_id.name
                        # else:
                        #     _logger.warning("❗ ไม่พบ branch_id จาก ref: %s", line.name)
                    elif line.tax_invoice_number:
                        move = self.env["account.move"].search([("name", "=", line.tax_invoice_number)], limit=1)
                        if move and move.branch_id:
                            move_branch = move.branch_id.name

                row_pos = self._write_line(
                    ws,
                    row_pos,
                    ws_params,
                    col_specs_section="data",
                    render_space={
                        "row_pos": row_pos - 5,
                        "tax_date": line.tax_date or "",
                        "invoice": move_invoice,
                        "payment": move_payment,
                        "tax_invoice_number": line.tax_invoice_number or "",
                        "partner_name": line.partner_id.display_name or "",
                        "partner_vat": line.partner_id.vat or "",
                        "partner_branch": line.partner_id.branch or "",
                        "tax_base_amount": line.tax_base_amount or 0.00,
                        "tax_amount": line.tax_amount or 0.00,
                        "doc_ref": line.name or "",
                        "branch_name": move_branch,

                    },
                    default_format=FORMATS["format_tcell_left"],
                )
        ws.write_row(
            row_pos,
            6,
            [total_base, total_tax],
            FORMATS["format_theader_blue_amount_right"],
        )
