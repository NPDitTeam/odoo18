from odoo import fields, models


class ReceiptCondition(models.Model):
    _name = 'advance.clear.receipt.condition'
    _description = 'Receipt Verification Condition'
    _order = 'id'

    advance_clear_id = fields.Many2one(
        'account.advance.clear',
        string='Advance Clear',
        required=True,
        ondelete='cascade',
        index=True,
    )
    filename = fields.Char(
        string='ชื่อไฟล์',
        required=True,
    )
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='ไฟล์แนบ',
        ondelete='set null',
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
        help='ระบุเหตุผลที่ข้ามการตรวจสอบ',
    )
