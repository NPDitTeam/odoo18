# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, models, fields
from odoo.exceptions import UserError

# ----------------------------------------------------------------------------
# เลขที่สัญญาเช่าเต็ม = {ตัวย่อบริษัท}{เลขรัน}.{ลำดับ}/{ทั้งหมด}
#   เช่น  nb-26061900004.3/3
#   - ตัวย่อบริษัท (nb-)  : default ตาม company (company_registry) + แก้เองได้ผ่านปุ่ม
#   - เลขรัน (26061900004): จาก ir.sequence (copy=True ซ้ำเอกสารใช้เลขเดิม)
#   - /Y                 : Y=จำนวนเอกสารในกลุ่ม (นับ deposit_ref + เอกสารนี้)
#
# หมายเหตุการพอร์ต odoo14 -> odoo18:
#   odoo14 แยก DB ต่อบริษัท จึง map ตัวย่อ/ชื่อบริษัทจากชื่อ DB (self._cr.dbname)
#   odoo18 เป็น single-DB หลายบริษัท จึง map จาก company_registry ("ID บริษัท")
#     1=นภดล กรุงเทพ, 2=นภดล อินเตอร์เทรดดิ้ง, 3=นภดล เอส กรุ๊ป,
#     4=เอ็นพีดี สตีลเทค, 5=เอ็นพีดี โลจิสติกส์
# ----------------------------------------------------------------------------

# Mapping company_registry -> ตัวย่อบริษัท (prefix เลขที่สัญญาเช่า) -- เป็น "ค่าเริ่มต้น"
REGISTRY_CONTRACT_PREFIX = {
    "1": "nb-",   # บริษัท นภดล กรุงเทพ จำกัด
    "2": "in-",   # บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด
    "3": "sg-",   # บริษัท นภดล เอส กรุ๊ป จำกัด
    "4": "st-",   # บริษัท เอ็นพีดี สตีลเทค จำกัด
    "5": "lg-",   # บริษัท เอ็นพีดี โลจิสติกส์ จำกัด
}

# ชื่อเดือนไทยแบบเต็ม (index = เลขเดือน 1-12)
THAI_MONTHS = (
    "",
    u"มกราคม", u"กุมภาพันธ์", u"มีนาคม", u"เมษายน", u"พฤษภาคม", u"มิถุนายน",
    u"กรกฎาคม", u"สิงหาคม", u"กันยายน", u"ตุลาคม", u"พฤศจิกายน", u"ธันวาคม",
)

# ชื่อเดือนไทยแบบย่อ (index = เลขเดือน 1-12)
THAI_MONTHS_ABBR = (
    "",
    u"ม.ค.", u"ก.พ.", u"มี.ค.", u"เม.ย.", u"พ.ค.", u"มิ.ย.",
    u"ก.ค.", u"ส.ค.", u"ก.ย.", u"ต.ค.", u"พ.ย.", u"ธ.ค.",
)

# เส้นประสำหรับช่องเว้นว่างในสัญญา (ให้เหมือนต้นฉบับ QWeb)
DOT_S = u"................"
DOT_M = u"..................................."
DOT_L = u"............................................."
DOT_XL = u"......................................................................"

# ---- แปลงจำนวนเงินเป็นข้อความไทย (บาท/สตางค์) ----
_BT_NUM = (u"", u"หนึ่ง", u"สอง", u"สาม", u"สี่", u"ห้า", u"หก", u"เจ็ด", u"แปด", u"เก้า")
_BT_UNIT = (u"", u"สิบ", u"ร้อย", u"พัน", u"หมื่น", u"แสน")


def _bt_read(n):
    """อ่านจำนวนเต็มเป็นข้อความไทย (ยังไม่รวมหน่วยบาท)"""
    if n == 0:
        return u""
    if n >= 1000000:
        return _bt_read(n // 1000000) + u"ล้าน" + _bt_read(n % 1000000)
    s = str(n)
    length = len(s)
    res = u""
    for i, ch in enumerate(s):
        d = int(ch)
        if d == 0:
            continue
        pos = length - i - 1  # 0=หน่วย, 1=สิบ, ...
        if pos == 0:
            res += u"เอ็ด" if (d == 1 and length > 1) else _BT_NUM[d]
        elif pos == 1:
            res += u"สิบ" if d == 1 else (u"ยี่สิบ" if d == 2 else _BT_NUM[d] + u"สิบ")
        else:
            res += _BT_NUM[d] + _BT_UNIT[pos]
    return res


def bahttext(amount):
    """1,250.50 -> หนึ่งพันสองร้อยห้าสิบบาทห้าสิบสตางค์"""
    amount = round(float(amount or 0.0), 2)
    baht = int(amount)
    satang = int(round((amount - baht) * 100))
    if baht == 0 and satang == 0:
        return u"ศูนย์บาทถ้วน"
    text = u""
    if baht > 0:
        text += _bt_read(baht) + u"บาท"
    if satang > 0:
        text += _bt_read(satang) + u"สตางค์"
    elif baht > 0:
        text += u"ถ้วน"
    return text


def _join_address(*parts):
    """รวมชิ้นส่วนที่อยู่เป็นบรรทัดเดียว ยุบช่องว่างซ้ำ"""
    addr = u" ".join([p for p in parts if p])
    return u" ".join(addr.split())


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # เลขที่สัญญาเช่า (คงตรรกะเดิมจาก odoo14)
    # ------------------------------------------------------------------
    rental_contract_no = fields.Char(
        string=u"เลขรันสัญญาเช่า",
        copy=True,  # ซ้ำเอกสารใช้เลขเดิม ไม่รันเลขใหม่
        readonly=True,
        help=u"เลขรันจาก ir.sequence (ส่วน 26061900004) -- ไม่รวมตัวย่อบริษัท",
    )
    rental_contract_prefix = fields.Char(
        string=u"ตัวย่อบริษัท",
        copy=True,
        help=u"ตัวย่อบริษัทหน้าเลขที่สัญญา (เช่น nb-) -- ปล่อยว่าง = ใช้ตาม company ของใบขาย "
             u"อัตโนมัติ (company_registry) เปลี่ยน override ได้ผ่านปุ่ม",
    )
    rental_contract_full = fields.Char(
        string=u"เลขที่สัญญาเช่า",
        compute="_compute_rental_contract_full",
        help=u"เลขที่สัญญาเช่าเต็ม = ตัวย่อ + เลขรัน + /ทั้งหมด",
    )

    @api.depends("rental_contract_prefix", "rental_contract_no", "deposit_ref")
    def _compute_rental_contract_full(self):
        for order in self:
            num = order.rental_contract_no or ""
            if not num:
                order.rental_contract_full = ""
                continue
            prefix = order.rental_contract_prefix or REGISTRY_CONTRACT_PREFIX.get(
                order.company_id.company_registry, ""
            )
            order.rental_contract_full = "%s%s%s" % (
                prefix,
                num,
                order._get_rental_deposit_position(),
            )

    def _get_rental_deposit_position(self):
        """ส่วนต่อท้าย /N  โดย N = จำนวนชุดใน deposit_ref + 1 (นับเอกสารนี้เพิ่มเสมอ)"""
        self.ensure_one()
        return "/%d" % self._get_rental_doc_count()

    def _get_rental_doc_count(self):
        """จำนวนเอกสารในกลุ่ม N = จำนวน SO ใน deposit_ref + 1 (นับเอกสารนี้)"""
        self.ensure_one()
        refs = []
        if "deposit_ref" in self._fields:
            refs = [r.strip() for r in (self.deposit_ref or "").split(",") if r.strip()]
        return len(refs) + 1

    def _get_rental_contract_base(self):
        """เลขที่สัญญา = ตัวย่อ + เลขรัน (ไม่รวม /N) -- ใช้ในหัวรายงานสัญญาเช่า"""
        self.ensure_one()
        num = self.rental_contract_no or ""
        if not num:
            return ""
        prefix = self.rental_contract_prefix or REGISTRY_CONTRACT_PREFIX.get(
            self.company_id.company_registry, ""
        )
        return "%s%s" % (prefix, num)

    def action_open_contract_prefix_wizard(self):
        """ปุ่ม header: เปิด wizard เปลี่ยนตัวย่อบริษัทของเลขที่สัญญาเช่า"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": u"เปลี่ยนตัวย่อบริษัท",
            "res_model": "npd.rental.contract.prefix.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_prefix": self.rental_contract_prefix
                or REGISTRY_CONTRACT_PREFIX.get(
                    self.company_id.company_registry, ""
                ),
            },
        }

    def _has_rental_deposit_ref(self, order):
        """เอกสารนี้อ้างอิงเอกสารก่อนหน้า (deposit_ref มีค่า) หรือไม่"""
        if "deposit_ref" not in order._fields:
            return False
        return bool((order.deposit_ref or "").strip())

    def _ensure_rental_contract_no(self):
        """สร้างเลขที่สัญญาเช่าให้ครั้งแรก แล้วเก็บไว้ (ไม่เปลี่ยนถ้ามีแล้ว)"""
        seq_obj = self.env["ir.sequence"]
        for order in self:
            if not order.rental_contract_no:
                number = seq_obj.next_by_code("npd.rental.contract")
                if not number:
                    raise UserError(
                        u"ไม่พบลำดับเลขที่สัญญาเช่า (ir.sequence code = "
                        u"'npd.rental.contract') กรุณาอัปเดตโมดูล "
                        u"pfb_npd_rental_equipment_contract_jasper"
                    )
                order.rental_contract_no = number
        return True

    def _is_rental_contract_order(self, order):
        """เป็นใบขายประเภท 'เช่า' (rent) หรือไม่"""
        if "pfb_so_type" in order._fields:
            return order.pfb_so_type == "rent"
        return False

    def _generate_rental_contract_no_if_needed(self):
        """สร้างเลขที่สัญญาเช่าตามเงื่อนไข odoo14 (เรียกได้ปลอดภัยหลายครั้ง)
          - ต้องเป็นใบขายประเภท rent
          - ยังไม่มีเลขที่สัญญา (rental_contract_no)
          - deposit_ref ว่าง = เอกสารใหม่ -> รันเลขใหม่
            (deposit_ref มีค่า = เอกสารต่อเนื่อง/ซ้ำ -> ใช้เลขเดิมที่ copy มา ไม่รันใหม่)"""
        for order in self:
            if not self._is_rental_contract_order(order):
                continue
            if order.rental_contract_no:
                continue
            if self._has_rental_deposit_ref(order):
                continue
            order._ensure_rental_contract_no()
        return True

    def action_confirm(self):
        """เผื่อ path ที่ยืนยันผ่าน action_confirm มาตรฐาน"""
        res = super(SaleOrder, self).action_confirm()
        self._generate_rental_contract_no_if_needed()
        return res

    def write(self, vals):
        """สร้างเลขที่สัญญาเช่าเมื่อใบขายถูกยืนยัน (state -> 'sale')

        ใน odoo18 flow นี้ (Convert to Order / อนุมัติ) บาง path ตั้ง state='sale'
        โดยไม่ผ่าน action_confirm จึง hook ที่ write() ให้ครอบคลุมทุกทาง
        (มี guard rental_contract_no แล้ว จึงไม่สร้างซ้ำ / ไม่วนซ้ำ)"""
        res = super(SaleOrder, self).write(vals)
        if vals.get("state") == "sale":
            self._generate_rental_contract_no_if_needed()
        return res

    # ==================================================================
    # ฟิลด์คำนวณสำหรับ Jasper (prefix jasper_rc_)
    #   Jasper ดึงค่าจากฟิลด์บน record ไม่เรียก method จึงต้อง expose ทุกค่า
    #   เป็นฟิลด์ Char และเติมเส้นประ (....) ให้เองเมื่อไม่มีค่า เหมือนต้นฉบับ
    # ==================================================================

    # ---- ผู้ให้เช่า (บริษัท) ----
    jasper_rc_lessor_name = fields.Char(compute="_compute_jasper_rc_lessor")
    jasper_rc_lessor_vat = fields.Char(compute="_compute_jasper_rc_lessor")
    jasper_rc_lessor_address = fields.Char(compute="_compute_jasper_rc_lessor")

    @api.depends(
        "company_id", "company_id.name", "company_id.vat",
        "company_id.street", "company_id.street2", "company_id.city",
        "company_id.state_id", "company_id.zip",
    )
    def _compute_jasper_rc_lessor(self):
        for rec in self:
            c = rec.company_id
            rec.jasper_rc_lessor_name = (c.name or "") if c else ""
            rec.jasper_rc_lessor_vat = (c.vat or DOT_M) if c else DOT_M
            addr = ""
            if c:
                addr = _join_address(
                    c.street, c.street2, c.city,
                    c.state_id.name if c.state_id else "", c.zip,
                )
            rec.jasper_rc_lessor_address = addr

    # ---- เลขที่สัญญา / สาขา ----
    jasper_rc_contract_base = fields.Char(compute="_compute_jasper_rc_ids")
    jasper_rc_branch_name = fields.Char(compute="_compute_jasper_rc_ids")
    jasper_rc_name = fields.Char(compute="_compute_jasper_rc_ids")

    @api.depends(
        "rental_contract_no", "rental_contract_prefix", "deposit_ref",
        "branch_id", "name",
    )
    def _compute_jasper_rc_ids(self):
        for rec in self:
            rec.jasper_rc_contract_base = rec._get_rental_contract_base() or DOT_M
            branch = ""
            if "branch_id" in rec._fields and rec.branch_id:
                branch = rec.branch_id.name or ""
            rec.jasper_rc_branch_name = branch or DOT_S
            rec.jasper_rc_name = rec.name or DOT_M

    # ---- ข้อมูลผู้เช่า (ลูกค้า) : แยก slot ตามนิติบุคคล/บุคคลธรรมดา ----
    jasper_rc_mark_company = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_mark_person = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_company_name = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_company_vat = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_company_address = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_person_name = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_person_vat = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_person_address = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_sign_customer = fields.Char(compute="_compute_jasper_rc_customer")
    jasper_rc_show_customer_stamp = fields.Char(compute="_compute_jasper_rc_customer")

    @api.depends(
        "partner_id", "partner_id.name", "partner_id.vat", "partner_id.is_company",
        "partner_id.street", "partner_id.street2", "partner_id.city",
        "partner_id.state_id", "partner_id.zip",
    )
    def _compute_jasper_rc_customer(self):
        for rec in self:
            p = rec.partner_id
            is_company = bool(p and p.is_company)
            name = (p.name or "") if p else ""
            vat = (p.vat or "") if p else ""
            addr = ""
            if p:
                addr = _join_address(
                    p.street, p.street2, p.city,
                    p.state_id.name if p.state_id else "", p.zip,
                )
            # ฟอนต์ Sarabun ไม่มี glyph ✓/☑ แต่มี √ (U+221A) ที่หน้าตาเหมือนเครื่องหมายถูก
            rec.jasper_rc_mark_company = u"[ √ ]" if is_company else u"[    ]"
            rec.jasper_rc_mark_person = u"[    ]" if is_company else u"[ √ ]"
            # slot นิติบุคคล
            rec.jasper_rc_company_name = (name if is_company else "") or DOT_M
            rec.jasper_rc_company_vat = (vat if is_company else "") or DOT_M
            rec.jasper_rc_company_address = (addr if is_company else "") or DOT_XL
            # slot บุคคลธรรมดา
            rec.jasper_rc_person_name = (name if not is_company else "") or DOT_M
            rec.jasper_rc_person_vat = (vat if not is_company else "") or DOT_M
            rec.jasper_rc_person_address = (addr if not is_company else "") or DOT_XL
            # บล็อกลายเซ็นผู้เช่า (นิติบุคคลเท่านั้น)
            if is_company:
                rec.jasper_rc_sign_customer = (
                    name or u"บริษัท............................................... จำกัด"
                )
            else:
                rec.jasper_rc_sign_customer = ""
            rec.jasper_rc_show_customer_stamp = "1" if is_company else "0"

    # ---- วันที่ (เริ่มเช่า) แบบไทย ----
    jasper_rc_date_day = fields.Char(compute="_compute_jasper_rc_dates")
    jasper_rc_date_month = fields.Char(compute="_compute_jasper_rc_dates")
    jasper_rc_date_year = fields.Char(compute="_compute_jasper_rc_dates")
    jasper_rc_start_short = fields.Char(compute="_compute_jasper_rc_dates")
    jasper_rc_return_day = fields.Char(compute="_compute_jasper_rc_dates")
    jasper_rc_return_month = fields.Char(compute="_compute_jasper_rc_dates")
    jasper_rc_return_year = fields.Char(compute="_compute_jasper_rc_dates")
    jasper_rc_duration = fields.Char(compute="_compute_jasper_rc_dates")

    @api.depends("start_rent_date", "end_rent_date", "pfb_date_of_rent")
    def _compute_jasper_rc_dates(self):
        for rec in self:
            start = rec.start_rent_date if "start_rent_date" in rec._fields else False
            end = rec.end_rent_date if "end_rent_date" in rec._fields else False
            d = rec._thai_date_parts(start)
            rec.jasper_rc_date_day = d[0] or DOT_S
            rec.jasper_rc_date_month = d[1] or DOT_M
            rec.jasper_rc_date_year = d[2] or DOT_S
            rec.jasper_rc_start_short = rec._thai_short_date(start) or DOT_S
            r = rec._thai_date_parts(end)
            rec.jasper_rc_return_day = r[0] or DOT_S
            rec.jasper_rc_return_month = r[1] or DOT_M
            rec.jasper_rc_return_year = r[2] or DOT_S
            dur = ""
            if "pfb_date_of_rent" in rec._fields and rec.pfb_date_of_rent:
                dur = str(rec.pfb_date_of_rent)
            rec.jasper_rc_duration = dur or DOT_S

    def _thai_date_parts(self, value):
        """date/datetime -> (day, เดือนไทยเต็ม, ปี พ.ศ.)"""
        if not value:
            return ("", "", "")
        if isinstance(value, datetime):
            value = fields.Datetime.context_timestamp(self, value)
        return (str(value.day), THAI_MONTHS[value.month], str(value.year + 543))

    def _thai_short_date(self, value):
        """แบบย่อไทย เช่น '19 มิ.ย.69'"""
        if not value:
            return ""
        if isinstance(value, datetime):
            value = fields.Datetime.context_timestamp(self, value)
        return "%d %s%02d" % (
            value.day, THAI_MONTHS_ABBR[value.month], (value.year + 543) % 100
        )

    # ---- จำนวนเงิน ----
    jasper_rc_amount_total = fields.Char(compute="_compute_jasper_rc_amounts")
    jasper_rc_invoice_amount = fields.Char(compute="_compute_jasper_rc_amounts")
    jasper_rc_invoice_amount_text = fields.Char(compute="_compute_jasper_rc_amounts")

    @api.depends("amount_total", "invoice_ids.state", "invoice_ids.payment_state",
                 "invoice_ids.amount_total", "invoice_ids.amount_residual")
    def _compute_jasper_rc_amounts(self):
        for rec in self:
            rec.jasper_rc_amount_total = "{:,.2f}".format(rec.amount_total or 0.0)
            amt = rec._get_rental_invoice_amount()
            rec.jasper_rc_invoice_amount = "{:,.2f}".format(amt) if amt else DOT_L
            rec.jasper_rc_invoice_amount_text = bahttext(amt) if amt else DOT_L

    def _get_rental_invoice_amount(self):
        """ยอดที่ชำระแล้วจริงจากใบแจ้งหนี้ที่ posted (เต็ม/บางส่วน)"""
        self.ensure_one()
        if "invoice_ids" not in self._fields:
            return 0.0
        invs = self.invoice_ids.filtered(
            lambda m: m.state == "posted"
            and m.move_type == "out_invoice"
            and m.payment_state in ("paid", "in_payment", "partial")
        )
        return sum((inv.amount_total - inv.amount_residual) for inv in invs)

    # ---- หน้างาน ----
    jasper_rc_on_site = fields.Char(compute="_compute_jasper_rc_on_site")

    @api.depends("on_site")
    def _compute_jasper_rc_on_site(self):
        for rec in self:
            val = ""
            if "on_site" in rec._fields:
                val = rec.on_site or ""
            rec.jasper_rc_on_site = val or DOT_L
