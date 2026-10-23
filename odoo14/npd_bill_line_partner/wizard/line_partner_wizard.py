# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NpdBillLinePartnerWizard(models.TransientModel):
    _name = 'npd.bill.line.partner.wizard'
    _description = 'ระบุ Partner รายบรรทัด (บิลที่ลงบันทึกแล้ว)'

    move_id = fields.Many2one('account.move', required=True, readonly=True)
    vendor_id = fields.Many2one(related='move_id.partner_id', string='ผู้ขาย')
    line_ids = fields.One2many('npd.bill.line.partner.wizard.line', 'wizard_id', string='รายการจากใบแจ้งหนี้')
    tax_ids = fields.One2many('npd.bill.line.partner.wizard.tax', 'wizard_id', string='Tax Invoice')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move = self.env['account.move'].browse(self.env.context.get('active_id'))
        if not move:
            return res
        res['move_id'] = move.id
        res['line_ids'] = [(0, 0, {
            'move_line_id': l.id, 'name': l.name, 'product_id': l.product_id.id,
            'price_total': l.price_total, 'partner_id': l.npd_line_partner_id.id,
        }) for l in move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))]
        if 'tax_invoice_ids' in move._fields:
            res['tax_ids'] = [(0, 0, {
                'tax_invoice_id': t.id, 'tax_invoice_number': t.tax_invoice_number,
                'tax_invoice_date': t.tax_invoice_date, 'tax_base_amount': t.tax_base_amount,
                'balance': t.balance, 'partner_id': t.partner_id.id,
            }) for t in move.tax_invoice_ids.sorted('id')]
        return res

    @api.onchange('line_ids')
    def _onchange_line_partner(self):
        """Partner ที่เลือกในรายการ วิ่งไปที่ Tax Invoice (กติกาเดียวกับบิลฉบับร่าง)"""
        partners = self.env['res.partner']
        for line in self.line_ids:
            if line.partner_id and line.partner_id not in partners:
                partners |= line.partner_id
        if not partners:
            return
        keep = self.tax_ids.filtered(lambda t: t.partner_id in partners)
        free = [p for p in partners if p not in keep.mapped('partner_id')] or [partners[-1]]
        for i, tax in enumerate(self.tax_ids - keep):
            tax.partner_id = free[min(i, len(free) - 1)]

    def action_apply(self):
        self.ensure_one()
        move = self.move_id
        if move.npd_require_line_partner:
            missing = self.line_ids.filtered(lambda l: not l.partner_id)
            if missing:
                raise UserError(_('กรุณาระบุ Partner ทุกบรรทัด'))
            vendor = move.partner_id.commercial_partner_id
            line_partners = self.line_ids.mapped('partner_id.commercial_partner_id')
            if self.tax_ids.filtered(lambda t: not t.partner_id or (
                    t.partner_id.commercial_partner_id == vendor and vendor not in line_partners)):
                raise UserError(_('กรุณาระบุ Partner (ผู้ออกใบกำกับภาษีจริง) ทุกแถวใน Tax Invoice'))
        changes = []
        for line in self.line_ids:
            if line.move_line_id.npd_line_partner_id != line.partner_id:
                changes.append('%s: %s → %s' % (line.name or line.product_id.display_name,
                                                  line.move_line_id.npd_line_partner_id.display_name or '-',
                                                  line.partner_id.display_name or '-'))
                line.move_line_id.npd_line_partner_id = line.partner_id
        for tax in self.tax_ids:
            if tax.tax_invoice_id.partner_id != tax.partner_id:
                changes.append('Tax Invoice %s: %s → %s' % (tax.tax_invoice_number or '',
                                                           tax.tax_invoice_id.partner_id.display_name or '-',
                                                           tax.partner_id.display_name or '-'))
                tax.tax_invoice_id.partner_id = tax.partner_id
        move._npd_apply_line_partner_to_journal()
        if changes:
            move.message_post(body=Markup('ระบุ Partner รายบรรทัด (หลังลงบันทึก):<br/>') + Markup('<br/>').join(escape(c) for c in changes))
        return {'type': 'ir.actions.act_window_close'}


class NpdBillLinePartnerWizardLine(models.TransientModel):
    _name = 'npd.bill.line.partner.wizard.line'
    _description = 'บรรทัดบิล'

    wizard_id = fields.Many2one('npd.bill.line.partner.wizard', ondelete='cascade')
    move_line_id = fields.Many2one('account.move.line', readonly=True)
    product_id = fields.Many2one('product.product', string='สินค้า', readonly=True)
    name = fields.Char('คำอธิบาย', readonly=True)
    price_total = fields.Float('ยอดรวม', digits=(16, 2), readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner')


class NpdBillLinePartnerWizardTax(models.TransientModel):
    _name = 'npd.bill.line.partner.wizard.tax'
    _description = 'แถว Tax Invoice'

    wizard_id = fields.Many2one('npd.bill.line.partner.wizard', ondelete='cascade')
    tax_invoice_id = fields.Many2one('account.move.tax.invoice', readonly=True)
    tax_invoice_number = fields.Char('Tax Invoice Number', readonly=True)
    tax_invoice_date = fields.Date('Tax Invoice Date', readonly=True)
    tax_base_amount = fields.Float('Tax Base', digits=(16, 2), readonly=True)
    balance = fields.Float('Tax Amount', digits=(16, 2), readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner')
