from odoo import api, fields, models


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    reason_code_id = fields.Many2one(
        "scrap.reason.code",
        string="Reason Code",
    )
    scrap_location_id = fields.Many2one(readonly=True)

    def _prepare_move_values(self):
        res = super()._prepare_move_values()
        res["reason_code_id"] = self.reason_code_id.id
        return res

    @api.onchange("reason_code_id")
    def _onchange_reason_code_id(self):
        if self.reason_code_id.location_id:
            self.scrap_location_id = self.reason_code_id.location_id

    def write(self, vals):
        if vals.get("reason_code_id"):
            vals["scrap_location_id"] = (
                self.env["scrap.reason.code"]
                .browse(vals["reason_code_id"])
                .location_id.id
            )
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reason_code_id"):
                vals["scrap_location_id"] = (
                    self.env["scrap.reason.code"]
                    .browse(vals["reason_code_id"])
                    .location_id.id
                )
        return super().create(vals_list)
