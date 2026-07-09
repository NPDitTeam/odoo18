# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import ValidationError


class StockTransferApprovalWizard(models.TransientModel):
    _name = "stock.transfer.approval.wizard"
    _description = "Wizard ส่งขออนุมัติการโยกสินค้า"

    transfer_id = fields.Many2one("stock.api.transfer", string="เอกสารโยกสินค้า", required=True)
    approver_id = fields.Many2one("res.users", string="ผู้อนุมัติ", required=True)
    reason = fields.Text(string="เหตุผลการโยก", required=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", "stock_transfer_wizard_attachment_rel",
        "wizard_id", "attachment_id", string="ไฟล์แนบ")

    def action_submit_approval(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise ValidationError("กรุณากรอกเหตุผลการโยก")
        if not self.approver_id:
            raise ValidationError("กรุณาเลือกผู้อนุมัติ")

        approval = self.env['stock.transfer.approval'].create({
            'transfer_id': self.transfer_id.id,
            'requester_id': self.env.user.id,
            'approver_id': self.approver_id.id,
            'reason': self.reason,
            'attachment_ids': [(6, 0, self.attachment_ids.ids)] if self.attachment_ids else False,
            'state': 'pending',
        })

        self.transfer_id.write({
            'state': 'waiting_approval',
            'approval_id': approval.id,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}
