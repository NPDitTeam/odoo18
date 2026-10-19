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
        self.name = self.env["ir.sequence"].with_company(self.company_id).next_by_code("account.advance.request")  # เลขแยกตามบริษัทของเอกสาร (ไม่ใช่บริษัทที่เลือกบนแถบ)
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


class IrSequenceAdvanceDaily(models.Model):
    """เลขเอกสารระบบเงินทดรองแบบ Odoo 14: date_range รายวัน แยกบริษัท

    ขอเบิกเงินทดรอง  ADR-261019-0001
    เงินทดรองจ่าย     AD-261019-0001
    เคลียร์เงินทดรอง  AD-261019-0001  (o14 ใช้ AD เหมือนกัน แต่คนละตัวนับ)
    prefix ของแต่ละวันมาจาก date_range (npd_generate_subsequences) — ปีถัดไป
    npd_sequence_auto_year_range สร้างช่วงให้เองตามรูปแบบเดิม
    """
    _inherit = 'ir.sequence'

    NPD_ADVANCE_DAILY_PREFIX = {
        'account.advance.request': 'ADR-%(prefix)s-',
        'account.advance': 'AD-%(prefix)s-',
        'account.advance.clear': 'AD-%(prefix)s-',
    }

    @api.model
    def _npd_setup_advance_daily_sequences(self):
        from datetime import date, timedelta
        DateRange = self.env['ir.sequence.date_range'].sudo()
        if 'prefix' not in DateRange._fields:
            return  # ไม่มี npd_generate_subsequences — %(prefix)s ใช้ไม่ได้
        year = fields.Date.context_today(self).year
        for code, seq_prefix in self.NPD_ADVANCE_DAILY_PREFIX.items():
            for seq in self.sudo().search([('code', '=', code), ('company_id', '!=', False)]):
                if seq.use_date_range and seq.prefix == seq_prefix:
                    continue
                # เลขเดิม (ADR202605-0009) รูปแบบไม่ซ้ำกับแบบใหม่ จึงเปลี่ยนได้แม้เคยออกเลขแล้ว
                seq.write({'prefix': seq_prefix, 'use_date_range': True})
                have = set(seq.date_range_ids.mapped('date_from'))
                day, vals = date(year, 1, 1), []
                while day.year == year:
                    if day not in have:
                        vals.append({'sequence_id': seq.id, 'date_from': day, 'date_to': day,
                                     'prefix': day.strftime('%y%m%d')})
                    day += timedelta(days=1)
                DateRange.create(vals)
