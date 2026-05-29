from odoo import models, fields


class StockPicking(models.Model):
    _inherit = "stock.picking"

    approval_state = fields.Selection([
        ('draft', 'ฉบับร่าง'),
        ('waiting', 'รออนุมัติ'),
        ('approved', 'อนุมัติแล้ว'),
        ('revise', 'แก้ไขตามคำแนะนำ'),
    ], string="สถานะการอนุมัติ", default='draft')

    approver_id = fields.Many2one('res.users', string="ผู้อนุมัติ")
    request_note = fields.Text(string="หมายเหตุการขออนุมัติ")
    approval_note = fields.Text(string="หมายเหตุจากผู้อนุมัติ")

    rent_discount = fields.Float(string="ส่วนลดค่าเช่า", tracking=True)
