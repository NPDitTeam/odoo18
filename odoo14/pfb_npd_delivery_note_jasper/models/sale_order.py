# -*- coding: utf-8 -*-
from odoo import models, fields, api

# โมดูลนี้ depend pfb_npd_rent_invoice_jasper จึงใช้ฟิลด์ jasper_* ร่วมได้
# (jasper_active_company_*, jasper_baht_text_rental, jasper_total_weight,
#  jasper_contract_full, jasper_date_order_thai, jasper_line_* ฯลฯ)
# ที่นี่เพิ่มเฉพาะฟิลด์เฉพาะใบส่งมอบสินค้า


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # เลขที่ใบส่งมอบสินค้า (RDO-yymmdd + ลำดับ) สร้างเมื่อยืนยันใบขายประเภทเช่า
    # port จาก O14 pfb_npd_sale_form_delivery_note
    # ------------------------------------------------------------------
    delivery_note_no = fields.Char(
        string=u"เลขที่ใบส่งมอบสินค้า",
        copy=True,          # ซ้ำเอกสารใช้เลขเดิม ไม่รันใหม่
        readonly=True,
        help=u"เลขรันใบส่งมอบสินค้า (RDO-yymmdd+ลำดับ) สร้างอัตโนมัติเมื่อยืนยันใบขาย",
    )

    def _dn_is_rent_order(self, order):
        if "pfb_so_type" in order._fields:
            return order.pfb_so_type == "rent"
        return True

    def _dn_has_deposit_ref(self, order):
        if "deposit_ref" not in order._fields:
            return False
        return bool((order.deposit_ref or "").strip())

    def _ensure_delivery_note_no(self):
        seq_obj = self.env["ir.sequence"]
        for order in self:
            if order.delivery_note_no:
                continue
            number = seq_obj.next_by_code("npd.delivery.note")
            if number:
                order.delivery_note_no = number
        return True

    def _generate_delivery_note_no_if_needed(self):
        # เรียกซ้ำได้ปลอดภัย: มี guard delivery_note_no แล้ว
        for order in self:
            if not self._dn_is_rent_order(order):
                continue
            if order.delivery_note_no:
                continue
            if self._dn_has_deposit_ref(order):
                continue
            order._ensure_delivery_note_no()
        return True

    def action_confirm(self):
        res = super().action_confirm()
        self._generate_delivery_note_no_if_needed()
        return res

    def write(self, vals):
        # O18 บาง path ตั้ง state='sale' โดยไม่ผ่าน action_confirm -> hook ที่ write()
        res = super().write(vals)
        if vals.get("state") == "sale":
            self._generate_delivery_note_no_if_needed()
        return res

    # ------------------------------------------------------------------
    # ฟิลด์สำหรับ Jasper
    # ------------------------------------------------------------------
    jasper_delivery_note_no = fields.Char(
        string="Delivery Note No (Jasper)",
        compute="_compute_jasper_dn",
    )
    jasper_user_name = fields.Char(
        string="Document Issuer Name",
        compute="_compute_jasper_dn",
    )

    def _compute_jasper_dn(self):
        uname = self.env.user.name or ""
        for rec in self:
            rec.jasper_delivery_note_no = rec.delivery_note_no or ""
            rec.jasper_user_name = uname
