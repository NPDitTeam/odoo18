# -*- coding: utf-8 -*-
"""หนังสือรับรองหัก ณ ที่จ่าย — เลขออกตามวันที่ในใบ + แยกบริษัท และห้ามแก้วันที่หลังออกเลข

o18 (OCA l10n_th_account_tax) ออกเลขในช่อง number ตอน action_done ด้วย next_by_code
แบบไม่ส่งวันที่และไม่ผูกบริษัท เลขจึงออกตาม "วันที่กดยืนยัน" และรันรวมทุกบริษัท
ที่นี่ออกเลขให้ก่อน (ตามวันที่ในใบ + บริษัทของใบ) ส่วน super จะข้ามเพราะ number ไม่ใช่ "/" แล้ว
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

UNNUMBERED = (False, '', '/')


class WithholdingTaxCert(models.Model):
    _inherit = 'withholding.tax.cert'

    @api.model
    def _npd_next_wt_number(self, date, company):
        """ขอเลขถัดไปตามวันที่ของใบ (ไม่ใช่วันที่กดทำรายการ) และตามบริษัทของใบ"""
        return self.env['ir.sequence'].with_company(company).next_by_code(
            'withholding.tax.cert', sequence_date=date) or '/'

    def action_done(self):
        for rec in self:
            if rec.number in UNNUMBERED:
                rec.number = self._npd_next_wt_number(
                    rec.date or fields.Date.context_today(rec), rec.company_id or self.env.company)
        return super().action_done()

    def write(self, vals):
        if 'date' in vals:
            new_date = fields.Date.to_date(vals['date'])
            self.filtered(lambda c: c.date != new_date)._check_wt_cert_date_locked()
        return super().write(vals)

    def _check_wt_cert_date_locked(self):
        """ห้ามเปลี่ยนวันที่ของใบที่ออกเลขแล้ว (ไม่นับใบที่ยกเลิก)

        เรียกกับใบที่วันที่กำลังจะเปลี่ยน ทั้งจากหน้าใบเอง และจากปุ่ม "สร้าง WHT อัตโนมัติ"
        """
        locked = self.filtered(lambda c: c.number not in UNNUMBERED and c.state != 'cancel')
        if not locked:
            return
        msgs = [_('ใบหัก ณ ที่จ่ายต่อไปนี้ออกเลขตามวันที่ไปแล้ว เปลี่ยนวันที่ไม่ได้:')]
        for cert in locked:
            msgs.append('  • %s (วันที่ %s, %s)' % (
                cert.number,
                cert.date and cert.date.strftime('%d/%m/%Y') or '-',
                cert.partner_id.display_name or '-',
            ))
        msgs.append('')
        msgs.append(_(
            'ถ้าวันที่ผิด ให้เปิดใบหัก ณ ที่จ่ายนั้น กด Set to Draft แล้วกด Cancel '
            'จากนั้นสร้างใบใหม่ (ถ้ามาจาก Advance Clear / ใบสำคัญ ให้กดปุ่ม '
            '"สร้าง WHT อัตโนมัติ" อีกครั้ง) ระบบจะออกเลขใหม่ตามวันที่ที่ถูกต้อง'))
        raise UserError('\n'.join(msgs))
