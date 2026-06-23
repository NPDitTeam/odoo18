import json
import logging

from odoo import fields, models, api, _

_logger = logging.getLogger(__name__)


class ReceiptCorrectionWizard(models.TransientModel):
    _name = 'receipt.correction.wizard'
    _description = 'Receipt Amount Correction Wizard'

    advance_clear_id = fields.Many2one(
        'account.advance.clear',
        string='Advance Clear',
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'receipt.correction.wizard.line',
        'wizard_id',
        string='รายการใบเสร็จที่ต้องแก้ไข',
    )

    def action_save_and_recheck(self):
        """Save corrections and re-render AI result with corrected amounts."""
        self.ensure_one()
        ac = self.advance_clear_id

        # Delete existing corrections for this advance clear
        ac.receipt_correction_ids.unlink()

        # Create new correction records from wizard lines
        for line in self.line_ids:
            if line.corrected_amount > 0:
                self.env['advance.clear.receipt.correction'].create({
                    'advance_clear_id': ac.id,
                    'filename': line.filename,
                    'original_amount': line.original_amount,
                    'corrected_amount': line.corrected_amount,
                })

        # Re-render the AI result with corrections
        ac.action_recheck_with_corrections()

        return {'type': 'ir.actions.act_window_close'}


class ReceiptCorrectionWizardLine(models.TransientModel):
    _name = 'receipt.correction.wizard.line'
    _description = 'Receipt Correction Wizard Line'
    _order = 'id'

    wizard_id = fields.Many2one(
        'receipt.correction.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    filename = fields.Char(
        string='ชื่อไฟล์',
        readonly=True,
    )
    original_amount = fields.Float(
        string='ยอดที่ AI อ่านได้',
        readonly=True,
        digits='Product Price',
    )
    corrected_amount = fields.Float(
        string='ยอดที่ถูกต้อง',
        digits='Product Price',
    )
