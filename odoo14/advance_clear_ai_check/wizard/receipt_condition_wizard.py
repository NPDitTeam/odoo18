from odoo import fields, models, api, _
from odoo.exceptions import UserError


class ReceiptConditionWizard(models.TransientModel):
    _name = 'receipt.condition.wizard'
    _description = 'Receipt Condition Wizard'

    advance_clear_id = fields.Many2one(
        'account.advance.clear',
        string='Advance Clear',
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'receipt.condition.wizard.line',
        'wizard_id',
        string='รายการใบเสร็จ',
    )

    def action_save(self):
        """Save wizard lines as persistent receipt condition records."""
        self.ensure_one()
        # Validate: if any toggle is OFF, skip_note is required
        for line in self.line_ids:
            has_skip = not (line.check_amount and line.check_vat and line.check_company
                           and line.check_invoice_detail and line.check_slip)
            if has_skip and not (line.skip_note or '').strip():
                raise UserError(_(
                    u'กรุณาระบุหมายเหตุสำหรับไฟล์ "%s"\n'
                    u'เนื่องจากมีการปิดเงื่อนไขการตรวจสอบ ต้องระบุเหตุผล'
                ) % line.filename)
        # Delete existing condition entries for this advance clear
        self.advance_clear_id.receipt_condition_ids.unlink()
        # Create new entries from wizard lines
        for line in self.line_ids:
            self.env['advance.clear.receipt.condition'].create({
                'advance_clear_id': self.advance_clear_id.id,
                'filename': line.filename,
                'attachment_id': line.attachment_id.id if line.attachment_id else False,
                'check_amount': line.check_amount,
                'check_amount_combined': line.check_amount_combined,
                'check_vat': line.check_vat,
                'check_company': line.check_company,
                'check_invoice_detail': line.check_invoice_detail,
                'check_slip': line.check_slip,
                'skip_note': line.skip_note,
            })
        return {'type': 'ir.actions.act_window_close'}


class ReceiptConditionWizardLine(models.TransientModel):
    _name = 'receipt.condition.wizard.line'
    _description = 'Receipt Condition Wizard Line'
    _order = 'id'

    wizard_id = fields.Many2one(
        'receipt.condition.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    filename = fields.Char(
        string='ชื่อไฟล์',
        readonly=True,
    )
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='ไฟล์แนบ',
        readonly=True,
    )
    image_preview = fields.Html(
        string='ตัวอย่าง',
        compute='_compute_image_preview',
        sanitize=False,
    )
    # --- Placeholder conditions (จะเปลี่ยนเมื่อ user แจ้งรายการจริง) ---
    check_amount = fields.Boolean(
        string='ตรวจยอดเงิน',
        default=True,
    )
    check_vat = fields.Boolean(
        string='ตรวจ VAT',
        default=True,
    )
    check_company = fields.Boolean(
        string='ตรวจชื่อบริษัท',
        default=True,
    )
    check_invoice_detail = fields.Boolean(
        string='ตรวจเลขที่/วันที่/ร้านค้า',
        default=True,
    )
    check_amount_combined = fields.Boolean(
        string='ยอดรวมบิล',
        default=True,
        help='ติ๊ก = ตรวจยอดรวมท้ายบิล, ไม่ติ๊ก = ตรวจแยกตามรายการในบิล',
    )
    check_slip = fields.Boolean(
        string='ตรวจสลิป',
        default=True,
        help='ติ๊ก = ตรวจสอบสลิปโอนเงิน (ข้อ 8), ไม่ติ๊ก = ข้ามการตรวจสลิป',
    )
    skip_note = fields.Text(
        string='หมายเหตุ',
    )
    has_any_skip = fields.Boolean(
        string='Has Skip',
        compute='_compute_has_any_skip',
        store=False,
    )

    @api.depends('check_amount', 'check_vat', 'check_company', 'check_invoice_detail', 'check_slip')
    def _compute_has_any_skip(self):
        for line in self:
            line.has_any_skip = not (line.check_amount and line.check_vat and line.check_company and line.check_invoice_detail and line.check_slip)

    @api.depends('attachment_id')
    def _compute_image_preview(self):
        for line in self:
            if line.attachment_id and line.attachment_id.mimetype and \
               line.attachment_id.mimetype.startswith('image/'):
                img_url = '/web/image/%d' % line.attachment_id.id
                line.image_preview = (
                    '<a href="%s" target="_blank">'
                    '<img src="%s" style="max-width: 60px; max-height: 60px; '
                    'object-fit: contain; border-radius: 3px; border: 1px solid #dee2e6;"/>'
                    '</a>'
                ) % (img_url, img_url)
            elif line.attachment_id and line.attachment_id.mimetype == 'application/pdf':
                line.image_preview = (
                    '<span style="font-size: 28px; color: #dc3545;">&#128196;</span>'
                )
            else:
                line.image_preview = '<span style="color: #999;">-</span>'
