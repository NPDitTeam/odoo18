# -*- coding: utf-8 -*-
"""ส่วนกลางของ Advance Clear / ใบสำคัญ: ช่อง WHT ต่อบรรทัด และการสร้างใบหัก ณ ที่จ่าย"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

NPD_LOGISTICS_REGISTRY = '5'  # บริษัท เอ็นพีดี โลจิสติกส์ จำกัด (o14 = ฐาน NPD_Logistics_New)


def is_logistics(company):
    return (company.company_registry or '').strip() == NPD_LOGISTICS_REGISTRY


class WhtLineMixin(models.AbstractModel):
    """ช่อง WHT ต่อบรรทัดเอกสาร (บรรทัด Advance Clear / บรรทัดใบสำคัญ)"""
    _name = 'npd.wht.line.mixin'
    _description = 'ช่องหัก ณ ที่จ่ายต่อบรรทัด'

    wht_category_id = fields.Many2one('wht.category', string='หมวดหมู่ WHT',
                                      help='หมวดหมู่ภาษีหัก ณ ที่จ่าย')
    wht_rate_display = fields.Char(string='อัตรา WHT', compute='_compute_wht_rate_display')
    is_deduct_vat = fields.Boolean(
        string='หัก VAT', default=False,
        help='ถ้าติ๊ก ระบบจะถอด VAT 7% จาก Unit Price ก่อนส่งไปสร้าง WHT '
             '(เฉพาะบริษัท เอ็นพีดี โลจิสติกส์)')
    wht_status = fields.Selection([
        ('eligible', 'ใช้ WHT ได้'),
        ('no_category', 'ยังไม่เลือกหมวดหมู่ WHT'),
    ], string='สถานะ WHT', compute='_compute_wht_status')

    def _npd_doc_company(self):
        raise NotImplementedError

    @api.depends('wht_category_id')
    def _compute_wht_status(self):
        for line in self:
            if not line.wht_category_id or line.wht_category_id.wht_rate == '0':
                line.wht_status = 'no_category'
            else:
                line.wht_status = 'eligible'

    @api.depends('wht_category_id')
    def _compute_wht_rate_display(self):
        for line in self:
            line.wht_rate_display = ('%s%%' % line.wht_category_id.wht_rate) if line.wht_category_id else ''

    def _get_wht_base_amount(self):
        """ยอดที่ใช้เป็นฐาน WHT

        - บริษัทโลจิสติกส์ + ติ๊กหัก VAT → round(price_unit / 1.07, 2)
        - บริษัทโลจิสติกส์ ไม่ติ๊ก → price_unit
        - บริษัทอื่น → price_subtotal (ยอดก่อน VAT)
        """
        self.ensure_one()
        if is_logistics(self._npd_doc_company()):
            if self.is_deduct_vat:
                return round(self.price_unit / 1.07, 2)
            return self.price_unit
        return self.price_subtotal

    @api.onchange('product_id')
    def _onchange_product_wht(self):
        """เลือกสินค้าแล้วดึงหมวดหมู่ WHT จากสินค้า"""
        if self.product_id and self.product_id.product_tmpl_id.wht_category_id:
            self.wht_category_id = self.product_id.product_tmpl_id.wht_category_id.id


class WhtDocMixin(models.AbstractModel):
    """การสร้าง/ผูกใบหัก ณ ที่จ่ายของเอกสาร (Advance Clear / ใบสำคัญ)"""
    _name = 'npd.wht.doc.mixin'
    _description = 'สร้างใบหัก ณ ที่จ่ายจากเอกสาร'

    npd_is_logistics = fields.Boolean(compute='_compute_npd_is_logistics')

    @api.depends('company_id')
    def _compute_npd_is_logistics(self):
        for rec in self:
            rec.npd_is_logistics = is_logistics(rec.company_id)

    def _remove_wht_cert_ids(self, cert_ids):
        """เอาใบหัก ณ ที่จ่ายที่ไม่ใช้แล้วออกจากเอกสาร

        o14 ลบทิ้งด้วย SQL ทุกใบ ใบที่ออกเลขไปแล้วเลขจะหาย (เลขรันขาด)
        ที่นี่: ใบที่มีเลขแล้ว → ยกเลิกแล้วปลดออก (เลขยังอยู่ในระบบ) / ใบที่ยังไม่มีเลข → ลบได้
        """
        if not cert_ids:
            return
        certs = self.env['withholding.tax.cert'].browse(cert_ids).exists()
        numbered = certs.filtered(lambda c: c.number not in (False, '', '/'))
        if numbered:
            todo = numbered.filtered(lambda c: c.state != 'cancel')
            if todo:
                todo.action_cancel()
            numbered.write({self._npd_wht_link_field(): False})
        drafts = certs - numbered
        if drafts:
            self.env.cr.execute('DELETE FROM withholding_tax_cert_line WHERE cert_id IN %s', (tuple(drafts.ids),))
            self.env.cr.execute('DELETE FROM withholding_tax_cert WHERE id IN %s', (tuple(drafts.ids),))
        self.env.invalidate_all()

    def _detach_cancelled_wht_certs(self):
        """ปลดใบที่ยกเลิกแล้วออกจากเอกสาร (เก็บไว้เป็นประวัติ แต่ไม่นับยอดซ้ำ)"""
        link = self._npd_wht_link_field()
        for rec in self:
            cancelled = rec.wt_cert_ids.filtered(lambda c: c.state == 'cancel')
            if cancelled:
                cancelled.write({link: False})

    @api.model
    def _npd_wht_link_field(self):
        raise NotImplementedError

    def _npd_wht_account(self, income_tax_form):
        company = self.company_id
        if income_tax_form == 'pnd53':
            return company.account_pnd53_withholding_tax_id.id
        return company.account_pnd3_withholding_tax_id.id

    @staticmethod
    def _npd_income_tax_form(partner):
        return 'pnd53' if partner.is_company else 'pnd3'

    def _npd_cert_line_vals(self, entries):
        vals = []
        for wht_cat, base in entries:
            rate = wht_cat.wht_rate_float
            vals.append({
                'wht_cert_income_type': '6',
                'wht_cert_income_desc': wht_cat.income_description or wht_cat.name,
                'base': base,
                'wht_percent': rate,
                'amount': base * rate / 100.0,
            })
        return vals

    def _npd_rewrite_cert(self, cert, partner, cert_date, line_vals):
        """อัปเดตใบเดิม คงเลขเดิม (ไม่ขอเลขใหม่ ไม่เกิดเลขข้าม)"""
        form = self._npd_income_tax_form(partner)
        state = cert.state
        self.env.cr.execute("UPDATE withholding_tax_cert SET state = 'draft' WHERE id = %s", (cert.id,))
        self.env.cr.execute('DELETE FROM withholding_tax_cert_line WHERE cert_id = %s', (cert.id,))
        self.env.invalidate_all()
        vals = {
            'partner_id': partner.id,
            'income_tax_form': form,
            'tax_payer': 'withholding',
            'wht_line': [(0, 0, v) for v in line_vals],
        }
        if cert.date != cert_date:
            vals['date'] = cert_date  # ใบที่มีเลขแล้วจะถูกกันใน write (ต้องยกเลิกแล้วออกใหม่)
        account_id = self._npd_wht_account(form)
        if account_id:
            vals['account_id'] = account_id
        cert.write(vals)
        if state == 'done' or cert.number not in (False, '', '/'):
            self.env.cr.execute("UPDATE withholding_tax_cert SET state = 'done' WHERE id = %s", (cert.id,))
            self.env.invalidate_all()

    def _npd_new_cert_vals(self, partner, cert_date, line_vals):
        form = self._npd_income_tax_form(partner)
        vals = {
            'partner_id': partner.id,
            'income_tax_form': form,
            'date': cert_date,
            'tax_payer': 'withholding',
            'company_id': self.company_id.id,
            'wht_line': [(0, 0, v) for v in line_vals],
        }
        account_id = self._npd_wht_account(form)
        if account_id:
            vals['account_id'] = account_id
        return vals

    def _npd_finish_certs(self):
        """ใบใหม่ที่ยังเป็นร่าง → action_done (ออกเลขตามวันที่ในใบ + บริษัท)"""
        drafts = self.wt_cert_ids.filtered(lambda c: c.state == 'draft')
        if drafts:
            drafts.action_done()

    def _npd_raise_missing(self, header, rows, footer):
        msgs = [header] + ['  • %s' % r for r in rows]
        if footer:
            msgs += ['', footer]
        raise UserError('\n'.join(msgs))

    def action_open_wt_cert_link_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('เลือกใบหัก ณ ที่จ่ายที่มีอยู่'),
            'res_model': 'npd.wt.cert.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_res_model': self._name, 'default_res_id': self.id},
        }
