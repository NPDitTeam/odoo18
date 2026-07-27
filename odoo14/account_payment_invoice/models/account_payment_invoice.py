from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ---- Relational fields ----
    advance_clear_id = fields.Many2one(
        'account.advance.clear', string='Advance Clear', ondelete='set null', copy=False,
    )
    custom_invoice_ids = fields.One2many(
        'account.payment.invoice', 'payment_id', string='รายการใบแจ้งหนี้', copy=True,
    )
    paid_ids = fields.One2many(
        'account.paid.line', 'payment_id', string='รายการชำระเงิน', copy=True,
    )
    wt_cert_ids = fields.One2many(
        'withholding.tax.cert', 'payment_id', string='หนังสือรับรองหัก ณ ที่จ่าย',
    )
    tax_invoice_ids = fields.One2many(
        'account.move.tax.invoice', 'payment_id', string='ใบกำกับภาษี',
    )
    voucher_source_id = fields.Many2one(
        'account.payment', string='รายการบันทึกบัญชี', copy=False,
    )
    cheque_id = fields.Many2one(
        'account.cheque', string='เช็ค', copy=False,
    )
    move_line_ids = fields.One2many(
        related='move_id.line_ids', string='รายการขาบัญชี', readonly=True,
    )

    # ---- Status / selection fields ----
    cash_status = fields.Selection([
        ('pending', 'รอดำเนินการ'),
        ('paid', 'ชำระแล้ว'),
        ('returned', 'คืนแล้ว'),
    ], string='สถานะเงินสด', copy=False, tracking=True)

    overpaid_refund_status = fields.Selection([
        ('none', 'ไม่มี'),
        ('to_refund', 'รอคืน'),
        ('refunded', 'คืนแล้ว'),
    ], string='สถานะคืนเงินโอนเกิน', default='none', copy=False, tracking=True)

    wtax_refund_status = fields.Selection([
        ('none', 'ไม่มี'),
        ('to_refund', 'รอคืน'),
        ('refunded', 'คืนแล้ว'),
    ], string='สถานะคืนหัก ณ ที่จ่าย', default='none', copy=False, tracking=True)

    rental_difference_status = fields.Selection([
        ('none', 'ไม่มี'),
        ('pending', 'รอดำเนินการ'),
        ('done', 'เสร็จสิ้น'),
    ], string='สถานะโอนคืนค่าเช่าส่วนต่าง', default='none', copy=False, tracking=True)

    # ---- เพิ่ม cancel state (Odoo 18 มีแค่ draft, in_process, paid) ----
    state = fields.Selection(
        selection_add=[('cancel', 'ยกเลิก')],
        ondelete={'cancel': 'set default'},
    )

    is_payment_multi = fields.Boolean(
        string='Payment Multi', default=False, copy=False,
    )
    payment_method_one_id = fields.Many2one(
        'custom.payment.method',
        string='Payment Method',
        domain="[('type', 'in', ['cash','bank','cheque']),('is_active','=',True)]",
        copy=False,
    )

    # ---- Monetary / numeric fields ----
    total_amount = fields.Monetary(
        string='ยอดรวม', compute='_compute_total_amount', store=True,
    )
    write_off_amount = fields.Monetary(
        string='ยอดตัดจ่าย', compute='_compute_write_off_amount', store=True,
    )
    total_invoice_amount = fields.Monetary(
        string='ยอดรวมใบแจ้งหนี้', compute='_compute_total_invoice', store=True,
    )
    total_paid_amount = fields.Monetary(
        string='ยอดรวมชำระ', compute='_compute_total_paid', store=True,
    )
    outstanding_amount = fields.Monetary(
        string='ยอดค้างชำระ', compute='_compute_outstanding', store=True,
    )
    wht_amount = fields.Monetary(
        string='ภาษีหัก ณ ที่จ่าย', compute='_compute_wht_amount', store=True,
    )

    # ---- Date fields ----
    can_edit_date = fields.Boolean(
        string='แก้ไขวันที่ได้', compute='_compute_can_edit_date',
    )
    min_allowed_date = fields.Date(
        string='วันที่ต่ำสุด', compute='_compute_can_edit_date',
    )
    max_allowed_date = fields.Date(
        string='วันที่สูงสุด', compute='_compute_can_edit_date',
    )

    # ---- Custom fields ----
    pfb_so_type = fields.Selection([
        ('sale', 'ขาย'),
        ('rent', 'เช่า'),
        ('other', 'อื่นๆ'),
    ], string='ประเภท', copy=False)

    pfb_date_of_rent = fields.Date(string='Day of Rent', copy=False)
    search_invoice_name = fields.Char(string='เลขใบแจ้งหนี้', copy=False)
    payment_memo = fields.Char(string='หมายเหตุ', copy=False)
    voucher_number = fields.Char(
        string='เลขที่ใบสำคัญ', copy=False, readonly=True,
        help='เลขรัน RV/PV สร้างอัตโนมัติเมื่อยืนยัน',
    )

    pfb_objective_id = fields.Many2one(
        'sale.objective', string='วัตถุประสงค์', copy=False, ondelete='set null',
    )

    # ================================================================
    # Computed methods
    # ================================================================

    @api.depends('custom_invoice_ids.paid_total')
    def _compute_total_invoice(self):
        """ยอดรวมใบแจ้งหนี้ = sum(paid_total) ไม่ใช้ amount_due เพราะจะถูก reset เป็น 0 หลัง post"""
        for payment in self:
            try:
                payment.total_invoice_amount = sum(
                    payment.custom_invoice_ids.mapped('paid_total')
                )
            except Exception:
                payment.total_invoice_amount = 0.0

    @api.depends('paid_ids.amount')
    def _compute_total_paid(self):
        for payment in self:
            try:
                payment.total_paid_amount = sum(
                    payment.paid_ids.mapped('amount')
                )
            except Exception:
                payment.total_paid_amount = 0.0

    @api.depends('total_invoice_amount', 'total_paid_amount')
    def _compute_outstanding(self):
        for payment in self:
            payment.outstanding_amount = (
                payment.total_invoice_amount - payment.total_paid_amount
            )

    @api.depends('custom_invoice_ids.paid_total', 'wt_cert_ids.tax_amount', 'write_off_amount')
    def _compute_total_amount(self):
        """ยอดรวม = paid_total - WHT - write_off (เหมือน Odoo 14)"""
        for payment in self:
            try:
                paid = sum(payment.custom_invoice_ids.mapped('paid_total'))
                wht = sum(payment.wt_cert_ids.mapped('tax_amount')) if payment.wt_cert_ids else 0
                wo = payment.write_off_amount or 0
                payment.total_amount = paid - wht - wo
            except Exception:
                payment.total_amount = 0.0

    @api.depends('paid_ids.is_write_off', 'paid_ids.amount')
    def _compute_write_off_amount(self):
        for payment in self:
            try:
                wo_lines = payment.paid_ids.filtered(lambda l: l.is_write_off)
                payment.write_off_amount = sum(wo_lines.mapped('amount'))
            except Exception:
                payment.write_off_amount = 0.0

    @api.depends('wt_cert_ids.tax_amount')
    def _compute_wht_amount(self):
        for payment in self:
            try:
                payment.wht_amount = sum(
                    payment.wt_cert_ids.mapped('tax_amount')
                )
            except Exception:
                payment.wht_amount = 0.0

    @api.depends('state', 'company_id')
    def _compute_can_edit_date(self):
        is_allowed = bool(self.env.user.account_payment_lock_draft_date)
        today = fields.Date.context_today(self)
        for payment in self:
            payment.can_edit_date = is_allowed
            if is_allowed:
                payment.min_allowed_date = False
                payment.max_allowed_date = False
            else:
                payment.min_allowed_date = today - timedelta(days=1)
                payment.max_allowed_date = today + timedelta(days=1)

    def _compute_allowed_date_range(self):
        for payment in self:
            payment.min_allowed_date = False
            payment.max_allowed_date = False

    def _compute_duplicate_payment_ids(self):
        """Disable duplicate payment warning"""
        for payment in self:
            payment.duplicate_payment_ids = self.env['account.payment']

    # ================================================================
    # Override _prepare_move_line_default_vals
    # ================================================================

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, **kwargs):
        """Override: ถ้ามี custom_invoice_ids ให้ใช้ lines ของเราแทน lines มาตรฐาน"""
        has_inv = bool(self.custom_invoice_ids)
        _logger.info(
            '_prepare_move_line_default_vals called for %s, custom_invoices=%s',
            self.id, has_inv,
        )
        if has_inv:
            lines = self._prepare_payment_move_lines()
            _logger.info('Returning %d custom lines', len(lines))
            for i, l in enumerate(lines):
                _logger.info('  Line %d: %s DR=%.2f CR=%.2f acc=%s',
                             i, l.get('name', ''), l.get('debit', 0), l.get('credit', 0), l.get('account_id'))
            return lines
        return super()._prepare_move_line_default_vals(write_off_line_vals, **kwargs)

    # ================================================================
    # Journal Entry Line Builder
    # ================================================================

    def _rebuild_move_lines(self):
        """Clear and rebuild journal entry lines from custom data.
        ใช้ SQL ทั้งหมด (DELETE + INSERT) เพื่อ bypass ALL Odoo 18 constraints"""
        self.ensure_one()
        if not self.custom_invoice_ids:
            return

        line_vals = self._prepare_payment_move_lines()
        if not line_vals:
            _logger.warning('No move lines generated for payment %s', self.id)
            return

        move = self.move_id
        if not move or not move.id:
            _logger.warning('No move_id for payment %s, skipping rebuild', self.id)
            return

        _logger.info(
            'Rebuilding %d journal lines for payment %s (move %s state=%s)',
            len(line_vals), self.name or self.id, move.id, move.state,
        )

        cr = self.env.cr

        # Step 1: Delete existing lines via SQL
        cr.execute("DELETE FROM account_move_line WHERE move_id = %s", (move.id,))

        # Step 2: Insert new lines via SQL
        for vals in line_vals:
            cr.execute("""
                INSERT INTO account_move_line (
                    move_id, move_name, date, journal_id, company_id,
                    account_id, partner_id, name,
                    debit, credit, balance,
                    amount_currency, currency_id,
                    date_maturity, display_type,
                    parent_state, quantity,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, 'payment_term',
                    %s, 1,
                    %s, NOW() AT TIME ZONE 'UTC', %s, NOW() AT TIME ZONE 'UTC'
                )
            """, (
                move.id,
                move.name or '',
                move.date,
                move.journal_id.id,
                move.company_id.id,
                vals['account_id'],
                vals.get('partner_id'),
                vals.get('name', ''),
                vals.get('debit', 0.0),
                vals.get('credit', 0.0),
                vals.get('debit', 0.0) - vals.get('credit', 0.0),
                vals.get('amount_currency', 0.0),
                vals.get('currency_id', move.company_id.currency_id.id),
                vals.get('date_maturity', move.date),
                move.state or 'draft',
                self.env.uid,
                self.env.uid,
            ))

        # Step 3: Invalidate ORM cache
        move.invalidate_recordset()
        self.env['account.move.line'].invalidate_model()
        self.invalidate_recordset(['move_line_ids'])

        _logger.info('Successfully rebuilt %d lines for move %s via SQL', len(line_vals), move.id)

    def _rebuild_move_lines_after_post(self):
        """Rebuild journal lines AFTER posting via pure SQL.
        1. Unreconcile (SQL)
        2. Delete old lines (SQL)
        3. Insert new lines (SQL)
        ทั้งหมดใช้ SQL เพื่อ bypass ทุก Odoo 18 constraint"""
        self.ensure_one()
        if not self.custom_invoice_ids:
            return

        line_vals = self._prepare_payment_move_lines()
        if not line_vals:
            return

        move = self.move_id
        cr = self.env.cr

        _logger.info('Rebuilding %d lines for move %s (SQL)', len(line_vals), move.id)

        # 1. Remove reconciliation (SQL)
        cr.execute("""
            DELETE FROM account_partial_reconcile
            WHERE debit_move_id IN (SELECT id FROM account_move_line WHERE move_id = %s)
               OR credit_move_id IN (SELECT id FROM account_move_line WHERE move_id = %s)
        """, (move.id, move.id))
        cr.execute("""
            UPDATE account_move_line
            SET reconciled = FALSE, full_reconcile_id = NULL
            WHERE move_id = %s
        """, (move.id,))

        # 2. Delete existing lines (SQL)
        cr.execute("DELETE FROM account_move_line WHERE move_id = %s", (move.id,))

        # 3. Insert custom lines (SQL)
        for vals in line_vals:
            cr.execute("""
                INSERT INTO account_move_line (
                    move_id, move_name, date, journal_id, company_id,
                    account_id, partner_id, name,
                    debit, credit, balance,
                    amount_currency, currency_id,
                    date_maturity, display_type,
                    parent_state, quantity,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, 'payment_term',
                    %s, 1,
                    %s, NOW() AT TIME ZONE 'UTC', %s, NOW() AT TIME ZONE 'UTC'
                )
            """, (
                move.id,
                move.name or '',
                move.date,
                move.journal_id.id,
                move.company_id.id,
                vals['account_id'],
                vals.get('partner_id'),
                vals.get('name', ''),
                vals.get('debit', 0.0),
                vals.get('credit', 0.0),
                vals.get('debit', 0.0) - vals.get('credit', 0.0),
                vals.get('amount_currency', 0.0),
                vals.get('currency_id', move.company_id.currency_id.id),
                vals.get('date_maturity', move.date),
                move.state or 'posted',
                self.env.uid,
                self.env.uid,
            ))

        # 4. Invalidate cache
        move.invalidate_recordset()
        self.env['account.move.line'].invalidate_model()
        self.invalidate_recordset(['move_line_ids'])
        _logger.info('SQL rebuild done: %d lines inserted for move %s', len(line_vals), move.id)

    def _prepare_payment_move_lines(self):
        """Build journal entry line values from custom invoice/paid lines.

        Returns a list of dicts ready for (0, 0, vals) commands.
        Structure:
        1. Bank/Cash lines (liquidity) - from paid_ids or journal
        2. Withholding Tax lines - from wt_cert_ids
        3. Receivable/Payable lines - from custom_invoice_ids
        4. Write-off lines - from paid_ids where is_write_off=True
        """
        self.ensure_one()
        line_vals_list = []
        currency_id = self.currency_id.id

        if not self.custom_invoice_ids and not self.amount:
            return line_vals_list

        # Check if any invoice is a refund (credit note)
        has_refund = any(
            inv.move_id.move_type in ('out_refund', 'in_refund')
            for inv in self.custom_invoice_ids if inv.move_id
        )

        # ---- 1. Bank/Cash lines (liquidity) ----
        if self.paid_ids and self.is_payment_multi:
            # Multiple payment methods
            for paid in self.paid_ids:
                if paid.is_write_off:
                    continue
                account = paid.account_id or paid.journal_id.default_account_id
                if not account:
                    raise UserError(
                        _("กรุณาตั้งค่าบัญชีสำหรับรายการชำระ %s") % paid.journal_id.name
                    )
                if has_refund:
                    liq_balance = (
                        -paid.amount if self.payment_type == 'inbound'
                        else paid.amount
                    )
                else:
                    liq_balance = (
                        paid.amount if self.payment_type == 'inbound'
                        else -paid.amount
                    )
                vals = {
                    'name': paid.journal_id.name or paid.payment_method_type or '',
                    'date_maturity': self.date,
                    'amount_currency': liq_balance,
                    'currency_id': currency_id,
                    'debit': liq_balance if liq_balance > 0 else 0.0,
                    'credit': -liq_balance if liq_balance < 0 else 0.0,
                    'partner_id': self.partner_id.id,
                    'account_id': account.id,
                }
                if paid.analytic_distribution:
                    vals['analytic_distribution'] = paid.analytic_distribution
                line_vals_list.append(vals)
        else:
            # Single payment method - use journal default account
            payment_account = self.journal_id.default_account_id
            if not payment_account:
                raise UserError(
                    _("สมุดรายวัน %s ไม่มีบัญชีเริ่มต้น") % self.journal_id.name
                )
            payment_amount = self.amount
            if has_refund:
                liq_balance = (
                    -payment_amount if self.payment_type == 'inbound'
                    else payment_amount
                )
            else:
                liq_balance = (
                    payment_amount if self.payment_type == 'inbound'
                    else -payment_amount
                )
            line_vals_list.append({
                'name': self.journal_id.name or '',
                'date_maturity': self.date,
                'amount_currency': liq_balance,
                'currency_id': currency_id,
                'debit': liq_balance if liq_balance > 0 else 0.0,
                'credit': -liq_balance if liq_balance < 0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': payment_account.id,
            })

        # ---- 2. Withholding Tax lines ----
        for wht_line in self.wt_cert_ids:
            wt_amount = (
                wht_line.tax_amount if self.payment_type == 'inbound'
                else -wht_line.tax_amount
            )
            wht_account_id = wht_line.account_id.id if wht_line.account_id else False
            if not wht_account_id:
                raise UserError(
                    _("ไม่มีบัญชีภาษีหัก ณ ที่จ่าย กรุณาตั้งค่า")
                )
            line_vals_list.append({
                'name': "Withholding Tax " + (wht_line.income_tax_form or ''),
                'date_maturity': self.date,
                'amount_currency': wt_amount,
                'currency_id': currency_id,
                'debit': wt_amount if wt_amount > 0 else 0.0,
                'credit': -wt_amount if wt_amount < 0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': wht_account_id,
            })

        # ---- 3. Receivable/Payable lines (counterpart) ----
        for invoice_line in self.custom_invoice_ids:
            invoice = invoice_line.move_id
            invoice_total = invoice_line.paid_total or invoice_line.amount_due
            if not invoice or invoice_total == 0:
                continue

            is_refund = invoice.move_type in ('out_refund', 'in_refund')

            if self.payment_type == 'inbound':
                if is_refund:
                    counterpart_balance = invoice_total
                    name = "Refund Credit Note " + invoice.name
                else:
                    counterpart_balance = -invoice_total
                    name = "Receive Invoice " + invoice.name
            else:
                if is_refund:
                    counterpart_balance = -invoice_total
                    name = "Refund Credit Note " + invoice.name
                else:
                    counterpart_balance = invoice_total
                    name = "Payment Invoice " + invoice.name

            if counterpart_balance != 0:
                line_vals_list.append({
                    'name': name,
                    'date_maturity': self.date,
                    'amount_currency': counterpart_balance,
                    'currency_id': currency_id,
                    'debit': counterpart_balance if counterpart_balance > 0 else 0.0,
                    'credit': -counterpart_balance if counterpart_balance < 0 else 0.0,
                    'partner_id': self.partner_id.id,
                    'account_id': self.destination_account_id.id,
                })

        # ---- 4. Write-off lines ----
        if self.paid_ids and self.is_payment_multi:
            for paid in self.paid_ids:
                if paid.is_write_off and paid.amount:
                    wo_account = paid.write_off_account_id or paid.account_id
                    if not wo_account:
                        continue
                    wo_balance = (
                        paid.amount if self.payment_type == 'inbound'
                        else -paid.amount
                    )
                    line_vals_list.append({
                        'name': paid.communication or 'Write-off',
                        'date_maturity': self.date,
                        'amount_currency': wo_balance,
                        'currency_id': currency_id,
                        'debit': wo_balance if wo_balance > 0 else 0.0,
                        'credit': -wo_balance if wo_balance < 0 else 0.0,
                        'partner_id': self.partner_id.id,
                        'account_id': wo_account.id,
                    })

        # Debug - check balance
        total_debit = sum(l['debit'] for l in line_vals_list)
        total_credit = sum(l['credit'] for l in line_vals_list)
        if abs(total_debit - total_credit) > 0.01:
            _logger.warning(
                'Payment %s: Journal Entry not balanced! '
                'Debit=%s Credit=%s Diff=%s',
                self.name, total_debit, total_credit,
                total_debit - total_credit,
            )

        return line_vals_list

    # ================================================================
    # Onchange methods
    # ================================================================

    @api.onchange('partner_id', 'search_invoice_name')
    def _onchange_partner_invoice_search(self):
        """ค้นหาใบแจ้งหนี้จาก partner และ/หรือเลขใบแจ้งหนี้"""
        if not self.partner_id:
            self.custom_invoice_ids = False
            return

        type_invoice = {
            'inbound': ['out_invoice', 'out_refund'],
            'outbound': ['in_invoice', 'in_refund'],
        }
        move_types = type_invoice.get(self.payment_type, ['out_invoice'])

        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('move_type', 'in', move_types),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'reversed']),
            ('currency_id', '=', self.currency_id.id),
        ]

        if self.search_invoice_name:
            domain.append(('name', 'ilike', self.search_invoice_name.strip()))

        invoices = self.env['account.move'].search(domain)
        lines = []
        for inv in invoices:
            if inv.amount_residual != 0:
                residual = abs(inv.amount_residual)
                line_vals = {
                    'move_id': inv.id,
                    'amount_due': residual,
                }
                if self.search_invoice_name:
                    line_vals['paid_total'] = residual
                lines.append((0, 0, line_vals))

        self.custom_invoice_ids = [(5, 0, 0)] + lines

        # Auto-fill amount from total invoice
        total_due = sum(
            abs(inv.amount_residual) for inv in invoices
            if inv.amount_residual != 0
        )
        if total_due > 0:
            self.amount = total_due

        # Auto-set journal from the invoice journal
        # จับคู่ได้ที่เมนู การขาย > การกำหนดค่า > สมุดรายวันรับชำระ
        if self.custom_invoice_ids:
            invoice_journals = self.env['account.journal']
            names = []
            for inv_line in self.custom_invoice_ids:
                if inv_line.move_id:
                    names.append(inv_line.move_id.name)
                    invoice_journals |= inv_line.move_id.journal_id
            self.search_invoice_name = (
                ', '.join(names) if names else self.search_invoice_name
            )

            payment_journal = self.env['npd.invoice.journal.config']._get_payment_journal(
                self.company_id, invoice_journals,
            )
            if payment_journal:
                self.journal_id = payment_journal.id

    @api.onchange('date')
    def _onchange_date_check_allowed(self):
        """ตรวจสอบวันที่ ±1 วัน สำหรับ user ที่ไม่มีสิทธิ์"""
        if not self.can_edit_date and self.date:
            today = fields.Date.context_today(self)
            min_date = today - timedelta(days=1)
            max_date = today + timedelta(days=1)
            if self.date < min_date or self.date > max_date:
                self.date = today
                return {
                    'warning': {
                        'title': _('ไม่สามารถเลือกวันที่นี้ได้'),
                        'message': _(
                            'คุณสามารถเลือกวันที่ได้ในช่วง %s ถึง %s เท่านั้น'
                        ) % (min_date, max_date),
                    }
                }

    @api.onchange('paid_ids', 'paid_ids.amount')
    def _onchange_paid_ids_amount(self):
        """Sync amount from paid_ids total"""
        if self.is_payment_multi and self.paid_ids:
            total = sum(
                line.amount for line in self.paid_ids if not line.is_write_off
            )
            self.amount = total

    @api.onchange('is_payment_multi')
    def _onchange_is_payment_multi(self):
        if self.is_payment_multi:
            self._onchange_paid_ids_amount()
        else:
            wht = sum(self.wt_cert_ids.mapped('tax_amount')) if self.wt_cert_ids else 0
            self.amount = self.total_invoice_amount - wht

    @api.onchange('custom_invoice_ids')
    def _onchange_custom_invoice_ids_sync(self):
        """Sync amount and search_invoice_name when invoice lines change"""
        if self.custom_invoice_ids:
            invoice_journals = self.env['account.journal']
            names = []
            for inv_line in self.custom_invoice_ids:
                if inv_line.move_id and inv_line.select:
                    names.append(inv_line.move_id.name)
                    invoice_journals |= inv_line.move_id.journal_id
            if names:
                self.search_invoice_name = ', '.join(names)

            # Auto journal selection
            # จับคู่ได้ที่เมนู การขาย > การกำหนดค่า > สมุดรายวันรับชำระ
            payment_journal = self.env['npd.invoice.journal.config']._get_payment_journal(
                self.company_id, invoice_journals,
            )
            if payment_journal:
                self.journal_id = payment_journal.id

    # ================================================================
    # Action methods
    # ================================================================

    def action_view_journal_entry(self):
        """Open the linked journal entry (move) form"""
        self.ensure_one()
        return {
            'name': _('รายการบันทึกบัญชี %s') % (self.voucher_number or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
            'views': [(self.env.ref('account.view_move_form').id, 'form')],
            'context': {'default_move_type': 'entry'},
        }

    def get_invoice(self):
        """Open related invoice"""
        self.ensure_one()
        if not self.custom_invoice_ids:
            raise UserError(_('ไม่พบรายการใบแจ้งหนี้'))
        move_ids = self.custom_invoice_ids.mapped('move_id').ids
        action = {
            'name': _('Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', move_ids)],
        }
        if len(move_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = move_ids[0]
        return action

    def action_post(self):
        """Override: Validate, build journal entries, set RV name, post, reconcile.

        Flow เหมือน Odoo 14:
        1. Validate ข้อมูล
        2. ลบ invoice line ที่ paid_total = 0
        3. สร้าง journal entry lines (Bank/WHT/Receivable)
        4. ตั้งชื่อ move เป็น RV-YYMMDDNNNN
        5. Post move
        6. Reconcile กับ invoice
        7. จัดการ cheque, tax invoice, update state
        """
        for rec in self:
            if not rec.custom_invoice_ids:
                continue

            # Validation
            if rec.amount == 0:
                raise UserError(
                    _("ยอดชำระเป็น 0 กรุณาตรวจสอบรายการใบแจ้งหนี้และยอดชำระ")
                )

            # Remove invoice lines with zero paid_total
            zero_lines = rec.custom_invoice_ids.filtered(
                lambda l: not l.paid_total and not l.amount_due
            )
            if zero_lines:
                zero_lines.sudo().unlink()

        # ---- Rebuild journal lines BEFORE posting ----
        for rec in self:
            has_inv = bool(rec.custom_invoice_ids)
            has_move = bool(rec.move_id)
            _logger.info(
                'PRE-POST %s: custom_invoices=%s, move_id=%s',
                rec.id, has_inv, rec.move_id.id if has_move else 'NONE',
            )
            if not has_inv:
                continue

            line_vals = rec._prepare_payment_move_lines()
            _logger.info('Prepared %d lines for %s', len(line_vals), rec.id)

            if has_move and line_vals:
                # Payment already has move → rebuild lines
                rec.move_id.with_context(
                    check_move_validity=False,
                    skip_account_move_synchronization=True,
                ).write({
                    'line_ids': [(5, 0, 0)] + [(0, 0, v) for v in line_vals],
                })
                _logger.info('Rebuilt %d lines on existing move %s', len(line_vals), rec.move_id.id)
            elif not has_move and line_vals:
                # Payment has no move → _prepare_move_line_default_vals override will handle
                _logger.info('No move yet for %s, override will create lines during super()', rec.id)

        # Call standard posting
        res = super().action_post()

        # Log post results
        for rec in self:
            if rec.custom_invoice_ids and rec.move_id:
                _logger.info(
                    'POST-RESULT %s: move=%s state=%s lines=%d',
                    rec.name, rec.move_id.id, rec.move_id.state,
                    len(rec.move_id.line_ids),
                )

        # Post-processing: set voucher number only
        for rec in self:
            if not rec.custom_invoice_ids:
                continue
            # ---- สร้างเลข RV/PV ----
            if not rec.voucher_number:
                if rec.payment_type == 'inbound':
                    seq_code = 'account.payment.receipt.voucher'
                else:
                    seq_code = 'account.payment.payment.voucher'
                try:
                    rv_name = self.env['ir.sequence'].with_context(
                        ir_sequence_date=rec.date,
                    ).next_by_code(seq_code)
                    if rv_name:
                        rec.voucher_number = rv_name
                except Exception as e:
                    _logger.warning('Voucher number error: %s', e)

            # ---- ตั้งชื่อ move เป็นเลข RV/PV (เหมือน Odoo 14) ----
            # Odoo 18: account.payment เป็น standalone model (ไม่ใช่ _inherits)
            # payment.name กับ move.name แยกกัน → เปลี่ยน move name ได้โดยไม่กระทบ payment
            if rec.voucher_number and rec.move_id:
                self.env.cr.execute(
                    "UPDATE account_move SET name = %s WHERE id = %s",
                    (rec.voucher_number, rec.move_id.id),
                )
                rec.move_id.invalidate_recordset(['name'])
                _logger.info(
                    'Move name updated (SQL): move=%s → %s, payment=%s stays',
                    rec.move_id.id, rec.voucher_number, rec.name,
                )

            # ---- Post-processing ----
            try:
                rec.cheque_assigned()
            except Exception as e:
                _logger.warning('Cheque error: %s', e)

        return res

    def _unreconcile_all(self):
        """Helper: Unreconcile ทุก invoice + payment move lines"""
        for rec in self:
            # Unreconcile invoice lines
            for inv_line in rec.custom_invoice_ids:
                invoice = inv_line.move_id
                if not invoice:
                    continue
                try:
                    for line in invoice.line_ids.filtered(
                        lambda l: l.account_id.reconcile and l.reconciled
                    ):
                        line.remove_move_reconcile()
                        _logger.info(
                            'Unreconciled invoice line: %s (account=%s) for %s',
                            line.name, line.account_id.code, invoice.name,
                        )
                except Exception as e:
                    _logger.warning('Unreconcile error for %s: %s', invoice.name, e)

            # Unreconcile payment move lines
            if rec.move_id:
                try:
                    for pml in rec.move_id.line_ids.filtered(
                        lambda l: l.account_id.reconcile and l.reconciled
                    ):
                        pml.remove_move_reconcile()
                        _logger.info(
                            'Unreconciled payment line: %s (account=%s)',
                            pml.name, pml.account_id.code,
                        )
                except Exception as e:
                    _logger.warning('Unreconcile payment move error: %s', e)

    def _reset_invoice_payment_states(self):
        """Helper: Reset invoice payment_state → not_paid"""
        for rec in self:
            for inv_line in rec.custom_invoice_ids:
                invoice = inv_line.move_id
                if not invoice:
                    continue
                try:
                    if invoice.move_type in ('out_refund', 'in_refund'):
                        self.env.cr.execute("""
                            UPDATE account_move
                            SET payment_state = 'not_paid',
                                amount_residual = -ABS(amount_total)
                            WHERE id = %s
                        """, (invoice.id,))
                    else:
                        self.env.cr.execute("""
                            UPDATE account_move
                            SET payment_state = 'not_paid',
                                amount_residual = amount_total
                            WHERE id = %s
                        """, (invoice.id,))
                    _logger.info('Reset invoice %s → not_paid', invoice.name)
                except Exception as e:
                    _logger.warning('Reset invoice error %s: %s', invoice.name, e)

    def action_draft(self):
        """รีเซ็ตเป็นฉบับร่าง: payment→draft, move→draft, invoice→not_paid

        Odoo 18 standard super().action_draft() ทำ:
          self.state = 'draft'
          self.move_id.button_draft()
        ซึ่งทำให้ทั้ง payment และ move เป็น draft — ตรงกับที่ต้องการแล้ว
        """
        for rec in self:
            if not rec.custom_invoice_ids:
                continue
            # Permission check
            if not self.env.user.account_payment_lock_draft_date:
                raise UserError(
                    _("คุณไม่มีสิทธิ์รีเซ็ตเป็นแบบร่างได้ "
                      "ต้องเป็นเจ้าหน้าที่การเงินส่วนกลางเท่านั้น")
                )
            _logger.info(
                '=== ACTION_DRAFT START === payment=%s, move=%s, move_state=%s',
                rec.name or rec.id,
                rec.move_id.name if rec.move_id else 'NO MOVE',
                rec.move_id.state if rec.move_id else 'N/A',
            )

        # 1. Unreconcile ทุกอย่าง
        self._unreconcile_all()

        # 2. เรียก super() — ทำ payment=draft, move=draft
        _logger.info('Calling super().action_draft()...')
        super().action_draft()
        _logger.info('super().action_draft() OK')

        # 3. Reset invoice payment_state
        self._reset_invoice_payment_states()

        # 4. Invalidate cache
        self.env['account.move'].invalidate_model(['state', 'payment_state', 'amount_residual'])
        self.env['account.payment'].invalidate_model(['state'])
        self.invalidate_recordset()

        for rec in self:
            _logger.info(
                '=== ACTION_DRAFT COMPLETE === payment=%s state=%s, move=%s state=%s',
                rec.name or rec.id, rec.state,
                rec.move_id.name if rec.move_id else 'N/A',
                rec.move_id.state if rec.move_id else 'N/A',
            )

    def action_cancel_payment(self):
        """ยกเลิกการชำระ: payment→canceled, move→cancel, invoice→not_paid
        ยกเลิกแล้วแก้ไขไม่ได้ (readonly ผ่าน view)"""
        for rec in self:
            _logger.info(
                '=== ACTION_CANCEL START === payment=%s, move=%s, move_state=%s',
                rec.name or rec.id,
                rec.move_id.name if rec.move_id else 'NO MOVE',
                rec.move_id.state if rec.move_id else 'N/A',
            )

        # 1. Unreconcile ทุกอย่าง
        self._unreconcile_all()

        # 2. Cancel move (รายการบันทึกบัญชี → ยกเลิก)
        for rec in self:
            if rec.move_id:
                try:
                    if rec.move_id.state == 'posted':
                        rec.move_id.button_draft()
                        _logger.info('Move %s: posted → draft', rec.move_id.name)
                    if rec.move_id.state == 'draft':
                        rec.move_id.button_cancel()
                        _logger.info('Move %s: draft → cancel', rec.move_id.name)
                except Exception as e:
                    _logger.warning('Cancel move error: %s, using SQL', e)
                # Force move = cancel ด้วย SQL (กัน edge case)
                self.env.cr.execute(
                    "UPDATE account_move SET state = 'cancel' WHERE id = %s",
                    (rec.move_id.id,),
                )

        # 3. Payment state → canceled
        # Odoo 18 ใช้ 'canceled' (ไม่ใช่ 'cancel')
        for rec in self:
            self.env.cr.execute(
                "UPDATE account_payment SET state = 'canceled' WHERE id = %s",
                (rec.id,),
            )
            _logger.info('Payment %s → canceled', rec.name or rec.id)

        # 4. Reset invoice payment_state
        self._reset_invoice_payment_states()

        # 5. Invalidate ALL caches
        self.env['account.move'].invalidate_model(['state', 'payment_state', 'amount_residual'])
        self.env['account.payment'].invalidate_model(['state'])
        self.invalidate_recordset()

        for rec in self:
            _logger.info(
                '=== ACTION_CANCEL COMPLETE === payment=%s state=%s, move=%s state=%s',
                rec.name or rec.id, rec.state,
                rec.move_id.name if rec.move_id else 'N/A',
                rec.move_id.state if rec.move_id else 'N/A',
            )
        return True

    # ================================================================
    # Reconciliation
    # ================================================================

    def _reconcile_payment(self):
        """Reconcile payment with invoices - supports refunds."""
        for rec in self:
            for inv_line in rec.custom_invoice_ids:
                invoice = inv_line.move_id
                paid_total = inv_line.paid_total or inv_line.amount_due
                if not invoice or paid_total <= 0:
                    continue

                is_refund = invoice.move_type in ('out_refund', 'in_refund')

                # Find reconcilable accounts
                invoice_accounts = invoice.line_ids.mapped(
                    'account_id'
                ).filtered(lambda a: a.reconcile)

                for account in invoice_accounts:
                    # Lines from invoice
                    invoice_lines = invoice.line_ids.filtered(
                        lambda l: l.account_id.id == account.id
                        and not l.reconciled
                    )
                    # Lines from payment
                    payment_lines = rec.move_id.line_ids.filtered(
                        lambda l: l.account_id.id == account.id
                        and not l.reconciled
                    )

                    if invoice_lines and payment_lines:
                        try:
                            (invoice_lines + payment_lines).with_context(
                                skip_invoice_sync=True,
                                no_exchange_difference=True,
                            ).reconcile()
                            _logger.info(
                                'Reconciled %s for account %s',
                                invoice.name, account.code,
                            )
                        except Exception as e:
                            _logger.warning(
                                'Reconcile error %s account %s: %s',
                                invoice.name, account.code, e,
                            )
                            # Try alternative for refunds
                            if is_refund:
                                try:
                                    refund_lines = invoice.line_ids.filtered(
                                        lambda l: l.account_id.account_type
                                        in ('asset_receivable', 'liability_payable')
                                        and not l.reconciled
                                    )
                                    pay_counterpart = rec.move_id.line_ids.filtered(
                                        lambda l: l.account_id.account_type
                                        in ('asset_receivable', 'liability_payable')
                                        and not l.reconciled
                                    )
                                    if refund_lines and pay_counterpart:
                                        (refund_lines + pay_counterpart).with_context(
                                            skip_invoice_sync=True,
                                        ).reconcile()
                                        _logger.info(
                                            'Alt reconcile OK for refund %s',
                                            invoice.name,
                                        )
                                except Exception as e2:
                                    _logger.error(
                                        'Alt reconcile failed for %s: %s',
                                        invoice.name, e2,
                                    )

    # ================================================================
    # Tax Invoice / Cheque helpers
    # ================================================================

    def group_account_tax_invoice(self):
        """Move tax invoice lines to payment's move."""
        for rec in self:
            for tax_invoice in rec.tax_invoice_ids:
                try:
                    account_tax = self.env['account.tax'].search([])
                    account_repartition = self.env[
                        'account.tax.repartition.line'
                    ].search([])
                    for line in tax_invoice.move_id.line_ids:
                        if (
                            account_tax.filtered(
                                lambda t: t.cash_basis_transition_account_id
                                == line.account_id
                            )
                            or account_repartition.filtered(
                                lambda t: t.account_id == line.account_id
                            )
                        ):
                            line.with_context(
                                check_move_validity=False
                            ).move_id = rec.move_id.id
                            line.with_context(
                                check_move_validity=False
                            ).name = line.account_id.name
                    tax_invoice.move_id.tax_cash_basis_rec_id = None
                    tax_invoice.move_id.button_draft()
                    tax_invoice.move_id.with_context(
                        force_delete=True
                    ).unlink()
                    tax_invoice.move_id = rec.move_id
                except Exception as e:
                    _logger.warning(
                        'Tax invoice grouping error: %s', e,
                    )

    def cheque_assigned(self):
        """Mark cheque as assigned to this payment."""
        for rec in self:
            # Single payment mode
            if not rec.is_payment_multi and rec.cheque_id:
                try:
                    if rec.cheque_id.state == 'draft':
                        rec.cheque_id.action_assigned()
                except Exception as e:
                    _logger.warning('Could not assign cheque: %s', e)
            # Multi payment mode
            if rec.is_payment_multi:
                for line in rec.paid_ids:
                    if (
                        line.payment_method_type == 'cheque'
                        and line.cheque_id
                        and line.cheque_id.state == 'draft'
                    ):
                        try:
                            line.cheque_id.action_assigned()
                        except Exception as e:
                            _logger.warning(
                                'Could not assign cheque: %s', e,
                            )

    def _update_invoice_payment_state(self):
        """Update invoice payment_state based on amount_residual."""
        for payment in self:
            for inv_line in payment.custom_invoice_ids:
                invoice = inv_line.move_id
                if not invoice:
                    continue
                try:
                    invoice.invalidate_recordset()
                    if (
                        invoice.amount_residual == 0
                        and invoice.payment_state != 'paid'
                    ):
                        self.env.cr.execute("""
                            UPDATE account_move
                            SET payment_state = 'paid'
                            WHERE id = %s AND amount_residual = 0
                        """, (invoice.id,))
                        _logger.info(
                            'Updated payment_state to paid for %s',
                            invoice.name,
                        )
                    elif (
                        0 < invoice.amount_residual < invoice.amount_total
                        and invoice.payment_state != 'partial'
                    ):
                        self.env.cr.execute("""
                            UPDATE account_move
                            SET payment_state = 'partial'
                            WHERE id = %s
                        """, (invoice.id,))
                        _logger.info(
                            'Updated payment_state to partial for %s',
                            invoice.name,
                        )
                except Exception as e:
                    _logger.warning(
                        'Update invoice state error for %s: %s',
                        invoice.name if invoice else '?', e,
                    )

    def calculate_outstanding_by_paid_total(self):
        """Recalculate outstanding amount based on paid totals."""
        for rec in self:
            for inv_line in rec.custom_invoice_ids:
                invoice = inv_line.move_id
                paid_total = inv_line.paid_total
                if not invoice or paid_total == 0:
                    continue
                try:
                    outstanding = inv_line.amount_due - paid_total
                    inv_line.write({'amount_due': outstanding})
                    self.env.cr.execute("""
                        UPDATE account_move
                        SET amount_residual = %s
                        WHERE id = %s
                    """, (outstanding, invoice.id))
                    _logger.info(
                        'Updated outstanding for %s: %s',
                        invoice.name, outstanding,
                    )
                except Exception as e:
                    _logger.warning(
                        'Calculate outstanding error: %s', e,
                    )


# ====================================================================
# Account Payment Invoice (invoice line in payment)
# ====================================================================

class AccountPaymentInvoice(models.Model):
    _name = 'account.payment.invoice'
    _description = 'Payment Invoice Line'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    payment_id = fields.Many2one(
        'account.payment', string='Payment', ondelete='cascade', index=True,
    )
    move_id = fields.Many2one(
        'account.move', string='Invoice',
    )
    move_line_id = fields.Many2one(
        'account.move.line', string='Journal Item',
    )
    partner_id = fields.Many2one(
        'res.partner', related='move_id.partner_id', store=True,
        string='Partner',
    )
    date_invoice = fields.Date(
        related='move_id.invoice_date', string='Invoice Date', store=True,
    )
    date_due = fields.Date(
        related='move_id.invoice_date_due', string='Due Date', store=True,
    )
    amount_total = fields.Monetary(
        related='move_id.amount_total', string='Total Amount',
    )
    amount_residual = fields.Monetary(
        related='move_id.amount_residual', string='Residual Amount',
    )
    amount_due = fields.Monetary(
        string='Amount to Pay',
    )
    paid_total = fields.Monetary(
        string='Paid Total',
    )
    wt_amount = fields.Monetary(
        string='WHT Amount',
    )
    net_amount = fields.Monetary(
        string='Net Amount', compute='_compute_net_amount', store=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='move_id.currency_id', store=True,
    )
    communication = fields.Char(string='Communication')
    select = fields.Boolean(string='เลือก', default=True)
    invoice_status = fields.Selection(
        related='move_id.state', string='สถานะ', store=True, readonly=True,
    )
    invoice_payment_state = fields.Selection(
        related='move_id.payment_state', string='สถานะการชำระ',
        store=True, readonly=True,
    )
    state = fields.Selection(
        related='payment_id.state', string='Payment State', store=True,
    )
    payment_state = fields.Selection(
        related='payment_id.state', string='Payment Status', store=True,
    )
    company_id = fields.Many2one(
        'res.company', related='payment_id.company_id', store=True,
    )
    payment_type = fields.Selection(
        related='payment_id.payment_type', string='Payment Type', store=True,
    )

    @api.depends('amount_due', 'wt_amount')
    def _compute_net_amount(self):
        for line in self:
            line.net_amount = (line.amount_due or 0.0) - (line.wt_amount or 0.0)

    @api.onchange('select')
    def _onchange_select(self):
        """Auto-fill paid_total when select is toggled"""
        if self.select:
            self.paid_total = self.amount_due
        else:
            self.paid_total = 0


# ====================================================================
# Account Paid Line (payment method line)
# ====================================================================

class AccountPaidLine(models.Model):
    _name = 'account.paid.line'
    _inherit = ['analytic.mixin']
    _description = 'Payment Method Line'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    payment_id = fields.Many2one(
        'account.payment', string='Payment', ondelete='cascade', index=True,
    )
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
    )
    amount = fields.Monetary(string='Amount')
    date = fields.Date(string='Date')
    cheque_id = fields.Many2one(
        'account.cheque', string='Cheque',
    )
    bank_account_id = fields.Many2one(
        'res.partner.bank', string='Bank Account',
    )
    account_id = fields.Many2one(
        'account.account', string='Account',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account',
    )
    analytic_distribution = fields.Json(
        string='Analytic Distribution',
    )
    payment_method_type = fields.Selection([
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('credit_card', 'Credit Card'),
        ('other', 'Other'),
    ], string='Payment Method', default='cash')
    is_write_off = fields.Boolean(string='Write Off', default=False)
    write_off_account_id = fields.Many2one(
        'account.account', string='Write-off Account',
    )
    communication = fields.Char(string='Memo')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        'res.company', related='payment_id.company_id', store=True,
    )
    state = fields.Selection(
        related='payment_id.state', string='Payment State', store=True,
    )
    partner_id = fields.Many2one(
        'res.partner', related='payment_id.partner_id', store=True,
    )
    cheque_number = fields.Char(
        string='Cheque Number',
    )
    cheque_date = fields.Date(
        string='Cheque Date',
    )


# ====================================================================
# Account Move Line extension
# ====================================================================

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    invoice_id = fields.Many2one(
        'account.payment.invoice', string='Payment Invoice Line',
        ondelete='set null', copy=False,
    )
