# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

BILL_TYPES = ('in_invoice', 'in_refund', 'in_receipt')


class AccountMove(models.Model):
    _inherit = 'account.move'

    npd_require_line_partner = fields.Boolean(
        compute='_compute_npd_require_line_partner',
        string='บังคับระบุ Partner รายบรรทัด')

    @api.depends('partner_id', 'partner_id.name', 'partner_id.npd_require_line_partner', 'move_type')
    def _compute_npd_require_line_partner(self):
        for move in self:
            move.npd_require_line_partner = bool(
                move.move_type in BILL_TYPES and move.partner_id and move.partner_id._npd_needs_line_partner())

    def _npd_check_line_partner(self):
        for move in self.filtered('npd_require_line_partner'):
            number = move.name if move.name and move.name != '/' else ''
            lines = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note') and not l.npd_line_partner_id)
            if lines:
                raise UserError(_(
                    'บิล %s ของ %s ต้องระบุ Partner ทุกบรรทัดในแท็บ รายการจากใบแจ้งหนี้\nบรรทัดที่ยังไม่ระบุ:\n%s'
                ) % (number, move.partner_id.display_name,
                     '\n'.join('- %s' % (l.name or l.product_id.display_name or '') for l in lines)))
            if 'tax_invoice_ids' not in move._fields:
                continue
            vendor = move.partner_id.commercial_partner_id
            line_partners = move.invoice_line_ids.mapped('npd_line_partner_id.commercial_partner_id')
            # ใบกำกับภาษียังเป็นชื่อผู้ขาย (ธนาคาร) ได้เฉพาะเมื่อมีบรรทัดที่เป็นของผู้ขายเองจริง (เช่น ค่าธรรมเนียม)
            bad = move.tax_invoice_ids.filtered(
                lambda t: not t.partner_id
                or (t.partner_id.commercial_partner_id == vendor and vendor not in line_partners))
            if bad:
                raise UserError(_(
                    'บิล %s ของ %s ต้องระบุ Partner (ผู้ออกใบกำกับภาษีจริง) ทุกบรรทัดในแท็บ Tax Invoice\n'
                    'ตอนนี้ยังว่างหรือยังเป็นชื่อ %s: %s'
                ) % (number, move.partner_id.display_name, vendor.display_name,
                     ', '.join(t.tax_invoice_number or '(ไม่มีเลข)' for t in bad)))

    def _npd_line_partners(self):
        """Partner รายบรรทัด เรียงตามลำดับบรรทัด ไม่ซ้ำ"""
        self.ensure_one()
        res = self.env['res.partner']
        for line in self.invoice_line_ids.sorted(lambda l: (l.sequence, l.id or 0)):
            if line.display_type not in ('line_section', 'line_note') and line.npd_line_partner_id and line.npd_line_partner_id not in res:
                res |= line.npd_line_partner_id
        return res

    def _npd_sync_tax_invoice_partner(self):
        """Partner ที่ใส่ในรายการจากใบแจ้งหนี้ วิ่งไปที่แท็บ Tax Invoice
        - Partner รายเดียว: ทุกบรรทัด Tax Invoice ใช้รายนั้น
        - หลายราย: Tax Invoice ที่ยังว่าง/ยังเป็นชื่อผู้ขาย/เป็นรายที่ไม่มีในบรรทัดแล้ว ได้ Partner ที่ยังไม่ถูกใช้ตามลำดับบรรทัด
        Tax Invoice ที่ระบุเป็น Partner ของบรรทัดอยู่แล้ว ไม่แตะ"""
        for move in self:
            if move.move_type not in BILL_TYPES or move.state != 'draft' or 'tax_invoice_ids' not in move._fields:
                continue
            partners = move._npd_line_partners()
            if not partners:
                # ยังไม่ระบุ Partner รายบรรทัด: Tax Invoice ต้องว่าง ไม่ใช้ชื่อผู้ขาย (ธนาคาร) แทน
                if move.npd_require_line_partner:
                    vendor = move.partner_id.commercial_partner_id
                    for taxinv in move.tax_invoice_ids:
                        if taxinv.partner_id and taxinv.partner_id.commercial_partner_id == vendor:
                            taxinv.partner_id = False
                continue
            taxinvs = move.tax_invoice_ids
            keep = taxinvs.filtered(lambda t: t.partner_id in partners)
            free = [p for p in partners if p not in keep.mapped('partner_id')] or [partners[-1]]
            for i, taxinv in enumerate(taxinvs - keep):
                taxinv.partner_id = free[min(i, len(free) - 1)]

    @api.onchange('invoice_line_ids')
    def _onchange_npd_line_partner_to_tax_invoice(self):
        self._npd_sync_tax_invoice_partner()

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._npd_sync_tax_invoice_partner()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if 'invoice_line_ids' in vals or 'line_ids' in vals:
            self._npd_sync_tax_invoice_partner()
        return res

    def action_post(self):
        self._npd_sync_tax_invoice_partner()
        self._npd_check_line_partner()
        return super().action_post()

    def _npd_apply_line_partner_to_journal(self):
        """ลงบันทึกแล้ว: Partner รายบรรทัด → partner_id ของบรรทัดค่าใช้จ่าย ให้บัญชีแยกประเภทกรองตาม Partner จริงได้
        (o14 AP-0930260007 Steeltech ไม่เจอใน General Ledger, 23 ต.ค. 2569) บรรทัดเจ้าหนี้ยังเป็นผู้ขาย"""
        for move in self.filtered(lambda m: m.state == 'posted' and m.move_type in BILL_TYPES):
            for line in move.invoice_line_ids:
                if line.display_type == 'product' and line.npd_line_partner_id \
                        and line.partner_id != line.npd_line_partner_id:
                    line.with_context(check_move_validity=False).write({'partner_id': line.npd_line_partner_id.id})

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._npd_apply_line_partner_to_journal()
        return posted


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    npd_line_partner_id = fields.Many2one(
        'res.partner', string='Partner', index=True,
        help='ผู้ขาย/ผู้ออกใบกำกับภาษีที่แท้จริงของบรรทัดนี้ (เช่น ปั๊มน้ำมันในบิลบัตรเติมน้ำมัน) '
             'ช่องแยกจากผู้ขายของบิล ไม่กระทบเจ้าหนี้')
