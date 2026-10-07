import re

from odoo import _, api, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.constrains('vat')
    def _check_vat_digits(self):
        """เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลขล้วน 13 หลักขึ้นไป

        เช็คเฉพาะรายชื่อหลัก (ผู้ติดต่อย่อยรับค่ามาจากบริษัทแม่ แก้เองไม่ได้)
        ทำงานเฉพาะตอนสร้าง/แก้ช่อง vat — รายชื่อเก่าที่ไม่แตะช่องนี้ไม่โดน
        """
        for rec in self:
            if rec.vat and not rec.parent_id and not re.fullmatch(r'[0-9]{13,}', rec.vat):
                raise ValidationError(_(
                    "เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลขเท่านั้น และต้องมี 13 หลักขึ้นไป\n"
                    "(ห้ามมีขีด ช่องว่าง หรือตัวอักษร)\n"
                    "หากยังไม่ได้ข้อมูลจากลูกค้าให้ใส่ 0000000000000\n\nที่กรอกมา: %s"
                ) % rec.vat)

    @api.model
    def _npd_clean_vals(self, vals):
        # ตัดช่องว่างหน้า-หลังเลขผู้เสียภาษีที่ติดมาตอนก็อปวาง
        if isinstance(vals.get('vat'), str):
            vals['vat'] = vals['vat'].strip()
        for field in ('phone', 'mobile'):
            if field in vals and field in self._fields:
                vals[field] = self._sanitize_phone_number(vals[field])
        return vals

    @api.model
    def _sanitize_phone_number(self, number):
        """ลบ +66 และเครื่องหมายพิเศษ แล้วนำหน้าด้วย 0 เช่น +66 88-772-9782 → 0887729782"""
        if number:
            number = re.sub(r'\D', '', number)
            if number.startswith('66'):
                number = '0' + number[2:]
            elif not number.startswith('0'):
                number = '0' + number
        return number

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._npd_clean_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._npd_clean_vals(vals)
        return super().write(vals)
