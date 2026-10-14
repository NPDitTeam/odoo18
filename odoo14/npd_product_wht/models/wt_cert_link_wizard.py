# -*- coding: utf-8 -*-
"""เลือกใบหัก ณ ที่จ่ายที่มีอยู่แล้วมาผูกกับ Advance Clear / ใบสำคัญ

แถบ Withholding Tax เป็น one2many กด "เพิ่มรายการ" ได้แค่สร้างใบใหม่
ใบที่สร้างจากเมนูหัก ณ ที่จ่าย (หรือใบที่ปลดออกมา) จึงเอากลับมาผูกไม่ได้
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# ฟิลด์บนใบหัก ณ ที่จ่ายที่บอกว่าใบนี้ผูกกับเอกสารต้นทางอยู่แล้ว
SOURCE_FIELDS = ('advance_clear_id', 'voucher_id', 'petty_expense_id', 'payment_id', 'move_id')
LINK_FIELD = {
    'account.advance.clear': 'advance_clear_id',
    'account.voucher': 'voucher_id',
}


class NpdWtCertLinkWizard(models.TransientModel):
    _name = 'npd.wt.cert.link.wizard'
    _description = 'เลือกใบหัก ณ ที่จ่ายที่มีอยู่'

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    available_cert_ids = fields.Many2many('withholding.tax.cert', compute='_compute_available_cert_ids')
    cert_ids = fields.Many2many('withholding.tax.cert', string='ใบหัก ณ ที่จ่าย')

    def _get_document(self):
        self.ensure_one()
        if self.res_model not in LINK_FIELD:
            raise UserError(_('ไม่รองรับเอกสารประเภท %s') % self.res_model)
        return self.env[self.res_model].browse(self.res_id).exists()

    @api.model
    def _candidate_domain(self, doc):
        Cert = self.env['withholding.tax.cert']
        domain = [('state', '!=', 'cancel')]
        for fname in SOURCE_FIELDS:
            if fname in Cert._fields:
                domain.append((fname, '=', False))
        if doc.company_id:
            domain.append(('company_id', '=', doc.company_id.id))
        partners = doc.clear_ids.mapped('partner_id') if doc._name == 'account.advance.clear' else doc.partner_id
        if partners:
            domain.append(('partner_id', 'child_of', partners.mapped('commercial_partner_id').ids))
        return domain

    @api.depends('res_model', 'res_id')
    def _compute_available_cert_ids(self):
        Cert = self.env['withholding.tax.cert']
        for wiz in self:
            doc = wiz._get_document() if wiz.res_model else False
            wiz.available_cert_ids = Cert.search(wiz._candidate_domain(doc)) if doc else Cert

    def action_link(self):
        self.ensure_one()
        doc = self._get_document()
        if not doc:
            raise UserError(_('ไม่พบเอกสาร'))
        if not self.cert_ids:
            raise UserError(_('กรุณาเลือกใบหัก ณ ที่จ่ายอย่างน้อย 1 ใบ'))
        # เช็กซ้ำฝั่งเซิร์ฟเวอร์ เผื่อมีคนผูกใบเดียวกันไปก่อนระหว่างเปิดหน้าต่างนี้
        allowed = self.env['withholding.tax.cert'].search(
            self._candidate_domain(doc) + [('id', 'in', self.cert_ids.ids)])
        rejected = self.cert_ids - allowed
        if rejected:
            raise UserError(_('ใบต่อไปนี้ผูกกับเอกสารอื่นหรือถูกยกเลิกไปแล้ว:\n%s')
                            % '\n'.join('  • %s' % (c.number or c.id) for c in rejected))
        allowed.write({LINK_FIELD[doc._name]: doc.id})
        doc._detach_cancelled_wht_certs()
        return {'type': 'ir.actions.act_window_close'}
