# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import UserError


class StockTransferApproval(models.Model):
    _name = "stock.transfer.approval"
    _description = "การอนุมัติการโยกสินค้า"
    _order = "create_date desc"

    transfer_id = fields.Many2one("stock.api.transfer", string="เอกสารโยกสินค้า",
                                  required=True, ondelete="cascade")
    requester_id = fields.Many2one("res.users", string="ผู้ขอ",
                                   default=lambda self: self.env.user, required=True)
    approver_id = fields.Many2one("res.users", string="ผู้อนุมัติ", required=True)
    reason = fields.Text(string="เหตุผลการโยก", required=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", "stock_transfer_approval_attachment_rel",
        "approval_id", "attachment_id", string="ไฟล์แนบ")
    state = fields.Selection([
        ("pending", "รออนุมัติ"),
        ("approved", "อนุมัติ"),
        ("rejected", "ตีกลับ"),
    ], default="pending", string="สถานะ")
    reject_note = fields.Text(string="หมายเหตุตีกลับ")
    approve_date = fields.Datetime(string="วันที่อนุมัติ/ตีกลับ")

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('stock_api_transfer.group_stock_transfer_approver'):
            raise UserError("คุณไม่มีสิทธิ์อนุมัติการโยกสินค้า")
        self.write({'state': 'approved', 'approve_date': fields.Datetime.now()})
        self.transfer_id.write({'state': 'approved'})

    def action_reject(self):
        """เรียกจาก wizard ตีกลับ (reject_note ถูก set มาก่อนแล้ว)"""
        self.ensure_one()
        if not self.env.user.has_group('stock_api_transfer.group_stock_transfer_approver'):
            raise UserError("คุณไม่มีสิทธิ์ตีกลับการโยกสินค้า")
        self.write({'state': 'rejected', 'approve_date': fields.Datetime.now()})
        self.transfer_id.write({'state': 'draft'})
