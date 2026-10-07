# -*- coding: utf-8 -*-
import re

from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _npd_partner_missing_info(self):
        """คืนรายการข้อมูลลูกค้าที่ยังขาด (ว่าง = ครบ)"""
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        missing = []
        if not partner.street:
            missing.append(_("ที่อยู่"))
        if not partner.city:
            missing.append(_("เขต / อำเภอ"))
        if not partner.state_id:
            missing.append(_("จังหวัด"))
        if not partner.zip:
            missing.append(_("รหัสไปรษณีย์"))
        if not (partner.phone or partner.mobile):
            missing.append(_("โทรศัพท์ หรือ มือถือ"))
        if not partner.email:
            missing.append(_("อีเมล"))
        vat = (partner.vat or '').strip()
        if not re.fullmatch(r'[0-9]{13,}', vat):
            missing.append(_("เลขประจำตัวผู้เสียภาษี (ต้องเป็นตัวเลข 13 หลักขึ้นไป)"))
        elif not vat.strip('0'):
            missing.append(_("เลขประจำตัวผู้เสียภาษี (ยังเป็น %s ต้องใส่เลขจริงของลูกค้า)") % vat)
        return missing

    def action_convert_to_order(self):
        for order in self:
            missing = order._npd_partner_missing_info()
            if missing:
                raise UserError(_(
                    "ไม่สามารถ Convert to Order ได้ เพราะข้อมูลลูกค้า \"%s\" ยังไม่ครบ:\n\n- %s\n\n"
                    "กรุณาแก้ไขที่หน้ารายชื่อลูกค้าก่อน แล้วกด Convert to Order ใหม่"
                ) % (order.partner_id.commercial_partner_id.display_name, "\n- ".join(missing)))
        return super().action_convert_to_order()
