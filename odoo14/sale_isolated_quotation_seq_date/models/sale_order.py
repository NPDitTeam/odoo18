# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def create(self, vals):
        order_sequence = vals.get("order_sequence") or self.env.context.get(
            "order_sequence"
        )
        if not order_sequence and vals.get("name", "/") == "/":
            vals["name"] = (
                self.env["ir.sequence"].next_by_code(
                    "sale.quotation",
                    sequence_date=vals.get("date_order", None),
                )
                or "/"
            )
        return super().create(vals)

    def _prepare_order_from_quotation(self):
        return {
            "name": (
                self.env["ir.sequence"].next_by_code(
                    "sale.order",
                    sequence_date=self.date_order,
                )
                or "/"
            ),
            "order_sequence": True,
            "quote_id": self.id,
            "client_order_ref": self.client_order_ref,
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.onchange('product_uom', 'product_uom_qty')
    def product_uom_change(self):
        price_unit = self.price_unit
        if hasattr(super(), 'product_uom_change'):
            super().product_uom_change()
        if price_unit >= 1:
            self.price_unit = price_unit
