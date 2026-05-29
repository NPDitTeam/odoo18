# Copyright 2019 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import fields, models, api
from odoo.tools.safe_eval import safe_eval
import io
import xlsxwriter
import logging
import base64
from urllib.parse import quote_plus

_logger = logging.getLogger(__name__)


class TaxReportWizard(models.TransientModel):
    _name = "tax.report.wizard"
    _description = "Wizard for Tax Report"

    # Search Criteria
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        string="Company",
        required=True,
        ondelete="cascade",
    )
    tax_group_id = fields.Many2one(
        comodel_name="account.tax.group",
        string="Tax Group",
        required=True,
    )
    tax_id = fields.Many2many(comodel_name="account.tax",
                              required=True, )

    date_range_id = fields.Many2one(
        comodel_name="date.range", string="Period", required=True
    )
    branch_id = fields.Many2one('res.branch', string='Branch')

    # New fields for storing generated report data temporarily
    report_file = fields.Binary(string="Report File", readonly=True)
    report_file_name = fields.Char(string="Report File Name")

    @api.onchange('tax_group_id')
    def _set_tex_id(self):
        for rec in self:
            rec.tax_id = False
            if rec.tax_group_id:
                tax = rec.env['account.tax'].search([('tax_group_id', '=', rec.tax_group_id.id), ('active', '=', True)])
                if tax:
                    rec.write({'tax_id': [(6, 0, tax.ids)]})

    def button_export_html(self):
        """Odoo 18: เปิดเป็น list view แทน HTML preview (legacy JS ไม่รองรับ)"""
        model = self.env["report.tax.report"]
        report = model.create(self._prepare_tax_report())
        # บังคับ compute เพื่อสร้างข้อมูล
        report._compute_results()
        result_ids = report.results.ids
        return {
            'name': 'TAX Report - %s' % (self.date_range_id.display_name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'tax.report.view',
            'view_mode': 'list',
            'domain': [('id', 'in', result_ids)],
            'target': 'current',
            'context': {'create': False, 'edit': False},
        }

    def button_export_pdf(self):

        report_type = "qweb-pdf"
        return self._export(report_type)

    def _generate_excel_report(self, is_test_report=False):
        """
        Helper method to generate the XLSX report using xlsxwriter.
        This logic is shared between button_export_xlsx and button_export_test_xlsx.
        """
        _logger.info("Starting _generate_excel_report process. Is test report: %s", is_test_report)
        report_values = self._prepare_tax_report()
        _logger.info("Report values prepared: %s", report_values)

        output = io.BytesIO()
        try:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})

            # กำหนดชื่อ Sheet ตามประเภทรายงาน
            sheet_name = 'Tax Report Test' if is_test_report else 'Tax Report'
            sheet = workbook.add_worksheet(sheet_name)

            text_format = workbook.add_format({'align': 'left'})
            currency_format = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
            header_format = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#D3D3D3'})

            row = 0
            col = 0

            # Title
            report_title = "VAT Report"
            tax_use = None
            if report_values.get('tax_id'):
                taxes = self.env['account.tax'].browse(report_values['tax_id'])
                if taxes:
                    tax_use = taxes[0].type_tax_use
                    if tax_use == 'sale':
                        report_title = "Sale VAT Report"
                    elif tax_use == 'purchase':
                        report_title = "Purchase VAT Report"

            # ปรับ Title ตาม is_test_report
            if is_test_report:
                report_title = "Test " + report_title

            sheet.merge_range(row, 0, row, 9, report_title,
                              workbook.add_format({'bold': True, 'align': 'center', 'font_size': 14}))
            row += 2

            # Filters
            sheet.write(row, col, 'Period', header_format)
            sheet.write(row, col + 1, 'Partner', header_format)
            sheet.write(row, col + 2, 'Tax ID', header_format)
            sheet.write(row, col + 3, 'Branch ID', header_format)
            row += 1

            date_range_display_name = self.env['date.range'].browse(
                report_values.get('date_range_id')).display_name if report_values.get('date_range_id') else ''
            company_name = self.env['res.company'].browse(
                report_values.get('company_id')).display_name if report_values.get('company_id') else ''
            company_partner = self.env['res.company'].browse(
                report_values.get('company_id')).partner_id if report_values.get('company_id') else False
            company_vat = company_partner.vat if company_partner else ''
            company_branch = company_partner.branch if company_partner else ''

            sheet.write(row, col, date_range_display_name, text_format)
            sheet.write(row, col + 1, company_name, text_format)
            sheet.write(row, col + 2, company_vat, text_format)
            sheet.write(row, col + 3, company_branch, text_format)
            row += 2

            # Detailed Report Data
            report_obj = self.env["report.tax.report"].create(report_values)
            _logger.info("Report object created: %s", report_obj)
            report_obj._compute_results()
            _logger.info("Report results computed.")

            # Get actual report lines (results)
            results_lines = report_obj.results
            _logger.info("Number of result lines: %s", len(results_lines))

            for tax in self.env['account.tax'].browse(report_values['tax_id']):
                tax_name = tax.name
                sheet.write(row, col, '', text_format)
                sheet.merge_range(row, col + 1, row, col + 9, tax_name,
                                  workbook.add_format({'bold': True, 'align': 'left', 'font_size': 12}))
                row += 1

                # Header Line for details
                sheet.write(row, col, '#', header_format)
                sheet.write(row, col + 1, 'Date', header_format)
                sheet.write(row, col + 2, 'Invoice', header_format)
                sheet.write(row, col + 3, 'Payment', header_format)
                sheet.write(row, col + 4, 'Number', header_format)
                sheet.write(row, col + 5, 'Cust./Sup.', header_format)
                sheet.write(row, col + 6, 'Tax ID', header_format)
                sheet.write(row, col + 7, 'Branch ID', header_format)
                sheet.write(row, col + 8, 'Base Amount', header_format)
                sheet.write(row, col + 9, 'Tax Amount', header_format)
                sheet.write(row, col + 10, 'Doc Ref.', header_format)
                sheet.write(row, col + 11, 'Branch', header_format)
                row += 1

                line_num = 1
                total_base = 0.0
                total_tax = 0.0

                move_invoice = ''
                move_payment = ''
                move_branch = ''  # ค่าเริ่มต้นเป็นว่าง

                for line in results_lines:
                    if line.tax_id.id == tax.id:
                        sheet.write(row, col, line_num, text_format)
                        sheet.write(row, col + 1, line.tax_date, text_format)

                        if line.tax_invoice_number:
                            move = self.env["account.move.tax.invoice"].search(
                                [("tax_invoice_number", "=", line.tax_invoice_number)], limit=1)
                            if move:
                                move_payment = move.payment_id.name
                                move_invoice = move.payment_id.search_invoice_name
                                move_branch = move.payment_id.branch_id.name

                        sheet.write(row, col + 2, move_invoice, text_format)
                        sheet.write(row, col + 3, move_payment, text_format)
                        sheet.write(row, col + 4, line.tax_invoice_number, text_format)
                        sheet.write(row, col + 5, line.partner_id.display_name, text_format)
                        sheet.write(row, col + 6, line.partner_id.vat or '', text_format)
                        sheet.write(row, col + 7, line.partner_id.branch or '', text_format)
                        sheet.write(row, col + 8, line.tax_base_amount, currency_format)
                        sheet.write(row, col + 9, line.tax_amount, currency_format)
                        sheet.write(row, col + 10, line.name or '', text_format)

                        if move_branch:
                            sheet.write(row, col + 11, move_branch, text_format)

                        else:
                            move_obj = False
                            if line.name:
                                move_obj = self.env['account.move'].search([('ref', '=', line.name)], limit=1)
                            if not move_obj and line.tax_invoice_number:
                                move_obj = self.env['account.move'].search([('name', '=', line.tax_invoice_number)],
                                                                           limit=1)

                            branch_name_from_move = move_obj.branch_id.name if move_obj and move_obj.branch_id else ''
                            sheet.write(row, col + 11, branch_name_from_move, text_format)

                        line_num += 1
                        total_base += line.tax_base_amount
                        total_tax += line.tax_amount
                        row += 1

                # Total Line
                sheet.write(row, col + 6, 'Total:', header_format)
                sheet.write(row, col + 7, total_base, currency_format)
                sheet.write(row, col + 8, total_tax, currency_format)
                sheet.write(row, col + 9, '', text_format)
                row += 2

            workbook.close()
            output.seek(0)
            xlsx_data = output.read()
            _logger.info("Excel data size: %s bytes", len(xlsx_data))

            return xlsx_data  # Return the binary data

        except Exception as e:
            _logger.error("Error creating Excel report: %s", e, exc_info=True)
            raise

    def _get_report_action(self, is_test_report=False):
        """Helper to generate and prepare the report data for download."""
        xlsx_data = self._generate_excel_report(is_test_report=is_test_report)
        report_name = 'Tax Report {} - {}.xlsx'.format(
            'Test' if is_test_report else '',
            self.date_range_id.display_name.replace(' ', '_')
        )

        # Store the binary data in the transient wizard instance
        self.write({
            'report_file': base64.b64encode(xlsx_data),
            'report_file_name': report_name,
        })

        # Return an action to download the file directly from the wizard
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/{}/{}/{}'.format(
                self._name, self.id, 'report_file'
            ),
            'target': 'new',
        }

    def button_export_xlsx(self):
        """
        This button now generates the Excel report and prepares it for download
        using the standard Odoo /web/content route.
        """
        return self._get_report_action(is_test_report=False)

    def button_export_test_xlsx(self):
        """
        This button generates the Test Excel report and prepares it for download
        using the standard Odoo /web/content route.
        """
        return self._get_report_action(is_test_report=True)

    def _prepare_tax_report(self):

        values = {
            "company_id": self.company_id.id,
            "tax_id": self.tax_id.ids,
            "date_range_id": self.date_range_id.id,
            "date_from": self.date_range_id.date_start,
            "date_to": self.date_range_id.date_end,
            "branch_id": self.branch_id.id,
        }
        print("📋 Tax Report Values:", values)
        return values

    def _export(self, report_type):
        # This method is now primarily for PDF export, as XLSX is handled by _generate_excel_report
        model = self.env["report.tax.report"]
        report = model.create(self._prepare_tax_report())
        print("📌 สร้างรายงานใหม่ >> ID=%s Branch=%s" % (report.id, report.branch_id.name))
        return report.print_report(report_type)