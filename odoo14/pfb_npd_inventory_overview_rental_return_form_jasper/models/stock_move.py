from odoo import models, fields, api


class StockMove(models.Model):
    _inherit = 'stock.move'

    jasper_seq = fields.Integer(
        string='Sequence',
        compute='_compute_jasper_line',
    )
    jasper_line_name = fields.Char(
        string='Line Name',
        compute='_compute_jasper_line',
    )
    jasper_line_weight = fields.Float(
        string='Line Weight',
        compute='_compute_jasper_line',
    )
    jasper_line_price_unit = fields.Float(
        string='Line Price Unit',
        compute='_compute_jasper_line',
    )
    jasper_line_qty_rent = fields.Float(
        string='Qty Rent',
        compute='_compute_jasper_line',
    )
    jasper_line_qty_return = fields.Float(
        string='Qty Return',
        compute='_compute_jasper_line',
    )
    jasper_line_lost = fields.Float(
        string='Lost Amount',
        compute='_compute_jasper_line',
    )
    jasper_line_damaged = fields.Float(
        string='Damaged Amount',
        compute='_compute_jasper_line',
    )
    jasper_line_subtotal = fields.Float(
        string='Line Subtotal',
        compute='_compute_jasper_line',
    )

    def _compute_jasper_line(self):
        for move in self:
            move.jasper_seq = 0
            move.jasper_line_name = move.product_id.display_name if move.product_id else ''
            move.jasper_line_weight = 0.0
            move.jasper_line_price_unit = 0.0
            move.jasper_line_qty_rent = move.product_uom_qty or 0.0
            move.jasper_line_qty_return = move.product_uom_qty or 0.0
            move.jasper_line_lost = 0.0
            move.jasper_line_damaged = 0.0
            move.jasper_line_subtotal = 0.0

            picking = move.picking_id
            if not picking:
                continue

            so = picking.sale_id
            sale_line = move.sale_line_id
            if not sale_line and so:
                sale_line = so.order_line.filtered(
                    lambda l: l.product_id.id == move.product_id.id and l.price_subtotal >= 0
                )
                sale_line = sale_line[:1]

            if so:
                lines = so.order_line.filtered(lambda l: l.price_subtotal >= 0)
                move_products = picking.move_ids.mapped('product_id').ids
                matched = [l for l in lines if l.product_id.id in move_products]
                for idx, l in enumerate(matched):
                    if sale_line and l.id == sale_line.id:
                        move.jasper_seq = idx + 1
                        break

            if not sale_line:
                continue

            lost_amt, lost_qty, damaged_amt = 0.0, 0.0, 0.0
            if so:
                lost_amt, lost_qty, damaged_amt = self._get_line_debit_amounts(so, move.product_id.id)

            qty_rent = getattr(sale_line, 'pfb_quantity', 0.0) or 0.0
            if lost_amt == 0 and damaged_amt == 0:
                qty_return = qty_rent
            elif lost_amt:
                qty_return = qty_rent - lost_qty
            else:
                qty_return = qty_rent

            days_used = picking.jasper_days_used or 0
            subtotal = days_used * qty_rent * (sale_line.price_unit or 0.0)

            move.jasper_line_name = sale_line.name or move.product_id.display_name or ''
            move.jasper_line_weight = getattr(sale_line, 'second_uom_qty', 0.0) or 0.0
            move.jasper_line_price_unit = sale_line.price_unit or 0.0
            move.jasper_line_qty_rent = qty_rent
            move.jasper_line_qty_return = qty_return
            move.jasper_line_lost = lost_amt
            move.jasper_line_damaged = damaged_amt
            move.jasper_line_subtotal = subtotal

    @staticmethod
    def _get_line_debit_amounts(sale_order, product_id):
        lost_amt = 0.0
        lost_qty = 0.0
        damaged_amt = 0.0
        for inv in sale_order.invoice_ids:
            for de in getattr(inv, 'debit_note_ids', []):
                if de.state != 'posted':
                    continue
                reason = de.reason_code_id.name if hasattr(de, 'reason_code_id') and de.reason_code_id else ''
                for line in de.invoice_line_ids:
                    if line.product_id.id != product_id:
                        continue
                    for tag in getattr(line, 'analytic_tag_ids', []):
                        if tag.name == 'L' and reason == 'สินค้าหาย':
                            lost_amt += getattr(line, 'price_total_full', line.price_total)
                            lost_qty += line.quantity
                        elif tag.name == 'D' and reason == 'สินค้าชำรุด':
                            if getattr(line, 'is_lost_item', False):
                                damaged_amt += getattr(line, 'price_total_full', line.price_total)
                            else:
                                damaged_amt += getattr(line, 'price_subtotal_without_discount', line.price_subtotal)
        return lost_amt, lost_qty, damaged_amt
