from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleRentFetchWizard(models.TransientModel):
    _name = "sale.rent.fetch.wizard"
    _description = "ดึงข้อมูลการเช่าจากบริษัทอื่น"

    order_id = fields.Many2one(
        "sale.order",
        string="ใบสั่งขายปลายทาง",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="order_id.company_id",
        string="บริษัทของเอกสาร",
    )
    source_company_id = fields.Many2one(
        "res.company",
        string="ดึงข้อมูลการเช่าจาก บ.อื่น",
        required=True,
    )
    so_number = fields.Char(string="เลขเอกสาร SO", required=True)

    def action_fetch(self):
        """ คัดลอกข้อมูลจาก SO ต้นทางมายังใบสั่งขายปลายทาง แล้วปิด popup """
        self.ensure_one()
        if not self.order_id:
            raise UserError(_("ไม่พบใบสั่งขายปลายทาง"))
        self.order_id._fetch_rental_data(self.source_company_id, self.so_number)
        return {"type": "ir.actions.act_window_close"}
