from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date


class AccountAdvance(models.Model):
    _name = "account.advance"
    _rec_name = "name"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Account Advance"
    _order = "name DESC"

    def _default_employee(self):
        return self.env.user.employee_id.id

    def _default_department(self):
        return self.env.user.employee_id.department_id.id

    def _get_journal_id(self):
        advance_journal_id = self.env.company.advance_journal_id.id
        if advance_journal_id:
            return advance_journal_id

    def _get_account_id(self):
        advance_account_id = self.env.company.advance_account_id.id
        if advance_account_id:
            return advance_account_id

    @api.depends("clear_ids.state", "clear_ids.exclude_amount", "clear_ids.clear_amount")
    def _compute_remaining(self):
        for adv in self:
            adv.clear = sum(
                clear.exclude_amount + clear.clear_amount
                if clear.state == "post"
                else 0
                for clear in adv.clear_ids
            )
            adv.remain = adv.payment_total - adv.clear
            if adv.remain == 0:
                adv.state_remain = "Clear"
            else:
                adv.state_remain = "Wait Clear"

    branch_id = fields.Many2one("res.branch", string="Branch",
        default=lambda self: self.env.user.branch_ids[:1].id)
    name = fields.Char(
        string="Number",
        required=True,
        default="/",
        readonly=True,
    )
    advance_date = fields.Date(
        string="Date",
        required=True,
        copy=False,
        default=fields.Date.context_today,
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        index=True,
        string="Department",
        default=_default_department,
        required=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        ondelete="restrict",
        index=True,
        default=_default_employee,
        string="Employee",
        required=True,
    )
    payee_ids = fields.Many2many("hr.employee", string="Payee")
    advance_request_id = fields.Many2one(
        comodel_name="account.advance.request",
        string="Reference",
        required=False,
    )
    due_date = fields.Date(
        string="Due Date Request",
        required=False,
    )
    due_date_clear = fields.Date(
        string="Due Date Clear",
        required=False,
    )
    description = fields.Text(
        string="Description",
        required=False,
    )
    payment_method_id = fields.Many2one(
        comodel_name="custom.payment.method",
        string="Payment Method",
        required=False,
        domain="[('is_active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    advance_total = fields.Float(
        string="Request Amount",
        related="advance_request_id.advance_total",
        required=False,
        readonly=True,
    )
    total = fields.Float(
        string="Total",
        required=False,
        tracking=True,
    )
    remain = fields.Float(
        string="Remaining",
        required=False,
        store=True,
        compute="_compute_remaining",
    )
    clear = fields.Float(
        string="Clear",
        required=False,
        readonly=True,
        store=True,
        compute="_compute_remaining",
    )
    state_remain = fields.Char(
        string="State Clear",
        compute="_compute_remaining",
    )
    state = fields.Selection(
        string="State",
        selection=[
            ("draft", "Draft"),
            ("submit", "Paid"),
            ("cancel", "Canceled"),
        ],
        required=False,
        default="draft",
        tracking=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Move Entry",
        required=False,
        readonly=True,
        tracking=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        index=True,
        string="Advance Journal",
        required=True,
        default=_get_journal_id,
    )
    account_id = fields.Many2one(
        "account.account",
        index=True,
        string="Advance Account",
        required=True,
        default=_get_account_id,
    )
    clear_ids = fields.One2many(
        comodel_name="account.advance.clear",
        inverse_name="advance_id",
        string="Clear Advance",
        required=False,
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        store=True,
        readonly=True,
        default=lambda self: self.env.company,
    )

    is_payment_multi = fields.Boolean(string="Payment Multi", default=False)
    payment_ids = fields.One2many(
        comodel_name="account.advance.payment",
        inverse_name="advance_id",
        string="Advance",
        required=False,
    )
    payment_total = fields.Float(
        string="Payment Total",
        compute="_compute_total",
        digits=(12, 2),
        store=True,
    )

    status_due = fields.Selection(
        string="Status Due",
        selection=[
            ("over", "Over Due"),
            ("normal", "Normal"),
        ],
        compute="_compute_status_due",
    )

    @api.depends("payment_ids.total", "is_payment_multi", "total")
    def _compute_total(self):
        for rec in self:
            rec.payment_total = (
                sum(line.total for line in rec.payment_ids)
                if rec.is_payment_multi
                else rec.total
            )

    def create_account_move(self):
        vals = []
        if self.payment_total == 0:
            raise UserError(_("Please Input Total."))
        if not self.is_payment_multi and not self.payment_method_id:
            raise UserError(_("Please Input Payment Method."))
        name = "Advance for employee %s" % self.employee_id.name
        vals.append(
            (
                0,
                0,
                {
                    "account_id": self.account_id.id,
                    "debit": abs(self.payment_total) if self.payment_total > 0 else 0,
                    "credit": abs(self.payment_total) if self.payment_total < 0 else 0,
                    "name": name,
                    "branch_id": self.branch_id.id,
                },
            )
        )
        if self.is_payment_multi:
            for pm in self.payment_ids:
                paid_total = pm.total
                vals.append(
                    (
                        0,
                        0,
                        {
                            "account_id": pm.payment_method_id.account_id.id,
                            "debit": abs(paid_total) if paid_total < 0 else 0,
                            "credit": abs(paid_total) if paid_total > 0 else 0,
                            "name": name,
                            "branch_id": self.branch_id.id,
                        },
                    )
                )
        else:
            vals.append(
                (
                    0,
                    0,
                    {
                        "account_id": self.payment_method_id.account_id.id,
                        "debit": (
                            abs(self.payment_total)
                            if self.payment_total < 0
                            else 0
                        ),
                        "credit": (
                            abs(self.payment_total)
                            if self.payment_total > 0
                            else 0
                        ),
                        "name": name,
                        "branch_id": self.branch_id.id,
                    },
                )
            )

        move_id = self.env["account.move"].create(
            {
                "date": self.advance_date,
                "journal_id": self.journal_id.id,
                "ref": self.name,
                "branch_id": self.branch_id.id,
                "line_ids": vals,
            }
        )

        move_id.action_post()
        self.move_id = move_id
        return True

    def open(self):
        self.name = self.env["ir.sequence"].next_by_code("account.advance")
        self.create_account_move()
        self.state = "submit"
        self.advance_request_id.update({"advance_id": self.id, "state": "receipt"})

    def cancel(self):
        for advance in self:
            advance.move_id.button_draft()
            advance.move_id.unlink()
            advance.state = "cancel"

    @api.onchange("advance_request_id")
    def _onchange_advance_request_id(self):
        if self.advance_request_id:
            self.branch_id = self.advance_request_id.branch_id

    def _compute_status_due(self):
        for rec in self:
            rec.status_due = "normal"
            if rec.due_date_clear:
                date_now = date.today()
                if date_now > rec.due_date_clear:
                    rec.status_due = "over"


class AccountAdvancePayment(models.Model):
    _name = "account.advance.payment"
    _rec_name = "ref"
    _description = "Advance Payment"

    advance_id = fields.Many2one(
        "account.advance", string="Advance", ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company",
        related="advance_id.company_id",
        string="Company",
        store=True,
        readonly=True,
    )
    payment_method_id = fields.Many2one(
        "custom.payment.method",
        string="Payment Method",
        required=True,
        domain="[('is_active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    bank_account_id = fields.Many2one(
        "res.partner.bank", string="Bank Account"
    )
    account_id = fields.Many2one(
        "account.account",
        related="payment_method_id.account_id",
        string="Account",
    )
    total = fields.Float(string="Total", digits=(36, 2), required=True)
    ref = fields.Char(string="Ref", required=False)
