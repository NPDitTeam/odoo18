# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AdvanceClearLine(models.Model):
    _name = 'advance.clear.line'
    _inherit = ['advance.clear.line', 'npd.wht.line.mixin']

    wht_total = fields.Float(string='Withholding Tax', compute='_compute_wht_total',
                             store=True, digits=(16, 2))

    def _npd_doc_company(self):
        return self.advance_clear_id.company_id or self.env.company

    @api.depends('wht_category_id', 'price_unit', 'quantity', 'tax_ids', 'is_deduct_vat',
                 'advance_clear_id.company_id')
    def _compute_wht_total(self):
        for line in self:
            if line.wht_category_id and line.wht_category_id.wht_rate != '0':
                rate = line.wht_category_id.wht_rate_float
                line.wht_total = round(line._get_wht_base_amount() * rate / 100.0, 2)
            else:
                line.wht_total = 0.0


class AccountAdvanceClear(models.Model):
    _name = 'account.advance.clear'
    _inherit = ['account.advance.clear', 'npd.wht.doc.mixin']

    @api.model
    def _npd_wht_link_field(self):
        return 'advance_clear_id'

    def _check_wht_cert_before_post(self):
        """ก่อนลงรายการ: บรรทัดที่ต้องหัก ณ ที่จ่ายต้องมีคู่ค้า และต้องมีใบที่ตรง (คู่ค้า, วันที่, อัตรา)"""
        self.ensure_one()
        doc_date = self.doc_date or fields.Date.today()
        needs_cert, no_partner = {}, []
        for line in self.clear_ids:
            if line.wht_status != 'eligible':
                continue
            if not line.partner_id:
                no_partner.append(line)
                continue
            key = (line.partner_id.id, line.invoice_date or doc_date, line.wht_category_id.wht_rate_float)
            needs_cert.setdefault(key, []).append(line)

        existing = set()
        for cert in self.wt_cert_ids.filtered(lambda c: c.state != 'cancel'):
            for cl in cert.wht_line:
                existing.add((cert.partner_id.id, cert.date, cl.wht_percent))
        missing = [l for key, lines in needs_cert.items() if key not in existing for l in lines]
        if not missing and not no_partner:
            return

        msgs = []
        if no_partner:
            msgs.append(_('⚠ รายการที่ใช้ WHT ได้ แต่ยังไม่ได้เลือกคู่ค้า:'))
            msgs += ['  • %s (ยอด %s บาท)' % (l.product_id.name or l.name or '-',
                                              '{:,.2f}'.format(l._get_wht_base_amount())) for l in no_partner]
        if missing:
            if msgs:
                msgs.append('')
            msgs.append(_('⚠ รายการที่ใช้ WHT ได้ แต่ยังไม่สร้าง Withholding Tax:'))
            msgs += ['  • %s | %s (ยอด %s บาท)' % (l.partner_id.name or '-', l.product_id.name or l.name or '-',
                                                   '{:,.2f}'.format(l._get_wht_base_amount())) for l in missing]
            msgs += ['', _('กรุณากดปุ่ม "สร้าง WHT อัตโนมัติ" ก่อน Post')]
        from odoo.exceptions import UserError
        raise UserError('\n'.join(msgs))

    def confirm(self):
        self._detach_cancelled_wht_certs()
        for rec in self:
            rec._check_wht_cert_before_post()
        return super().confirm()

    def action_auto_create_wht_cert(self):
        """สร้าง/อัปเดตใบหัก ณ ที่จ่ายจากบรรทัด (แยกใบต่อ คู่ค้า + วันที่ใบกำกับ)

        ใบเดิมของ (คู่ค้า, วันที่) เดิม → อัปเดต คงเลขเดิม
        ใบที่ (คู่ค้า, วันที่) หายไป → นำมาใช้กับ key ใหม่ที่วันที่เดียวกัน (เลขฝังวันที่)
        เหลือจากนั้น → ใบที่มีเลขแล้วยกเลิก / ใบที่ยังไม่มีเลขลบ
        """
        self._detach_cancelled_wht_certs()
        Cert = self.env['withholding.tax.cert']
        for rec in self:
            doc_date = rec.doc_date or fields.Date.today()
            groups = {}  # (partner, date) -> {wht_cat: base}
            for line in rec.clear_ids:
                cat = line.wht_category_id
                if not cat or cat.wht_rate == '0' or not line.product_id or not line.partner_id:
                    continue
                gkey = (line.partner_id.id, line.invoice_date or doc_date)
                bucket = groups.setdefault(gkey, {})
                bucket[cat] = bucket.get(cat, 0.0) + line._get_wht_base_amount()
            if not groups:
                continue

            existing = {}
            for cert in rec.wt_cert_ids.sorted('id'):
                existing.setdefault((cert.partner_id.id, cert.date), Cert)
                existing[(cert.partner_id.id, cert.date)] |= cert

            recyclable = Cert
            for ckey in set(existing) - set(groups):
                recyclable |= existing[ckey]
            recyclable = recyclable.sorted('id')
            new_keys = [k for k in groups if k not in existing]
            used = set()
            for nkey in new_keys:
                cert = next((c for c in recyclable if c.id not in used
                             and (c.date == nkey[1] or c.number in (False, '', '/'))), None)
                if cert:
                    existing[nkey] = cert
                    used.add(cert.id)
            leftover = recyclable.filtered(lambda c: c.id not in used)
            if any(k not in existing for k in new_keys):
                leftover._check_wt_cert_date_locked()
            rec._remove_wht_cert_ids(leftover.ids)

            new_vals = []
            for gkey, cats in groups.items():
                partner = self.env['res.partner'].browse(gkey[0])
                line_vals = rec._npd_cert_line_vals(list(cats.items()))
                if gkey in existing:
                    certs = existing[gkey]
                    rec._remove_wht_cert_ids(certs[1:].ids)
                    rec._npd_rewrite_cert(certs[0], partner, gkey[1], line_vals)
                else:
                    new_vals.append((0, 0, rec._npd_new_cert_vals(partner, gkey[1], line_vals)))
            if new_vals:
                rec.write({'wt_cert_ids': new_vals})
            rec._npd_finish_certs()
        return True
