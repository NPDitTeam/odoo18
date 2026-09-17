from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # o14: "( user.name )" เหนือ "ผู้วางบิล" = ผู้ที่กดพิมพ์
    jasper_ors_user_name = fields.Char(compute='_compute_jasper_ors_user_name')

    def _compute_jasper_ors_user_name(self):
        name = self.env.user.name or ''
        for move in self:
            move.jasper_ors_user_name = name


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # จัดรูปแบบตัวเลขใน Python ให้ช่องว่างได้เหมือน o14
    jasper_ors_name = fields.Char(compute='_compute_jasper_ors_line')
    jasper_ors_rate = fields.Char(compute='_compute_jasper_ors_line')
    jasper_ors_days = fields.Char(compute='_compute_jasper_ors_line')
    jasper_ors_amount = fields.Char(compute='_compute_jasper_ors_line')

    def _compute_jasper_ors_line(self):
        for line in self:
            line.jasper_ors_name = line.name or line.product_id.name or ''
            # คอลัมน์ตาม o14 ตรงตัว: ค่าเช่าต่อวัน = price_unit (แสดงเฉพาะบรรทัดที่มีจำนวนวันเช่า),
            # จำนวนวัน = pfb_quantity, จำนวนเงิน = ราคาต่อหน่วยถอด VAT (price_unit_no_vat ของ o14)
            line.jasper_ors_rate = '{:,.2f}'.format(line.price_unit or 0.0) if line.pfb_date_of_rent else ''
            line.jasper_ors_days = '{:,.2f}'.format(line.pfb_quantity or 0.0)
            line.jasper_ors_amount = '{:,.2f}'.format(line.jasper_abs_price_unit or 0.0)
