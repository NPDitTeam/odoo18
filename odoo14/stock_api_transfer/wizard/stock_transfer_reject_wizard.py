# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import ValidationError


class StockTransferRejectWizard(models.TransientModel):
    _name = "stock.transfer.reject.wizard"
    _description = "Wizard ตีกลับการโยกสินค้า"

    transfer_id = fields.Many2one("stock.api.transfer", string="เอกสารโยกสินค้า", required=True)
    reject_note = fields.Text(string="หมายเหตุตีกลับ", required=True)

    def action_reject(self):
        self.ensure_one()
        if not self.reject_note or not self.reject_note.strip():
            raise ValidationError("กรุณากรอกหมายเหตุตีกลับ")
        approval = self.transfer_id.approval_id
        if approval:
            approval.write({'reject_note': self.reject_note})
            approval.action_reject()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
