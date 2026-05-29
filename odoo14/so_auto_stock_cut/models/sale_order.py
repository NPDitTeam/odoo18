from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    return_greenhome_state = fields.Selection([
        ('none', '—'),
        ('processing', 'กำลังคืนบ้านเขียว'),
        ('done', 'คืนสำเร็จ'),
        ('error', 'คืนล้มเหลว'),
    ], string='สถานะการคืนบ้านเขียว', default='none', tracking=True)

    def action_auto_validate_delivery(self):
        self.ensure_one()
        lines = []
        for picking in self.picking_ids.filtered(lambda p: p.state in ['draft', 'waiting', 'confirmed']):
            # Odoo 18: move_ids แทน move_ids_without_package
            for move in picking.move_ids:
                sol = self.order_line.filtered(lambda l: l.product_id.id == move.product_id.id)
                if sol and sol[0].pfb_quantity > 0:
                    lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'quantity': sol[0].pfb_quantity,
                        'location_name': picking.location_id.display_name,
                    }))
        return {
            'name': 'ยืนยันตัดสต๊อก',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.cut.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_confirm_line_ids': lines,
            }
        }
