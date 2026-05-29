from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountCheque(models.Model):
    _name = 'account.cheque'
    _description = 'เช็ค'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_cheque desc, id desc'

    name = fields.Char(string='เลขที่เช็ค', required=True, tracking=True)
    date_cheque = fields.Date(string='วันที่เช็ค', required=True, tracking=True)
    date_done = fields.Date(string='วันที่ตัดเช็ค')
    date_receipt = fields.Date(string='วันที่รับเช็ค')
    cheque_type = fields.Selection([
        ('inbound', 'รับเงิน'),
        ('outbound', 'จ่ายเงิน'),
    ], string='ประเภท', required=True, tracking=True)
    cheque_total = fields.Float(string='จำนวนเงิน', tracking=True)
    remark = fields.Text(string='หมายเหตุ')
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('assigned', 'กำหนดแล้ว'),
        ('reject', 'ปฏิเสธ'),
        ('done', 'เสร็จสิ้น'),
        ('cancel', 'ยกเลิก'),
    ], string='สถานะ', default='draft', tracking=True)
    partner_id = fields.Many2one('res.partner', string='คู่ค้า')
    bank_id = fields.Many2one('res.bank', string='ธนาคาร')
    journal_id = fields.Many2one('account.journal', string='สมุดรายวัน')
    move_id = fields.Many2one('account.move', string='รายการบัญชี', readonly=True)
    company_id = fields.Many2one('res.company', string='บริษัท', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    _sql_constraints = [
        ('unique_cheque_number', 'unique(name, company_id)', 'เลขที่เช็คซ้ำ!'),
    ]

    def action_assigned(self):
        self.write({'state': 'assigned'})

    def action_reject(self):
        self.write({'state': 'reject'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_redraft(self):
        self.write({'state': 'draft'})

    def action_cheque_done(self):
        self.write({'state': 'done', 'date_done': fields.Date.context_today(self)})
