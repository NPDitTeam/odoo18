# -*- coding: utf-8 -*-
from odoo import api, fields, models


THAI_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]

_TH_NUM = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
_TH_POS = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]


def _th_read_group(num_str):
    """อ่านเลขกลุ่มไม่เกิน 6 หลัก (หลักล้านจัดการภายนอก)"""
    result = ""
    length = len(num_str)
    for idx, ch in enumerate(num_str):
        digit = int(ch)
        pos = length - idx - 1
        if digit == 0:
            continue
        if pos == 0 and digit == 1 and length > 1:
            result += "เอ็ด"
        elif pos == 1 and digit == 2:
            result += "ยี่" + _TH_POS[pos]
        elif pos == 1 and digit == 1:
            result += _TH_POS[pos]
        else:
            result += _TH_NUM[digit] + _TH_POS[pos]
    return result


def _baht_text(amount):
    """แปลงจำนวนเงินเป็นข้อความภาษาไทย (pure-Python ไม่พึ่ง lib ภายนอก)"""
    try:
        amount = float(amount or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    negative = amount < 0
    amount = abs(round(amount + 1e-9, 2))
    baht = int(amount)
    satang = int(round((amount - baht) * 100))

    def read_int(n):
        if n == 0:
            return "ศูนย์"
        text = ""
        millions = []
        while n > 0:
            millions.append(n % 1000000)
            n //= 1000000
        for i in range(len(millions) - 1, -1, -1):
            grp = millions[i]
            if grp == 0:
                continue
            text += _th_read_group(str(grp))
            text += "ล้าน" * i
        return text

    words = read_int(baht) + "บาท"
    if satang == 0:
        words += "ถ้วน"
    else:
        words += _th_read_group(str(satang).zfill(2)) + "สตางค์"
    if negative:
        words = "ลบ" + words
    return words


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # ---- ข้อมูลบริษัทผู้ซื้อ ----
    jasper_po_company_name = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_company_address = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_company_vat = fields.Char(compute="_compute_jasper_po", store=False)

    # ---- ข้อมูลผู้จำหน่าย ----
    jasper_po_vendor_name = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_vendor_address = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_vendor_vat = fields.Char(compute="_compute_jasper_po", store=False)

    # ---- หัวเอกสาร ----
    jasper_po_name = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_order_date_thai = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_date_planned_thai = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_rfq = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_department = fields.Char(compute="_compute_jasper_po", store=False)

    # ---- ยอดเงิน (จัดรูปแบบเป็นข้อความแล้ว) ----
    jasper_po_amount_before_discount = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_discount = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_amount_untaxed = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_amount_tax = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_amount_total = fields.Char(compute="_compute_jasper_po", store=False)
    jasper_po_baht_text = fields.Char(compute="_compute_jasper_po", store=False)

    jasper_po_note = fields.Char(compute="_compute_jasper_po", store=False)

    @staticmethod
    def _fmt(value):
        try:
            return "{:,.2f}".format(float(value or 0.0))
        except (TypeError, ValueError):
            return "0.00"

    @staticmethod
    def _thai_date(value):
        if not value:
            return ""
        return "%d %s %d" % (value.day, THAI_MONTHS[value.month], value.year + 543)

    @staticmethod
    def _partner_address(partner):
        if not partner:
            return ""
        parts = []
        street = " ".join([p for p in [partner.street, partner.street2] if p])
        if street:
            parts.append(street)
        locality = []
        if partner.city:
            locality.append(partner.city)
        if partner.state_id:
            locality.append(partner.state_id.name)
        if partner.zip:
            locality.append(partner.zip)
        if locality:
            parts.append(" ".join(locality))
        return " ".join(parts)

    def _compute_jasper_po(self):
        for order in self:
            company = order.company_id or self.env.company
            company_partner = company.partner_id
            order.jasper_po_company_name = company_partner.name or company.name or ""
            order.jasper_po_company_address = self._partner_address(company_partner)
            order.jasper_po_company_vat = company_partner.vat or ""

            vendor = order.partner_id
            order.jasper_po_vendor_name = vendor.name or ""
            order.jasper_po_vendor_address = self._partner_address(vendor)
            order.jasper_po_vendor_vat = vendor.vat or ""

            order.jasper_po_name = order.name or ""

            # วันที่สั่งซื้อ: ใช้ฟิลด์ custom order_date ถ้ามี ไม่งั้น date_order
            order_date = getattr(order, "order_date", False) or order.date_order
            if order_date and hasattr(order_date, "date"):
                order_date = order_date.date()
            order.jasper_po_order_date_thai = self._thai_date(order_date)

            date_planned = getattr(order, "date_planned", False)
            if date_planned and hasattr(date_planned, "date"):
                date_planned = date_planned.date()
            order.jasper_po_date_planned_thai = self._thai_date(date_planned)

            quote = getattr(order, "quote_id", False)
            order.jasper_po_rfq = quote.name if quote else ""
            dept = getattr(order, "department_id", False)
            order.jasper_po_department = dept.name if dept else ""

            # ยอดเงิน
            discount_total = 0.0
            for line in order.order_line:
                if getattr(line, "display_type", False):
                    continue
                discount_total += (line.product_qty * line.price_unit) - line.price_subtotal
            before_discount = order.amount_untaxed + discount_total
            order.jasper_po_amount_before_discount = self._fmt(before_discount)
            order.jasper_po_discount = self._fmt(discount_total)
            order.jasper_po_amount_untaxed = self._fmt(order.amount_untaxed)
            order.jasper_po_amount_tax = self._fmt(order.amount_tax)
            order.jasper_po_amount_total = self._fmt(order.amount_total)
            order.jasper_po_baht_text = _baht_text(order.amount_total)

            order.jasper_po_note = order.notes or "" if hasattr(order, "notes") else ""


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    jasper_po_line_name = fields.Char(compute="_compute_jasper_po_line", store=False)
    jasper_po_line_qty = fields.Char(compute="_compute_jasper_po_line", store=False)
    jasper_po_line_uom = fields.Char(compute="_compute_jasper_po_line", store=False)
    jasper_po_line_price = fields.Char(compute="_compute_jasper_po_line", store=False)
    jasper_po_line_discount = fields.Char(compute="_compute_jasper_po_line", store=False)
    jasper_po_line_total = fields.Char(compute="_compute_jasper_po_line", store=False)

    def _compute_jasper_po_line(self):
        for line in self:
            if getattr(line, "display_type", False):
                # แถวหัวข้อ/หมายเหตุ: แสดงเฉพาะชื่อ
                line.jasper_po_line_name = line.name or ""
                line.jasper_po_line_qty = ""
                line.jasper_po_line_uom = ""
                line.jasper_po_line_price = ""
                line.jasper_po_line_discount = ""
                line.jasper_po_line_total = ""
                continue
            line.jasper_po_line_name = line.name or ""
            qty = line.product_qty or 0.0
            line.jasper_po_line_qty = str(qty)
            line.jasper_po_line_uom = line.product_uom.name if line.product_uom else ""
            line.jasper_po_line_price = "{:,.2f}".format(line.price_unit or 0.0)
            discount = getattr(line, "discount", 0.0) or 0.0
            line.jasper_po_line_discount = "{:,.2f}".format(discount)
            line.jasper_po_line_total = "{:,.2f}".format((line.product_qty or 0.0) * (line.price_unit or 0.0))
