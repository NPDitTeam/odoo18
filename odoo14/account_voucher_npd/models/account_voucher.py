# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class AccountVoucher(models.Model):
    _name = 'account.voucher'
    _description = 'Accounting Voucher'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "date desc, id desc"

    def _default_journal(self):
        is_sale = self._context.get('voucher_type') == 'sale'
        journal_type = 'receivable' if is_sale else 'payable'
        company_id = self._context.get('company_id', self.env.company.id)
        company = self.env['res.company'].browse(company_id)

        # ตั้งค่าได้ที่ การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้
        # กรณี "ใบสำคัญรับ" / "ใบสำคัญจ่าย"
        journal = self.env['npd.invoice.journal.config']._get_journal(
            company, 'voucher_sale' if is_sale else 'voucher_purchase',
        )
        if journal:
            return journal

        # ไม่ได้ตั้งค่าไว้: เอาเล่มแรกตามเดิม
        # (ระวัง เล่ม 'Payable'/'Receivable' ที่ Odoo สร้างให้ตอนติดตั้งมี id ต่ำกว่า
        #  จึงชนะเล่มที่ใช้งานจริงเสมอ เป็นเหตุผลที่ควรตั้งค่าในเมนู)
        return self.env['account.journal'].search([
            ('type', '=', journal_type),
            ('company_id', '=', company_id),
        ], limit=1)

    def _default_payment_journal(self):
        company_id = self._context.get('company_id', self.env.company.id)
        domain = [
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', company_id),
        ]
        return self.env['account.journal'].search(domain, limit=1)

    voucher_type = fields.Selection([
        ('sale', 'Sale'),
        ('purchase', 'Purchase')
    ], string='Type', readonly=False)
    name = fields.Char('Payment Memo', readonly=False, copy=False)
    date = fields.Date("Bill Date", readonly=False, required=True,
                       index=True, copy=False, default=fields.Date.context_today)
    account_date = fields.Date("Accounting Date",
                               readonly=False, index=True,
                               help="Effective date for accounting entries", copy=False,
                               default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', 'Journal',
                                 required=True, readonly=False,
                                 default=_default_journal)
    payment_journal_id = fields.Many2one('account.journal', string='Payment Method', readonly=False,
                                         domain="[('type', 'in', ['cash', 'bank'])]", default=_default_payment_journal)
    account_id = fields.Many2one('account.account', 'Account',
                                 required=False, readonly=False,
                                 domain="[('deprecated', '=', False)]")
    line_ids = fields.One2many('account.voucher.line', 'voucher_id', 'Voucher Lines',
                               readonly=False, copy=True)
    narration = fields.Text('Notes', readonly=False, tracking=True)
    currency_id = fields.Many2one('res.currency', compute='_get_journal_currency',
                                  string='Currency', readonly=True, store=True,
                                  default=lambda self: self._get_currency())
    company_id = fields.Many2one('res.company', 'Company',
                                 store=True, readonly=True,
                                 default=lambda self: self._get_company())
    state = fields.Selection([
        ('draft', 'Draft'),
        ('paid', 'paid'),
        ('cancel', 'Cancelled'),
        ('proforma', 'Pro-forma'),
        ('posted', 'Posted')
    ], 'Status', readonly=True, copy=False, default='draft', tracking=True,
        help=" * The 'Draft' status is used when a user is encoding a new and unconfirmed Voucher.\n"
             " * The 'Pro-forma' status is used when the voucher does not have a voucher number.\n"
             " * The 'Posted' status is used when user create voucher,a voucher number is generated and voucher entries are created in account.\n"
             " * The 'Cancelled' status is used when user cancel voucher.")
    reference = fields.Char('Bill Reference', readonly=False,
                            help="The partner reference of this document.", copy=False)
    amount = fields.Monetary(string='Total', store=True, readonly=True, compute='_compute_total')
    tax_amount = fields.Monetary(readonly=True, store=True, compute='_compute_total')
    tax_correction = fields.Monetary(readonly=False,
                                     help='In case we have a rounding problem in the tax, use this field to correct it')
    number = fields.Char(readonly=True, copy=False)
    move_id = fields.Many2one('account.move', 'Journal Entry', copy=False)
    partner_id = fields.Many2one('res.partner', 'Partner', required=True, change_default=1, readonly=False)
    paid = fields.Boolean(compute='_check_paid', help="The Voucher has been totally paid.")
    pay_now = fields.Selection([
        ('pay_now', 'Pay Directly'),
        ('pay_later', 'Pay Later'),
    ], 'Payment', index=True, readonly=False, default='pay_now')
    date_due = fields.Date('Due Date', readonly=False, index=True)
    payment_method_id = fields.Many2one('custom.payment.method', string='Payment Method', required=False, tracking=True,
                                        domain="[('is_active','=',True),'|',('company_id', '=', False),('company_id', '=', company_id)]")
    cheque_id = fields.Many2one("account.cheque", string="Cheque",
                                domain="[('state', '=', 'draft')]")
    type = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
            ('bank', 'Bank'),
            ('discount', 'Discount'),
            ('ap', 'AP'),
            ('ar', 'AR'),
            ('other', 'Other'),
        ],
        string='Payment method',
        related='payment_method_id.type',
    )
    is_payment_multi = fields.Boolean(string='Payment Multi', default=False)
    wt_cert_ids = fields.One2many(
        comodel_name="withholding.tax.cert",
        inverse_name="voucher_id",
        string="Withholding Tax Cert.",
        readonly=False,
    )
    payment_ids = fields.One2many(comodel_name="account.voucher.payment", inverse_name="voucher_id", string="payment",
                                  required=False)
    wht_amount = fields.Monetary(string='Withholding Tax Amount', store=True, readonly=True, compute='_compute_total')
    cheque_type = fields.Selection(
        [
            ("outbound", "Payment Cheque"),
            ("inbound", "Receipt Cheque"),
        ],
        string="Cheque Type",
        default="inbound",
        required=True,
    )
    tax_line = fields.One2many(comodel_name="account.move.tax.invoice", inverse_name="voucher_id", string="",
                               required=False)
    old_move_name = fields.Char(
        string="Old Move name",
        required=False,
    )

    check_type_show = fields.Char('Check Type Show', readonly=True, store=True, compute="_compute_check_type")

    rental_return_select_id = fields.Many2one(
        'stock.picking',
        string='เลือกใบคืนการเช่า',
        domain="rental_return_domain",
        help="เลือกใบคืนการเช่าที่เกี่ยวข้อง",
        store=True
    )

    rental_return_id = fields.Many2one(
        'stock.picking',
        string='เลขใบคืนการเช่า',
        help="เลือกใบคืนการเช่าที่เกี่ยวข้อง", store=True, readonly=True
    )

    check_show = fields.Boolean(string="Check Show", default=False)
    check_type_show_selection = fields.Selection(
        [('true', 'True'), ('false', 'False')],
        string="Check Type Show",
        compute="_compute_check_type_show",
        store=True
    )
    no_deduction = fields.Boolean(string="ไม่หักค่าประกัน", default=True)

    invoice_ids = fields.Many2many(
        'account.move',
        string='หนี้ค้างชำระ',
        relation='voucher_move_rel_npd',
        column1='voucher_id',
        column2='move_id',
        domain=[],
    )

    available_invoice_ids = fields.Many2many(
        'account.move',
        string='Available Invoices',
        compute='_compute_available_invoice_ids',
        store=False,
    )
    total_outstanding = fields.Float(
        string='ยอดหนี้ค้างชำระรวม',
        compute='_compute_total_outstanding',
        store=True,
        digits=(12, 2)
    )

    payment_t_ids = fields.Many2many('account.payment', string="Payments")

    show_payment_button = fields.Boolean(
        compute='_compute_show_payment_button',
        store=False,
    )

    invoice_ref_ids = fields.Many2many(
        'account.move',
        string='อ้างอิงหนี้ค้างชำระ (ประวัติ)',
        help='บันทึกใบแจ้งหนี้ที่เคยถูกเลือกตอนกดรับชำระ เพื่ออ้างอิงภายหลัง',
        readonly=True
    )

    can_edit_lines = fields.Boolean(
        compute='_compute_can_edit_lines',
        store=False,
    )
    outstanding_amount_snapshot = fields.Float(
        string='ยอดค้างชำระรวมที่บันทึก',
        readonly=True,
        digits=(12, 2),
        copy=False,
    )

    payment_ref_id = fields.Many2one(
        'account.payment',
        string='ใบรับชำระค่าประกัน',
        compute='_compute_payment_from_reference',
        store=True,
        help='ใบรับชำระแรกที่พบจาก Bill Reference'
    )

    rental_return_domain = fields.Char(
        compute='_compute_rental_return_domain',
        readonly=True,
        store=False,
    )

    refund_of_rental = fields.Boolean(
        string="Show refund_of_rental",
        compute="_compute_refund_of_rental",
        store=False
    )

    @api.depends("check_show")
    def _compute_check_type_show(self):
        for record in self:
            _logger.info(f"[_compute_check_type_show] check_show = {record.check_show}")
            record.check_type_show_selection = 'true' if record.check_show else 'false'

    @api.model
    def default_get(self, fields_list):
        """ดึงค่า `default_check_show` จาก context แล้วตั้งค่าให้ `check_show`"""
        res = super().default_get(fields_list)
        context_check_show = self.env.context.get('default_check_show', False)
        res['check_show'] = context_check_show
        return res

    @api.depends('partner_id', 'reference')
    def _compute_rental_return_domain(self):
        """คำนวณ domain สำหรับ rental_return_select_id แบบ dynamic"""
        for rec in self:
            domain = [
                ('deposit_return_state', '=', 'not_returned'),
                ('name', 'not ilike', '%OUT%')
            ]

            if rec.reference and rec.check_show:
                sale_order = rec.env['sale.order'].search([
                    ('name', '=', rec.reference),
                    ('rental_status', '!=', 'done')
                ], limit=1)
                if sale_order:
                    domain.append(('group_id.name', '=', rec.reference))
                else:
                    domain.append(('id', '=', False))
            elif rec.partner_id:
                domain.append(('partner_id', '=', rec.partner_id.id))
                domain.append(('group_id.sale_id.rental_status', '!=', 'done'))
            else:
                domain.append(('id', '=', False))

            rec.rental_return_domain = str(domain)

    @api.depends('rental_return_select_id', 'partner_id', 'reference')
    def _compute_payment_from_reference(self):
        for rec in self:
            if not rec.reference or not rec.check_show:
                rec.payment_ref_id = False
                continue

            invoices = self.env['account.move'].search([
                ('invoice_origin', '=', rec.reference),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('name', 'ilike', 'INS-'),
            ], limit=1)

            if not invoices:
                rec.payment_ref_id = False
                continue

            payment = self.env['account.payment'].search([
                ('search_invoice_name', '=', invoices.name),
                ('state', '=', 'posted'),
                ('payment_type', '=', 'inbound')
            ], order='date desc', limit=1)

            if payment:
                rec.payment_ref_id = payment
            else:
                rec.payment_ref_id = False
                continue

    @api.depends('state')
    def _compute_can_edit_lines(self):
        for voucher in self:
            voucher.can_edit_lines = voucher.state == 'draft'

    @api.depends('invoice_ids', 'state', 'total_outstanding')
    def _compute_show_payment_button(self):
        for rec in self:
            rec.show_payment_button = bool(rec.invoice_ids) and rec.state == 'draft' and rec.total_outstanding > 0

    @api.onchange('partner_id', 'reference')
    def _onchange_rental_return_domain(self):
        """คำนวณ domain สำหรับ rental_return_select_id"""
        domain = [
            ('deposit_return_state', '=', 'not_returned'),
            ('name', 'not ilike', '%OUT%')
        ]

        if self.reference and self.check_show:
            sale_order = self.env['sale.order'].search([
                ('name', '=', self.reference),
                ('rental_status', '!=', 'done')
            ], limit=1)
            if sale_order:
                domain.append(('group_id.name', '=', self.reference))
            else:
                raise UserError(
                    _("ลูกค้า %s ได้ปิดบิล %s เรียบร้อยแล้ว") % (self.partner_id.name or '', self.reference))
        elif self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
            domain.append(('group_id.sale_id.rental_status', '!=', 'done'))
        else:
            domain.append(('id', '=', False))

        return {
            'domain': {
                'rental_return_select_id': domain
            }
        }

    @api.onchange('partner_id', 'voucher_type', 'reference')
    def _onchange_partner_filter_invoices(self):
        """กรอง Invoice ที่แสดงใน Dropdown แบบเข้มงวด + อัปเดต Picking"""

        if self.reference and self.check_show:
            sale_order = self.env['sale.order'].search([
                ('name', '=', self.reference),
                ('rental_status', '!=', 'done')
            ], limit=1)

            if not sale_order:
                self.rental_return_select_id = False
                self.rental_return_id = False
                raise UserError(
                    _("ลูกค้า %s ได้ปิดบิล %s เรียบร้อยแล้ว") % (self.partner_id.name or '', self.reference))

            picks = self.env['stock.picking'].search([
                ('group_id.name', '=', self.reference),
                ('deposit_return_state', '=', 'not_returned'),
                ('name', 'not ilike', '%OUT%')
            ], order='name desc', limit=1)

            self.rental_return_select_id = picks.id or False

            if self.rental_return_select_id:
                self.rental_return_id = self.rental_return_select_id

        elif self.partner_id:
            picks = self.env['stock.picking'].search([
                ('partner_id', '=', self.partner_id.id),
                ('deposit_return_state', '=', 'not_returned'),
                ('name', 'not ilike', '%OUT%'),
                ('group_id.sale_id.rental_status', '!=', 'done')
            ], order='name desc', limit=1)

            self.rental_return_select_id = picks.id or False

            if self.rental_return_select_id:
                self.rental_return_id = self.rental_return_select_id

        domain = self._get_invoice_domain()

        if self.partner_id:
            invoices = self.env['account.move'].search(domain)
            _logger.info(f"[FILTER] Partner: {self.partner_id.name}, Valid {len(invoices)} invoices")

        return {
            'domain': {
                'invoice_ids': domain
            }
        }

    def action_create_payment_from_outstanding(self):
        """สร้างใบรับชำระแยกใบตามจำนวน Invoice ที่เลือก"""
        if not self.refund_of_rental:
            raise UserError(_("อนุญาตเฉพาะการเงินส่วนกลางเท่านั้น ในการรับชำระหนี้ค้างชำระ"))

        self.ensure_one()

        if not self.invoice_ids or self.total_outstanding <= 0:
            raise UserError(_("ไม่มีหนี้ค้างชำระที่เลือก หรือยอดเป็น 0"))

        selected_invoices = self.invoice_ids
        selected_invoice_ids = selected_invoices.ids
        snapshot_amount = self.total_outstanding

        payment_method = self.env['custom.payment.method'].search([
            ('name', '=', 'หักเงินประกันค่าเช่า'),
            ('is_active', '=', True)
        ], limit=1)
        if not payment_method:
            raise UserError(_("ไม่พบวิธีการชำระ 'หักเงินประกันค่าเช่า' กรุณาตั้งค่าในระบบก่อน"))
        if not payment_method.account_id:
            raise UserError(_("วิธีการชำระ 'หักเงินประกันค่าเช่า' ยังไม่ได้ตั้งค่าบัญชี"))

        def get_journal_for_invoice(invoice):
            """สมุดรายวันที่จะใช้สร้าง account.payment ตัดหนี้ใบแจ้งหนี้ใบนี้

            เดิมเดาจากคำนำหน้าเลขที่เอกสาร (INV/ILS/IBK) ซึ่งผูกกับรูปแบบเลขที่
            ตอนนี้อิงสมุดรายวันของใบแจ้งหนี้ตรง ๆ ตั้งค่าได้ที่คอลัมน์
            "สมุดรายวันรับเงิน (Payment)" ในเมนูสมุดรายวันออกใบแจ้งหนี้

            ต้องเป็นประเภท ธนาคาร/เงินสด/เครดิต เท่านั้น เพราะ Odoo 18 บังคับว่า
            account.payment ใช้ได้แค่สามประเภทนี้ ถ้าใส่ receivable/payable เข้าไป
            จะโพสต์ไม่ผ่านเพราะหา payment_method_line_id ไม่เจอ
            """
            journal = self.env['npd.invoice.journal.config']._get_payment_journal(
                self.company_id, invoice.journal_id,
            )
            # เล่มที่ตั้งไว้ต้องรองรับ account.payment จริง ๆ ไม่งั้นโพสต์ไม่ผ่าน
            # (Odoo 18 ให้เฉพาะ bank/cash/credit และต้องมี payment_method_line)
            if journal and journal.inbound_payment_method_line_ids:
                return journal
            if journal:
                _logger.warning(
                    "สมุดรายวัน '%s' ที่ตั้งไว้สำหรับใบแจ้งหนี้ %s ใช้กับ account.payment ไม่ได้ "
                    "(ประเภท '%s' ไม่มี payment method) จะใช้สมุดรายวันธนาคาร/เงินสดแทน",
                    journal.display_name, invoice.name or '', journal.type,
                )

            # ไม่ได้ตั้งค่าไว้ หรือเล่มที่ตั้งไว้ใช้ไม่ได้: เอาเล่มแรกที่ใช้ได้จริง
            default_journal = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash', 'credit')),
                ('company_id', '=', self.company_id.id),
                ('inbound_payment_method_line_ids', '!=', False),
            ], limit=1)

            if not default_journal:
                raise UserError(_(
                    "ไม่พบสมุดรายวันสำหรับรับชำระเงินของบริษัท %(company)s\n"
                    "กรุณาตั้งค่าคอลัมน์ \"สมุดรายวันรับเงิน (Payment)\" "
                    "ของสมุดรายวัน %(journal)s ที่เมนู\n"
                    "การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้",
                    company=self.company_id.display_name,
                    journal=invoice.journal_id.display_name,
                ))

            return default_journal

        destination_account = self.partner_id.property_account_receivable_id
        if not destination_account:
            raise UserError(_("ลูกค้ายังไม่ได้ตั้งค่าบัญชีลูกหนี้"))

        created_payments = self.env['account.payment']

        for invoice in selected_invoices:
            amount_residual = invoice.amount_residual
            if amount_residual <= 0:
                continue

            journal = get_journal_for_invoice(invoice)

            invoice_lines = [(0, 0, {
                'invoice_id': invoice.id,
                'amount_due': amount_residual,
                'amount_total': invoice.amount_total,
                'paid': True,
                'paid_total': amount_residual,
                'wht_total': invoice.wht_amt or 0,
                'wht_base': invoice.wht_base or 0,
            })]

            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': self.partner_id.id,
                'amount': amount_residual,
                'currency_id': self.currency_id.id or self.company_id.currency_id.id,
                'date': self.date,
                'journal_id': journal.id,
                'payment_method_one_id': payment_method.id,
                'is_payment_multi': False,
                'invoice_ids': invoice_lines,
                'destination_account_id': destination_account.id,
                'search_invoice_name': invoice.name,
                'ref': f"เปิดบิลเช่าหักจากเงินประกัน {self.number or 'Draft Voucher'} - {invoice.name}",
            }

            payment = self.env['account.payment'].create(payment_vals)

            try:
                payment.action_post()
                payment.voucher_source_id = self.id
                created_payments |= payment
            except Exception as e:
                if payment.exists():
                    payment.unlink()
                raise UserError(_("ไม่สามารถบันทึกใบรับชำระสำหรับ %s: %s") % (invoice.name, str(e)))

        if created_payments:
            self.invoice_ref_ids = [(4, inv_id) for inv_id in selected_invoice_ids]
            current_snapshot = self.outstanding_amount_snapshot
            self.outstanding_amount_snapshot = current_snapshot + snapshot_amount

            self._onchange_rental_return_select_id()

            for payment in created_payments:
                self.payment_t_ids = [(4, payment.id)]

            self.invoice_ids = [(5, 0, 0)]

            payment_names = ', '.join(created_payments.mapped('name'))
            self.message_post(
                body=f"<p>สร้างใบรับชำระสำเร็จ {len(created_payments)} ใบ:</p>"
                     f"<p><b>{payment_names}</b></p>"
                     f"<p>ยอดเงินรวม: <b>{snapshot_amount:,.2f}</b> {self.currency_id.name or 'THB'}</p>"
                     f"<p>วิธีชำระ: <b>{payment_method.name}</b></p>"
            )

            return {
                'name': _('ใบรับชำระ'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created_payments.ids)],
                'target': 'current',
            }
        else:
            raise UserError(_("ไม่สามารถสร้างใบรับชำระได้"))

    @api.depends('partner_id', 'voucher_type', 'state')
    def _compute_available_invoice_ids(self):
        for rec in self:
            if not rec.partner_id:
                rec.available_invoice_ids = [(5, 0, 0)]
                continue

            domain = [
                ('partner_id', '=', rec.partner_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('amount_residual', '>', 0),
            ]

            invoices = self.env['account.move'].search(domain)
            rec.available_invoice_ids = [(6, 0, invoices.ids)]

    @api.depends('invoice_ids')
    def _compute_total_outstanding(self):
        for rec in self:
            if not rec.check_show:
                rec.total_outstanding = 0.0
                continue

            if not rec.invoice_ids:
                rec.total_outstanding = 0.0
                continue

            # Odoo 18: invalidate_recordset แทน invalidate_cache
            fresh_invoices = self.env['account.move'].browse(rec.invoice_ids.ids)
            fresh_invoices.invalidate_recordset(['amount_residual', 'payment_state'])

            total = sum(fresh_invoices.mapped('amount_residual'))
            rec.total_outstanding = total

    @api.onchange('reference')
    def _onchange_reference(self):
        if self.reference and self.check_show:
            sale_order = self.env['sale.order'].search([
                ('name', '=', self.reference),
                ('rental_status', '!=', 'done')
            ], limit=1)

            if not sale_order:
                self.rental_return_select_id = False
                self.rental_return_id = False
                raise UserError(
                    _("ลูกค้า %s ได้ปิดบิล %s เรียบร้อยแล้ว") % (self.partner_id.name or '', self.reference))

            picks = self.env['stock.picking'].search([
                ('group_id.name', '=', self.reference),
                ('deposit_return_state', '=', 'not_returned'),
                ('name', 'not ilike', '%OUT%')
            ], order='name desc', limit=1)

            if picks:
                self.rental_return_select_id = picks.id
                self.rental_return_id = picks.id

    @api.model
    def _get_invoice_domain(self):
        if not self.partner_id:
            return [('id', '=', False)]

        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('amount_residual', '>', 0),
        ]

        return domain

    @api.onchange('invoice_ids')
    def _onchange_invoice_ids_proxy(self):
        if self.invoice_ids:
            fresh_invoices = self.env['account.move'].browse(self.invoice_ids.ids)
            fresh_invoices.invalidate_recordset(['amount_residual', 'payment_state'])

            for inv in fresh_invoices:
                _ = inv.amount_residual
                _ = inv.payment_state

        self._compute_total_outstanding()
        self._onchange_rental_return_select_id()

        # สมุดรายวันของใบสำคัญ อิงสมุดรายวันของใบแจ้งหนี้ที่เลือก
        # ตั้งค่าได้ที่คอลัมน์ "สมุดรายวันรับชำระ (ใบสำคัญ)" ในเมนู
        # การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้
        if self.invoice_ids:
            voucher_journal = self.env['npd.invoice.journal.config']._get_voucher_journal(
                self.company_id, self.invoice_ids.journal_id,
            )
            # ตั้งเฉพาะเล่มที่ตรงประเภทกับใบสำคัญใบนี้ (รับ=receivable, จ่าย=payable)
            # ไม่งั้นจะสลับประเภทเอกสารโดยไม่ตั้งใจ
            wanted_type = 'receivable' if self.voucher_type == 'sale' else 'payable'
            if voucher_journal and voucher_journal.type == wanted_type:
                self.journal_id = voucher_journal

    @api.onchange('rental_return_select_id', 'rental_return_id', 'no_deduction', 'invoice_ids')
    def _onchange_rental_return_select_id(self):

        def _to_float(v):
            try:
                return float(v or 0.0)
            except Exception:
                return 0.0

        for record in self:
            record.check_type_show = 'show' if record.partner_id else ''

            def _remove_line(prod=None, name=None):
                if record.id:
                    dom = [('voucher_id', '=', record.id)]
                    if prod:
                        dom.append(('product_id', '=', prod.id))
                    else:
                        dom += [('product_id', '=', False), ('name', '=', name)]
                    record.env['account.voucher.line'].search(dom).unlink()
                else:
                    olds = (record.line_ids.filtered(lambda l: l.product_id == prod) if prod
                            else record.line_ids.filtered(lambda l: not l.product_id and l.name == name))
                    if olds:
                        record.line_ids -= olds

            if not record.rental_return_select_id:
                prod_dep = record.env['product.product'].search([('name', '=', "เงินประกันค่าเช่า")], limit=1)
                if prod_dep:
                    _remove_line(prod=prod_dep)
                continue

            picking = record.env['stock.picking'].browse(record.rental_return_select_id.id)
            if not picking:
                continue

            record.rental_return_id = record.rental_return_select_id
            if record.check_show:
                record.reference = picking.group_id.name

            if picking.origin:
                related_picking = record.env['stock.picking'].browse(record.rental_return_select_id.id)
            else:
                related_picking = False

            if not related_picking:
                prod_dep = record.env['product.product'].search([('name', '=', "เงินประกันค่าเช่า")], limit=1)
                if prod_dep:
                    _remove_line(prod=prod_dep)
                continue

            # ---- ค่าพื้นฐาน ----
            pfb_amount = _to_float(related_picking.sale_id.pfb_amount if related_picking.sale_id else 0.0)
            amount_total = _to_float(related_picking.sale_id.amount_total if related_picking.sale_id else 0.0)
            if related_picking.approval_state == 'approved':
                total_rental_discount = related_picking.rent_discount
            else:
                total_rental_discount = 0.0

            sx = picking.start_x_date.date() if isinstance(picking.start_x_date, datetime) else picking.start_x_date
            ex = picking.end_x_date.date() if isinstance(picking.end_x_date, datetime) else picking.end_x_date
            fx = picking.return_date.date() if isinstance(picking.return_date, datetime) else picking.return_date

            if sx and ex and fx:
                total_days = (ex - sx).days or 1
                actual_days = (fx - sx).days or 1
                daily_cost = (amount_total / total_days) if total_days > 0 else 0.0
                value_16 = (daily_cost * actual_days) - amount_total
            else:
                value_16 = 0.0

            deposit_ref = related_picking.sale_id.deposit_ref or ''
            deposit_count = len(deposit_ref.split(',')) if deposit_ref else 0

            if deposit_count == 0:
                is_referenced_by_other = record.env['sale.order'].search([
                    ('deposit_ref', '=', related_picking.sale_id.name),
                    ('state', '=', 'sale')
                ], limit=1)

                campaign_name = getattr(related_picking.sale_id.campaign_id, 'name', '') or ''

                if campaign_name in ['โปร 2026 ส่งฟรีไม่เกิน 25 Km.', 'โปร 2026 ส่งฟรีไม่เกิน 35 Km.']:
                    today_date = fields.Date.today()
                    if today_date > ex:
                        value_18 = (value_16 - total_rental_discount)
                    else:
                        value_18 = (0 - total_rental_discount)

                elif 'เรทเดือน' in getattr(related_picking.sale_id.pricelist_id, 'name', ''):
                    dd = (1 if (fx == sx) else (fx - sx).days)

                    if deposit_count == 0 and not is_referenced_by_other and fx <= ex:
                        value_18 = (0 - total_rental_discount)
                    elif deposit_count == 0 and not is_referenced_by_other and fx > ex:
                        value_18 = (value_16 - total_rental_discount)
                    elif deposit_count == 0 and is_referenced_by_other and fx > ex:
                        value_18 = (value_16 - total_rental_discount)
                    elif deposit_count == 0 and is_referenced_by_other:
                        value_18 = (0 - total_rental_discount)
                    else:
                        if dd < 30:
                            value_18 = (0 - total_rental_discount)
                        else:
                            value_18 = (value_16 - total_rental_discount)
                else:
                    value_18 = value_16 - total_rental_discount

            else:
                deposit_refs = [ref.strip() for ref in deposit_ref.split(',')]

                related_pickings = record.env['stock.picking'].search([
                    ('group_id.name', 'in', deposit_refs)
                ])

                has_diff_end_date = 0
                if related_pickings:
                    for rp in related_pickings:
                        rp_end_date = rp.end_x_date.date() if isinstance(rp.end_x_date, datetime) else rp.end_x_date
                        if rp_end_date != ex:
                            has_diff_end_date = 1
                            break

                if related_pickings:
                    if has_diff_end_date == 0 and fx <= ex:
                        campaign_name = getattr(related_picking.sale_id.campaign_id, 'name', '') or ''

                        if campaign_name in ['โปร 2026 ส่งฟรีไม่เกิน 25 Km.', 'โปร 2026 ส่งฟรีไม่เกิน 35 Km.']:
                            value_18 = (0 - total_rental_discount)
                        elif 'เรทเดือน' in getattr(related_picking.sale_id.pricelist_id, 'name', ''):
                            dd = (1 if (fx == sx) else (fx - sx).days)
                            if dd < 30:
                                value_18 = (0 - total_rental_discount)
                            else:
                                value_18 = (value_16 - total_rental_discount)
                        else:
                            value_18 = value_16 - total_rental_discount
                    else:
                        value_18 = value_16 - total_rental_discount
                else:
                    value_18 = value_16 - total_rental_discount

            # สินค้าหาย / สินค้าชำรุด
            debit_notes_l = related_picking.sale_id.invoice_ids.mapped('debit_note_ids').filtered(
                lambda dn: dn.state == 'posted' and dn.reason_code_id and dn.reason_code_id.name == 'สินค้าหาย'
            )
            total_l = _to_float(sum(debit_notes_l.mapped('amount_total')) or 0.0)

            debit_notes_d = related_picking.sale_id.invoice_ids.mapped('debit_note_ids').filtered(
                lambda dn: dn.state == 'posted' and dn.reason_code_id and dn.reason_code_id.name == 'สินค้าชำรุด'
            )
            total_d = _to_float(sum(debit_notes_d.mapped('amount_total')) or 0.0)

            discount_total_d = 0.0
            for debit_note in debit_notes_d:
                for line in debit_note.invoice_line_ids:
                    if line.discount_method == 'per':
                        discount_value = ((line.quantity * line.price_unit) * line.discount_amount / 100)
                        discount_total_d += _to_float(discount_value)
                    else:
                        discount_total_d += _to_float(line.discount_amount)

            discount_total_d = _to_float(discount_total_d or 0.0)

            # สินค้า/บัญชี
            prod_dep = record.env['product.product'].search([('name', '=', "เงินประกันค่าเช่า")], limit=1)
            if not prod_dep:
                raise UserError(_("ไม่พบสินค้า '%s'") % "เงินประกันค่าเช่า")
            acc_dep = prod_dep.property_account_income_id.id or prod_dep.categ_id.property_account_income_categ_id.id
            if not acc_dep:
                raise UserError(_("สินค้า '%s' ยังไม่ได้ตั้งค่าบัญชีรายได้") % "เงินประกันค่าเช่า")

            _remove_line(prod=prod_dep)

            deposit_base = _to_float(pfb_amount - ((total_l + total_d) - discount_total_d))
            calculated_result = _to_float(pfb_amount - ((value_18 + total_l + total_d) - discount_total_d))

            total_outs = _to_float(
                sum(record.env['account.move'].browse(record.invoice_ids.ids).mapped('amount_residual')))

            def add_outstanding(amount):
                snapshot = _to_float(record.outstanding_amount_snapshot)
                if snapshot > 0 and amount > 0:
                    return amount - snapshot
                return amount

            if value_18 < 0:
                dep_base = _to_float(pfb_amount) if record.no_deduction else deposit_base
                dep_amt = add_outstanding(dep_base)
                if dep_amt != 0.0:
                    record.line_ids |= record.env['account.voucher.line'].new({
                        'product_id': prod_dep.id,
                        'name': prod_dep.name,
                        'quantity': 1.0,
                        'price_unit': dep_amt,
                        'account_id': acc_dep,
                    })
            else:
                dep_base = _to_float(pfb_amount) if record.no_deduction else calculated_result
                dep_amt = add_outstanding(dep_base)
                if dep_amt != 0.0:
                    record.line_ids |= record.env['account.voucher.line'].new({
                        'product_id': prod_dep.id,
                        'name': prod_dep.name,
                        'quantity': 1.0,
                        'price_unit': dep_amt,
                        'account_id': acc_dep,
                    })

    @api.depends('move_id.line_ids.reconciled', 'move_id.line_ids.account_id.account_type')
    def _check_paid(self):
        for voucher in self:
            voucher.paid = any(
                [((line.account_id.account_type in ('asset_receivable', 'liability_payable')) and line.reconciled)
                 for line in voucher.move_id.line_ids])

    def _get_currency(self):
        journal = self.env['account.journal'].browse(self.env.context.get('default_journal_id', False))
        if journal.currency_id:
            return journal.currency_id.id
        return self.env.company.currency_id.id

    def _get_company(self):
        return self.env.company

    @api.constrains('company_id', 'currency_id')
    def _check_company_id(self):
        for voucher in self:
            if not voucher.company_id:
                raise ValidationError(_("Missing Company"))
            if not voucher.currency_id:
                raise ValidationError(_("Missing Currency"))

    def _compute_display_name(self):
        for r in self:
            r.display_name = r.number or _('Voucher')

    @api.depends('journal_id', 'company_id')
    def _get_journal_currency(self):
        for voucher in self:
            voucher.currency_id = voucher.journal_id.currency_id.id or voucher.company_id.currency_id.id

    def _get_tax_vals(self):
        for voucher in self:
            tax_vals = {}
            for line in voucher.line_ids:
                tax_info = line.tax_ids.compute_all(line.price_unit, voucher.currency_id, line.quantity,
                                                    line.product_id, voucher.partner_id)
                for t in tax_info.get('taxes', False):
                    tax_vals.setdefault(
                        t['id'], {"amount": 0.0, "base": 0.0, "account_id": "", "tax_repartition_line_id": ""}
                    )
                    tax_vals[t['id']]["account_id"] = t['account_id']
                    tax_vals[t['id']]["name"] = t['name']
                    tax_vals[t['id']]["tax_repartition_line_id"] = t['tax_repartition_line_id']
                    tax_vals[t['id']]["amount"] += t["amount"]
                    tax_vals[t['id']]["base"] += t["base"]
            return tax_vals

    @api.depends('tax_correction', 'line_ids.price_subtotal', 'wt_cert_ids')
    def _compute_total(self):
        tax_calculation_rounding_method = self.env.company.tax_calculation_rounding_method
        for voucher in self:
            total = 0
            tax_amount = 0
            tax_lines_vals_merged = {}

            for line in voucher.line_ids:
                tax_info = line.tax_ids.compute_all(line.price_unit, voucher.currency_id, line.quantity,
                                                    line.product_id, voucher.partner_id)
                if tax_calculation_rounding_method == 'round_globally':
                    total += tax_info.get('total_excluded', 0.0)
                    for t in tax_info.get('taxes', False):
                        key = (
                            t['id'],
                            t['account_id'],
                        )
                        if key not in tax_lines_vals_merged:
                            tax_lines_vals_merged[key] = t.get('amount', 0.0)
                        else:
                            tax_lines_vals_merged[key] += t.get('amount', 0.0)
                else:
                    total += tax_info.get('total_included', 0.0)
                    tax_amount += sum([t.get('amount', 0.0) for t in tax_info.get('taxes', False)])
            if tax_calculation_rounding_method == 'round_globally':
                tax_amount = sum([voucher.currency_id.round(t) for t in tax_lines_vals_merged.values()])
                voucher.amount = total + tax_amount + voucher.tax_correction
            else:
                voucher.amount = total + voucher.tax_correction
            voucher.tax_amount = tax_amount
            voucher.wht_amount = sum(line.tax_amount for line in voucher.wt_cert_ids)

    @api.onchange('date')
    def onchange_date(self):
        self.account_date = self.date

    @api.onchange('partner_id', 'pay_now')
    def onchange_partner_id(self):
        pay_journal_domain = [('type', 'in', ['cash', 'bank'])]
        if self.partner_id:
            self.account_id = self.partner_id.property_account_receivable_id \
                if self.voucher_type == 'sale' else self.partner_id.property_account_payable_id
        else:
            if self.voucher_type == 'purchase':
                pay_journal_domain.append(('outbound_payment_method_line_ids', '!=', False))
            else:
                pay_journal_domain.append(('inbound_payment_method_line_ids', '!=', False))
        return {'domain': {'payment_journal_id': pay_journal_domain}}

    @api.depends()
    def _compute_refund_of_rental(self):
        for rec in self:
            rec.refund_of_rental = self.env.user.refund_of_rental

    def proforma_voucher(self):
        self.action_move_line_create()
        for record in self:
            if record.state == 'posted' and record.rental_return_select_id:
                picking = self.env['stock.picking'].browse(record.rental_return_select_id.id)
                if picking:
                    picking.write({'deposit_return_state': 'returned'})

                if record.reference:
                    sale_order = self.env['sale.order'].search([('name', '=', record.reference)], limit=1)
                    if sale_order:
                        sale_order.write({
                            'rental_status': 'done',
                            'check_state': 'done',
                        })

                        if sale_order.deposit_ref:
                            ref_names = sale_order.deposit_ref.split(',')

                            for ref_name in ref_names:
                                ref_name = ref_name.strip()
                                if not ref_name:
                                    continue

                                sale_order_deposit_ref = self.env['sale.order'].search([('name', '=', ref_name)],
                                                                                       limit=1)

                                if sale_order_deposit_ref:
                                    sale_order_deposit_ref.sudo().write({
                                        'rental_status': 'done',
                                        'check_state': 'done',
                                    })

                                    picking_related = self.env['stock.picking'].search([
                                        ('group_id.name', '=', sale_order_deposit_ref.name),
                                        ('name', 'like', '%IN%')
                                    ], limit=1)

                                    if picking_related:
                                        picking_related.write({'deposit_return_state': 'returned'})

                    else:
                        _logger.warning("ไม่พบเอกสาร %s", record.reference)

    def action_cancel_draft(self):
        """Set voucher กลับเป็น Draft, ยกเลิก Payment ที่เกี่ยวข้อง และเคลียร์ค่าอ้างอิง (รวม Snapshot)"""
        self.ensure_one()
        self.write({'state': 'draft'})

        payments_to_unlink = self.env['account.payment']

        if self.payment_t_ids:
            for payment in self.payment_t_ids:
                if not payment.exists():
                    self.message_post(
                        body=f"<p>ข้ามการยกเลิก Payment ID: {payment.id} เนื่องจากถูกลบไปแล้ว.</p>"
                    )
                    continue

                try:
                    if payment.state == 'posted':
                        if payment.move_id and payment.move_id.exists():
                            reconciled_lines = payment.move_id.line_ids.filtered(lambda l: l.reconciled)
                            if reconciled_lines:
                                reconciled_lines.remove_move_reconcile()

                            payment.move_id.button_draft()
                            payment.move_id.button_cancel()
                            payment.move_id.with_context(force_delete=True).unlink()

                        if payment.exists():
                            payment.write({'state': 'draft'})
                            self.message_post(body=f"<p>ยกเลิกใบรับชำระ: <b>{payment.name}</b></p>")
                            payments_to_unlink |= payment

                except Exception as e:
                    self.message_post(
                        body=f"<p>ไม่สามารถยกเลิก Payment {payment.name} (ID {payment.id}): {str(e)}</p>"
                    )

        if payments_to_unlink:
            payments_to_unlink.unlink()

        update_vals = {}

        if self.outstanding_amount_snapshot > 0:
            snapshot = self.outstanding_amount_snapshot

            update_vals['total_outstanding'] = snapshot
            update_vals['outstanding_amount_snapshot'] = 0.0

            for line in self.line_ids:
                if line.price_unit != 0 and line.product_id.name == "เงินประกันค่าเช่า":
                    old_price = line.price_unit
                    new_price = old_price + snapshot
                    line.write({'price_unit': new_price})

                    self.message_post(
                        body=f"<p>ปรับ '{line.name}' จาก {old_price:,.2f} เป็น {new_price:,.2f} "
                             f"(คืนยอดค้างชำระ {snapshot:,.2f})</p>"
                    )

            self.message_post(body=f"<p>คืนค่ายอดค้างชำระรวม: {snapshot:,.2f} บาท</p>")

        update_vals['invoice_ids'] = [(5, 0, 0)]
        update_vals['invoice_ref_ids'] = [(5, 0, 0)]
        update_vals['payment_t_ids'] = [(5, 0, 0)]

        if update_vals:
            self.write(update_vals)

        self.message_post(body="<p>เคลียร์ความสัมพันธ์หนี้ค้างชำระและใบรับชำระทั้งหมดเรียบร้อยแล้ว.</p>")

        for record in self:
            picking = self.env['stock.picking'].browse(record.rental_return_select_id.id)
            if picking and picking.exists():
                picking.write({'deposit_return_state': 'not_returned'})

            if record.reference:
                sale_order = self.env['sale.order'].search([('name', '=', record.reference)], limit=1)
                if sale_order:
                    if sale_order.deposit_ref:
                        ref_names = sale_order.deposit_ref.split(',')

                        for ref_name in ref_names:
                            ref_name = ref_name.strip()
                            if not ref_name:
                                continue

                            sale_order_deposit_ref = self.env['sale.order'].search([('name', '=', ref_name)], limit=1)

                            if sale_order_deposit_ref:
                                picking_related = self.env['stock.picking'].search([
                                    ('group_id.name', '=', sale_order_deposit_ref.name),
                                    ('name', 'like', '%IN%')
                                ], limit=1)

                                if picking_related:
                                    picking_related.write({'deposit_return_state': 'not_returned'})

        return True

    def cancel_voucher(self):
        for voucher in self:
            voucher.old_move_name = voucher.move_id.name
            voucher.move_id.button_cancel()
            voucher.move_id.unlink()
            voucher.message_post(body="<p><b>Cancel Receipts </b> </p>"
                                      "<p><b>Cancel Date:</b> %s </p>"
                                      "<p><b>Total:</b> %s </p>" % (
                                          datetime.today().strftime('%d/%m/%Y'), voucher.amount))
        self.write({'state': 'cancel', 'move_id': False})

    def unlink(self):
        for voucher in self:
            if voucher.state not in ('draft', 'cancel'):
                raise UserError(_('Cannot delete voucher(s) which are already opened or paid.'))
        return super().unlink()

    def first_move_line_get(self, move_id, company_currency, current_currency):
        debit = credit = 0.0
        amount = abs(self.amount - self.wht_amount)
        if self.voucher_type == 'purchase':
            if self.amount < 0:
                debit = amount
            else:
                credit = amount
        elif self.voucher_type == 'sale':
            if self.amount < 0:
                credit = amount
            else:
                debit = amount

        sign = debit - credit < 0 and -1 or 1

        move_line = {
            'name': self.payment_method_id.name or '/',
            'debit': debit,
            'credit': credit,
            'account_id': self.payment_method_id.account_id.id,
            'move_id': move_id,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'currency_id': company_currency != current_currency and current_currency or False,
            'amount_currency': (sign * abs(self.amount)
                                if company_currency != current_currency else 0.0),
            'date': self.account_date,
            'date_maturity': self.date_due,
        }
        return move_line

    def multi_move_line_get(self, move_id, company_currency, current_currency, payment_method_id, amount):
        debit = credit = 0.0

        if self.voucher_type == 'purchase':
            if amount < 0:
                debit = amount
            else:
                credit = amount
        elif self.voucher_type == 'sale':
            if amount < 0:
                credit = amount
            else:
                debit = amount
        sign = debit - credit < 0 and -1 or 1

        move_line = {
            'name': payment_method_id.name or '/',
            'debit': debit,
            'credit': abs(credit),
            'account_id': payment_method_id.account_id.id,
            'move_id': move_id,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'currency_id': company_currency != current_currency and current_currency or False,
            'amount_currency': (sign * abs(amount)
                                if company_currency != current_currency else 0.0),
            'date': self.account_date,
            'date_maturity': self.date_due,
        }
        return move_line

    def wht_move_line_get(self, move_id, company_currency, current_currency, wht_line):
        debit = credit = 0.0
        if self.voucher_type == 'purchase':
            credit = self._convert(wht_line.tax_amount)
        elif self.voucher_type == 'sale':
            debit = self._convert(wht_line.tax_amount)
        if debit < 0.0: debit = 0.0
        if credit < 0.0: credit = 0.0
        sign = debit - credit < 0 and -1 or 1
        wht_account_id = wht_line.account_id.id
        move_line = {
            'name': _('Withholding Tax'),
            'debit': debit,
            'credit': credit,
            'account_id': wht_account_id,
            'move_id': move_id,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'currency_id': company_currency != current_currency and current_currency or False,
            'amount_currency': (sign * abs(self.amount)
                                if company_currency != current_currency else 0.0),
            'date': self.account_date,
            'date_maturity': self.date_due,
        }
        return move_line

    def get_seq_voucher(self):
        if self.number:
            return self.number
        elif self.voucher_type == "sale":
            return self.env["ir.sequence"].next_by_code("sale.receipt", sequence_date=self.date)
        elif self.voucher_type == "purchase":
            return self.env["ir.sequence"].next_by_code("purchase.receipt", sequence_date=self.date)

    def account_move_get(self):
        move = {
            'journal_id': self.journal_id.id,
            'narration': self.narration,
            'date': self.account_date,
            'ref': self.reference,
            'voucher_id': self.id,
        }
        if self.old_move_name:
            move.update({
                'name': self.old_move_name,
                'sequence_generated': True
            })

        return move

    def _convert(self, amount):
        for voucher in self:
            return voucher.currency_id._convert(amount, voucher.company_id.currency_id, voucher.company_id,
                                                voucher.account_date)

    def _create_tax_move(self, move_id, move_line_id, tax_line_id, tax_base=0.00, tax_amount=0.00):
        TaxInvoice = self.env["account.move.tax.invoice"]
        taxinv = TaxInvoice.create(
            {
                "move_id": move_id,
                "move_line_id": move_line_id.id,
                "voucher_id": self.id,
                "partner_id": self.partner_id.id,
                "tax_invoice_number": move_line_id.move_id.name,
                "tax_invoice_date": fields.Date.today() or False,
                "tax_base_amount": abs(tax_base),
                "balance": abs(tax_amount),
                'tax_line_id': tax_line_id,
            }
        )

    def voucher_move_line_create(self, line_total, move_id, company_currency, current_currency):
        tax_calculation_rounding_method = self.env.company.tax_calculation_rounding_method
        tax_lines_vals = []
        for line in self.line_ids:
            if not line.price_subtotal:
                continue
            line_subtotal = line.price_subtotal
            if self.voucher_type == 'sale':
                line_subtotal = -1 * line.price_subtotal
            credit = debit = 0
            if self.voucher_type == 'sale':
                if line.price_subtotal < 0:
                    debit = abs(line_subtotal)
                else:
                    credit = abs(line_subtotal)
            else:
                if line.price_subtotal < 0:
                    credit = abs(line_subtotal)
                else:
                    debit = abs(line_subtotal)

            move_line = {
                'journal_id': self.journal_id.id,
                'name': line.name or '/',
                'account_id': line.account_id.id,
                'move_id': move_id,
                'quantity': line.quantity,
                'product_id': line.product_id.id,
                'partner_id': self.partner_id.commercial_partner_id.id,
                'analytic_distribution': line.analytic_distribution or False,
                'credit': credit,
                'debit': debit,
                'date': self.account_date,
                'tax_ids': [(4, t.id) for t in line.tax_ids],
                'amount_currency': line_subtotal if current_currency != company_currency else 0.0,
                'currency_id': company_currency != current_currency and current_currency or False,
                'payment_id': self._context.get('payment_id'),
            }
            self.env['account.move.line'].create(move_line)
        return line_total

    def vat_move_line_create(self, move_id, company_currency, current_currency):
        tax_vals = self._get_tax_vals()
        Currency = self.env['res.currency']
        company_cur = Currency.browse(company_currency)
        current_cur = Currency.browse(current_currency)
        for tax in tax_vals:
            temp = {
                'account_id': tax_vals[tax]['account_id'],
                'name': tax_vals[tax]['name'],
                'tax_line_id': tax,
                'move_id': move_id,
                'date': self.account_date,
                'partner_id': self.partner_id.id,
                'debit': self.voucher_type != 'sale' and tax_vals[tax]['amount'] or 0.0,
                'credit': self.voucher_type == 'sale' and tax_vals[tax]['amount'] or 0.0,
            }
            if company_currency != current_currency:
                ctx = {}
                sign = temp['credit'] and -1 or 1
                amount_currency = company_cur._convert(tax_vals[tax]['amount'], current_cur, self.company_id,
                                                       self.account_date or fields.Date.today(), round=True)
                if self.account_date:
                    ctx['date'] = self.account_date
                temp['currency_id'] = current_currency
                temp['amount_currency'] = sign * abs(amount_currency)

            move_line_id = self.env['account.move.line'].create(temp)
            self._create_tax_move(move_id, move_line_id, tax, tax_vals[tax]['base'], tax_vals[tax]['amount'])
            move_line_id.update({'tax_repartition_line_id': tax_vals[tax]['tax_repartition_line_id']})

    def action_move_line_create(self):
        '''
        Confirm the vouchers given in ids and create the journal entries for each of them
        '''
        for voucher in self:
            local_context = dict(self._context)
            if voucher.move_id:
                continue
            company_currency = voucher.journal_id.company_id.currency_id.id
            current_currency = voucher.currency_id.id or company_currency
            ctx = local_context.copy()
            ctx['date'] = voucher.account_date
            ctx['check_move_validity'] = False
            # Create the account move record.
            move = self.env['account.move'].create(voucher.account_move_get())
            # Create the first line of the voucher
            if voucher.is_payment_multi is False:
                move_line = self.env['account.move.line'].with_context(ctx).create(
                    voucher.with_context(ctx).first_move_line_get(move.id, company_currency, current_currency))
            else:
                for payment in voucher.payment_ids:
                    move_line = self.env['account.move.line'].with_context(ctx).create(
                        voucher.with_context(ctx).multi_move_line_get(move.id, company_currency, current_currency,
                                                                      payment.payment_method_id, payment.total))
            line_total = move_line.debit - move_line.credit
            if voucher.voucher_type == 'sale':
                line_total = line_total - voucher._convert(voucher.tax_amount)
            elif voucher.voucher_type == 'purchase':
                line_total = line_total + voucher._convert(voucher.tax_amount)

            # Create move line with wht certificate
            for wht_line in self.wt_cert_ids:
                move_line = self.env['account.move.line'].with_context(ctx).create(
                    voucher.with_context(ctx).wht_move_line_get(move.id, company_currency, current_currency, wht_line))

            # Create one move line per voucher line where amount is not 0.0
            line_total = voucher.with_context(ctx).voucher_move_line_create(line_total, move.id, company_currency,
                                                                            current_currency)
            # Create move line vat
            voucher.with_context(ctx).vat_move_line_create(move.id, company_currency, current_currency)

            # Add tax correction to move line if any tax correction specified
            if voucher.tax_correction != 0.0:
                tax_move_line = self.env['account.move.line'].search(
                    [('move_id', '=', move.id), ('tax_line_id', '!=', False)], limit=1)
                if len(tax_move_line):
                    tax_move_line.write(
                        {'debit': tax_move_line.debit + voucher.tax_correction if tax_move_line.debit > 0 else 0,
                         'credit': tax_move_line.credit + voucher.tax_correction if tax_move_line.credit > 0 else 0})

            # We post the voucher.
            voucher.write({
                'move_id': move.id,
                'state': 'posted',
                'number': self.get_seq_voucher()
            })
            # Odoo 18: action_post() แทน post()
            move.action_post()
        return True

    def _track_subtype(self, init_values):
        if 'state' in init_values:
            return self.env.ref('account_voucher_npd.mt_voucher_state_change')
        return super()._track_subtype(init_values)


class AccountVoucherLine(models.Model):
    _name = 'account.voucher.line'
    _description = 'Accounting Voucher Line'

    name = fields.Text(string='Description', required=True)
    sequence = fields.Integer(default=10,
                              help="Gives the sequence of this line when displaying the voucher.")
    voucher_id = fields.Many2one('account.voucher', 'Voucher', required=1, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product',
                                 ondelete='set null', index=True)
    account_id = fields.Many2one('account.account', string='Account',
                                 required=True, domain=[('deprecated', '=', False)],
                                 help="The income or expense account related to the selected product.")
    price_unit = fields.Float(
        string='Unit Price',
        required=True,
        digits='Product Price',
    )
    price_subtotal = fields.Monetary(string='Amount',
                                     store=True, readonly=True, compute='_compute_subtotal')
    quantity = fields.Float(digits='Product Unit of Measure',
                            required=True, default=1)
    account_analytic_id = fields.Many2one('account.analytic.account', 'Analytic Account')
    # Odoo 18: analytic_distribution แทน analytic_tag_ids
    analytic_distribution = fields.Json(string='Analytic Distribution')
    company_id = fields.Many2one('res.company', related='voucher_id.company_id', string='Company', store=True,
                                 readonly=True)
    tax_ids = fields.Many2many('account.tax', string='Tax', help="Only for tax excluded from price")
    currency_id = fields.Many2one('res.currency', related='voucher_id.currency_id', readonly=False)
    wht_total = fields.Float(string="Withholding Tax", required=False, digits='Product Price')

    can_edit_voucher = fields.Boolean(
        string="Can Edit Voucher",
        compute="_compute_can_edit_voucher",
        store=False
    )

    def _compute_can_edit_voucher(self):
        for rec in self:
            rec.can_edit_voucher = self.env.user.can_edit_voucher_lines

    @api.depends('price_unit', 'tax_ids', 'quantity', 'product_id', 'voucher_id.currency_id')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(line.price_unit, line.voucher_id.currency_id, line.quantity,
                                                 product=line.product_id, partner=line.voucher_id.partner_id)
                line.price_subtotal = taxes['total_excluded']

    @api.onchange('product_id', 'voucher_id', 'price_unit', 'company_id')
    def _onchange_line_details(self):
        if not self.voucher_id or not self.product_id or not self.voucher_id.partner_id:
            return
        onchange_res = self.product_id_change(
            self.product_id.id,
            self.voucher_id.partner_id.id,
            self.price_unit,
            self.company_id.id,
            self.voucher_id.currency_id.id,
            self.voucher_id.voucher_type)
        for fname, fvalue in onchange_res['value'].items():
            setattr(self, fname, fvalue)

    def _get_account(self, product, fpos, type):
        accounts = product.product_tmpl_id.get_product_accounts(fpos)
        if type == 'sale':
            return accounts['income']
        return accounts['expense']

    def product_id_change(self, product_id, partner_id=False, price_unit=False, company_id=None, currency_id=None,
                          type=None):
        context = self._context
        company_id = company_id if company_id is not None else context.get('company_id', False)
        company = self.env['res.company'].browse(company_id)
        currency = self.env['res.currency'].browse(currency_id)
        if not partner_id:
            raise UserError(_("You must first select a partner."))
        part = self.env['res.partner'].browse(partner_id)
        if part.lang:
            self = self.with_context(lang=part.lang)

        product = self.env['product.product'].browse(product_id)
        fpos = part.property_account_position_id
        account = self._get_account(product, fpos, type)
        values = {
            'name': product.partner_ref,
            'account_id': account.id,
        }

        if type == 'purchase':
            values['price_unit'] = price_unit or product.standard_price
            taxes = product.supplier_taxes_id or account.tax_ids
            if product.description_purchase:
                values['name'] += '\n' + product.description_purchase
        else:
            values['price_unit'] = price_unit or product.lst_price
            taxes = product.taxes_id or account.tax_ids
            if product.description_sale:
                values['name'] += '\n' + product.description_sale

        values['tax_ids'] = taxes.ids

        if company and currency:
            if company.currency_id != currency:
                if type == 'purchase':
                    values['price_unit'] = price_unit or product.standard_price
                values['price_unit'] = values['price_unit'] * currency.rate

        return {'value': values, 'domain': {}}


class AccountVoucherPayment(models.Model):
    _name = 'account.voucher.payment'
    _rec_name = 'ref'
    _description = 'Account Voucher Payment'

    voucher_id = fields.Many2one("account.voucher", string="Payment", ondelete="cascade")
    company_id = fields.Many2one('res.company', related='voucher_id.company_id', string='Company', store=True,
                                 readonly=True)

    payment_method_id = fields.Many2one("custom.payment.method", string="Payment Method",
                                        required=True)
    bank_account_id = fields.Many2one(
        "res.partner.bank", string="Bank Account"
    )
    account_id = fields.Many2one("account.account", related='payment_method_id.account_id', string="Account")
    cheque_id = fields.Many2one("account.cheque", string="Cheque", domain="[('state', '=', 'draft')]")
    total = fields.Float(string="Total", digits=(36, 2), required=True)
    ref = fields.Char(string="Ref", required=False)
    type = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
            ('bank', 'Bank'),
            ('discount', 'Discount'),
            ('ap', 'AP'),
            ('ar', 'AR'),
            ('other', 'Other'),
        ],
        string='Payment method',
        related='payment_method_id.type',
    )


class WithholdingTaxCert(models.Model):
    _inherit = "withholding.tax.cert"

    voucher_id = fields.Many2one('account.voucher', string='Account Voucher', ondelete="cascade")


class AccountMoveTaxInvoice(models.Model):
    _inherit = "account.move.tax.invoice"

    voucher_id = fields.Many2one('account.voucher', string='Account Voucher', ondelete="cascade")


class AccountCheque(models.Model):
    _inherit = "account.cheque"

    voucher_id = fields.Many2one("account.voucher", string="Sale/Purchase", compute='_compute_voucher_id')

    def _compute_voucher_id(self):
        for cheque in self:
            voucher_id = cheque.voucher_id.search([('cheque_id', '=', cheque.id)], limit=1)
            voucher_line_ids = self.env['account.voucher.payment'].search([('cheque_id', '=', cheque.id)])
            for voucher_line in voucher_line_ids:
                voucher_id = voucher_line.voucher_id
            cheque.voucher_id = voucher_id


class AccountMove(models.Model):
    _inherit = "account.move"

    voucher_id = fields.Many2one('account.voucher', string='Account Voucher', ondelete="cascade", readonly=True)
