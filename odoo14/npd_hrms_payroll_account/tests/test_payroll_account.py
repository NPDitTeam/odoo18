# -*- coding: utf-8 -*-
"""ทดสอบการลงบัญชีเงินเดือน — รันบนสำเนาฐานข้อมูลเท่านั้น (ห้ามรันบน NPD_Logistics)

บริษัททดสอบไม่มีผังบัญชีมาตรฐาน สร้างบัญชีเองด้วยรหัสที่สลับไม่เหมือนผังจริง
เพื่อพิสูจน์ว่าการจับคู่ยึดชื่อบัญชี ไม่ใช่รหัส
"""
from collections import defaultdict
from datetime import date

import psycopg2

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.npd_hrms_payroll_account.models.constants import KNOWN_LINES

# (ชื่อตามผังใหม่, ประเภท, กระทบยอด)
ACCOUNT_SPECS = [
    ('เงินเดือน', 'expense', False),
    ('ค่าล่วงเวลา', 'expense', False),
    ('เงินเดือนค้างจ่าย', 'liability_current', True),
    ('เงินสมทบกองทุนประกันสังคม', 'expense', False),
    ('เงินสมทบกองทุนประกันสังคมรอนำส่ง', 'liability_current', False),
    ('ภาษีหัก ณ ที่จ่ายค้างจ่าย - ภ.ง.ด.1', 'liability_current', False),
    ('เงินประกันการทำงานของพนักงาน', 'liability_current', False),
    ('ลูกหนี้ - พนักงาน', 'asset_current', False),
    ('เงินกู้ยืม กยศ. รอนำส่ง', 'liability_current', False),
    ('ค่านายหน้าและค่าคอมมิชชั่น', 'expense', False),
    ('ค่าเบี้ยเลี้ยงและค่าใช้จ่ายเดินทางพนักงานขนส่ง', 'expense_direct_cost', False),
    ('โบนัสและผลตอบแทนพิเศษ', 'expense', False),
    ('เงินสะสมกองทุนสงเคราะห์ลูกจ้างรอนำส่ง', 'liability_current', False),
    ('ค่าเที่ยวขนส่ง (ทดสอบ)', 'expense_direct_cost', False),
    ('ค่าเบี้ยเลี้ยงขนส่ง (ทดสอบ)', 'expense_direct_cost', False),
    ('เงินเดือนแผนกทดสอบ', 'expense_direct_cost', False),
    ('ธนาคารทดสอบ', 'asset_cash', False),
]

PERIOD_DATE = date(2030, 3, 28)
REVERSE_DATE = date(2030, 3, 31)


@tagged('post_install', '-at_install')
class TestPayrollAccount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(
            cls.env.context, tracking_disable=True, mail_create_nolog=True,
            mail_notrack=True, no_reset_password=True))
        thb = cls.env.ref('base.THB')
        thb.active = True
        Company = cls.env['res.company']
        cls.company_a = Company.create({'name': 'NPD ทดสอบบัญชีเงินเดือน A', 'currency_id': thb.id})
        cls.company_b = Company.create({'name': 'NPD ทดสอบบัญชีเงินเดือน B', 'currency_id': thb.id})
        cls.companies = cls.company_a | cls.company_b

        cls.accounts = {}
        for company, prefix in ((cls.company_a, 'A'), (cls.company_b, 'B')):
            cls.accounts[company.id] = cls._make_accounts(company, prefix)
            cls.env['account.journal'].create({
                'name': 'สมุดรายวันทั่วไป', 'code': 'T%sJV' % prefix,
                'type': 'general', 'company_id': company.id,
            })

        Branch = cls.env['res.branch'].with_context(bypass_branch_company_filter=True)
        cls.branch_1 = Branch.create({
            'name': 'สาขาทดสอบบัญชีเงินเดือน 1', 'company_ids': [Command.set(cls.companies.ids)]})
        cls.branch_2 = Branch.create({
            'name': 'สาขาทดสอบบัญชีเงินเดือน 2', 'company_ids': [Command.set(cls.companies.ids)]})
        Department = cls.env['hr.department.custom']
        cls.dept_1 = Department.create({'name': 'แผนกทดสอบบัญชีเงินเดือน 1'})
        cls.dept_2 = Department.create({'name': 'แผนกทดสอบบัญชีเงินเดือน 2'})

        cls.emp_a1 = cls._make_employee('ทดสอบเอหนึ่ง', cls.company_a, cls.branch_1, cls.dept_1)
        cls.emp_a2 = cls._make_employee('ทดสอบเอสอง', cls.company_a, cls.branch_2, cls.dept_2)
        cls.emp_b1 = cls._make_employee('ทดสอบบีหนึ่ง', cls.company_b, cls.branch_1, cls.dept_1)

        # รอบเป็นของบริษัท A แต่มีสลิปของ B ด้วย (เหมือนรอบที่ซิงก์จาก o14)
        cls.period = cls.env['payroll.period'].create({
            'month': 3, 'year': 2030, 'company_id': cls.company_a.id,
            'cutoff_start_day': 25, 'cutoff_end_day': 24, 'payment_date': PERIOD_DATE,
        })
        cls.slip_a1 = cls._make_slip(
            cls.emp_a1, cls.company_a,
            income=[('เงินเดือน', 20000.0), ('ค่าล่วงเวลา/โอที', 1500.0),
                    ('ค่าคอมมิชชั่น', 3000.0), ('ค่าเดินทาง', 510.0), ('ค่าอาหาร', 0.0)],
            deduction=[('ประกันสังคม', 750.0), ('ภาษีหัก ณ ที่จ่าย', 500.0),
                       ('หักสาย', 100.0), ('กยศ', 1000.0)],
            income_transport_trip=300.0, income_transport_allowance=210.0)
        cls.slip_a2 = cls._make_slip(
            cls.emp_a2, cls.company_a,
            income=[('เงินเดือน', 15000.0)], deduction=[('ประกันสังคม', 750.0)])
        cls.slip_b1 = cls._make_slip(
            cls.emp_b1, cls.company_b,
            income=[('เงินเดือน', 18000.0)],
            deduction=[('ประกันสังคม', 750.0), ('เบิกเงินล่วงหน้า', 2000.0)])
        cls.period.state = 'approved'

        Config = cls.env['npd.payroll.account.config']
        cls.config_a = Config.create({'company_id': cls.company_a.id})
        cls.config_b = Config.create({'company_id': cls.company_b.id})
        (cls.config_a | cls.config_b).action_generate_defaults()

        Users = cls.env['res.users']
        group_user = cls.env.ref('base.group_user')
        group_manager = cls.env.ref('account.group_account_manager')
        group_poster = cls.env.ref('npd_hrms_payroll_account.group_payroll_account')
        group_hr = cls.env.ref('npd_hrms_base.group_hrms_payroll')
        cls.poster = cls._make_user(
            Users, 'npd_payacc_poster', cls.companies, group_user | group_manager | group_poster)
        cls.poster_a_only = cls._make_user(
            Users, 'npd_payacc_poster_a', cls.company_a,
            group_user | group_manager | group_poster)
        cls.manager_only = cls._make_user(
            Users, 'npd_payacc_manager', cls.companies, group_user | group_manager)
        cls.hr_user = cls._make_user(Users, 'npd_payacc_hr', cls.companies, group_user | group_hr)

    # ------------------------------------------------------------------
    # ตัวช่วย
    # ------------------------------------------------------------------
    @classmethod
    def _make_accounts(cls, company, prefix):
        Account = cls.env['account.account'].with_company(company)
        result = {}
        for number, (name, account_type, reconcile) in enumerate(ACCOUNT_SPECS, start=1):
            result[name] = Account.create({
                # รหัสสลับไม่ตรงผังจริง: ถ้าเอนจินเดาจากรหัสจะผิดทันที
                'code': '%s%d' % (prefix, 9900 - number * 7),
                'name': name,
                'account_type': account_type,
                'reconcile': reconcile,
                'company_ids': [Command.set([company.id])],
            })
        return result

    @classmethod
    def _make_employee(cls, name, company, branch, department):
        return cls.env['employee.salary'].create({
            'firstname': name, 'company_id': company.id, 'branch_id': branch.id,
            'department_id': department.id, 'salary': 20000.0,
        })

    @classmethod
    def _make_slip(cls, employee, company, income, deduction, **vals):
        Salary = cls.env['payroll.salary'].with_context(skip_payroll_recalculate=True)
        slip = Salary.create(dict({
            'period_id': cls.period.id, 'employee_id': employee.id,
            'company_id': company.id, 'month': cls.period.month,
            'year': str(cls.period.year), 'cutoff_day': 24, 'payment_date': PERIOD_DATE,
        }, **vals))
        commands = [Command.create({'name': name, 'type': 'income', 'amount': amount,
                                    'sequence': (i + 1) * 10})
                    for i, (name, amount) in enumerate(income)]
        commands += [Command.create({'name': name, 'type': 'deduction', 'amount': amount,
                                     'sequence': 1000 + (i + 1) * 10})
                     for i, (name, amount) in enumerate(deduction)]
        slip.write({'line_ids': commands})
        slip.write({'state': 'done'})
        return slip

    @classmethod
    def _make_user(cls, Users, login, companies, groups):
        return Users.create({
            'name': login, 'login': login,
            'company_id': companies[:1].id,
            'company_ids': [Command.set(companies.ids)],
            'groups_id': [Command.set(groups.ids)],
        })

    def _acc(self, company, name):
        return self.accounts[company.id][name]

    def _wizard(self, user):
        action = self.period.with_user(user).action_open_payroll_account_wizard()
        return self.env['npd.payroll.account.post.wizard'].with_user(user).browse(
            action['res_id'])

    def _row(self, wizard, company):
        return wizard.company_line_ids.filtered(lambda row: row.company_id == company)

    def _link(self, company):
        return self.env['npd.payroll.account.move'].search([
            ('period_id', '=', self.period.id), ('company_id', '=', company.id),
            ('state', '=', 'posted')])

    def _config(self, company):
        return self.config_a if company == self.company_a else self.config_b

    def _prepare(self, company):
        config = self._config(company)
        return config._npd_prepare_entries(
            self.period, config._npd_get_slips(self.period), PERIOD_DATE)

    @staticmethod
    def _sum_by_account(result, side):
        totals = defaultdict(float)
        for line in result['lines']:
            totals[line['account'].id] += line[side]
        return totals

    @staticmethod
    def _blocks(result):
        return [issue['message'] for issue in result['issues'] if issue['severity'] == 'block']

    # ------------------------------------------------------------------
    # ค่าเริ่มต้นจากผังบัญชี
    # ------------------------------------------------------------------
    def test_defaults_by_name(self):
        config = self.config_a
        self.assertEqual(config.payable_account_id,
                         self._acc(self.company_a, 'เงินเดือนค้างจ่าย'))
        self.assertEqual(config.employer_sso_expense_account_id,
                         self._acc(self.company_a, 'เงินสมทบกองทุนประกันสังคม'))
        self.assertEqual(config.employer_sso_payable_account_id,
                         self._acc(self.company_a, 'เงินสมทบกองทุนประกันสังคมรอนำส่ง'))
        self.assertEqual(config.journal_id.code, 'TAJV')
        index = config._npd_map_index()
        for line_type, names in KNOWN_LINES.items():
            for name in names:
                self.assertIn((line_type, name, False), index)
        self.assertEqual(index[('income', 'ค่าคอมมิชชั่น', False)].account_id,
                         self._acc(self.company_a, 'ค่านายหน้าและค่าคอมมิชชั่น'))
        self.assertEqual(index[('income', 'ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์', False)].account_id,
                         self._acc(self.company_a, 'ค่าล่วงเวลา'))
        self.assertEqual(index[('deduction', 'ภาษีหัก ณ ที่จ่าย', False)].account_id,
                         self._acc(self.company_a, 'ภาษีหัก ณ ที่จ่ายค้างจ่าย - ภ.ง.ด.1'))
        self.assertEqual(index[('income', 'income_deposit_refund_total', False)].account_id,
                         self._acc(self.company_a, 'เงินประกันการทำงานของพนักงาน'))
        self.assertTrue(index[('deduction', 'หักสาย', False)].reduce_expense)
        self.assertFalse(index[('deduction', 'หักสาย', False)].account_id)
        for key in (('income', 'ค่าอาหาร'), ('income', 'รายได้อื่นๆ'),
                    ('deduction', 'หักเงินอื่นๆ'), ('deduction', 'กองทุนสำรองเลี้ยงชีพ'),
                    ('deduction', 'expense_deposit_extra_total')):
            self.assertFalse(index[key + (False,)].account_id, key)
        self.assertIn('ต้องเลือกเอง', config.default_report)

        # ชื่อซ้ำหลายบัญชี -> ปล่อยว่าง ไม่เดา
        self.env['account.account'].with_company(self.company_b).create({
            'code': 'B1111', 'name': 'ค่าล่วงเวลา', 'account_type': 'expense',
            'company_ids': [Command.set([self.company_b.id])],
        })
        self.config_b.map_ids.filtered(
            lambda row: row.line_name.startswith('ค่าล่วงเวลา')).unlink()
        self.config_b.action_generate_defaults()
        index_b = self.config_b._npd_map_index()
        self.assertFalse(index_b[('income', 'ค่าล่วงเวลา/โอที', False)].account_id)
        self.assertIn('ชื่อซ้ำ', self.config_b.default_report)

        # กดซ้ำไม่ทับแถวที่ฝ่ายบัญชีแก้ไว้ และไม่สร้างแถวซ้ำ
        row = index[('income', 'เงินเดือน', False)]
        manual = self._acc(self.company_a, 'เงินเดือนแผนกทดสอบ')
        row.account_id = manual
        count = len(config.map_ids)
        config.action_generate_defaults()
        self.assertEqual(row.account_id, manual)
        self.assertEqual(len(config.map_ids), count)
        self.assertIn('มีอยู่แล้วไม่แตะ', config.default_report)

    # ------------------------------------------------------------------
    # ลงบัญชี
    # ------------------------------------------------------------------
    def test_post_two_companies(self):
        wizard = self._wizard(self.poster)
        for company in self.companies:
            row = self._row(wizard, company)
            self.assertEqual(row.state, 'ready', row.issue_ids.mapped('message'))
        wizard.action_post()

        links = self.env['npd.payroll.account.move'].search([
            ('period_id', '=', self.period.id), ('state', '=', 'posted')])
        self.assertEqual(links.company_id, self.companies)
        for link in links:
            config = self._config(link.company_id)
            move = link.move_id
            self.assertEqual(move.state, 'posted')
            self.assertEqual(move.company_id, link.company_id)
            self.assertEqual(move.journal_id, config.journal_id)
            self.assertFalse(move.branch_id)
            self.assertAlmostEqual(sum(move.line_ids.mapped('debit')),
                                   sum(move.line_ids.mapped('credit')), places=2)
            slips = config._npd_get_slips(self.period)
            payable = move.line_ids.filtered(
                lambda line: line.account_id == config.payable_account_id)
            self.assertAlmostEqual(
                sum(payable.mapped('credit')) - sum(payable.mapped('debit')),
                sum(round(slip.net_salary, 2) for slip in slips) + link.rounding_residue,
                places=2)
            self.assertLess(abs(link.rounding_residue), 1.0)
            for line in move.line_ids:
                if line.account_id.internal_group in ('income', 'expense'):
                    self.assertTrue(line.branch_id, line.name)
                else:
                    self.assertFalse(line.branch_id, line.name)

        move_a = self._link(self.company_a).move_id
        salary = self._acc(self.company_a, 'เงินเดือน')
        salary_lines = move_a.line_ids.filtered(lambda line: line.account_id == salary)
        self.assertAlmostEqual(sum(salary_lines.filtered(
            lambda line: line.branch_id == self.branch_1).mapped('debit')), 20000.0)
        self.assertAlmostEqual(sum(salary_lines.filtered(
            lambda line: line.branch_id == self.branch_2).mapped('debit')), 15000.0)
        # หักสายเครดิตบัญชีเงินเดือน (ลดค่าใช้จ่าย) ไม่ใช่หนี้สิน
        self.assertAlmostEqual(sum(salary_lines.mapped('credit')), 100.0)
        payable_a = move_a.line_ids.filtered(
            lambda line: line.account_id == self.config_a.payable_account_id)
        self.assertAlmostEqual(sum(payable_a.mapped('credit')), 22660.0 + 14250.0)

        self.period.invalidate_recordset(['npd_account_status'])
        self.assertEqual(self.period.npd_account_status, 'done')

    def test_rounding(self):
        employee = self._make_employee('ทดสอบปัดเศษ', self.company_a, self.branch_1, self.dept_1)
        self._make_slip(
            employee, self.company_a,
            income=[('เงินเดือน', 1000.005), ('ค่าล่วงเวลา/โอที', 100.005)],
            deduction=[('ภาษีหัก ณ ที่จ่าย', 0.0)])
        result = self._prepare(self.company_a)
        self.assertFalse(self._blocks(result))
        residue = result['totals']['rounding_residue']
        self.assertLessEqual(abs(residue), 0.02)
        self.assertNotEqual(residue, 0.0)
        wizard = self._wizard(self.poster)
        self._row(wizard, self.company_b).to_post = False
        wizard.action_post()
        move = self._link(self.company_a).move_id
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')),
                               sum(move.line_ids.mapped('credit')), places=2)

    def test_split_consistent_and_inconsistent(self):
        trip = self._acc(self.company_a, 'ค่าเที่ยวขนส่ง (ทดสอบ)')
        allowance = self._acc(self.company_a, 'ค่าเบี้ยเลี้ยงขนส่ง (ทดสอบ)')
        transport = self._acc(self.company_a, 'ค่าเบี้ยเลี้ยงและค่าใช้จ่ายเดินทางพนักงานขนส่ง')
        self.config_a.write({'map_ids': [
            Command.create({'line_type': 'income', 'line_name': 'income_transport_trip',
                            'account_id': trip.id}),
            Command.create({'line_type': 'income', 'line_name': 'income_transport_allowance',
                            'account_id': allowance.id}),
        ]})
        debits = self._sum_by_account(self._prepare(self.company_a), 'debit')
        self.assertAlmostEqual(debits[trip.id], 300.0)
        self.assertAlmostEqual(debits[allowance.id], 210.0)
        self.assertNotIn(transport.id, debits)

        # ยอดบรรทัดไม่ตรงกับฟิลด์ (แบบสลิปที่ซิงก์จาก o14) -> ไม่แยก ลงทั้งก้อน + เตือน
        self.slip_a1.line_ids.filtered(lambda line: line.name == 'ค่าเดินทาง').amount = 600.0
        result = self._prepare(self.company_a)
        warnings = [issue for issue in result['issues']
                    if issue['severity'] == 'warn' and 'ค่าเดินทาง' in issue['message']]
        self.assertTrue(warnings)
        debits = self._sum_by_account(result, 'debit')
        self.assertAlmostEqual(debits[transport.id], 600.0)
        self.assertNotIn(trip.id, debits)
        self.assertFalse(self._blocks(result))

    def test_reduce_expense_and_department_override(self):
        dept_salary = self._acc(self.company_a, 'เงินเดือนแผนกทดสอบ')
        salary = self._acc(self.company_a, 'เงินเดือน')
        self.config_a.write({'map_ids': [Command.create({
            'line_type': 'income', 'line_name': 'เงินเดือน',
            'department_id': self.dept_1.id, 'account_id': dept_salary.id,
        })]})
        result = self._prepare(self.company_a)
        debits = self._sum_by_account(result, 'debit')
        credits = self._sum_by_account(result, 'credit')
        self.assertAlmostEqual(debits[dept_salary.id], 20000.0)
        self.assertAlmostEqual(credits[dept_salary.id], 100.0)
        self.assertAlmostEqual(debits[salary.id], 15000.0)
        # ตัวช่วยบวกช่องเครดิตของทุกบรรทัด บรรทัดเดบิตจึงโผล่เป็น 0 ได้ ดูที่ยอดแทนการมีคีย์
        self.assertAlmostEqual(credits.get(salary.id, 0.0), 0.0)

    def test_employer_sso(self):
        expense = self._acc(self.company_a, 'เงินสมทบกองทุนประกันสังคม')
        payable = self._acc(self.company_a, 'เงินสมทบกองทุนประกันสังคมรอนำส่ง')
        result = self._prepare(self.company_a)
        self.assertAlmostEqual(self._sum_by_account(result, 'debit')[expense.id], 1500.0)
        self.assertAlmostEqual(self._sum_by_account(result, 'credit')[payable.id], 3000.0)
        self.assertAlmostEqual(result['totals']['employer_sso'], 1500.0)

        self.config_a.employer_sso_enabled = False
        result = self._prepare(self.company_a)
        self.assertNotIn(expense.id, self._sum_by_account(result, 'debit'))
        self.assertAlmostEqual(self._sum_by_account(result, 'credit')[payable.id], 1500.0)

    def test_unmapped_blocks(self):
        self.slip_a2.write({'line_ids': [Command.create({
            'name': 'เบี้ยเลี้ยง', 'type': 'income', 'amount': 50.0})]})
        wizard = self._wizard(self.poster)
        row_a = self._row(wizard, self.company_a)
        row_b = self._row(wizard, self.company_b)
        self.assertEqual(row_a.state, 'blocked')
        self.assertTrue(any('ยังไม่ได้ผูกบัญชี' in message and 'เบี้ยเลี้ยง' in message
                            for message in row_a.issue_ids.mapped('message')))
        move_count = self.env['account.move'].search_count(
            [('company_id', 'in', self.companies.ids)])
        # จำลองหน้าตัวอย่างที่เปิดค้างไว้: ตอนกดต้องคำนวณใหม่และหยุด
        row_a.write({'state': 'ready', 'to_post': True})
        row_b.write({'to_post': False})
        with self.assertRaises(UserError) as error:
            wizard.action_post()
        self.assertIn('ยังไม่ได้ผูกบัญชี', str(error.exception))
        self.assertEqual(move_count, self.env['account.move'].search_count(
            [('company_id', 'in', self.companies.ids)]))

    def test_residue_blocks(self):
        self.slip_a2.write({'manual_override': True,
                            'net_salary': self.slip_a2.net_salary + 5.0})
        blocks = self._blocks(self._prepare(self.company_a))
        self.assertTrue(any('ไม่ตรงกับผลรวมบรรทัด' in message
                            and (self.slip_a2.employee_code or '') in message
                            for message in blocks))

    def test_lock_date(self):
        self.company_a.fiscalyear_lock_date = REVERSE_DATE
        wizard = self._wizard(self.poster)
        row_a = self._row(wizard, self.company_a)
        self.assertEqual(row_a.state, 'blocked')
        self.assertTrue(any('ล็อกงวดบัญชี' in message
                            for message in row_a.issue_ids.mapped('message')))
        self.assertEqual(self._row(wizard, self.company_b).state, 'ready')
        wizard.action_post()
        self.assertTrue(self._link(self.company_b))
        self.assertFalse(self._link(self.company_a))

    def test_double_post(self):
        self._wizard(self.poster).action_post()
        wizard = self._wizard(self.poster)
        self.assertEqual(set(wizard.company_line_ids.mapped('state')), {'posted'})
        with self.assertRaises(UserError):
            wizard.action_post()
        with self.assertRaises(UserError):
            self.config_a._npd_post_period(self.period, PERIOD_DATE)
        link = self._link(self.company_a)
        with self.assertRaises(psycopg2.IntegrityError), mute_logger('odoo.sql_db'), \
                self.cr.savepoint():
            self.env['npd.payroll.account.move'].create({
                'period_id': self.period.id, 'company_id': self.company_a.id,
                'move_id': link.move_id.id, 'state': 'posted',
            })

    def test_reverse_and_repost(self):
        self._wizard(self.poster).action_post()
        link = self._link(self.company_a)
        old_move = link.move_id
        link.with_user(self.poster)._npd_reverse(REVERSE_DATE, 'ทดสอบกลับรายการ')
        link.invalidate_recordset()
        self.assertEqual(link.state, 'reversed')
        self.assertEqual(link.reversal_move_id.state, 'posted')
        payable = (old_move.line_ids | link.reversal_move_id.line_ids).filtered(
            lambda line: line.account_id == self.config_a.payable_account_id)
        self.assertTrue(all(payable.mapped('reconciled')))

        wizard = self._wizard(self.poster)
        self.assertEqual(self._row(wizard, self.company_a).state, 'ready')
        self.assertEqual(self._row(wizard, self.company_b).state, 'posted')
        wizard.action_post()
        new_link = self._link(self.company_a)
        self.assertTrue(new_link)
        self.assertNotEqual(new_link, link)
        self.assertNotEqual(new_link.move_id, old_move)

    def test_reverse_blocked_when_reconciled(self):
        self._wizard(self.poster).action_post()
        link = self._link(self.company_a)
        move = link.move_id
        payable = self.config_a.payable_account_id
        amount = sum(move.line_ids.filtered(
            lambda line: line.account_id == payable).mapped('credit'))
        payment = self.env['account.move'].with_company(self.company_a).create({
            'move_type': 'entry', 'journal_id': self.config_a.journal_id.id,
            'date': PERIOD_DATE, 'branch_id': False,
            'line_ids': [
                Command.create({'name': 'จ่ายเงินเดือน', 'account_id': payable.id,
                                'debit': amount, 'credit': 0.0, 'branch_id': False}),
                Command.create({'name': 'จ่ายเงินเดือน',
                                'account_id': self._acc(self.company_a, 'ธนาคารทดสอบ').id,
                                'debit': 0.0, 'credit': amount, 'branch_id': False}),
            ],
        })
        payment.action_post()
        (move.line_ids | payment.line_ids).filtered(
            lambda line: line.account_id == payable).reconcile()
        with self.assertRaises(UserError):
            link.with_user(self.poster)._npd_reverse(REVERSE_DATE)

    def test_hr_guards(self):
        self._wizard(self.poster).action_post()
        with self.assertRaises(UserError):
            self.period.action_reset_draft()
        with self.assertRaises(UserError):
            self.period.action_cancel()
        with self.assertRaises(UserError):
            self.slip_a1.action_reset_draft()
        with self.assertRaises(UserError):
            self.period.unlink()

    def test_access(self):
        with self.assertRaises(AccessError):
            self.period.with_user(self.hr_user).action_open_payroll_account_wizard()
        with self.assertRaises(AccessError):
            self.config_a.with_user(self.hr_user).read(['journal_id'])
        with self.assertRaises(AccessError):
            self.period.with_user(self.manager_only).action_open_payroll_account_wizard()

        wizard = self._wizard(self.poster_a_only)
        row_b = self._row(wizard, self.company_b)
        self.assertEqual(row_b.state, 'no_access')
        self.assertFalse(row_b.line_ids)
        self.assertEqual(row_b.total_net, 0.0)
        self.assertEqual(self._row(wizard, self.company_a).state, 'ready')
        wizard.action_post()
        self.assertTrue(self._link(self.company_a))
        self.assertFalse(self._link(self.company_b))

    def test_period_state(self):
        self.period.state = 'computed'
        with self.assertRaises(UserError) as error:
            self.period.with_user(self.poster).action_open_payroll_account_wizard()
        self.assertIn('ลงบัญชีได้เฉพาะรอบที่อนุมัติแล้วหรือจ่ายแล้ว', str(error.exception))

    def test_outdated(self):
        self._wizard(self.poster).action_post()
        link = self._link(self.company_a)
        self.assertFalse(link.is_outdated)
        self.slip_a2.line_ids.filtered(lambda line: line.name == 'เงินเดือน').amount = 15100.0
        link.invalidate_recordset(['is_outdated'])
        self.assertTrue(link.is_outdated)
        self.period.invalidate_recordset(['npd_account_status'])
        self.assertEqual(self.period.npd_account_status, 'outdated')
