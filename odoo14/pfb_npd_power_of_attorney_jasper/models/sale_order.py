# -*- coding: utf-8 -*-
from odoo import api, models, fields

# เส้นประ fallback -- ตรงกับ dot_* ของเทมเพลต QWeb ฝั่ง Odoo 14
DOT_S = u"............"
DOT_M = u"............................"
DOT_ADDR = u"..............................."
DOT_ID = u"............................................"
DOT_L = u"........................................................"


def _join_address(*parts):
    """ต่อที่อยู่ โดยข้ามส่วนที่ว่าง"""
    return u" ".join(p.strip() for p in parts if p and p.strip())


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # ข้อมูลผู้มอบอำนาจ (ลูกค้า) แบบรวม ไม่แยก นิติบุคคล/บุคคลธรรมดา
    #
    # ต่างจาก jasper_rc_company_* / jasper_rc_person_* ของโมดูลสัญญาเช่า
    # ที่แยกเป็น 2 slot เพื่อใช้กับช่องติ๊ก -- หนังสือมอบอำนาจใช้ค่าเดียว
    # ตรงกับ cust['name'] / cust['vat'] / cust['address'] ในเทมเพลต QWeb เดิม
    # ------------------------------------------------------------------
    jasper_poa_cust_name = fields.Char(compute="_compute_jasper_poa_customer")
    jasper_poa_cust_vat = fields.Char(compute="_compute_jasper_poa_customer")
    jasper_poa_cust_address = fields.Char(compute="_compute_jasper_poa_customer")
    jasper_poa_place = fields.Char(
        compute="_compute_jasper_poa_customer",
        help=u"ค่าช่อง 'ทำที่' : นิติบุคคลใช้ชื่อลูกค้า บุคคลธรรมดาใช้ที่อยู่",
    )

    @api.depends(
        "partner_id", "partner_id.name", "partner_id.vat", "partner_id.is_company",
        "partner_id.street", "partner_id.street2", "partner_id.city",
        "partner_id.state_id", "partner_id.zip",
    )
    def _compute_jasper_poa_customer(self):
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

            rec.jasper_poa_cust_name = name or DOT_L
            rec.jasper_poa_cust_vat = vat or DOT_M
            rec.jasper_poa_cust_address = addr or DOT_M
            # ทำที่ : นิติบุคคล -> ชื่อลูกค้า, บุคคลธรรมดา -> ที่อยู่
            rec.jasper_poa_place = (name if is_company else addr) or DOT_L
