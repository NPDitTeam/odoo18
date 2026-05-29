# -*- coding: utf-8 -*-
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from io import BytesIO
from odoo import models, api, _

import logging

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError as e:
    _logger.debug(e)


class ReportSaleOrderExcel(models.TransientModel):
    _name = 'report.multi_branch_management_aagam.report_excel_sale_order'
    _description = ' Sale order excel report model'

    @api.model
    def generate_xlsx_report(self, workbook, data, wizard):
        
        bold = workbook.add_format({'bold': True})
        c_middle = workbook.add_format({'bold': True, 'top': 1})
        report_format = workbook.add_format(
            {'font_size': 20, 'align': 'center'})

        report = self.env.ref(
            'multi_branch_management_aagam.action_cash_flow_excelreport')

        for rec in wizard:
            yearly = True if wizard.report_period == 'year_report' else False
            sheet = workbook.add_worksheet(report.name)
            # headers for sheet
            sheet.merge_range(2, 0, 2, 7, report.name, report_format)
            sheet.set_row(2, 28)
            sheet.merge_range(4, 0, 4, 1, _('Company:'), bold)
            sheet.merge_range(4, 2, 4, 3, wizard.company_id.name)

            # sheet.merge_range(1, 0, 1, 1, _('Branch:'), bold)
            # sheet.merge_range(1, 2, 1, 3, wizard.branch_id.name)

        #     sheet.merge_range(5, 0, 5, 3,
        #                       _('Print on %s') % datetime.now().strftime(
        #                           DEFAULT_SERVER_DATE_FORMAT))
        #     years = rec.get_years(is_getdata=False)
        #     currency = _('Currency: %s' % (wizard.company_id.currency_id.name))
        #     sheet.merge_range(5, 4, 5, 5, currency, bold)
        #
        #     #
        #     sheet.merge_range(8, 0, 8, 1, _('Branch:'), bold)
        #     sheet.merge_range(8, 2, 8, 3, wizard.branch_id.name)
        #     #
        #
        #     if not yearly:
        #         sheet.merge_range(
        #             6, 0, 6, 2, 'Start Date: %s' % wizard.date_from, bold)
        #         sheet.merge_range(
        #             6, 3, 6, 5, 'End Date: %s' % wizard.date_to, bold)
        #     row_number = 9
        #     if yearly:
        #         if len(years) > 1:
        #             sheet.merge_range(
        #                 7, 5, 7, 4 + len(years), 'Yearly Balance',
        #                 workbook.add_format(
        #                     {'bold': True, 'align': 'center', 'bottom': 1}))
        #         for i in range(0, len(years)):
        #             sheet.write(row_number, i + 5, years[i], bold)
        #     else:
        #         sheet.write(row_number, 5, 'Balance', bold)
        #
        #     data = rec.get_data()
        #     row_number += 1
        #     sheet.write(row_number, 0, 'Operating Activities', bold)
        #     # operating income
        #     if data.get('operation_income', False):
        #         row_number += 1
        #         sheet.write(row_number, 1, 'Income', bold)
        #         for account in data['operation_income']['account']:
        #             row_number += 1
        #             account_details = rec.get_acc_details(account)
        #             account_no_nm = '%s %s' % (
        #                 account_details['ac_no'], account_details['ac_nm'])
        #             sheet.write(row_number, 1, account_no_nm)
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['operation_income'
        #                         ]['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5,
        #                     data['operation_income']['account'][account])
        #     # operating expense
        #     if data.get('operation_expense', False):
        #         row_number += 1
        #         sheet.write(row_number, 1, 'Expense', bold)
        #         for account in data['operation_expense']['account']:
        #             row_number += 1
        #             account_details = rec.get_acc_details(account)
        #             account_no_nm = '%s %s' % (
        #                 account_details['ac_no'], account_details['ac_nm'])
        #             sheet.write(row_number, 1, account_no_nm)
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['operation_expense'
        #                         ]['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5,
        #                     data['operation_expense']['account'][account])
        #     # current assets
        #     if data.get('operation_current_asset', False):
        #         row_number += 1
        #         sheet.write(row_number, 1, 'Current Assets', bold)
        #         for account in data['operation_current_asset']['account']:
        #             row_number += 1
        #             account_details = rec.get_acc_details(account)
        #             account_no_nm = '%s %s' % (
        #                 account_details['ac_no'], account_details['ac_nm'])
        #             sheet.write(row_number, 1, account_no_nm)
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['operation_current_asset'
        #                         ]['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5,
        #                     data['operation_current_asset'
        #                     ]['account'][account])
        #     # current liability
        #     if data.get('operation_current_liability', False):
        #         row_number += 1
        #         sheet.write(row_number, 1, 'Current Assets', bold)
        #         for account in data['operation_current_liability']['account']:
        #             row_number += 1
        #             account_details = rec.get_acc_details(account)
        #             account_no_nm = '%s %s' % (
        #                 account_details['ac_no'], account_details['ac_nm'])
        #             sheet.write(row_number, 1, account_no_nm)
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['operation_current_liability'
        #                         ]['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5,
        #                     data['operation_current_liability'
        #                     ]['account'][account])
        #     # operating activity - net cash
        #     row_number += 1
        #     sheet.write(
        #         row_number, 1, 'Net cash from operating activities', bold)
        #     if yearly:
        #         for i in range(0, len(years)):
        #             sheet.write(
        #                 row_number, i + 5,
        #                 rec.get_total(
        #                     data, years[i],
        #                     ['operation_current_asset',
        #                      'operation_current_liability', 'operation_income',
        #                      'operation_expense']), c_middle)
        #     else:
        #         sheet.write(
        #             row_number, 5,
        #             rec.get_total(
        #                 data, False,
        #                 ['operation_current_asset',
        #                  'operation_current_liability', 'operation_income',
        #                  'operation_expense']), c_middle)
        #     # investing activity
        #     if data.get('investing', False):
        #         row_number += 1
        #         sheet.write(row_number, 1, 'Investing Activities', bold)
        #         for account in data['investing']['account']:
        #             row_number += 1
        #             account_details = rec.get_acc_details(account)
        #             account_no_nm = '%s %s' % (
        #                 account_details['ac_no'], account_details['ac_nm'])
        #             sheet.write(row_number, 1, account_no_nm)
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['investing'
        #                         ]['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5,
        #                     data['investing']['account'][account])
        #         # investing activity - net cash
        #         row_number += 1
        #         sheet.write(
        #             row_number, 1, 'Net cash from investing activities', bold)
        #         if yearly:
        #             for i in range(0, len(years)):
        #                 sheet.write(
        #                     row_number, i + 5,
        #                     data['investing']['total'][years[i]], c_middle)
        #         else:
        #             sheet.write(
        #                 row_number, 5,
        #                 data['investing']['total'], c_middle)
        #     # finance activity
        #     if data.get('financing', False):
        #         row_number += 1
        #         sheet.write(row_number, 1, 'Financing Activities', bold)
        #         for account in data['financing']['account']:
        #             row_number += 1
        #             account_details = rec.get_acc_details(account)
        #             account_no_nm = '%s %s' % (
        #                 account_details['ac_no'], account_details['ac_nm'])
        #             sheet.write(row_number, 1, account_no_nm)
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['financing'
        #                         ]['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5,
        #                     data['financing']['account'][account])
        #         # investing activity - net cash
        #         row_number += 1
        #         sheet.write(
        #             row_number, 1, 'Net cash from financing activities', bold)
        #         if yearly:
        #             for i in range(0, len(years)):
        #                 sheet.write(
        #                     row_number, i + 5,
        #                     data['financing']['total'][years[i]])
        #         else:
        #             sheet.write(row_number, 5, data['financing']['total'])
        #     # net - operation, finance, investing
        #     row_number += 1
        #     sheet.merge_range(
        #         row_number, 0, row_number, 4,
        #         'Operating + Financing + Investing', c_middle)
        #     if yearly:
        #         for i in range(0, len(years)):
        #             sheet.write(
        #                 row_number, i + 5,
        #                 rec.get_total(
        #                     data, years[i],
        #                     ['operation_current_asset',
        #                      'operation_current_liability', 'operation_income',
        #                      'operation_expense', 'financing', 'investing']),
        #                 c_middle)
        #     else:
        #         sheet.write(
        #             row_number, 5,
        #             rec.get_total(
        #                 data, False,
        #                 ['operation_current_asset',
        #                  'operation_current_liability', 'operation_income',
        #                  'operation_expense', 'financing', 'investing']),
        #             c_middle)
        #     # cash
        #     row_number += 1
        #     if data.get('Cash', False):
        #         row_number += 1
        #         sheet.write(row_number, 0, 'Cash', bold)
        #         for account in data['Cash']['account']:
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['Cash']['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5, data['Cash']['account'][account])
        #     # bank
        #     if data.get('Bank', False):
        #         row_number += 1
        #         sheet.write(row_number, 0, 'Bank', bold)
        #         for account in data['Bank']['account']:
        #             if yearly:
        #                 for i in range(0, len(years)):
        #                     sheet.write(
        #                         row_number, i + 5,
        #                         data['Bank']['account'][account][years[i]])
        #             else:
        #                 sheet.write(
        #                     row_number, 5, data['Bank']['account'][account])

    @api.model
    def _get_objs_for_report(self, docids, data):
        """
        Returns objects for xlx report.  From WebUI these
        are either as docids taken from context.active_ids or
        in the case of wizard are in data.  Manual calls may rely
        on regular context, setting docids, or setting data.

        :param docids: list of integers, typically provided by
            qwebactionmanager for regular Models.
        :param data: dictionary of data, if present typically provided
            by qwebactionmanager for TransientModels.
        :param ids: list of integers, provided by overrides.
        :return: recordset of active model for ids.
        """
        if docids:
            ids = docids
        elif data and 'context' in data:
            ids = data["context"].get('active_ids', [])
        else:
            ids = self.env.context.get('active_ids', [])
        return self.env[self.env.context.get('active_model')].browse(ids)

    @api.model
    def create_xlsx_report(self, docids, data):
        objs = self._get_objs_for_report(docids, data)
        file_data = BytesIO()
        workbook = xlsxwriter.Workbook(file_data, self.get_workbook_options())
        self.generate_xlsx_report(workbook, data, objs)
        workbook.close()
        file_data.seek(0)
        return file_data.read(), 'xlsx'

    @api.model
    def get_workbook_options(self):
        """
        See https://xlsxwriter.readthedocs.io/workbook.html constructor options
        :return: A dictionary of options
        """
        return {}
