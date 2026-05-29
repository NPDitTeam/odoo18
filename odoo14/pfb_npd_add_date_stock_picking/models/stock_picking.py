from odoo import api, fields, models
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    start_x_date = fields.Date(
        string='วันที่เริ่มต้นการเช่า',
        compute='_compute_rent_dates',
        store=True,
        readonly=False,
    )
    end_x_date = fields.Date(
        string='วันที่สิ้นสุดการเช่า',
        compute='_compute_rent_dates',
        store=True,
        readonly=False,
    )
    branch_id = fields.Many2one('res.branch', string='Branch')

    deposit_return_state = fields.Selection(
        selection=[
            ('not_returned', 'ยังไม่คืนเงิน'),
            ('returned', 'คืนเงินแล้ว'),
        ],
        string='สถานะการคืนเงินประกัน',
        default='not_returned',
        store=True,
    )

    no_deduction = fields.Boolean(string="ไม่หักค่าประกัน", default=False)

    return_date = fields.Datetime(
        string='วันที่และเวลาคืน',
        help='วันที่และเวลาคืนสินค้า',
        default=lambda self: fields.Datetime.now(),
        copy=False,
        tracking=True,
    )

    is_return_date_readonly = fields.Boolean(
        string='Return Date is Readonly',
        compute='_compute_is_return_date_readonly',
    )

    @api.depends('create_uid')
    def _compute_is_return_date_readonly(self):
        for rec in self:
            rec.is_return_date_readonly = not getattr(rec.env.user, 'can_edit_force_date', False)

    @api.depends('branch_id', 'origin', 'backorder_id')
    def _compute_rent_dates(self):
        for picking in self:
            start_date = False
            end_date = False
            sale_order = False

            if 'sale_id' in picking._fields and picking.sale_id:
                sale_order = picking.sale_id

            if not sale_order and picking.origin:
                sale_order = self.env['sale.order'].search([
                    ('name', '=', picking.origin)
                ], limit=1)

            if not sale_order and picking.backorder_id:
                current = picking.backorder_id
                visited = set()
                while current and current.id not in visited and not sale_order:
                    visited.add(current.id)
                    if 'sale_id' in current._fields and current.sale_id:
                        sale_order = current.sale_id
                        break
                    if current.origin:
                        sale_order = self.env['sale.order'].search([
                            ('name', '=', current.origin)
                        ], limit=1)
                        if sale_order:
                            break
                    current = current.backorder_id

            if sale_order and 'start_rent_date' in sale_order._fields:
                start_date = sale_order.start_rent_date
                end_date = sale_order.end_rent_date

            picking.start_x_date = start_date
            picking.end_x_date = end_date

    @api.model
    def create(self, vals):
        picking = super().create(vals)
        return picking

    def write(self, vals):
        res = super().write(vals)
        if 'branch_id' in vals:
            self._compute_rent_dates()
        return res

    def update_location_from_branch(self):
        for picking in self:
            origin_prefix = picking.origin[:2] if picking.origin else ''

            if picking.group_id and picking.group_id.name:
                group_name = picking.group_id.name[:2]
            else:
                group_name = ''

            if group_name == 'SO':
                if picking.branch_id:
                    default_location = self.env['stock.location'].search([
                        ('branch_id', '=', picking.branch_id.id),
                        ('usage', '=', 'internal'),
                    ], limit=1)

                    sale_order = self.env['sale.order'].search([
                        ('name', '=', picking.origin)
                    ], limit=1)

                    if default_location:
                        picking.start_x_date = sale_order.start_rent_date
                        picking.end_x_date = sale_order.end_rent_date

                        for move_line in picking.move_line_ids:
                            if move_line.location_dest_id != default_location:
                                if "IN" in picking.name.upper():
                                    move_line.location_dest_id = default_location.id

            if origin_prefix == 'SR':
                stock_request = self.env['stock.request'].search([
                    ('name', '=', picking.origin)
                ], limit=1)
                default_location = self.env['stock.location'].search([
                    ('id', '=', stock_request.location_src_id.id)
                ], limit=1)

                if default_location:
                    picking.write({
                        'branch_id': self.env.user.branch_id.id,
                    })
                    if picking.location_dest_id:
                        default_location = picking.location_dest_id

                        move_lines = self.env['stock.move'].search([
                            ('picking_id', '=', picking.id)
                        ])

                        for move in move_lines:
                            if not move.move_line_ids:
                                self.env['stock.move.line'].create({
                                    'move_id': move.id,
                                    'picking_id': picking.id,
                                    'product_id': move.product_id.id,
                                    'product_uom_id': move.product_uom.id,
                                    'quantity': move.product_uom_qty,
                                    'location_id': default_location.id,
                                    'location_dest_id': picking.location_dest_id.id,
                                })

                        for move_line in picking.move_line_ids:
                            if "IN" in picking.name.upper():
                                move_line.location_dest_id = picking.location_dest_id.id

        return True

    def action_assign(self):
        res = super().action_assign()
        self.update_location_from_branch()

        if self.env.cr.dbname != 'NPD_Logistics_New':
            for picking in self:
                out_of_stock = []
                branch_name = picking.branch_id.name or 'ไม่ทราบสาขา'
                for move in picking.move_ids:
                    if move.state == 'confirmed' and move.quantity <= 0:
                        out_of_stock.append(
                            f"- {move.product_id.display_name} ({move.product_uom_qty} {move.product_uom.name}) สาขา: {branch_name}"
                        )

                if out_of_stock:
                    msg = "\n".join(out_of_stock)
                    raise UserError(f"พบสินค้าที่ไม่มีสต็อกในสาขา ไม่สามารถจองได้:\n\n{msg}")

        return res


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    @api.model
    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move):
        vals = super()._prepare_stock_return_picking_line_vals_from_move(stock_move)
        quantity = stock_move.quantity
        for move in stock_move.move_dest_ids:
            if move.origin_returned_move_id and move.origin_returned_move_id == stock_move:
                if move.state in ('partially_available', 'assigned', 'confirmed', 'done'):
                    quantity -= sum(move.move_line_ids.mapped('quantity'))
        vals['quantity'] = max(quantity, 0.0)
        return vals

    def _prepare_picking_default_values(self):
        vals = super()._prepare_picking_default_values()
        src = self.picking_id
        if not src:
            return vals
        fields_to_copy = [
            'rent_discount',
            'approval_state',
            'approver_id',
            'approval_note',
            'request_note',
            'start_x_date',
            'end_x_date',
            'branch_id',
        ]
        for fname in fields_to_copy:
            if fname in src._fields:
                value = src[fname]
                if hasattr(value, 'id'):
                    value = value.id
                if value:
                    vals[fname] = value
        return vals
