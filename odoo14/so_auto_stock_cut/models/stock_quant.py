# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.tools.float_utils import float_compare, float_is_zero
import logging

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _update_reserved_quantity(self, product_id, location_id, quantity,
                                  lot_id=None, package_id=None, owner_id=None,
                                  strict=False):
        """
        Override: เมื่อ unreserve (quantity < 0) ถ้า reserved ไม่พอ
        ให้ cap ค่าแทนที่จะ raise error
        แก้ปัญหา "It is not possible to unreserve more products than you have in stock"
        ที่เกิดจาก reserved_quantity desync กับ stock.move.line
        """
        self = self.sudo()
        rounding = product_id.uom_id.rounding
        quants = self._gather(product_id, location_id, lot_id=lot_id,
                              package_id=package_id, owner_id=owner_id,
                              strict=strict)
        reserved_quants = []

        if float_compare(quantity, 0, precision_rounding=rounding) > 0:
            # Reserve: ใช้ logic เดิมของ Odoo
            available_quantity = (
                sum(quants.filtered(
                    lambda q: float_compare(q.quantity, 0, precision_rounding=rounding) > 0
                ).mapped('quantity'))
                - sum(quants.mapped('reserved_quantity'))
            )
            if float_compare(quantity, available_quantity, precision_rounding=rounding) > 0:
                raise models.UserError(
                    _('It is not possible to reserve more products of %s than you have in stock.',
                      product_id.display_name))

        elif float_compare(quantity, 0, precision_rounding=rounding) < 0:
            # Unreserve: แทนที่จะ raise error ให้ cap ค่า
            available_quantity = sum(quants.mapped('reserved_quantity'))
            if float_compare(abs(quantity), available_quantity, precision_rounding=rounding) > 0:
                _logger.warning(
                    "⚠️ Unreserve capped: %s tried to unreserve %.2f but only %.2f reserved. "
                    "Capping to available. (location=%s)",
                    product_id.display_name, abs(quantity), available_quantity,
                    location_id.complete_name,
                )
                # Cap: unreserve เท่าที่มี แทนที่จะ error
                quantity = -available_quantity
                if float_is_zero(available_quantity, precision_rounding=rounding):
                    return reserved_quants
        else:
            return reserved_quants

        for quant in quants:
            if float_compare(quantity, 0, precision_rounding=rounding) > 0:
                max_quantity_on_quant = quant.quantity - quant.reserved_quantity
                if float_compare(max_quantity_on_quant, 0, precision_rounding=rounding) <= 0:
                    continue
                max_quantity_on_quant = min(max_quantity_on_quant, quantity)
                quant.reserved_quantity += max_quantity_on_quant
                reserved_quants.append((quant, max_quantity_on_quant))
                quantity -= max_quantity_on_quant
                available_quantity -= max_quantity_on_quant
            else:
                max_quantity_on_quant = min(quant.reserved_quantity, abs(quantity))
                quant.reserved_quantity -= max_quantity_on_quant
                reserved_quants.append((quant, -max_quantity_on_quant))
                quantity += max_quantity_on_quant
                available_quantity += max_quantity_on_quant

            if float_is_zero(quantity, precision_rounding=rounding) or \
               float_is_zero(available_quantity, precision_rounding=rounding):
                break

        return reserved_quants
