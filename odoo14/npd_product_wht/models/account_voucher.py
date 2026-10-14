# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountVoucherLine(models.Model):
    _name = 'account.voucher.line'
    _inherit = ['account.voucher.line', 'npd.wht.line.mixin']

    def _npd_doc_company(self):
        return self.voucher_id.company_id or self.env.company

    @api.onchange('product_id')
    def _onchange_product_wht(self):
        super()._onchange_product_wht()
        self._calc_wht_total()

    @api.onchange('wht_category_id', 'price_unit', 'quantity', 'tax_ids', 'is_deduct_vat')
    def _onchange_wht_total(self):
        self._calc_wht_total()

    def _calc_wht_total(self):
        """wht_total: โลจิสติกส์ใช้ฐานจาก _get_wht_base_amount (รองรับหัก VAT), บริษัทอื่นใช้ยอดก่อน VAT"""
        for line in self:
            cat = line.wht_category_id
            if not cat or cat.wht_rate == '0':
                line.wht_total = 0.0
                continue
            from .wht_common import is_logistics
            if is_logistics(line._npd_doc_company()):
                base = line._get_wht_base_amount()
            elif line.tax_ids:
                base = line.tax_ids.compute_all(
                    line.price_unit, line.voucher_id.currency_id, line.quantity,
                    product=line.product_id)['total_excluded']
            else:
                base = line.price_unit * line.quantity
            line.wht_total = round(base * cat.wht_rate_float / 100.0, 2)


class AccountVoucher(models.Model):
    _name = 'account.voucher'
    _inherit = ['account.voucher', 'npd.wht.doc.mixin']

    # ยอดที่จ่าย/รับจริง = รวม - หัก ณ ที่จ่าย (ตรงกับบรรทัดธนาคารในสมุดรายวัน)
    net_payment_amount = fields.Monetary(
        string='ยอดจ่ายสุทธิ', currency_field='currency_id', compute='_compute_net_payment_amount',
        help='ยอดที่จ่าย/รับจริงหลังหักภาษี ณ ที่จ่ายแล้ว (รวม - Withholding Tax)')

    @api.model
    def _npd_wht_link_field(self):
        return 'voucher_id'

    @api.depends('amount', 'wht_amount')
    def _compute_net_payment_amount(self):
        for voucher in self:
            voucher.net_payment_amount = (voucher.amount or 0.0) - (voucher.wht_amount or 0.0)

    def _check_wht_cert_before_validate(self):
        """ก่อนยืนยัน (เฉพาะ check_type_show_selection = 'false' ตรงกับเงื่อนไขปุ่ม):
        บรรทัดที่ต้องหักต้องมีคู่ค้า และต้องมีใบหัก ณ ที่จ่ายของอัตรานั้นแล้ว"""
        self.ensure_one()
        if self.check_type_show_selection != 'false':
            return
        needs = {}
        for line in self.line_ids:
            if line.wht_status == 'eligible':
                needs.setdefault(line.wht_category_id.wht_rate, []).append(line)
        if not needs:
            return
        fmt = lambda l: '%s (ยอด %s บาท)' % (l.product_id.name or l.name or '-',
                                            '{:,.2f}'.format(l._get_wht_base_amount()))
        if not self.partner_id:
            self._npd_raise_missing(_('⚠ รายการใช้ WHT ได้ แต่ยังไม่ได้เลือกคู่ค้า:'),
                                    [fmt(l) for ls in needs.values() for l in ls], None)
        existing_rates = set()
        for cert in self.wt_cert_ids.filtered(lambda c: c.state != 'cancel'):
            if cert.wht_line[:1]:
                existing_rates.add('%g' % cert.wht_line[:1].wht_percent)
        missing = [l for rate, ls in needs.items() if rate not in existing_rates for l in ls]
        if missing:
            self._npd_raise_missing(_('⚠ รายการที่ใช้ WHT ได้ แต่ยังไม่สร้าง Withholding Tax:'),
                                    [fmt(l) for l in missing],
                                    _('กรุณากดปุ่ม "สร้าง WHT อัตโนมัติ" ก่อนตรวจสอบ'))

    def proforma_voucher(self):
        self._detach_cancelled_wht_certs()
        for rec in self:
            rec._check_wht_cert_before_validate()
        return super().proforma_voucher()

    def action_auto_create_wht_cert(self):
        """สร้าง/อัปเดตใบหัก ณ ที่จ่ายจากบรรทัด (ใบสำคัญ 1 ใบ = 1 คู่ค้า แยกใบตามอัตรา)"""
        self._detach_cancelled_wht_certs()
        Cert = self.env['withholding.tax.cert']
        for rec in self:
            rec.line_ids._calc_wht_total()
            doc_date = rec.date or fields.Date.today()
            groups = {}  # rate -> (wht_cat, base)
            for line in rec.line_ids:
                cat = line.wht_category_id
                if not cat or cat.wht_rate == '0' or not line.product_id:
                    continue
                cur = groups.get(cat.wht_rate)
                groups[cat.wht_rate] = (cur[0] if cur else cat, (cur[1] if cur else 0.0) + line._get_wht_base_amount())

            existing = {}
            for cert in rec.wt_cert_ids.sorted('id'):
                rate = ('%g' % cert.wht_line[:1].wht_percent) if cert.wht_line[:1] else '0'
                existing.setdefault(rate, Cert)
                existing[rate] |= cert

            # เลขฝังวันที่ ถ้าวันที่ใบสำคัญเปลี่ยน ห้ามแก้วันที่ใบเดิม ให้ยกเลิกแล้วออกใหม่
            if groups:
                rec.wt_cert_ids.filtered(lambda c: c.date != doc_date)._check_wt_cert_date_locked()

            recyclable = Cert
            for rate in set(existing) - set(groups):
                recyclable |= existing[rate]
            recyclable = recyclable.sorted('id')
            it = iter(recyclable)
            for rate in [r for r in groups if r not in existing]:
                cert = next(it, None)
                if cert is None:
                    break
                existing[rate] = cert
            used = {c.id for rate in groups if rate in existing for c in existing[rate][:1]}
            rec._remove_wht_cert_ids([c.id for c in recyclable if c.id not in used])
            if not groups:
                continue

            partner = rec.partner_id
            new_vals = []
            for rate, (cat, base) in groups.items():
                line_vals = rec._npd_cert_line_vals([(cat, base)])
                if rate in existing:
                    certs = existing[rate]
                    rec._remove_wht_cert_ids(certs[1:].ids)
                    rec._npd_rewrite_cert(certs[0], partner, doc_date, line_vals)
                else:
                    new_vals.append((0, 0, rec._npd_new_cert_vals(partner, doc_date, line_vals)))
            if new_vals:
                rec.write({'wt_cert_ids': new_vals})
            rec._npd_finish_certs()
        return True
