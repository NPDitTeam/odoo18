from odoo import fields, models, api, _
from odoo.exceptions import UserError


class AccountAdvanceClear(models.Model):
    _name = "account.advance.clear"
    _rec_name = "name"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Account Advance Clear"
    _order = "name DESC"

    def _get_journal_id(self):
        advance_journal_id = self.env.company.advance_journal_id.id
        if advance_journal_id:
            return advance_journal_id

    def _get_account_id(self):
        advance_account_id = self.env.company.advance_account_id.id
        if advance_account_id:
            return advance_account_id

    branch_id = fields.Many2one("res.branch", string="Branch",
        default=lambda self: self.env.user.branch_ids[:1].id)
    name = fields.Char(
        string="Number",
        required=True,
        default="/",
        readonly=True,
    )
    doc_date = fields.Date(
        string="Doc Date",
        required=False,
        default=fields.Date.context_today,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        ondelete="restrict",
        index=True,
        string="Employee",
        required=True,
    )
    advance_id = fields.Many2one(
        comodel_name="account.advance",
        string="Advance",
        required=True,
        tracking=True,
        domain="[('employee_id', '=', employee_id), ('state', '=', 'submit'), ('remain', '>', 0)]",
    )
    description = fields.Text(
        string="Description",
        required=False,
    )
    clear_ids = fields.One2many(
        comodel_name="advance.clear.line",
        inverse_name="advance_clear_id",
        string="Advance Clear",
        required=False,
    )
    advance_amount = fields.Float(
        string="Amount Advance",
        store=True,
        readonly=True,
        required=False,
    )
    payment_method_id = fields.Many2one(
        comodel_name="account.journal",
        string="Payment Method Clear",
        required=False,
        tracking=True,
        domain="[('type', 'in', ['bank', 'cash'])]",
    )
    state = fields.Selection(
        string="State",
        selection=[
            ("draft", "Draft"),
            ("confirm", "Confirmed"),
            ("post", "Posted"),
            ("cancel", "Canceled"),
        ],
        required=True,
        default="draft",
        tracking=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        "Journal",
        required=True,
        readonly=True,
        default=_get_journal_id,
    )
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        required=True,
        default=_get_account_id,
        help="The income or expense account related to the selected product.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        compute="_get_journal_currency",
        string="Currency",
        readonly=True,
        store=True,
        default=lambda self: self._get_currency(),
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        store=True,
        readonly=True,
        related="journal_id.company_id",
        default=lambda self: self.env.company,
    )
    amount = fields.Monetary(
        string="Total", store=True, readonly=True, compute="_compute_total"
    )
    exclude_amount = fields.Monetary(
        string="Total Exclude WHT",
        store=False,
        readonly=True,
        compute="_compute_total",
    )
    untaxed_amount = fields.Monetary(
        string="UnTaxed Amount",
        store=True,
        readonly=True,
        compute="_compute_total",
    )
    tax_amount = fields.Monetary(
        readonly=True, store=True, compute="_compute_total"
    )
    amount_wht = fields.Float(
        string="Wht Amount",
        required=False,
    )
    tax_correction = fields.Monetary(
        readonly=False,
        help="In case we have a rounding problem in the tax, use this field to correct it",
    )
    wt_cert_ids = fields.One2many(
        comodel_name="withholding.tax.cert",
        inverse_name="advance_clear_id",
        string="Withholding Tax Cert.",
        readonly=False,
    )
    wht_amount = fields.Monetary(
        string="Withholding Tax Amount",
        store=True,
        readonly=True,
        compute="_compute_total",
    )
    clear_amount = fields.Monetary(
        string="Clear Amount",
        store=True,
        readonly=True,
        compute="_compute_total",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Move Entry",
        required=False,
        tracking=True,
    )
    tax_line = fields.One2many(
        comodel_name="account.move.tax.invoice",
        inverse_name="advance_clear_id",
        string="Invoice Tax",
        required=False,
    )
    is_partial = fields.Boolean(
        string="Partial Clearing",
        default=False,
    )
    amount_clearing = fields.Float(
        string="Partial Amount Clearing",
        required=False,
    )
    note = fields.Text(
        string="Note",
        required=False,
    )

    @api.depends("journal_id", "company_id")
    def _get_journal_currency(self):
        for rec in self:
            rec.currency_id = (
                rec.journal_id.currency_id.id or rec.company_id.currency_id.id
            )

    def _get_currency(self):
        journal = self.env["account.journal"].browse(
            self.env.context.get("default_journal_id", False)
        )
        if journal.currency_id:
            return journal.currency_id.id
        return self.env.company.currency_id.id

    @api.depends(
        "is_partial",
        "tax_correction",
        "clear_ids.price_subtotal",
        "wt_cert_ids",
        "amount_clearing",
    )
    def _compute_total(self):
        tax_calculation_rounding_method = (
            self.env.company.tax_calculation_rounding_method
        )
        for advance_clear in self:
            total = 0
            tax_amount = 0
            amount = 0
            tax_lines_vals_merged = {}
            for line in advance_clear.clear_ids:
                tax_info = line.tax_ids.compute_all(
                    line.price_unit,
                    advance_clear.currency_id,
                    line.quantity,
                    line.product_id,
                )
                if tax_calculation_rounding_method == "round_globally":
                    total += tax_info.get("total_excluded", 0.0)
                    for t in tax_info.get("taxes", False):
                        key = (
                            t["id"],
                            t["account_id"],
                        )
                        if key not in tax_lines_vals_merged:
                            tax_lines_vals_merged[key] = t.get("amount", 0.0)
                        else:
                            tax_lines_vals_merged[key] += t.get("amount", 0.0)
                else:
                    total += tax_info.get("total_included", 0.0)
                    tax_amount += sum(
                        t.get("amount", 0.0)
                        for t in tax_info.get("taxes", False)
                    )
            if tax_calculation_rounding_method == "round_globally":
                tax_amount = sum(
                    advance_clear.currency_id.round(t)
                    for t in tax_lines_vals_merged.values()
                )
                amount = total + tax_amount + advance_clear.tax_correction
            else:
                amount = total + advance_clear.tax_correction
            advance_clear.tax_amount = tax_amount
            advance_clear.wht_amount = sum(
                wht_line.amount
                for cert in advance_clear.wt_cert_ids
                for wht_line in cert.wht_line
            )
            advance_clear.untaxed_amount = sum(
                line.price_subtotal for line in advance_clear.clear_ids
            )

            advance_clear.exclude_amount = amount - advance_clear.wht_amount
            advance_clear.amount = (
                amount
                if advance_clear.is_partial
                else amount - advance_clear.wht_amount
            )
            advance_clear.clear_amount = (
                advance_clear.advance_amount - advance_clear.amount
            )
            if advance_clear.is_partial:
                advance_clear.clear_amount = advance_clear.amount_clearing

    def submit(self):
        if self.name == "/":
            self.name = self.env["ir.sequence"].next_by_code(
                "account.advance.clear"
            )
        if self.clear_amount != 0 and not self.payment_method_id:
            raise UserError(_("Please Select Payment method Clear."))
        self.state = "confirm"

    def confirm(self):
        self.action_move_line_create()
        self.state = "post"

    def first_move_line_get(self, move_id, company_currency, current_currency):
        debit = credit = 0.0
        if self.is_partial:
            credit = self.amount_clearing + self.amount - self.wht_amount
        else:
            credit = self.advance_amount
        if self.is_partial and credit > self.advance_amount:
            raise UserError(
                _(
                    "Clearing over advance balance please not select Partial Clearing."
                )
            )

        if debit < 0.0:
            debit = 0.0
        if credit < 0.0:
            credit = 0.0
        sign = -1 if debit - credit < 0 else 1
        move_line = {
            "name": "Advance Clear %s" % self.advance_id.name,
            "debit": debit,
            "credit": credit,
            "account_id": self.account_id.id,
            "move_id": move_id,
            "journal_id": self.journal_id.id,
            "currency_id": current_currency
            if company_currency != current_currency
            else company_currency,
            "amount_currency": (
                sign * abs(self.amount)
                if company_currency != current_currency
                else 0.0
            ),
            "date": self.doc_date,
            "date_maturity": self.doc_date,
        }
        return move_line

    def clear_move_line_get(self, move_id, company_currency, current_currency):
        debit = credit = 0.0
        if self.clear_amount < 0:
            credit = self._convert(self.clear_amount)
        elif self.clear_amount > 0:
            debit = self._convert(self.clear_amount)

        move_line = {
            "name": self.payment_method_id.name or "/",
            "debit": abs(debit),
            "credit": abs(credit),
            "account_id": self.payment_method_id.default_account_id.id,
            "move_id": move_id,
            "journal_id": self.journal_id.id,
            "currency_id": current_currency
            if company_currency != current_currency
            else company_currency,
            "amount_currency": (
                abs(self.amount)
                if company_currency != current_currency
                else 0.0
            ),
            "date": self.doc_date,
            "date_maturity": self.doc_date,
        }
        return move_line

    def account_move_get(self):
        move = {
            "journal_id": self.journal_id.id,
            "date": self.doc_date,
            "ref": self.name,
        }
        return move

    def _convert(self, amount):
        for advance_clear in self:
            return advance_clear.currency_id._convert(
                amount,
                advance_clear.company_id.currency_id,
                advance_clear.company_id,
                advance_clear.doc_date,
            )

    def advance_clear_move_line_create(
        self, line_total, move_id, company_currency, current_currency
    ):
        for line in self.clear_ids:
            if not line.price_subtotal:
                continue
            line_subtotal = line.price_subtotal
            amount = self._convert(line.price_subtotal)
            move_line = {
                "journal_id": self.journal_id.id,
                "name": line.name or "/",
                "account_id": line.account_id.id,
                "move_id": move_id,
                "quantity": line.quantity,
                "product_id": line.product_id.id,
                "partner_id": line.partner_id.id or False,
                "credit": 0.0,
                "debit": abs(amount),
                "date": self.doc_date,
                "tax_ids": [(4, t.id) for t in line.tax_ids],
                "amount_currency": line_subtotal
                if current_currency != company_currency
                else 0.0,
                "currency_id": current_currency
                if company_currency != current_currency
                else company_currency,
            }
            self.env["account.move.line"].with_context(
                check_move_validity=False
            ).create(move_line)

        return line_total

    def wht_move_line_get(
        self, move_id, company_currency, current_currency, wht_cert_line
    ):
        """Create journal entry line for a withholding tax cert line.
        In Odoo 18, WHT amounts are on withholding.tax.cert.line,
        and the account comes from wht_tax_id.account_id.
        """
        debit = credit = 0.0
        credit = self._convert(wht_cert_line.amount)
        if debit < 0.0:
            debit = 0.0
        if credit < 0.0:
            credit = 0.0
        sign = -1 if debit - credit < 0 else 1
        wht_account_id = wht_cert_line.wht_tax_id.account_id.id
        move_line = {
            "name": _("Withholding Tax"),
            "debit": debit,
            "credit": credit,
            "account_id": wht_account_id,
            "move_id": move_id,
            "journal_id": self.journal_id.id,
            "currency_id": current_currency
            if company_currency != current_currency
            else company_currency,
            "amount_currency": (
                sign * abs(wht_cert_line.amount)
                if company_currency != current_currency
                else 0.0
            ),
            "date": self.doc_date,
            "date_maturity": self.doc_date,
        }
        return move_line

    def action_move_line_create(self):
        """Confirm the advance clears and create the journal entries."""
        for advance_clear in self:
            company_currency = (
                advance_clear.journal_id.company_id.currency_id.id
            )
            current_currency = (
                advance_clear.currency_id.id or company_currency
            )
            ctx = dict(self._context)
            ctx["date"] = advance_clear.doc_date
            ctx["check_move_validity"] = False
            # Create the account move record
            move = self.env["account.move"].create(
                advance_clear.account_move_get()
            )
            # Create the first line of the advance clear
            move_line = (
                self.env["account.move.line"]
                .with_context(**ctx)
                .create(
                    advance_clear.with_context(**ctx).first_move_line_get(
                        move.id, company_currency, current_currency
                    )
                )
            )
            line_total = move_line.debit - move_line.credit
            line_total = line_total + advance_clear._convert(
                advance_clear.tax_amount
            )

            if self.clear_amount != 0:
                self.env["account.move.line"].with_context(**ctx).create(
                    advance_clear.with_context(**ctx).clear_move_line_get(
                        move.id, company_currency, current_currency
                    )
                )

            # Create move line with wht certificate lines
            for cert in self.wt_cert_ids:
                for wht_cert_line in cert.wht_line:
                    if wht_cert_line.amount:
                        self.env["account.move.line"].with_context(
                            **ctx
                        ).create(
                            advance_clear.with_context(
                                **ctx
                            ).wht_move_line_get(
                                move.id,
                                company_currency,
                                current_currency,
                                wht_cert_line,
                            )
                        )
            # Create one move line per advance clear line
            line_total = (
                advance_clear.with_context(
                    **ctx
                ).advance_clear_move_line_create(
                    line_total,
                    move.id,
                    company_currency,
                    current_currency,
                )
            )
            # Create move line vat
            advance_clear.with_context(**ctx).vat_move_line_create(
                move.id, company_currency, current_currency
            )

            # Add tax correction to move line if any
            if advance_clear.tax_correction != 0.0:
                tax_move_line = self.env["account.move.line"].search(
                    [
                        ("move_id", "=", move.id),
                        ("tax_line_id", "!=", False),
                    ],
                    limit=1,
                )
                if tax_move_line:
                    tax_move_line.write(
                        {
                            "debit": tax_move_line.debit
                            + advance_clear.tax_correction
                            if tax_move_line.debit > 0
                            else 0,
                            "credit": tax_move_line.credit
                            + advance_clear.tax_correction
                            if tax_move_line.credit > 0
                            else 0,
                        }
                    )
            # Fill in tax invoice number/date and amounts for l10n_th
            # Build lookup from clear lines: tax_id -> data
            tax_inv_data = {}
            for line in advance_clear.clear_ids:
                if line.tax_ids and line.invoice_number:
                    tax_info = line.tax_ids.compute_all(
                        line.price_unit,
                        advance_clear.currency_id,
                        line.quantity,
                        line.product_id,
                        line.partner_id,
                    )
                    for t in tax_info.get("taxes", []):
                        tax_inv_data.setdefault(t["id"], {
                            "tax_invoice_number": line.invoice_number,
                            "tax_invoice_date": line.invoice_date,
                            "partner_id": line.partner_id.id,
                            "advance_clear_id": advance_clear.id,
                            "tax_base_amount": 0.0,
                            "balance": 0.0,
                        })
                        tax_inv_data[t["id"]]["tax_base_amount"] += t["base"]
                        tax_inv_data[t["id"]]["balance"] += t["amount"]
            # Update all tax invoice records on the move that need data
            all_tax_invoices = self.env["account.move.tax.invoice"].search([
                ("move_id", "=", move.id),
            ])
            for tax_inv in all_tax_invoices:
                tax_id = tax_inv.tax_line_id.id
                if tax_id in tax_inv_data:
                    tax_inv.write(tax_inv_data[tax_id])
                elif not tax_inv.tax_invoice_number:
                    # Fallback: use first available data
                    if tax_inv_data:
                        first_data = list(tax_inv_data.values())[0]
                        tax_inv.write(first_data)

            # Post the advance clear
            advance_clear.write(
                {
                    "move_id": move.id,
                }
            )
            move.action_post()
        return True

    def action_cancel_draft(self):
        self.write({"state": "cancel"})

    def set_draft(self):
        self.write({"state": "draft"})
        self.ensure_one()
        query = """
            DELETE FROM account_move_tax_invoice
            WHERE advance_clear_id = %s
        """
        self.env.cr.execute(query, (self.id,))
        return True

    def cancel_advance(self):
        for advance in self:
            advance.move_id.button_draft()
            advance.move_id.unlink()
        self.write({"state": "cancel", "move_id": False})

    def _get_tax_vals(self):
        for voucher in self:
            tax_vals = {}
            for line in voucher.clear_ids:
                if line.tax_ids:
                    if not line.partner_id or not line.invoice_number:
                        raise UserError(
                            _(
                                "Please input partner and invoice_number in line tax"
                            )
                        )
                    tax_info = line.tax_ids.compute_all(
                        line.price_unit,
                        voucher.currency_id,
                        line.quantity,
                        line.product_id,
                        line.partner_id,
                    )
                    for t in tax_info.get("taxes", False):
                        group_key = "%s_%s_%s" % (
                            t["id"],
                            line.invoice_number,
                            line.partner_id.id,
                        )
                        tax_vals.setdefault(
                            group_key,
                            {
                                "tax_line_id": t["id"],
                                "amount": 0.0,
                                "base": 0.0,
                                "account_id": "",
                                "tax_repartition_line_id": "",
                                "partner_id": line.partner_id.id,
                                "invoice_number": line.invoice_number or "",
                                "invoice_date": line.invoice_date,
                            },
                        )
                        tax_vals[group_key]["account_id"] = t["account_id"]
                        tax_vals[group_key]["name"] = t["name"]
                        tax_vals[group_key][
                            "tax_repartition_line_id"
                        ] = t["tax_repartition_line_id"]
                        tax_vals[group_key]["amount"] += t["amount"]
                        tax_vals[group_key]["base"] += t["base"]
            return tax_vals

    def vat_move_line_create(
        self, move_id, company_currency, current_currency
    ):
        tax_vals = self._get_tax_vals()
        Currency = self.env["res.currency"]
        company_cur = Currency.browse(company_currency)
        current_cur = Currency.browse(current_currency)

        for tax in tax_vals:
            temp = {
                "account_id": tax_vals[tax]["account_id"],
                "name": tax_vals[tax]["name"],
                "tax_line_id": tax_vals[tax]["tax_line_id"],
                "move_id": move_id,
                "date": self.doc_date,
                "partner_id": tax_vals[tax]["partner_id"],
                "debit": tax_vals[tax]["amount"] or 0.0,
                "credit": 0.0,
            }
            if company_currency != current_currency:
                sign = -1 if temp["credit"] else 1
                amount_currency = company_cur._convert(
                    tax_vals[tax]["amount"],
                    current_cur,
                    self.company_id,
                    self.doc_date or fields.Date.today(),
                    round=True,
                )
                temp["currency_id"] = current_currency
                temp["amount_currency"] = sign * abs(amount_currency)
            else:
                temp["currency_id"] = company_currency
                temp["amount_currency"] = 0.0

            move_line_id = self.env["account.move.line"].with_context(
                check_move_validity=False
            ).create(temp)
            move_line_id.update(
                {
                    "tax_repartition_line_id": tax_vals[tax][
                        "tax_repartition_line_id"
                    ]
                }
            )

    def _create_tax_move(
        self,
        move_id,
        move_line_id,
        tax_line_id,
        tax_base=0.00,
        tax_amount=0.00,
        partner_id=None,
        invoice_number=None,
        invoice_date=None,
    ):
        TaxInvoice = self.env["account.move.tax.invoice"]
        TaxInvoice.create(
            {
                "move_id": move_id,
                "move_line_id": move_line_id.id,
                "advance_clear_id": self.id,
                "partner_id": partner_id,
                "tax_invoice_number": invoice_number,
                "tax_invoice_date": invoice_date or False,
                "tax_base_amount": abs(tax_base),
                "balance": abs(tax_amount),
                "tax_line_id": tax_line_id,
            }
        )

    @api.onchange("advance_id")
    def _onchange_advance_id(self):
        self.advance_amount = self.advance_id.remain


class AdvanceClearLine(models.Model):
    _name = "advance.clear.line"
    _description = "Advance Clear line"

    advance_clear_id = fields.Many2one(
        comodel_name="account.advance.clear",
        string="Advance Clear Id",
        required=False,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        required=False,
    )
    name = fields.Char(
        string="Description",
        required=False,
    )
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        required=True,
        help="The income or expense account related to the selected product.",
    )
    price_unit = fields.Float(
        string="Unit Price",
        required=True,
        digits="Product Price",
    )
    price_subtotal = fields.Monetary(
        string="Amount",
        store=True,
        readonly=True,
        compute="_compute_subtotal",
    )
    quantity = fields.Float(
        digits="Product Unit of Measure",
        required=True,
        default=1,
    )
    analytic_distribution = fields.Json(
        string="Analytic Distribution",
    )
    analytic_precision = fields.Integer(
        default=2,
        store=False,
    )
    company_id = fields.Many2one(
        "res.company",
        related="advance_clear_id.company_id",
        string="Company",
        store=True,
        readonly=True,
    )
    tax_ids = fields.Many2many(
        "account.tax",
        string="Tax",
        help="Only for tax excluded from price",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="advance_clear_id.currency_id",
        readonly=False,
    )
    partner_id = fields.Many2one("res.partner", "Partner", required=False)
    invoice_number = fields.Char(
        string="Invoice Number",
        required=False,
    )
    invoice_date = fields.Date(
        string="Invoice Date",
        required=False,
    )

    @api.depends(
        "price_unit",
        "tax_ids",
        "quantity",
        "product_id",
        "advance_clear_id.currency_id",
    )
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(
                    line.price_unit,
                    line.advance_clear_id.currency_id,
                    line.quantity,
                    product=line.product_id,
                )
                line.price_subtotal = taxes["total_excluded"]

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if not self.advance_clear_id or not self.product_id:
            return
        product = self.product_id
        self.name = product.name
        self.account_id = (
            product.categ_id.property_account_expense_categ_id
            or product.property_account_expense_id
        )
        taxes = product.supplier_taxes_id
        if product.description_sale:
            self.name += "\n" + product.name
        self.tax_ids = taxes


class WithholdingTaxCert(models.Model):
    _inherit = "withholding.tax.cert"

    advance_clear_id = fields.Many2one(
        "account.advance.clear",
        string="Account Advance Clear",
        ondelete="cascade",
    )


class AccountMoveTaxInvoice(models.Model):
    _inherit = "account.move.tax.invoice"

    advance_clear_id = fields.Many2one(
        "account.advance.clear",
        string="Account Clear",
        ondelete="cascade",
    )
