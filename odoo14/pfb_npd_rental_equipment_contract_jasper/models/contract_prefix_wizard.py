# -*- coding: utf-8 -*-
from odoo import models, fields

# ตัวย่อบริษัท -> ป้ายแสดง (บอกว่าเป็นของบริษัทอะไร)
PREFIX_COMPANY = [
    ("sg-", u"sg-  :  บริษัท นภดล เอส กรุ๊ป จำกัด"),
    ("in-", u"in-  :  บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด"),
    ("st-", u"st-  :  บริษัท เอ็นพีดี สตีลเทค จำกัด"),
    ("nb-", u"nb-  :  บริษัท นภดล กรุงเทพ จำกัด"),
    ("lg-", u"lg-  :  บริษัท เอ็นพีดี โลจิสติกส์ จำกัด"),
]


class ContractPrefixWizard(models.TransientModel):
    _name = "npd.rental.contract.prefix.wizard"
    _description = u"เปลี่ยนตัวย่อบริษัท (เลขที่สัญญาเช่า)"

    order_id = fields.Many2one("sale.order", string=u"ใบขาย", required=True)
    prefix = fields.Selection(
        PREFIX_COMPANY, string=u"ตัวย่อบริษัท", required=True
    )

    def action_apply(self):
        """บันทึกตัวย่อใหม่ลงใบขาย"""
        self.ensure_one()
        self.order_id.rental_contract_prefix = self.prefix or ""
        return {"type": "ir.actions.act_window_close"}
