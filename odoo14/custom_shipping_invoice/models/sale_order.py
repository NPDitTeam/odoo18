import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # หมายเหตุ: shipping_cost / shipping_cost_m / use_special_delivery_zero
    # ถูกกำหนดในโมดูล pfb_npd_tap_shipment_information แล้ว
    # ส่วน start_rent_date / end_rent_date อยู่ใน pfb_npd_add_date_quatation_order แล้ว
    # จึงไม่ต้องนิยามซ้ำที่นี่
    shipping_invoice_id = fields.Many2one('account.move', string="Shipping Invoice")

    def action_open_shipping_popup(self):
        """
        เปิด Popup สำหรับสร้าง Invoice ค่าขนส่ง
        เลือกใช้ค่า: shipping_cost_m (ถ้า > 0) หรือ shipping_cost
        """
        self.ensure_one()

        # 1) ตรวจสอบและดึงสินค้าค่าขนส่ง
        shipping_product = self.env['product.product'].search(
            [('default_code', '=', 'PR/00363')], limit=1)
        if not shipping_product:
            raise ValidationError(_("ไม่พบสินค้าค่าขนส่ง รหัส PR/00363"))

        # 2) เงื่อนไขการคำนวณ final_shipping_cost
        final_shipping_cost = 0.0

        if self.use_special_delivery_zero and self.shipping_cost_m == 0:
            final_shipping_cost = self.shipping_cost_m
        elif not self.use_special_delivery_zero and self.shipping_cost_m > 0:
            final_shipping_cost = self.shipping_cost_m
        elif not self.use_special_delivery_zero and self.shipping_cost_m == 0:
            final_shipping_cost = self.shipping_cost
        else:
            final_shipping_cost = self.shipping_cost

        _logger.info("Final shipping cost for popup: %s (SO: %s)", final_shipping_cost, self.name)

        return {
            'name': _('สร้างใบค่าขนส่ง'),
            'type': 'ir.actions.act_window',
            'res_model': 'popup.shipping.invoice',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_shipping_cost': final_shipping_cost,
                'default_shipping_product_id': shipping_product.id,
            },
        }

    def action_view_shipping_invoice(self):
        """ เปิดหน้าต่างดู Invoice ค่าขนส่ง """
        self.ensure_one()
        if self.shipping_invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': self.shipping_invoice_id.id,
                'target': 'current',
            }


class PopupShippingInvoice(models.TransientModel):
    _name = 'popup.shipping.invoice'
    _description = 'Popup for Creating Invoice with Shipping Cost'

    order_id = fields.Many2one('sale.order', string="Order")
    shipping_cost = fields.Float(string="Shipping Cost")
    shipping_product_id = fields.Many2one('product.product', string="Shipping Product")

    def _create_invoice(self):
        self.ensure_one()
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.order_id.partner_id.id,
            'invoice_origin': self.order_id.name,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.shipping_product_id.id,
                'name': self.shipping_product_id.name,
                'quantity': 1,
                'price_unit': self.shipping_cost,
            })],
        })
        self.order_id.write({'shipping_invoice_id': invoice.id})
        return invoice

    def action_create_invoice(self):
        self._create_invoice()
        return {'type': 'ir.actions.act_window_close'}

    def action_create_view_invoice(self):
        invoice = self._create_invoice()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
            'target': 'current',
        }
