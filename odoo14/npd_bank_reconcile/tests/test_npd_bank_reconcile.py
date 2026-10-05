# -*- coding: utf-8 -*-
import base64
import io

import openpyxl

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

HEADER = ['วันที่', 'เวลา', 'รายละเอียด', 'ถอนเงิน', 'ฝากเงิน', 'ยอดคงเหลือ']
OCA_FIXTURES = 'account_statement_import_sheet_file/tests/fixtures/'


def _xlsx_bytes(rows):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class NpdBankReconcileCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        # แบบจับคู่/แนะนำที่มากับผังจะกระทบยอดเองตอนนำเข้า หรือเติมคู่รายการไว้ก่อน
        # (_add_account_move_line ของ OCA กดซ้ำ = เอาออก) ทำให้ผลทดสอบไม่นิ่ง
        cls.env['account.reconcile.model'].search([
            ('company_id', '=', cls.company.id),
            ('rule_type', '!=', 'writeoff_button'),
        ]).active = False
        cls.Account = cls.env['account.account']
        cls.Journal = cls.env['account.journal']
        cls.Mapping = cls.env['account.statement.import.sheet.mapping']
        cls.Statement = cls.env['account.bank.statement']
        cls.StLine = cls.env['account.bank.statement.line']
        cls.Wizard = cls.env['account.statement.import']
        cls.npd_suspense = cls.Account.create({
            'code': 'NPD1199',
            'name': 'บัญชีพักธนาคาร',
            'account_type': 'asset_current',
        })

    def _import(self, data, filename, mapping, journal, button='import_file_button'):
        # account_statement_import_sheet_file_test: ให้ error จริงหลุดออกมา ไม่ถูกห่อเป็น UserError
        wizard = self.Wizard.with_context(account_statement_import_sheet_file_test=True).create({
            'statement_filename': filename,
            'statement_file': base64.b64encode(data),
            'sheet_mapping_id': mapping.id,
            'npd_journal_id': journal.id,
        })
        return getattr(wizard, button)()


@tagged('post_install', '-at_install')
class TestNpdBankReconcile(NpdBankReconcileCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.Journal.create({
            'name': 'NPD Test Bank',
            'type': 'bank',
            'code': 'NPDB1',
            'suspense_account_id': cls.npd_suspense.id,
        })
        # ใช้ค่าตั้งต้นแบบไทยของโมดูล (คั่นพันด้วยจุลภาค, dd/mm/yyyy, แยกฝาก/ถอน)
        cls.mapping = cls.Mapping.create({
            'name': 'NPD KBank test',
            'header_lines_skip_count': 1,
            'timestamp_column': 'วันที่',
            'description_column': 'รายละเอียด',
            'amount_debit_column': 'ฝากเงิน',
            'amount_credit_column': 'ถอนเงิน',
            'balance_column': 'ยอดคงเหลือ',
        })
        cls.journal.default_sheet_mapping_id = cls.mapping

    def _statement(self):
        return self.Statement.search([('journal_id', '=', self.journal.id)])

    def _lines(self):
        return self.StLine.search([('journal_id', '=', self.journal.id)])

    def _imp(self, data, filename, mapping=None):
        return self._import(data, filename, mapping or self.mapping, self.journal)

    # ---------------------------------------------------------------- ค่าตั้งต้น
    def test_00_thai_mapping_defaults(self):
        self.assertEqual(self.mapping.float_thousands_sep, 'comma')
        self.assertEqual(self.mapping.float_decimal_sep, 'dot')
        self.assertEqual(self.mapping.file_encoding, 'utf-8-sig')
        self.assertEqual(self.mapping.timestamp_format, '%d/%m/%Y')
        self.assertEqual(self.mapping.amount_type, 'distinct_credit_debit')
        encodings = dict(self.Mapping._fields['file_encoding'].selection)
        self.assertIn('cp874', encodings)

    # ------------------------------------------------------- (1) XLSX ไทย พ.ศ.
    def test_01_xlsx_thai_be_newest_first(self):
        data = _xlsx_bytes([
            HEADER,
            ['03/10/2569', '09:00', 'ค่าธรรมเนียม', 25, None, 1975],
            ['02/10/2569', '15:00', 'ถอนเงินสด', 500, None, 2000],
            ['02/10/2569', '10:00', 'รับโอน', None, 1500, 2500],
        ])
        self._imp(data, 'kbank.xlsx')
        statement = self._statement()
        self.assertEqual(len(statement), 1)
        self.assertEqual(len(statement.line_ids), 3)
        by_ref = {line.payment_ref: line for line in statement.line_ids}
        self.assertEqual(by_ref['รับโอน'].amount, 1500.0)
        self.assertEqual(by_ref['ถอนเงินสด'].amount, -500.0)
        self.assertEqual(by_ref['ค่าธรรมเนียม'].amount, -25.0)
        self.assertEqual(by_ref['รับโอน'].date, fields.Date.to_date('2026-10-02'))
        self.assertEqual(by_ref['ค่าธรรมเนียม'].date, fields.Date.to_date('2026-10-03'))
        self.assertAlmostEqual(statement.balance_start, 1000.0)
        self.assertAlmostEqual(statement.balance_end_real, 1975.0)
        self.assertTrue(all(line.unique_import_id for line in statement.line_ids))

    def test_02_same_day_newest_first_detected_by_balance(self):
        data = _xlsx_bytes([
            HEADER,
            ['02/10/2569', None, 'ถอนเงินสด', 500, None, 2000],
            ['02/10/2569', None, 'รับโอน', None, 1500, 2500],
        ])
        self._imp(data, 'same_day.xlsx')
        statement = self._statement()
        self.assertAlmostEqual(statement.balance_start, 1000.0)
        self.assertAlmostEqual(statement.balance_end_real, 2000.0)

    # ----------------------------------------------------- (2) CSV TIS-620
    def test_03_csv_cp874_be_leap_day(self):
        mapping = self.mapping.copy({'name': 'NPD TIS-620', 'file_encoding': 'cp874'})
        data = (
            'วันที่,รายละเอียด,ถอนเงิน,ฝากเงิน,ยอดคงเหลือ\r\n'
            '29/02/2567,รับโอน,,"1,000.00","1,000.00"\r\n'
        ).encode('cp874')
        self._imp(data, 'ktb.csv', mapping)
        line = self._lines()
        self.assertEqual(len(line), 1)
        self.assertEqual(line.date, fields.Date.to_date('2024-02-29'))
        self.assertEqual(line.amount, 1000.0)
        self.assertEqual(line.payment_ref, 'รับโอน')

    # ------------------------------------------------------ (3) นำเข้าซ้ำ
    def test_04_reimport_same_file_is_refused(self):
        data = _xlsx_bytes([
            HEADER,
            ['02/10/2569', None, 'รับโอน', None, 1500, 2500],
            ['02/10/2569', None, 'ถอนเงินสด', 500, None, 2000],
        ])
        self._imp(data, 'a.xlsx')
        count = len(self._lines())
        with self.assertRaisesRegex(UserError, 'already imported'):
            self._imp(data, 'a.xlsx')
        self.assertEqual(len(self._lines()), count)

    def test_05_overlapping_file_imports_only_new_rows(self):
        first = _xlsx_bytes([
            HEADER,
            ['02/10/2569', None, 'รับโอน', None, 1500, 2500],
        ])
        second = _xlsx_bytes([
            HEADER,
            ['02/10/2569', None, 'รับโอน', None, 1500, 2500],
            ['03/10/2569', None, 'ถอนเงินสด', 500, None, 2000],
        ])
        self._imp(first, 'w1.xlsx')
        self._imp(second, 'w2.xlsx')
        self.assertEqual(len(self._lines()), 2)

    # ---------------------------------------- (4) รายการหน้าตาเหมือนกันในวันเดียว
    def test_06_identical_rows_with_different_balance(self):
        data = _xlsx_bytes([
            HEADER,
            ['05/10/2569', None, 'ค่าธรรมเนียม', 10, None, 990],
            ['05/10/2569', None, 'ค่าธรรมเนียม', 10, None, 980],
        ])
        self._imp(data, 'twins.xlsx')
        lines = self._lines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(set(lines.mapped('unique_import_id'))), 2)

    def test_07_identical_rows_without_balance_column(self):
        mapping = self.mapping.copy({'name': 'NPD no balance', 'balance_column': False})
        data = _xlsx_bytes([
            HEADER,
            ['05/10/2569', None, 'ค่าธรรมเนียม', 10, None, None],
            ['05/10/2569', None, 'ค่าธรรมเนียม', 10, None, None],
        ])
        self._imp(data, 'twins_nobal.xlsx', mapping)
        self.assertEqual(len(self._lines()), 2)
        with self.assertRaises(UserError):
            self._imp(data, 'twins_nobal.xlsx', mapping)
        self.assertEqual(len(self._lines()), 2)

    # ------------------------------------------------- (5) ตรวจก่อนนำเข้า
    def test_08_wizard_prechecks_in_thai(self):
        wizard = self.Wizard.create({
            'statement_filename': 'x.csv',
            'statement_file': base64.b64encode(b'x'),
            'sheet_mapping_id': self.mapping.id,
        })
        with self.assertRaisesRegex(UserError, 'กรุณาเลือกสมุดบัญชีธนาคาร'):
            wizard.import_file_button()
        no_suspense = self.Journal.create({'name': 'NPD no suspense', 'type': 'bank', 'code': 'NPDB2'})
        no_suspense.suspense_account_id = False
        wizard.npd_journal_id = no_suspense
        with self.assertRaisesRegex(UserError, 'บัญชีพักธนาคาร'):
            wizard.import_file_button()
        with self.assertRaisesRegex(UserError, 'บัญชีพักธนาคาร'):
            wizard.import_file_and_reconcile_button()

    def test_09_journal_onchange_fills_mapping(self):
        wizard = self.Wizard.new({'npd_journal_id': self.journal.id})
        wizard._onchange_npd_journal_id()
        self.assertEqual(wizard.sheet_mapping_id, self.mapping)

    def test_10_journal_from_dashboard_context(self):
        wizard = self.Wizard.with_context(journal_id=self.journal.id).create({
            'statement_filename': 'x.csv',
            'statement_file': base64.b64encode(b'x'),
        })
        self.assertEqual(wizard.npd_journal_id, self.journal)
        self.assertEqual(wizard.sheet_mapping_id, self.mapping)

    # --------------------------------------------------- (6) ตั้งค่าเริ่มต้น
    def test_11_setup_by_name_is_idempotent(self):
        company = self.company
        fee = self.Account.create({'code': 'NPD5360', 'name': 'ค่าธรรมเนียมธนาคาร', 'account_type': 'expense'})
        interest = self.Account.create({
            'code': 'NPD4200', 'name': 'ดอกเบี้ยรับ - เงินฝาก', 'account_type': 'income_other',
        })
        shortage = self.Account.create({'code': 'NPD5370', 'name': 'เงินขาด(เกิน)บัญชี', 'account_type': 'expense'})
        # บัญชีสินทรัพย์ชื่อคล้ายกันต้องไม่ถูกเลือกแทนบัญชีค่าใช้จ่าย
        self.Account.create({'code': 'NPD1113', 'name': 'เงินขาด/เกินบัญชี', 'account_type': 'asset_current'})
        company.sudo().account_journal_suspense_account_id = False
        bank2 =self.Journal.create({'name': 'NPD Bank 2', 'type': 'bank', 'code': 'NPDB3'})
        bank2.suspense_account_id = False
        # เลียนแบบสมุดเช็คบน prod: ประเภทธนาคาร แต่ไม่มีบัญชีเงินฝาก/บัญชีพัก
        cheque = self.Journal.create({'name': 'NPD Cheque', 'type': 'bank', 'code': 'NPDCQ'})
        cheque.write({'default_account_id': False, 'suspense_account_id': False})

        RecModel = self.env['account.reconcile.model']
        before = RecModel.search_count([('company_id', '=', company.id)])
        report = company._npd_setup_bank_reconcile()
        self.assertTrue(report)

        self.assertEqual(company.account_journal_suspense_account_id, self.npd_suspense)
        self.assertEqual(bank2.suspense_account_id, self.npd_suspense)
        self.assertFalse(cheque.suspense_account_id)
        buttons = RecModel.search([
            ('company_id', '=', company.id),
            ('rule_type', '=', 'writeoff_button'),
            ('name', 'in', ['ค่าธรรมเนียมธนาคาร', 'ดอกเบี้ยรับเงินฝาก', 'เงินขาด/เกินบัญชี']),
        ])
        self.assertEqual(len(buttons), 3)
        self.assertEqual(RecModel.search_count([('company_id', '=', company.id)]), before + 3)
        accounts = {b.name: b.line_ids.account_id for b in buttons}
        self.assertEqual(accounts['ค่าธรรมเนียมธนาคาร'], fee)
        self.assertEqual(accounts['ดอกเบี้ยรับเงินฝาก'], interest)
        self.assertEqual(accounts['เงินขาด/เกินบัญชี'], shortage)

        snapshot = (
            company.account_journal_suspense_account_id,
            company.transfer_account_id,
            bank2.suspense_account_id,
            self.journal.suspense_account_id,
        )
        company._npd_setup_bank_reconcile()
        self.assertEqual(RecModel.search_count([('company_id', '=', company.id)]), before + 3)
        self.assertEqual(snapshot, (
            company.account_journal_suspense_account_id,
            company.transfer_account_id,
            bank2.suspense_account_id,
            self.journal.suspense_account_id,
        ))
        self.assertFalse(cheque.suspense_account_id)

    def test_12_setup_reports_missing_accounts(self):
        report = self.company._npd_setup_bank_reconcile()
        self.assertTrue(any('ค่าธรรมเนียมธนาคาร' in line for line in report))
        action = self.company._npd_setup_bank_reconcile_action()
        self.assertEqual(action['tag'], 'display_notification')

    # ------------------------------------------------ (7) Mode A จับคู่ RV
    def test_13_mode_a_match_outstanding_receipt(self):
        outstanding = self.Account.create({
            'code': 'NPD1190',
            'name': 'บัญชีพักรับเงิน',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        receivable = self.company_data['default_account_receivable']
        # จำลอง RV ที่ลงบัญชีพักรับเงินแทนบัญชีเงินฝาก
        rv = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2026-10-02',
            'journal_id': self.company_data['default_journal_misc'].id,
            'line_ids': [
                Command.create({
                    'name': 'RV จำลอง', 'account_id': outstanding.id,
                    'partner_id': self.partner_a.id, 'debit': 1500.0, 'credit': 0.0,
                }),
                Command.create({
                    'name': 'RV จำลอง', 'account_id': receivable.id,
                    'partner_id': self.partner_a.id, 'debit': 0.0, 'credit': 1500.0,
                }),
            ],
        })
        rv.action_post()
        out_line = rv.line_ids.filtered(lambda line: line.account_id == outstanding)

        data = (
            'วันที่,รายละเอียด,ถอนเงิน,ฝากเงิน,ยอดคงเหลือ\n'
            '02/10/2569,รับโอนจากลูกค้า,,1500.00,1500.00\n'
        ).encode('utf-8')
        self._imp(data, 'mode_a.csv')
        st_line = self._lines()
        self.assertEqual(len(st_line), 1)
        self.assertFalse(st_line.is_reconciled)

        st_line._add_account_move_line(out_line)
        self.assertTrue(st_line.can_reconcile)
        st_line.reconcile_bank_line()

        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(out_line.reconciled)
        bank_lines = self.env['account.move.line'].search([
            ('account_id', '=', self.journal.default_account_id.id),
            ('parent_state', '=', 'posted'),
        ])
        self.assertAlmostEqual(sum(bank_lines.mapped('balance')), 1500.0)
        self.assertFalse(st_line.move_id.line_ids.filtered(
            lambda line: line.account_id == self.journal.suspense_account_id
        ))

    def test_14_import_and_reconcile_button_opens_journal(self):
        data = _xlsx_bytes([HEADER, ['02/10/2569', None, 'รับโอน', None, 1500, 2500]])
        action = self._import(data, 'r.xlsx', self.mapping, self.journal,
                              button='import_file_and_reconcile_button')
        self.assertEqual(action['context']['active_id'], self.journal.id)

    # --------------------------------------------------------- (8) สิทธิ์
    def test_15_oca_reconcile_bindings_restricted(self):
        group_user = self.env.ref('account.group_account_user')
        for xmlid in (
            'account_reconcile_oca.action_reconcile',
            'account_reconcile_oca.res_partner_account_account_reconcile_act_window',
            'account_reconcile_oca.account_account_account_account_reconcile_act_window',
        ):
            self.assertIn(group_user, self.env.ref(xmlid).groups_id, xmlid)
        group = self.env.ref('npd_bank_reconcile.group_npd_bank_reconcile')
        self.assertIn(group_user, group.trans_implied_ids)


@tagged('post_install', '-at_install')
class TestNpdOcaXlsxFixtures(NpdBankReconcileCommon):
    """ไฟล์ตัวอย่าง .xlsx ของ OCA ผ่านตัวอ่าน openpyxl ของเรา

    เทสต์ของ OCA เองเป็น at_install จึงรันก่อนโมดูลนี้ถูกโหลด และพังบน xlrd 2.0.1
    ชุดนี้รันซ้ำแบบ post_install เพื่อพิสูจน์ว่าตัวอ่านใช้แทน xlrd ได้
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency_usd = cls.env.ref('base.USD')
        cls.currency_eur = cls.env.ref('base.EUR')
        (cls.currency_usd | cls.currency_eur).active = True
        cls.journal = cls.Journal.create({
            'name': 'Bank OCA fixtures',
            'type': 'bank',
            'code': 'NPDFX',
            'currency_id': cls.currency_usd.id,
            'suspense_account_id': cls.npd_suspense.id,
        })
        # เหมือน demo sample_statement_map ของ OCA (ไม่พึ่ง demo data)
        cls.sample_map = cls.Mapping.create({
            'name': 'Sample Statement (NPD test)',
            'footer_lines_skip_count': 0,
            'header_lines_skip_count': 1,
            'float_thousands_sep': 'comma',
            'float_decimal_sep': 'dot',
            'delimiter': 'comma',
            'quotechar': '"',
            'file_encoding': 'utf-8',
            'timestamp_format': '%m/%d/%Y',
            'timestamp_column': 'Date',
            'amount_type': 'simple_value',
            'amount_column': 'Amount',
            'original_currency_column': 'Currency',
            'original_amount_column': 'Amount Currency',
            'description_column': 'Label',
            'partner_name_column': 'Partner Name',
            'bank_account_column': 'Bank Account',
        })

    def _fixture(self, name):
        with file_open(OCA_FIXTURES + name, 'rb') as handle:
            return handle.read()

    def _statement(self):
        return self.Statement.search([('journal_id', '=', self.journal.id)])

    def test_oca_sample_xlsx(self):
        self._import(self._fixture('sample_statement_en.xlsx'), 'sample.xlsx', self.sample_map, self.journal)
        statement = self._statement()
        self.assertEqual(len(statement), 1)
        self.assertEqual(len(statement.line_ids), 2)

    def test_oca_empty_xlsx(self):
        with self.assertRaises(UserError):
            self._import(self._fixture('empty_statement_en.xlsx'), 'empty.xlsx', self.sample_map, self.journal)
        self.assertFalse(self._statement())

    def test_oca_metadata_separated_debit_credit_xlsx(self):
        self.sample_map.write({
            'footer_lines_skip_count': 1,
            'header_lines_skip_count': 5,
            'amount_column': False,
            'partner_name_column': False,
            'bank_account_column': False,
            'float_thousands_sep': 'none',
            'float_decimal_sep': 'comma',
            'timestamp_format': '%m/%d/%y',
            'original_currency_column': False,
            'original_amount_column': False,
            'amount_type': 'distinct_credit_debit',
            'amount_debit_column': 'Debit',
            'amount_credit_column': 'Credit',
        })
        self._import(
            self._fixture('meta_data_separated_credit_debit.xlsx'), 'meta.xlsx', self.sample_map, self.journal,
        )
        statement = self._statement()
        self.assertEqual(len(statement.line_ids), 4)
        by_ref = {line.payment_ref: line for line in statement.line_ids}
        self.assertEqual(by_ref['LABEL 1'].amount, 50)
        self.assertEqual(by_ref['LABEL 4'].amount, -1300)

    def test_oca_xlsx_empty_values(self):
        mapping = self.Mapping.create({
            'name': 'Sample Statement with empty values (NPD test)',
            'amount_type': 'distinct_credit_debit',
            'float_decimal_sep': 'comma',
            'delimiter': 'n/a',
            'no_header': False,
            'footer_lines_skip_count': 1,
            'amount_inverse_sign': False,
            'header_lines_skip_count': 1,
            'quotechar': '"',
            'float_thousands_sep': 'dot',
            'reference_column': 'REF',
            'description_column': 'DESCRIPTION',
            'amount_credit_column': 'DEBIT',
            'amount_debit_column': 'CREDIT',
            'balance_column': 'BALANCE',
            'timestamp_format': '%d/%m/%Y',
            'timestamp_column': 'DATE',
        })
        self._import(
            self._fixture('sample_statement_en_empty_values.xlsx'), 'empty_values.xlsx', mapping, self.journal,
        )
        self.assertEqual(len(self._statement().line_ids), 3)

    def test_oca_offsets_xlsx(self):
        self.sample_map.write({'offset_column': 1, 'header_lines_skip_count': 3})
        self._import(self._fixture('sample_statement_offsets.xlsx'), 'offsets.xlsx', self.sample_map, self.journal)
        statement = self._statement()
        self.assertEqual(len(statement.line_ids), 2)
        self.assertEqual(statement.balance_start, 0.0)
        self.assertEqual(statement.balance_end_real, 1491.5)
