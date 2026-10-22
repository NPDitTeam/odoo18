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
                # จำนวนของจริง = Quantity Rent ถ้ามี ไม่มีค่อยใช้ product_uom_qty (กฎเดียวกับ api_transport ของ o14)
                # - ใบเช่า: product_uom_qty = Quantity Rent × จำนวนวัน ไม่ใช่จำนวนของ
                # - ใบ "ขาย" ของ Logistics: Quantity Rent = จำนวนของ, product_uom_qty = 1 (หน่วยคิดค่าขนส่ง)
                # - ใบขายที่ไม่ได้กรอก Quantity Rent (0) → ใช้ product_uom_qty
                'quantity': _g(line, 'pfb_quantity', 0) or line.product_uom_qty,
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
                # ประเภทการจัดส่งสินค้า + หมายเหตุ (โมดูล npd_shipment_purpose)
                'shipment_purpose': _g(order, 'shipment_purpose'),
                'shipment_note': _g(order, 'shipment_note'),
                'transfer_ref': order.transfer_ref_id.name if _g(order, 'transfer_ref_id') else None,
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
            # เลขเอกสาร SO ต้นทาง (ช่อง "เลขเอกสาร SO" บนใบ) — ไม่ส่งแล้วใบขนส่งจะว่าง
            # และหาใบคู่ไป/กลับ (trip_direction) ไม่เจอ
            'so_number': _g(order, 'so_number'),
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

    # ------------------------------------------------------------------
    # ใบที่ส่งเข้าระบบขนส่งแล้วถูกนำไปจองคิวรถ ห้ามลบ/ยกเลิกใบสั่งขาย
    # ต้องยกเลิกการจองคิวรถก่อน (หรือยังไม่ได้จอง) ถึงจะลบ/ยกเลิกได้
    # ------------------------------------------------------------------
    def _transport_active_bookings(self):
        """การจองคิวรถที่ยังไม่ยกเลิก ของคำสั่งขนส่งที่สร้างจากใบเหล่านี้ -> [(ใบสั่งขาย, เลขจอง, สถานะ)]

        ใช้ SQL ตรง เพราะ vehicle.booking กรองตามสาขาของผู้ใช้ใน _search (sudo ก็ยังโดนกรอง)
        คนต่างสาขาจะมองไม่เห็นการจองแล้วลบผ่าน ทั้งที่รถถูกจองไปแล้ว
        """
        names = [n for n in self.mapped('name') if n]
        if not names:
            return []
        self.env.cr.execute("SELECT to_regclass('vehicle_booking') IS NOT NULL")
        if not self.env.cr.fetchone()[0]:
            return []
        self.env['vehicle.booking'].flush_model() if 'vehicle.booking' in self.env else None
        self.env.cr.execute("""
            SELECT t.name, b.name, b.state
              FROM vehicle_booking b
              JOIN transport_order t ON t.id = b.transport_order_id
             WHERE t.is_from_odoo18 AND t.name = ANY(%s) AND b.state != 'cancelled'
             ORDER BY b.id
        """, (names,))
        return self.env.cr.fetchall()

    def _check_transport_booking_lock(self, action_label):
        rows = self._transport_active_bookings()
        if not rows:
            return
        states = {}
        if 'vehicle.booking' in self.env:
            states = dict(self.env['vehicle.booking']._fields['state']._description_selection(self.env))
        lines = '\n'.join('• %s → การจองคิวรถ %s (สถานะ: %s)' % (so, booking or '-', states.get(state, state))
                          for so, booking, state in rows)
        raise UserError(_(
            '❌ %(action)sไม่ได้ เพราะใบสั่งขายถูกนำไปจองคิวรถขนส่งแล้ว\n\n%(lines)s\n\n'
            'ต้องยกเลิกการจองคิวรถขนส่งก่อน จึงจะ%(action)sใบสั่งขายได้'
        ) % {'action': action_label, 'lines': lines})

    def _remove_transport_orders(self, names):
        """ลบ/ยกเลิกใบสั่งขาย -> ลบคำสั่งขนส่งที่สร้างจากใบนั้นออกด้วย (ข้อมูลขนส่งค้างจะถูกจองผิด)

        ถ้ายังมีการจองคิวรถที่ "ยกเลิกแล้ว" อ้างถึงอยู่ ลบไม่ได้ (ช่องบังคับ) -> ตั้งเป็นยกเลิกแทน
        """
        names = [n for n in names if n]
        if not names:
            return
        Transport = self.env['transport.order'].sudo().with_context(transport_sync_all_branches=True)
        transports = Transport.search([('name', 'in', names), ('is_from_odoo18', '=', True)])
        so_numbers = [n for n in transports.mapped('so_number') if n]
        for transport in transports:
            try:
                with self.env.cr.savepoint():
                    transport.unlink()
            except Exception as error:  # noqa: BLE001
                _logger.info("คำสั่งขนส่ง %s ลบไม่ได้ (%s) -> ตั้งเป็นยกเลิก", transport.name, error)
                transport.write({'state': 'cancel'})
        # ใบคู่ที่ใช้เลข SO เดียวกันอาจเคยเป็น "ไปกลับ" เพราะใบนี้ -> คำนวณใหม่
        if so_numbers:
            Transport._recompute_trip_direction_siblings(so_numbers)

    def unlink(self):
        self._check_transport_booking_lock(_('ลบ'))
        names = self.mapped('name')
        res = super().unlink()
        self._remove_transport_orders(names)
        return res

    def _action_cancel(self):
        self._check_transport_booking_lock(_('ยกเลิก'))
        res = super()._action_cancel()
        self._remove_transport_orders(self.mapped('name'))
        self.filtered('transport_sent').write({'transport_sent': False})
        return res

    def _check_transport_quantities(self):
        """ห้ามส่งสินค้าที่ไม่รู้จำนวนจริงไปให้คนขับ (ผู้ใช้สั่ง 22 ต.ค. 2569)

        - ใบเช่าที่ไม่ได้กรอก Quantity Rent: product_uom_qty คือ จำนวน × วัน ถ้าส่งไปคนขับจะเห็นเกินจริงหลายเท่า
        - สินค้าที่จำนวนออกมาเป็น 0
        บรรทัดค่าบริการ (ชื่อขึ้นต้น "ค่า" เช่น ค่าขนส่ง) และบรรทัดหัวข้อ/หมายเหตุ ไม่ตรวจ
        """
        self.ensure_one()
        goods = self.order_line.filtered(
            lambda l: l.product_id and not l.display_type
            and not (l.product_id.name or '').startswith('ค่า'))
        missing_rent = goods.filtered(
            lambda l: _g(self, 'pfb_so_type') == 'rent' and not _g(l, 'pfb_quantity', 0))
        zero = goods.filtered(lambda l: not (_g(l, 'pfb_quantity', 0) or l.product_uom_qty))
        if missing_rent or zero:
            names = '\n'.join('- %s' % l.product_id.display_name for l in (missing_rent | zero)[:15])
            head = (_('ใบเช่ายังไม่ได้ระบุ Quantity Rent (จำนวนสินค้าที่เช่า) กรุณาระบุก่อนส่งไปยังระบบขนส่ง')
                    if missing_rent else _('จำนวนสินค้ายังไม่ได้ระบุ กรุณาระบุก่อนส่งไปยังระบบขนส่ง'))
            raise UserError('%s\n\n%s' % (head, names))

    def action_send_to_transport(self):
        """ ส่งข้อมูลใบสั่งขายไปยังระบบขนส่งโดยตรง (ไม่ผ่าน API เพราะ db เดียวกัน)
            ส่งซ้ำ = อัพเดททับ record เดิม """
        self.ensure_one()

        if self.company_id.company_registry != NPD_LOGISTICS_REGISTRY:
            raise UserError(_("❌ ส่งได้เฉพาะบริษัท เอ็นพีดี โลจิสติกส์ จำกัด เท่านั้น"))
        if self.state != 'sale':
            raise UserError(_("❌ ส่งได้เฉพาะใบที่เป็นคำสั่งขายแล้ว"))
        self._check_transport_quantities()

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
