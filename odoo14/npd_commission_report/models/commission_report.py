# -*- coding: utf-8 -*-
"""รายงานค่าคอมมิชชั่นสาขา — ยอดเช่าสุทธิรายสาขาต่อเดือน

พอร์ตจาก Odoo 14 (``npd_commission_report``) ตรรกะการเงินคงเดิมทุกข้อ
สิ่งที่เปลี่ยนคือโครงสร้าง เพราะระบบเปลี่ยนจาก "แยกฐานข้อมูลต่อบริษัท"
มาเป็น "รวมฐานเดียว แยกด้วยบริษัท"

1. **กรองด้วยบริษัททุกจุด** — ของเดิมค้นสมุดรายวันทั้งฐานโดยไม่กรองบริษัท
   ซึ่งถูกต้องตอนแยกฐาน แต่พอรวมฐานแล้วยอดของ 5 บริษัทจะบวกกันมั่ว
2. **เก็บถาวรแทนที่จะเป็นตารางชั่วคราว** — ของเดิมเป็น TransientModel
   กดสร้างทีนึงแล้วหาย สลิปเงินเดือนย้อนหลังจึงอ้างอิงไม่ได้
   ตอนนี้เก็บเป็นงวด (บริษัท + สาขา + เดือน + ปี) สร้างซ้ำได้ทับของเดิม
3. **ค่าจ้างพนักงานอ่านผ่าน ORM** — ของเดิมต่อ psycopg2 ข้ามไปฐาน HRMS
   ตอนนี้เงินเดือนอยู่ฐานเดียวกันแล้ว

ฐานที่ใช้คิดค่าคอมคือ ``net_rental`` (ยอดเช่าสุทธิ) ไม่ใช่ยอดเช่าดิบ
"""
import logging
import math
from calendar import monthrange
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MONTH_SELECTION = [
    ('1', 'มกราคม'), ('2', 'กุมภาพันธ์'), ('3', 'มีนาคม'), ('4', 'เมษายน'),
    ('5', 'พฤษภาคม'), ('6', 'มิถุนายน'), ('7', 'กรกฎาคม'), ('8', 'สิงหาคม'),
    ('9', 'กันยายน'), ('10', 'ตุลาคม'), ('11', 'พฤศจิกายน'), ('12', 'ธันวาคม'),
]


def truncate_decimal(value, decimals=2):
    """ตัดทศนิยมทิ้งโดยไม่ปัดเศษ เช่น 1234.567 -> 1234.56

    การเงินคิดแบบตัดทิ้ง ไม่ใช่ปัด — ถ้าเปลี่ยนไปปัดยอดจะไม่ตรงกับของเดิม
    """
    multiplier = 10 ** decimals
    return math.trunc((value or 0.0) * multiplier) / multiplier


class CommissionReport(models.Model):
    _name = 'npd.commission.report'
    _description = 'รายงานค่าคอมมิชชั่นสาขา'
    _order = 'year desc, month desc, branch_id'
    _rec_name = 'display_summary'

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True,
        default=lambda self: self.env.company, ondelete='cascade')
    branch_id = fields.Many2one(
        'res.branch', string='สาขา', required=True, index=True, ondelete='cascade')
    month = fields.Selection(MONTH_SELECTION, string='เดือน', required=True, index=True)
    year = fields.Char(string='ปี', required=True, index=True)
    date_from = fields.Date(string='ตั้งแต่', readonly=True)
    date_to = fields.Date(string='ถึง', readonly=True)

    rental_amount = fields.Float(
        string='ยอดเช่า', digits=(16, 2), readonly=True,
        help='ใบแจ้งหนี้ในสมุดยอดเช่า หักใบลดหนี้แล้ว (ไม่รวม VAT)')
    payment_received = fields.Float(
        string='รับชำระหนี้', digits=(16, 2), readonly=True,
        help='เงินที่รับในเดือนนี้ของหนี้ที่ออกใบไว้เดือนก่อน')
    outstanding_debt = fields.Float(
        string='หนี้ค้างชำระ', digits=(16, 2), readonly=True,
        help='ยอดค้าง ณ วันสิ้นรอบ ไม่ใช่ ณ วันนี้')
    total_expense = fields.Float(
        string='รายจ่ายรวม', digits=(16, 2), readonly=True)
    salary_expense = fields.Float(
        string='  - ค่าจ้างพนักงาน', digits=(16, 2), readonly=True,
        help='ส่วนหนึ่งของรายจ่ายรวม แยกให้เห็นว่ามาจากเงินเดือนเท่าไหร่')
    net_rental = fields.Float(
        string='ยอดเช่าสุทธิ', digits=(16, 2), readonly=True,
        help='ยอดเช่า + รับชำระหนี้ - หนี้ค้างชำระ - รายจ่ายรวม '
             '— ตัวนี้คือฐานคิดค่าคอมสาขา')

    generated_at = fields.Datetime(string='สร้างเมื่อ', readonly=True)
    note = fields.Text(string='หมายเหตุการคำนวณ', readonly=True)
    display_summary = fields.Char(compute='_compute_display_summary')

    _sql_constraints = [
        ('period_uniq', 'unique(company_id, branch_id, month, year)',
         'มีรายงานของสาขานี้ในงวดนี้อยู่แล้ว'),
    ]

    @api.depends('branch_id', 'month', 'year')
    def _compute_display_summary(self):
        labels = dict(MONTH_SELECTION)
        for rec in self:
            rec.display_summary = '%s %s %s' % (
                rec.branch_id.name or '-', labels.get(rec.month, ''), rec.year or '')

    # ------------------------------------------------------------------
    # ตัวช่วย
    # ------------------------------------------------------------------
    @api.model
    def _period_window(self, month, year):
        month, year = int(month), int(year)
        return (date(year, month, 1),
                date(year, month, monthrange(year, month)[1]))

    @api.model
    def _outstanding_residual_asof(self, invoice, as_of, vat_divisor):
        """ยอดค้างชำระของใบแจ้งหนี้ ณ วันที่ ``as_of`` (ถอด VAT แล้ว)

        ``amount_residual`` เป็นยอด ณ ปัจจุบัน ถ้าลูกค้าจ่ายทีหลังยอดจะหด
        แต่การเงินคิดหนี้ค้าง ณ วันสิ้นรอบ จึงต้องย้อนกลับไปดูว่า ณ วันนั้น
        มีเงินหรือใบลดหนี้จับคู่เข้ามาแล้วเท่าไหร่
        """
        total_open = 0.0
        recv_lines = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable')
        for line in recv_lines:
            bal = (line.debit or 0.0) - (line.credit or 0.0)
            paid = 0.0
            for pr in line.matched_credit_ids:
                cdate = pr.credit_move_id.date
                if cdate and cdate <= as_of:
                    paid += pr.amount or 0.0
            for pr in line.matched_debit_ids:
                ddate = pr.debit_move_id.date
                if ddate and ddate <= as_of:
                    paid += pr.amount or 0.0
            open_amt = bal - paid
            if open_amt > 0:
                total_open += open_amt
        return total_open / vat_divisor

    @api.model
    def _salary_expense(self, branch, month, year, company):
        """ค่าจ้างพนักงานของสาขานั้นในงวดนั้น

        ของเดิมต่อ psycopg2 ข้ามไปอ่านฐาน HRMS แล้วเก็บลงตาราง snapshot
        ตอนนี้เงินเดือนอยู่ฐานเดียวกัน อ่านตรงได้เลย และได้ยอดล่าสุดเสมอ
        ไม่ต้องคอยกดรีเฟรช snapshot เหมือนเดิม
        """
        Salary = self.env['payroll.salary'].sudo()
        slips = Salary.search([
            ('branch_id', '=', branch.id),
            ('company_id', '=', company.id),
            ('month', '=', int(month)),
            ('year', '=', str(year)),
        ])
        return sum(slips.mapped('total_gross'))

    # ------------------------------------------------------------------
    # คำนวณ
    # ------------------------------------------------------------------
    @api.model
    def compute_branch_data(self, month, year, company=None, branches=None):
        """คำนวณยอดรายสาขาของงวดนั้น คืน list ของ dict (ยังไม่บันทึก)"""
        company = company or self.env.company
        config = self.env['npd.commission.config'].get_for(company)
        config.check_ready()
        vat_divisor = config.vat_divisor

        if branches is None:
            branches = self.env['res.branch'].sudo().search(
                [('company_ids', 'in', company.id)])
        date_from, date_to = self._period_window(month, year)

        Move = self.env['account.move'].sudo()
        Payment = self.env['account.payment'].sudo()
        rental_ids = config.rental_journal_ids.ids
        penalty_ids = config.penalty_journal_ids.ids
        invoice_journal_ids = rental_ids + penalty_ids
        gross_payment_ids = set(config.gross_payment_journal_ids.ids)

        # ฟิลด์ที่ Odoo 14 มีแต่ระบบนี้ยังไม่มี — เช็คครั้งเดียว ไม่เช็ครายสาขา
        has_contact_type = 'contact_type' in Move._fields
        skipped = []

        rows = []
        for branch in branches:
            rental_amount = payment_received = outstanding_debt = 0.0

            base_domain = [
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('branch_id', '=', branch.id),
                ('company_id', '=', company.id),
                ('state', '=', 'posted'),
            ]
            if has_contact_type:
                base_domain.append(('contact_type', '=', 'branch'))

            invoices = Move.search(base_domain + [
                ('journal_id', 'in', invoice_journal_ids),
                ('move_type', '=', 'out_invoice'),
            ])
            for inv in invoices:
                # ยอดเช่านับเฉพาะสมุดยอดเช่า ค่าปรับไม่นับเป็นยอดเช่า
                if inv.journal_id.id in rental_ids:
                    rental_amount += inv.amount_untaxed or 0.0
                # แต่ค่าปรับที่ยังไม่จ่าย ณ สิ้นรอบ นับเป็นหนี้ค้าง
                outstanding_debt += self._outstanding_residual_asof(
                    inv, date_to, vat_divisor)

            # ใบลดหนี้หักออกจากยอดเช่า
            if config.credit_note_journal_id:
                credit_notes = Move.search(base_domain + [
                    ('journal_id', '=', config.credit_note_journal_id.id),
                    ('move_type', '=', 'out_refund'),
                ])
                for cn in credit_notes:
                    rental_amount -= cn.amount_untaxed or 0.0

            # รับชำระหนี้ — เฉพาะเงินที่รับ "คนละเดือน" กับวันที่ออกใบ
            # และต้องรับหลังวันออกใบ (จ่ายในเดือนเดียวกันไม่ถือเป็นการตามหนี้)
            if config.payment_journal_ids:
                payments = Payment.search([
                    ('journal_id', 'in', config.payment_journal_ids.ids),
                    ('company_id', '=', company.id),
                    ('state', '=', 'posted'),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                    ('branch_id', '=', branch.id),
                ])
                for payment in payments:
                    pay_date = payment.date
                    for inv in payment.reconciled_invoice_ids:
                        # ใบขาย (เลขขึ้นต้น IV) ไม่ใช่ใบเช่า ไม่นับ
                        if (inv.name or '').strip().upper().startswith('IV'):
                            continue
                        if not (inv.invoice_date and pay_date):
                            continue
                        different_month = (
                            inv.invoice_date.month != pay_date.month
                            or inv.invoice_date.year != pay_date.year)
                        later = pay_date > inv.invoice_date
                        if not (different_month and later):
                            continue
                        if has_contact_type and inv.contact_type != 'branch':
                            continue
                        amount = payment.amount or 0.0
                        if payment.journal_id.id in gross_payment_ids:
                            payment_received += amount
                        else:
                            payment_received += amount / vat_divisor
                        break   # นับเงินก้อนนี้ครั้งเดียว

            total_expense, salary_expense, notes = self._branch_expense(
                branch, company, date_from, date_to, month, year, config)
            skipped.extend(n for n in notes if n not in skipped)

            net_rental = (rental_amount + payment_received
                          - outstanding_debt - total_expense)
            rows.append({
                'company_id': company.id,
                'branch_id': branch.id,
                'month': str(int(month)),
                'year': str(year),
                'date_from': date_from,
                'date_to': date_to,
                'rental_amount': truncate_decimal(rental_amount),
                'payment_received': truncate_decimal(payment_received),
                'outstanding_debt': truncate_decimal(outstanding_debt),
                'total_expense': truncate_decimal(total_expense),
                'salary_expense': truncate_decimal(salary_expense),
                'net_rental': truncate_decimal(net_rental),
                'generated_at': fields.Datetime.now(),
                'note': '\n'.join(skipped) or False,
            })
        return rows

    @api.model
    def _branch_expense(self, branch, company, date_from, date_to,
                        month, year, config):
        """รายจ่ายของสาขาในงวดนั้น คืน (ยอดรวม, ส่วนที่เป็นค่าจ้าง, หมายเหตุ)"""
        Move = self.env['account.move'].sudo()
        total = 0.0
        notes = []

        # 1) บิลผู้ขาย — นับ "เงินที่จ่ายจริง" ไม่ใช่ยอดบิล
        bills = Move.search([
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('company_id', '=', company.id),
            ('branch_id', '=', branch.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', ['in_invoice', 'in_refund']),
        ])
        for bill in bills:
            for payment in bill._get_reconciled_payments():
                total += payment.amount or 0.0

        # 2) เคลียร์เงินทดรอง
        AdvanceClear = self.env.get('account.advance.clear')
        if AdvanceClear is not None:
            clears = self.env['account.advance.clear'].sudo().search([
                ('doc_date', '>=', date_from),
                ('doc_date', '<=', date_to),
                ('company_id', '=', company.id),
                ('state', '=', 'post'),
            ])
            for clear in clears:
                for line in clear.clear_ids:
                    analytic = line.account_analytic_id
                    if not analytic or analytic.branch_id.id != branch.id:
                        continue
                    total += self._line_amount_with_vat(line)

        # 3) ใบสำคัญจ่าย
        total += self._voucher_expense(branch, company, date_from, date_to, notes)

        # 4) รายการสมุดรายวันทั่วไปที่เลขขึ้นต้น JV-
        jv_moves = Move.search([
            ('name', '=like', 'JV-%'),
            ('branch_id', '=', branch.id),
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', '=', 'posted'),
        ])
        for move in jv_moves:
            total += sum(l.debit for l in move.line_ids if l.debit and l.debit > 0)

        # 5) ค่าจ้างพนักงาน — บวกเฉพาะสาขาที่มีรายจ่ายอื่นอยู่แล้ว
        #    (สาขาที่ไม่มีรายจ่ายเลย = ยังไม่เปิดดำเนินการในเดือนนั้น)
        salary = 0.0
        if config.include_salary_in_expense and total > 0:
            salary = self._salary_expense(branch, month, year, company)
            total += salary

        return total, salary, notes

    @api.model
    def _line_amount_with_vat(self, line):
        """ยอดของบรรทัดหลังจัดการ VAT ตามชนิดภาษีที่ติดอยู่

        ภาษีซื้อที่ "รวม Vat" แล้ว ใช้ราคาต่อหน่วยตรง ๆ
        ส่วนที่ "ไม่รวม Vat" ต้องบวก VAT กลับเข้าไป เพราะเป็นเงินที่จ่ายจริง
        """
        names = ' , '.join(t.name or '' for t in line.tax_ids)
        if 'ภาษีซื้อรวม Vat' in names:
            return line.price_unit or 0.0
        if 'ภาษีซื้อไม่รวม Vat' in names:
            return (line.price_unit or 0.0) * 1.07
        if line.tax_ids:
            return 0.0
        return line.price_subtotal or 0.0

    @api.model
    def _voucher_expense(self, branch, company, date_from, date_to, notes):
        """รายจ่ายจากใบสำคัญจ่าย

        Odoo 14 กรองด้วย ``account.voucher.line.payment_date`` (วันที่กำหนดจ่าย)
        ซึ่งมาจากโมดูล ``account_advance_sales_contact`` ที่ยังไม่ได้พอร์ตมา
        ระบบนี้จึงไม่มีฟิลด์นั้น — ใช้วันที่ของใบสำคัญจ่ายแทน และบันทึกหมายเหตุ
        ไว้บนรายงาน เพื่อไม่ให้เข้าใจผิดว่าตัวเลขคิดด้วยเกณฑ์เดียวกับของเดิม
        """
        VoucherLine = self.env.get('account.voucher.line')
        if VoucherLine is None:
            return 0.0
        Line = self.env['account.voucher.line'].sudo()
        base = [
            ('voucher_id.state', 'in', ['posted', 'transferred']),
            ('voucher_id.voucher_type', '=', 'purchase'),
            ('voucher_id.company_id', '=', company.id),
            ('account_analytic_id.branch_id', '=', branch.id),
        ]
        if 'payment_date' in Line._fields:
            domain = base + [('payment_date', '>=', date_from),
                             ('payment_date', '<=', date_to)]
        else:
            domain = base + [('voucher_id.date', '>=', date_from),
                             ('voucher_id.date', '<=', date_to)]
            notes.append(
                'ใบสำคัญจ่าย: ใช้ "วันที่ใบสำคัญ" แทน "วันที่กำหนดจ่าย" '
                'เพราะระบบนี้ยังไม่มีฟิลด์วันที่กำหนดจ่าย '
                '(โมดูล account_advance_sales_contact ยังไม่ได้พอร์ต) '
                'ยอดอาจต่างจาก Odoo 14 ถ้าวันกำหนดจ่ายคนละเดือนกับวันที่ใบ')
        if 'check_show' in self.env['account.voucher']._fields:
            domain.append(('voucher_id.check_show', '=', False))

        total = 0.0
        for line in Line.search(domain):
            subtotal = line.price_subtotal or 0.0
            names = ' , '.join(t.name or '' for t in line.tax_ids)
            if 'ภาษีซื้อรวม Vat' in names or 'ภาษีซื้อไม่รวม Vat' in names:
                total += subtotal * 1.07
            else:
                total += subtotal
        return total

    # ------------------------------------------------------------------
    # สร้าง/อัปเดตรายงาน
    # ------------------------------------------------------------------
    @api.model
    def generate(self, month, year, company=None, branches=None):
        """สร้างรายงานของงวดนั้น เขียนทับของเดิมถ้ามีอยู่แล้ว"""
        company = company or self.env.company
        rows = self.compute_branch_data(month, year, company=company,
                                        branches=branches)
        result = self.browse()
        for vals in rows:
            existing = self.sudo().search([
                ('company_id', '=', vals['company_id']),
                ('branch_id', '=', vals['branch_id']),
                ('month', '=', vals['month']),
                ('year', '=', vals['year']),
            ], limit=1)
            if existing:
                existing.sudo().write(vals)
                result |= existing
            else:
                result |= self.sudo().create(vals)
        _logger.info('[COMMISSION] สร้างรายงานค่าคอมสาขา %s งวด %s/%s จำนวน %d สาขา',
                     company.name, month, year, len(result))
        return result

    @api.model
    def get_net_rental(self, branch, month, year, company=None):
        """ยอดเช่าสุทธิของสาขาในงวดนั้น — ฝั่งเงินเดือนเรียกตัวนี้"""
        company = company or self.env.company
        rec = self.sudo().search([
            ('branch_id', '=', branch.id),
            ('company_id', '=', company.id),
            ('month', '=', str(int(month))),
            ('year', '=', str(year)),
        ], limit=1)
        return rec.net_rental if rec else 0.0
