from odoo import fields, models, api, _
from odoo.exceptions import UserError


class AccountAdvanceRequest(models.Model):
    _name = "account.advance.request"
    _rec_name = "name"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Advance Request"
    _order = "name DESC"

    def _default_employee(self):
        return self.env.user.employee_id.id

    def _default_department(self):
        return self.env.user.employee_id.department_id.id

    branch_id = fields.Many2one("res.branch", string="Branch",
        default=lambda self: self.env.user.branch_ids[:1].id)

    name = fields.Char(
        string="Number",
        required=False,
        default="/",
        readonly=True,
    )
    request_date = fields.Date(
        "Request Date",
        readonly=True,
        index=True,
        copy=False,
        default=fields.Date.context_today,
    )
    due_date = fields.Date(
        string="Due Date",
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Create by",
        index=True,
        default=lambda self: self.env.user,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        ondelete="restrict",
        index=True,
        default=_default_employee,
        string="Employee",
        required=True,
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        index=True,
        string="Department",
        default=_default_department,
        required=True,
    )
    description = fields.Text(
        string="Description",
        required=True,
    )
    advance_total = fields.Float(
        string="Advance Total",
        required=True,
    )
    state = fields.Selection(
        string="State",
        selection=[
            ("draft", "Draft"),
            ("submit", "Waiting to Approved"),
            ("approve", "Approve"),
            ("receipt", "Receipt"),
            ("cancel", "Canceled"),
        ],
        required=True,
        default="draft",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        store=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        copy=False,
        ondelete="set null",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
    advance_id = fields.Many2one(
        comodel_name="account.advance",
        string="Reference Advance",
        readonly=True,
    )

    def submit(self):
        self.name = self.env["ir.sequence"].next_by_code("account.advance.request")
        self.state = "submit"

    def approve(self):
        vals = {
            "employee_id": self.employee_id.id,
            "department_id": self.department_id.id,
            "advance_request_id": self.id,
            "description": self.description,
            "total": self.advance_total,
            "due_date": self.due_date,
            "branch_id": self.branch_id.id,
        }
        self.env["account.advance"].create(vals)
        self.state = "approve"

    def cancel(self):
        self.state = "cancel"
