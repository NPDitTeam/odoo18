import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# company_registry ("ID บริษัท") ของบริษัท เอ็นพีดี โลจิสติกส์ จำกัด
NPD_LOGISTICS_REGISTRY = '5'


def _g(obj, attr, default=None):
    """ getattr ปลอดภัย (กัน field ไม่มี/ค่า False) """
    try:
        val = getattr(obj, attr, default)
    except Exception:
        return default
    return default if (val is False or val is None) else val


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    transport_sent = fields.Boolean(
        string='ส่งเข้าระบบขนส่งแล้ว', default=False, copy=False)

    # ใช้คุมการแสดงปุ่ม: เฉพาะบริษัท เอ็นพีดี โลจิสติกส์ จำกัด
    tr_is_npd_logistics = fields.Boolean(
        string='เป็นบริษัทเอ็นพีดี โลจิสติกส์',
        compute='_compute_tr_is_npd_logistics')

    @api.depends('company_id', 'company_id.company_registry')
    def _compute_tr_is_npd_logistics(self):
        for order in self:
            order.tr_is_npd_logistics = (
                order.company_id.company_registry == NPD_LOGISTICS_REGISTRY)

    def _prepare_transport_payload(self):
        """ สร้าง dict โครงสร้างเดียวกับ API /api/sale_orders ของ odoo14
            (ฝั่ง api_transport.controllers.sale_order_api) เป๊ะ
            เพื่อให้ transport.order ประมวลผลแบบเดียวกับการ sync จาก odoo14 """
        self.ensure_one()
        order = self

        order_lines = []
        for line in order.order_line:
            order_lines.append({
                'id': line.id,
                'product_id': line.product_id.id if line.product_id else None,
                'product_name': line.product_id.name if line.product_id else None,
                'product_code': line.product_id.default_code if line.product_id else None,
                'description': line.name or '',
                'quantity': line.product_uom_qty,
                'uom': line.product_uom.name if line.product_uom else None,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'price_subtotal': line.price_subtotal,
                'price_tax': line.price_tax,
                'price_total': line.price_total,
                'total_weight': _g(line, 'total_weight', 0.0),
            })

        shipment_information = {
            'basic': {
                'pickup_location': _g(order, 'pickup_location'),
                'destination': _g(order, 'destination'),
                'vehicle_type_id': order.vehicle_type_id.id if _g(order, 'vehicle_type_id') else None,
                'vehicle_type_name': order.vehicle_type_id.name if _g(order, 'vehicle_type_id') else None,
                'distance_km': _g(order, 'distance_km'),
                'shipping_cost_raw': _g(order, 'shipping_cost_raw'),
                'shipping_cost': _g(order, 'shipping_cost'),
                'shipping_cost_m': _g(order, 'shipping_cost_m'),
                'delivery_type': _g(order, 'delivery_type'),
                'trip_allowance': _g(order, 'trip_allowance'),
                'daily_allowance': _g(order, 'daily_allowance'),
                'use_special_delivery_zero': _g(order, 'use_special_delivery_zero'),
            },
            'vehicle_assignment': {
                'delivery_employee_id': order.delivery_employee_id.id if _g(order, 'delivery_employee_id') else None,
                'delivery_employee_name': order.delivery_employee_id.name if _g(order, 'delivery_employee_id') else None,
                'license_plate_id': order.license_plate_id.id if _g(order, 'license_plate_id') else None,
                'license_plate_name': order.license_plate_id.name if _g(order, 'license_plate_id') else None,
            },
            'fuel': {
                'fuel_price_per_liter': _g(order, 'fuel_price_per_liter'),
                'fuel_consumption_rate': _g(order, 'fuel_consumption_rate'),
                'fuel_used_per_trip': _g(order, 'fuel_used_per_trip'),
                'fuel_cost_per_trip': _g(order, 'fuel_cost_per_trip'),
            },
            'depreciation': {
                'vehicle': _g(order, 'vehicle'),
                'vehicle_cost': _g(order, 'vehicle_cost'),
                'salvage_value': _g(order, 'salvage_value'),
                'depreciation_period': _g(order, 'depreciation_period'),
                'depreciation_per_trip': _g(order, 'depreciation_per_trip'),
            },
            'annual_expenses': {
                'annual_vehicle_tax_y': _g(order, 'annual_vehicle_tax_y'),
                'annual_vehicle_tax': _g(order, 'annual_vehicle_tax'),
                'annual_insurance_class2': _g(order, 'annual_insurance_class2'),
                'annual_insurance_class1': _g(order, 'annual_insurance_class1'),
                'annual_compulsory_insurance1': _g(order, 'annual_compulsory_insurance1'),
                'annual_compulsory_insurance': _g(order, 'annual_compulsory_insurance'),
                'total_depreciation_per_trip': _g(order, 'total_depreciation_per_trip'),
            },
            'labor': {
                'labor_costs': _g(order, 'labor_costs'),
                'working_days_per_month': _g(order, 'working_days_per_month'),
                'driver_salary': _g(order, 'driver_salary'),
                'maintenance_cost': _g(order, 'maintenance_cost'),
                'trips_per_day': _g(order, 'trips_per_day'),
                'labor_cost_per_trip': _g(order, 'labor_cost_per_trip'),
                'total_labor_per_trip': _g(order, 'total_labor_per_trip'),
            },
            'other_expenses': {
                'other_expenses': _g(order, 'other_expenses'),
            },
            'cost_summary': {
                'total_cost_per_trip': _g(order, 'total_cost_per_trip'),
                'profit_per_trip': _g(order, 'profit_per_trip'),
                'profit_per_trip_p': _g(order, 'profit_per_trip_p'),
            },
        }

        return {
            'id': order.id,
            'name': order.name,
            'branch_id': order.branch_id.name if _g(order, 'branch_id') else None,
            'state': order.state,
            'date_order': order.date_order.strftime('%Y-%m-%d %H:%M:%S') if order.date_order else None,
            'validity_date': order.validity_date.strftime('%Y-%m-%d') if order.validity_date else None,
            'partner_id': order.partner_id.id if order.partner_id else None,
            'partner_name': order.partner_id.name if order.partner_id else None,
            'partner_phone': order.partner_id.phone if order.partner_id else None,
            'partner_email': order.partner_id.email if order.partner_id else None,
            'shipment_information': shipment_information,
            'amount_untaxed': order.amount_untaxed,
            'amount_tax': order.amount_tax,
            'amount_total': order.amount_total,
            'currency': order.currency_id.name if order.currency_id else 'THB',
            'user_id': order.user_id.id if order.user_id else None,
            'salesperson_name': order.user_id.name if order.user_id else None,
            'company_id': order.company_id.id if order.company_id else None,
            'company_name': order.company_id.name if order.company_id else None,
            'note': order.note or '',
            'is_renew_green_house': _g(order, 'is_renew_green_house', False),
            'order_lines': order_lines,
            'order_lines_count': len(order_lines),
        }

    def action_send_to_transport(self):
        """ ส่งข้อมูลใบสั่งขายไปยังระบบขนส่งโดยตรง (ไม่ผ่าน API เพราะ db เดียวกัน)
            ส่งซ้ำ = อัพเดททับ record เดิม """
        self.ensure_one()

        if self.company_id.company_registry != NPD_LOGISTICS_REGISTRY:
            raise UserError(_("❌ ส่งได้เฉพาะบริษัท เอ็นพีดี โลจิสติกส์ จำกัด เท่านั้น"))
        if self.state != 'sale':
            raise UserError(_("❌ ส่งได้เฉพาะใบที่เป็นคำสั่งขายแล้ว"))

        payload = self._prepare_transport_payload()
        transport, status = self.env['transport.order'].sudo()._receive_from_sale_order(payload)

        if status == 'skipped':
            # รายการเดิมถูกดึงไปใช้แล้ว/ลบไม่ได้ -> ข้ามการอัพเดท เพื่อป้องกันข้อมูลเสียหาย
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('ข้ามการอัพเดท'),
                    'message': _('คำสั่งขนส่ง %s ถูกดึงไปใช้งานแล้ว (แก้ไขไม่ได้) '
                                 'จึงข้ามการอัพเดทเพื่อป้องกันข้อมูลเสียหาย')
                                 % (transport.name if transport else self.name),
                    'type': 'warning',
                    'sticky': True,
                },
            }

        self.transport_sent = True
        msg = _('สร้างคำสั่งขนส่งแล้ว: %s') if status == 'created' \
            else _('อัพเดทคำสั่งขนส่งแล้ว: %s')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('สำเร็จ'),
                'message': msg % (transport.name if transport else self.name),
                'type': 'success',
                'sticky': False,
            },
        }
