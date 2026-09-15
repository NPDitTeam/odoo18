# -*- coding: utf-8 -*-
"""รายงานค่าคอม Sales — ยอดเช่าสุทธิรายเซลล์ต่อสาขาต่อเดือน

พอร์ตจาก Odoo 14 ตรรกะการเงินคงเดิม ต่างกันที่โครงสร้างเหมือนฝั่งสาขา
(กรองด้วยบริษัท เก็บถาวร ชื่อสมุดรายวันตั้งค่าได้)

ต่างจากฝั่งสาขาอย่างไร
----------------------
* จัดกลุ่มด้วย (เซลล์, สาขา) ไม่ใช่สาขาอย่างเดียว
* รายจ่ายที่หักคือ **ค่าขนส่ง** จากใบสำคัญจ่ายที่ระบุเซลล์ไว้
  ไม่ใช่รายจ่ายทั้งสาขา
* **Sales สำนักงานใหญ่** เป็นกรณีพิเศษ: ยอดเช่านับเฉพาะบิลแรก
  บิลต่ออายุ (ใบสั่งขายมีเลขอ้างอิงเงินประกัน) ไม่นับ
"""
import logging

from odoo import _, api, fields, models

from .commission_report import MONTH_SELECTION, truncate_decimal

_logger = logging.getLogger(__name__)


class CommissionReportSales(models.Model):
    _name = 'npd.commission.report.sales'
    _description = 'รายงานค่าคอม Sales'
    _order = 'year desc, month desc, sales_contact_id'
    _rec_name = 'display_summary'

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True,
        default=lambda self: self.env.company, ondelete='cascade')
    sales_contact_id = fields.Many2one(
        'res.users', string='Sales', required=True, index=True, ondelete='cascade')
    branch_id = fields.Many2one('res.branch', string='สาขา', index=True)
    employee_code = fields.Char(
        string='รหัสพนักงาน', related='sales_contact_id.employee_code',
        store=True, readonly=True,
        help='ใช้จับคู่กับพนักงานฝั่งระบบเงินเดือน')
    month = fields.Selection(MONTH_SELECTION, string='เดือน', required=True, index=True)
    year = fields.Char(string='ปี', required=True, index=True)
    date_from = fields.Date(string='ตั้งแต่', readonly=True)
    date_to = fields.Date(string='ถึง', readonly=True)

    rental_amount = fields.Float(string='ยอดเช่า', digits=(16, 2), readonly=True)
    payment_received = fields.Float(string='รับชำระหนี้', digits=(16, 2), readonly=True)
    outstanding_debt = fields.Float(string='หนี้ค้างชำระ', digits=(16, 2), readonly=True)
    shipping_cost = fields.Float(string='ค่าขนส่ง', digits=(16, 2), readonly=True)
    net_rental = fields.Float(
        string='ยอดเช่าสุทธิ', digits=(16, 2), readonly=True,
        help='ยอดเช่า + รับชำระหนี้ - หนี้ค้างชำระ - ค่าขนส่ง '
             '— ตัวนี้คือฐานคิดค่าคอม Sales')
    is_headoffice = fields.Boolean(
        string='Sales สำนักงานใหญ่', readonly=True,
        help='คิดยอดเช่าเฉพาะบิลแรก ไม่นับบิลต่ออายุ')

    generated_at = fields.Datetime(string='สร้างเมื่อ', readonly=True)
    display_summary = fields.Char(compute='_compute_display_summary')

    _sql_constraints = [
        ('period_uniq',
         'unique(company_id, sales_contact_id, branch_id, month, year)',
         'มีรายงานของเซลล์คนนี้ในสาขาและงวดนี้อยู่แล้ว'),
    ]

    @api.depends('sales_contact_id', 'branch_id', 'month', 'year')
    def _compute_display_summary(self):
        labels = dict(MONTH_SELECTION)
        for rec in self:
            rec.display_summary = '%s / %s / %s %s' % (
                rec.sales_contact_id.name or '-', rec.branch_id.name or 'ไม่ระบุสาขา',
                labels.get(rec.month, ''), rec.year or '')

    # ------------------------------------------------------------------
    @api.model
    def _headoffice_user_ids(self):
        """ผู้ใช้ที่เป็น Sales สำนักงานใหญ่

        รายชื่ออยู่ฝั่งระบบบุคคล (commission.sale.headoffice) เก็บเป็นพนักงาน
        ส่วนใบแจ้งหนี้ผูกกับผู้ใช้ระบบ จึงต้องแปลงผ่านรหัสพนักงาน
        """
        if 'commission.sale.headoffice' not in self.env:
            return set()
        employees = self.env['commission.sale.headoffice'].sudo().search([]) \
            .mapped('employee_id')
        users = employees.mapped('user_id')
        return set(users.ids)

    @api.model
    def _is_renewal_invoice(self, invoice):
        """บิลต่ออายุไหม — ดูจากใบสั่งขายที่เชื่อมว่ามีเลขอ้างอิงเงินประกัน"""
        origin = (invoice.invoice_origin or '').strip()
        if not origin:
            return False
        orders = self.env['sale.order'].sudo().search([('name', '=', origin)])
        return any((o.deposit_ref or '').strip() for o in orders)

    # ------------------------------------------------------------------
    @api.model
    def compute_sales_data(self, month, year, company=None):
        company = company or self.env.company
        Report = self.env['npd.commission.report']
        config = self.env['npd.commission.config'].get_for(company)
        config.check_ready()
        vat_divisor = config.vat_divisor
        date_from, date_to = Report._period_window(month, year)

        Move = self.env['account.move'].sudo()
        rental_ids = config.rental_journal_ids.ids
        invoice_journal_ids = rental_ids + config.penalty_journal_ids.ids
        gross_payment_ids = set(config.gross_payment_journal_ids.ids)
        headoffice = self._headoffice_user_ids()

        buckets = {}

        def bucket(sales_id, branch_id):
            key = (sales_id, branch_id)
            if key not in buckets:
                buckets[key] = {'rental_amount': 0.0, 'payment_received': 0.0,
                                'outstanding_debt': 0.0, 'shipping_cost': 0.0}
            return buckets[key]

        base = [
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('contact_type', '=', 'sale'),
            ('sales_contact_id', '!=', False),
        ]

        # ---------- ใบแจ้งหนี้ ----------
        for inv in Move.search(base + [
                ('journal_id', 'in', invoice_journal_ids),
                ('move_type', '=', 'out_invoice')]):
            data = bucket(inv.sales_contact_id.id,
                          inv.branch_id.id if inv.branch_id else False)
            if inv.journal_id.id in rental_ids:
                # Sales สนญ. คิดเฉพาะบิลแรก บิลต่ออายุไม่นับเป็นยอดเช่า
                if not (inv.sales_contact_id.id in headoffice
                        and self._is_renewal_invoice(inv)):
                    data['rental_amount'] += inv.amount_untaxed or 0.0
            data['outstanding_debt'] += Report._outstanding_residual_asof(
                inv, date_to, vat_divisor)

        # ---------- ใบลดหนี้ ----------
        if config.credit_note_journal_id:
            for cn in Move.search(base + [
                    ('journal_id', '=', config.credit_note_journal_id.id),
                    ('move_type', '=', 'out_refund')]):
                data = bucket(cn.sales_contact_id.id,
                              cn.branch_id.id if cn.branch_id else False)
                data['rental_amount'] -= cn.amount_untaxed or 0.0

        # ---------- ใบค่าปรับที่อยู่นอกสมุดข้างบน ----------
        penalty = self.env['scrap.reason.code'].sudo().search(
            [('name', 'in', ['สินค้าหาย', 'สินค้าชำรุด'])])
        if penalty:
            for pinv in Move.search(base + [
                    ('move_type', '=', 'out_invoice'),
                    ('reason_code_id', 'in', penalty.ids),
                    ('journal_id', 'not in', invoice_journal_ids)]):
                data = bucket(pinv.sales_contact_id.id,
                              pinv.branch_id.id if pinv.branch_id else False)
                data['outstanding_debt'] += Report._outstanding_residual_asof(
                    pinv, date_to, vat_divisor)

        # ---------- รับชำระหนี้ ----------
        if config.payment_journal_ids:
            payments = self.env['account.payment'].sudo().search([
                ('journal_id', 'in', config.payment_journal_ids.ids),
                ('company_id', '=', company.id),
                ('state', '=', 'posted'),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ])
            for payment in payments:
                for inv in payment.reconciled_invoice_ids:
                    if (inv.name or '').strip().upper().startswith('IV'):
                        continue
                    if not (inv.invoice_date and payment.date):
                        continue
                    if inv.contact_type != 'sale' or not inv.sales_contact_id:
                        continue
                    different_month = (
                        inv.invoice_date.month != payment.date.month
                        or inv.invoice_date.year != payment.date.year)
                    if not (different_month and payment.date > inv.invoice_date):
                        continue
                    data = bucket(inv.sales_contact_id.id,
                                  inv.branch_id.id if inv.branch_id else False)
                    amount = payment.amount or 0.0
                    if payment.journal_id.id in gross_payment_ids:
                        data['payment_received'] += amount
                    else:
                        data['payment_received'] += amount / vat_divisor
                    break

        # ---------- ค่าขนส่ง ----------
        self._add_shipping_cost(buckets, company, date_from, date_to)

        rows = []
        for (sales_id, branch_id), data in buckets.items():
            if not sales_id:
                continue
            net = (data['rental_amount'] + data['payment_received']
                   - data['outstanding_debt'] - data['shipping_cost'])
            rows.append({
                'company_id': company.id,
                'sales_contact_id': sales_id,
                'branch_id': branch_id or False,
                'month': str(int(month)),
                'year': str(year),
                'date_from': date_from,
                'date_to': date_to,
                'is_headoffice': sales_id in headoffice,
                'rental_amount': truncate_decimal(data['rental_amount']),
                'payment_received': truncate_decimal(data['payment_received']),
                'outstanding_debt': truncate_decimal(data['outstanding_debt']),
                'shipping_cost': truncate_decimal(data['shipping_cost']),
                'net_rental': truncate_decimal(net),
                'generated_at': fields.Datetime.now(),
            })
        return rows

    @api.model
    def _add_shipping_cost(self, buckets, company, date_from, date_to):
        """ค่าขนส่งจากใบสำคัญจ่าย หักออกจากยอดของเซลล์คนนั้น

        Odoo 14 จับคู่เซลล์และสาขาด้วย **ชื่อ** ซึ่งพลาดได้ถ้าชื่อซ้ำหรือ
        มีช่องว่างต่างกัน ที่นี่จับคู่ด้วยรหัสของเรคคอร์ดโดยตรง
        """
        Line = self.env.get('account.voucher.line')
        if Line is None or 'sales_contact_id' not in self.env['account.voucher.line']._fields:
            _logger.info('[COMMISSION] ไม่มีฟิลด์เซลล์บนใบสำคัญจ่าย ข้ามค่าขนส่ง')
            return
        VL = self.env['account.voucher.line'].sudo()
        domain = [
            ('sales_contact_id', '!=', False),
            ('voucher_id.state', 'in', ['posted', 'transferred']),
            ('voucher_id.company_id', '=', company.id),
        ]
        if 'payment_date' in VL._fields:
            domain += [('payment_date', '>=', date_from),
                       ('payment_date', '<=', date_to)]
        else:
            domain += [('voucher_id.date', '>=', date_from),
                       ('voucher_id.date', '<=', date_to)]
        for line in VL.search(domain):
            voucher = line.voucher_id
            branch = voucher.branch_id if 'branch_id' in voucher._fields else False
            key = (line.sales_contact_id.id, branch.id if branch else False)
            if key not in buckets:
                # ใบสำคัญจ่ายอาจอยู่คนละสาขากับที่มียอดเช่า — ยังต้องหักออก
                buckets[key] = {'rental_amount': 0.0, 'payment_received': 0.0,
                                'outstanding_debt': 0.0, 'shipping_cost': 0.0}
            buckets[key]['shipping_cost'] += line.price_subtotal or 0.0

    # ------------------------------------------------------------------
    @api.model
    def generate(self, month, year, company=None):
        company = company or self.env.company
        rows = self.compute_sales_data(month, year, company=company)
        result = self.browse()
        for vals in rows:
            existing = self.sudo().search([
                ('company_id', '=', vals['company_id']),
                ('sales_contact_id', '=', vals['sales_contact_id']),
                ('branch_id', '=', vals['branch_id']),
                ('month', '=', vals['month']),
                ('year', '=', vals['year']),
            ], limit=1)
            if existing:
                existing.sudo().write(vals)
                result |= existing
            else:
                result |= self.sudo().create(vals)
        _logger.info('[COMMISSION] รายงานค่าคอม Sales %s งวด %s/%s จำนวน %d แถว',
                     company.name, month, year, len(result))
        return result

    @api.model
    def get_net_rental(self, employee, month, year, company=None):
        """ยอดเช่าสุทธิรวมทุกสาขาของเซลล์คนนั้น — ฝั่งเงินเดือนเรียกตัวนี้"""
        company = company or self.env.company
        code = (employee.employee_code or '').strip()
        if not code:
            return 0.0
        records = self.sudo().search([
            ('employee_code', '=', code),
            ('company_id', '=', company.id),
            ('month', '=', str(int(month))),
            ('year', '=', str(year)),
        ])
        return sum(records.mapped('net_rental'))
