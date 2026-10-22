import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ตัวย่อบริษัทหน้าเลขที่สัญญาเช่า (map ตาม company_registry) จากโมดูลสัญญาเช่า
# import แบบปลอดภัย เผื่อโมดูลนั้นไม่ได้ติดตั้ง
try:
    from odoo.addons.pfb_npd_rental_equipment_contract_jasper.models.sale_order import (
        REGISTRY_CONTRACT_PREFIX,
    )
except Exception:  # pragma: no cover
    REGISTRY_CONTRACT_PREFIX = {}

# เลขทะเบียนบริษัท (company_registry / "ID บริษัท") — ใช้ระบุบริษัทแทน database id
# เพราะ id อาจต่างกันในแต่ละฐานข้อมูล แต่เลขทะเบียนคงที่
NPD_LOGISTICS_REGISTRY = "5"   # บริษัท เอ็นพีดี โลจิสติกส์ จำกัด (ใช้ฟีเจอร์นี้ได้)
NPD_STEELTECH_REGISTRY = "4"   # บริษัท เอ็นพีดี สตีลเทค จำกัด (ห้ามเป็นแหล่งดึง)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # เดิมใน Odoo 14 ดึงข้อมูลข้ามฐานข้อมูลผ่าน API (database_selection)
    # Odoo 18 ใช้ฐานข้อมูลเดียวกันแต่แยกบริษัท จึงเลือกผ่าน company แทน
    # เลือก "บริษัทอื่น" เป็นแหล่งที่จะดึงข้อมูลเข้ามา (ไม่ใช่บริษัทตัวเอง)
    # domain กรองไม่ให้เลือกบริษัทตัวเองถูกกำหนดในวิว: [('id','!=',company_id)]
    source_company_id = fields.Many2one(
        "res.company",
        string="ดึงข้อมูลการเช่าจาก บ.อื่น",
    )

    so_number = fields.Char(string="เลขเอกสาร SO")
    is_renew_green_house = fields.Boolean(string="บิลต่ออายุจากบ้านเขียว", default=False)

    # ใช้คุมการแสดงผลฟิลด์/ปุ่มในฟอร์ม ให้แสดงเฉพาะบริษัท เอ็นพีดี โลจิสติกส์ จำกัด
    is_npd_logistics_company = fields.Boolean(
        string="เป็นบริษัทเอ็นพีดี โลจิสติกส์",
        compute="_compute_is_npd_logistics_company",
    )

    # ------------------------------------------------------------------
    # โลจิสติกส์เปิดแค่ SO สำหรับงานขนส่ง ไม่ผ่านใบเสนอราคา (o14 ฐานโลจิสติกส์ไม่มีใบเสนอราคาแยก)
    # กด "สร้าง" จากเมนูใบกำกับการเช่า -> เป็นใบสั่งขาย (order_sequence) เลขรัน SO ทันที
    # บริษัทอื่นยังต้องเปิดใบเสนอราคาแล้ว Convert to Order เหมือนเดิม
    # ------------------------------------------------------------------
    def _is_logistics_direct_order(self, company_id=None):
        if self.env.context.get("menu_name") != "Sales Orders Rent":
            return False
        company = self.env["res.company"].browse(company_id) if company_id else self.env.company
        return company.company_registry == NPD_LOGISTICS_REGISTRY

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # ให้ฟอร์มใบใหม่แสดงหัวแบบใบสั่งขาย (ปุ่มยืนยัน) ไม่ใช่หัวใบเสนอราคา
        if "order_sequence" in self._fields and self._is_logistics_direct_order(res.get("company_id")):
            res["order_sequence"] = True
        return res

    @api.model_create_multi
    def create(self, vals_list):
        # order_sequence เป็นช่องอ่านอย่างเดียว ฟอร์มไม่ส่งมาตอนบันทึก จึงตั้งที่นี่
        # ต้องตั้งก่อน sale_isolated_quotation.create ไม่งั้นได้เลข QT
        if "order_sequence" in self._fields:
            for vals in vals_list:
                if "order_sequence" not in vals and self._is_logistics_direct_order(vals.get("company_id")):
                    vals["order_sequence"] = True
        return super().create(vals_list)

    @api.depends("company_id", "company_id.company_registry")
    def _compute_is_npd_logistics_company(self):
        for order in self:
            order.is_npd_logistics_company = (
                order.company_id.company_registry == NPD_LOGISTICS_REGISTRY
            )

    def action_fetch_rental_data(self):
        """ ดึงข้อมูลการเช่า — กรอกบริษัท + เลข SO บนฟอร์มครบแล้วดึงเลยเหมือน o14
            ยังกรอกไม่ครบค่อยเปิด popup ให้เลือก """
        self.ensure_one()

        # ใช้ได้เฉพาะใบสั่งขายของบริษัท เอ็นพีดี โลจิสติกส์ จำกัด เท่านั้น
        if self.company_id.company_registry != NPD_LOGISTICS_REGISTRY:
            raise UserError(_("❌ ฟังก์ชันนี้ใช้ได้เฉพาะบริษัท เอ็นพีดี โลจิสติกส์ จำกัด เท่านั้น"))

        so_number = (self.so_number or "").strip()
        if self.source_company_id and so_number:
            self._fetch_rental_data(self.source_company_id, so_number)
            return self._fetch_rental_done_notification(
                {"type": "ir.actions.client", "tag": "soft_reload"})

        return {
            "type": "ir.actions.act_window",
            "name": _("ดึงข้อมูลการเช่า"),
            "res_model": "sale.rent.fetch.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_source_company_id": self.source_company_id.id or False,
                "default_so_number": self.so_number or "",
            },
        }

    def _fetch_rental_done_notification(self, next_action):
        """ แจ้งผลหลังดึงสำเร็จ — พนักงานจะได้รู้ว่าดึงมาจริงและได้กี่รายการ """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("ดึงข้อมูลการเช่าสำเร็จ"),
                "message": _("ดึงจาก %(so)s (%(company)s) ได้ %(count)s รายการสินค้า") % {
                    "so": self.so_number,
                    "company": self.source_company_id.name,
                    "count": len(self.order_line),
                },
                "type": "success",
                "sticky": False,
                "next": next_action,
            },
        }

    def _fetch_rental_data(self, source_company, so_number):
        """ คัดลอกข้อมูลการเช่าจาก SO ต้นทาง (บริษัทอื่น) มายังใบสั่งขายนี้
            ดึงได้ทุกสถานะของ SO ต้นทาง (รวมถึงคำสั่งขายแล้ว) """
        self.ensure_one()

        if not source_company or not so_number:
            raise UserError(_("กรุณาเลือกบริษัทต้นทางและกรอกเลข SO ก่อนดำเนินการ!"))

        # ต้องเป็นบริษัทอื่น ไม่ใช่บริษัทของตัวเอง
        if source_company.id == self.company_id.id:
            raise UserError(_("❌ กรุณาเลือกบริษัทอื่น (ไม่ใช่บริษัทของตัวเอง) เพื่อดึงข้อมูล"))

        # ไม่รองรับการดึงจากบริษัท เอ็นพีดี สตีลเทค
        if source_company.company_registry == NPD_STEELTECH_REGISTRY:
            raise UserError(_("❌ ไม่รองรับการดึงข้อมูลจากบริษัท เอ็นพีดี สตีลเทค จำกัด"))

        # ค้นหา SO ต้นทาง (ข้ามบริษัทด้วย sudo เพราะอยู่คนละ company) — ไม่กรองสถานะ
        source_order = self.env["sale.order"].sudo().search([
            ("name", "=", so_number),
            ("company_id", "=", source_company.id),
        ], limit=1)

        if not source_order:
            raise UserError(_("❌ ไม่พบ SO เลขที่ %s ในบริษัท %s")
                            % (so_number, source_company.name))

        sol_data = source_order.order_line.filtered(lambda l: l.product_id)
        if not sol_data:
            raise UserError(_("❌ ไม่พบรายการสินค้าใน SO ต้นทาง"))

        _logger.info("📥 ดึงข้อมูลการเช่าจาก SO %s (company %s)",
                     source_order.name, source_company.name)

        # คัดลอกข้อมูลส่วนหัว/ขนส่ง + บันทึกแหล่งที่ดึงไว้บนเอกสาร
        self.write({
            "source_company_id": source_company.id,
            "so_number": so_number,
            "delivery_type": source_order.delivery_type,
            "pickup_location": source_order.pickup_location,
            "destination": source_order.destination,
            "vehicle_type_id": source_order.vehicle_type_id.id,
            "delivery_employee_id": source_order.delivery_employee_id.id,
            "license_plate_id": source_order.license_plate_id.id,
            "distance_km": source_order.distance_km,
            "shipping_cost_raw": source_order.shipping_cost_raw,
            "shipping_cost": source_order.shipping_cost,
            "shipping_cost_m": source_order.shipping_cost_m,
            "trip_allowance": source_order.trip_allowance,
            "daily_allowance": source_order.daily_allowance,
            "profit_per_trip_p": source_order.profit_per_trip_p,
            "profit_per_trip": source_order.profit_per_trip,
            "use_special_delivery_zero": source_order.use_special_delivery_zero,
            # ค่าขนส่งเป็น 0 เพราะโปรของบริษัท ไม่ใช่คนกดเอง
            # ต้องติดมาด้วย ไม่งั้นใบนี้จะถูกขอให้อนุมัติค่าขนส่งพิเศษซ้ำ
            "npd_free_shipping_zero_set": getattr(
                source_order, "npd_free_shipping_zero_set", False),
            # แท็บการตลาด — อยู่ฐานเดียวกัน ใช้ id ของต้นทางได้ตรง ๆ
            # ต้องติดมาด้วย ไม่งั้นใบฝั่งโลจิสติกส์จะไม่รู้ว่างานนี้มาจากโปรไหน
            # และดูรายงานแยกตามแคมเปญไม่ได้
            "campaign_id": source_order.campaign_id.id,
            "medium_id": source_order.medium_id.id,
            "source_id": source_order.source_id.id,
        })

        # คัดลอก "เลขที่สัญญาเช่า" จากต้นทางมาด้วย (เฉพาะบริษัท เอ็นพีดี โลจิสติกส์)
        # โลจิสติกส์รับงานขนส่งแทนบริษัทอื่น จึงต้องใช้เลขสัญญาของต้นทาง
        # ไม่ใช่รันเลขใหม่ของตัวเอง -> คัดลอกเลขรัน + ตัวย่อบริษัทที่ใช้จริงของต้นทาง
        # (rental_contract_full = prefix + no + /N เป็น compute จึงตั้งค่าผ่านฟิลด์ต้นทาง)
        if (
            self.company_id.company_registry == NPD_LOGISTICS_REGISTRY
            and "rental_contract_no" in self._fields
            and source_order.rental_contract_no
        ):
            src_prefix = source_order.rental_contract_prefix or REGISTRY_CONTRACT_PREFIX.get(
                source_company.company_registry, ""
            )
            self.write({
                "rental_contract_no": source_order.rental_contract_no,
                "rental_contract_prefix": src_prefix,
            })
            _logger.info(
                "📄 คัดลอกเลขที่สัญญาเช่าจากต้นทาง: %s%s",
                src_prefix, source_order.rental_contract_no,
            )

        # ลบรายการสินค้าเดิมก่อนคัดลอกใหม่
        if self.order_line:
            _logger.info("🗑️ ลบรายการสินค้าเดิมใน SO: %s", self.name)
            self.order_line.unlink()

        for sol in sol_data:
            # ไม่ก็อป product_uom_qty: ต้นทางเป็นใบเช่า ค่านี้คือ จำนวน x วันเช่า (เช่น 364 x 30 = 10,920)
            # o14 ฐานโลจิสติกส์ก็อปแค่ Quantity Rent จำนวนปล่อยค่าเริ่มต้น 1 (ผู้ใช้สั่ง 22 ต.ค. 2569 ให้เหมือน o14)
            self.env["sale.order.line"].create({
                "order_id": self.id,
                "product_id": sol.product_id.id,
                "name": sol.name,
                "pfb_quantity": sol.pfb_quantity,
                "second_uom_qty": sol.second_uom_qty,
                "total_weight": sol.total_weight,
            })

        _logger.info("✅ บันทึกรายการสินค้าเรียบร้อย: %s", so_number)
        return True


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_renew_green_house_line = fields.Boolean(
        related="order_id.is_renew_green_house",
        string="บิลต่ออายุจากบ้านเขียว",
        readonly=True,
    )
    total_weight = fields.Float(
        string="น้ำหนักรวม",
        compute="_compute_total_weight",
        store=True,
        readonly=False,
    )

    @api.depends(
        "pfb_quantity", "second_uom_qty",
        "order_id.source_company_id", "order_id.so_number",
        "order_id.is_renew_green_house",
    )
    def _compute_total_weight(self):
        for line in self:
            order = line.order_id
            # ถ้าติ๊กบิลต่ออายุจากบ้านเขียว → ไม่ compute ให้กรอกเอง
            if order.is_renew_green_house:
                continue
            # คำนวณอัตโนมัติเฉพาะกรณีกรอกเองในบริษัทตัวเอง (ไม่ได้ดึงข้อมูลจากบริษัทอื่น)
            if (
                line.pfb_quantity and line.second_uom_qty
                and not order.source_company_id
                and not order.so_number
            ):
                line.total_weight = line.pfb_quantity * line.second_uom_qty
