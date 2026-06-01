import requests
import logging
import math
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ShipmentInformation(models.Model):
    _inherit = 'sale.order'

    delivery_type = fields.Selection([
        ('customer', 'จัดส่งไปยังลูกค้า'),
        ('branch', 'จัดส่งมายังสาขา'),
    ], string='ประเภทการจัดส่ง', default='customer', required=True, tracking=True)

    pickup_location = fields.Char(string='ต้นทาง')
    destination = fields.Char(string='ปลายทาง')
    vehicle_type_id = fields.Many2one('shipping.cost', string='ประเภทรถ')

    distance_km = fields.Float(string='ระยะทาง (km)', compute='_compute_distance', store=True)
    shipping_cost_raw = fields.Float(string='ค่าขนส่งก่อนปัดเศษ', compute='_compute_shipping_cost', store=True, readonly=False)
    shipping_cost = fields.Float(string='ค่าขนส่งหลังปัดเศษ', compute='_compute_shipping_cost', store=True, readonly=True)

    use_special_delivery_zero = fields.Boolean(string='ใช้ค่าขนส่งพิเศษที่เป็น 0', default=False)
    shipping_cost_m = fields.Float(string='ค่าขนส่งพิเศษ', store=True)
    delivery_employee_id = fields.Many2one('hr.employee', string='พนักงานส่งของ')
    license_plate_id = fields.Many2one('fleet.license_plate', string='ป้ายทะเบียนรถ', domain=[('active', '=', True)])

    trip_allowance = fields.Float(string='ค่าเที่ยว (บาท)', compute='_compute_trip_allowance', store=True, readonly=True)
    daily_allowance = fields.Float(string='ค่าเบี้ยเลี้ยง (บาท)', compute='_compute_daily_allowance', store=True, readonly=True)

    # Fuel
    fuel_price_per_liter = fields.Float(string='ค่าน้ำมันเชื้อเพลิง (บาท/ลิตร)', related='vehicle_type_id.fuel_price_per_liter', store=True, readonly=False)
    fuel_consumption_rate = fields.Float(string='อัตราสิ้นเปลืองเชื้อเพลิง (กม./ลิตร)', related='vehicle_type_id.fuel_consumption_rate', store=True, readonly=False)
    fuel_used_per_trip = fields.Float(string='น้ำมันที่ใช้ต่อเที่ยวไป-กลับ (ลิตร)', compute='_compute_fuel_used', store=True)
    fuel_cost_per_trip = fields.Float(string='ค่าน้ำมันเที่ยวไปกลับ (บาท)', compute='_compute_fuel_cost', store=True)

    # Depreciation
    vehicle = fields.Float(string='ต้นทุนค่ารถ', related='vehicle_type_id.vehicle', store=True, readonly=False)
    vehicle_cost = fields.Float(string='ต้นทุนค่ารถดอกเบี้ย (บาท)', compute='_compute_vehicle_cost', store=True)
    salvage_value = fields.Float(string='มูลค่าซาก (บาท)', related='vehicle_type_id.salvage_value', store=True, readonly=False)
    depreciation_period = fields.Integer(string='ระยะเวลาค่าเสื่อมราคา (ปี)', related='vehicle_type_id.depreciation_period', store=True, readonly=False)
    depreciation_per_trip = fields.Float(string='ค่าเสื่อมตัวรถต่อรอบ (บาท)', compute='_compute_depreciation_per_trip', store=True)

    annual_vehicle_tax_y = fields.Float(string='ค่าภาษีป้ายวงกลม (บาท/ปี)', related='vehicle_type_id.annual_vehicle_tax_y', store=True, readonly=False)
    annual_vehicle_tax = fields.Float(string='ค่าภาษีป้ายวงกลม (บาท/วัน)', compute='_compute_annual_vehicle_tax', store=True)
    annual_insurance_class2 = fields.Float(string='ค่าเบี้ยประกันชั้น', related='vehicle_type_id.annual_insurance_class2', store=True, readonly=False)
    annual_insurance_class1 = fields.Float(string='ประกันชั้น 1 (บาท/วัน)', compute='_compute_annual_insurance_class1', store=True)
    annual_compulsory_insurance1 = fields.Float(string='ค่าประกัน พรบ', related='vehicle_type_id.annual_compulsory_insurance1', store=True, readonly=False)
    annual_compulsory_insurance = fields.Float(string='ค่าประกัน พรบ. (บาท/วัน)', compute='_compute_annual_compulsory_insurance', store=True)
    total_depreciation_per_trip = fields.Float(string='รวมค่าเสื่อมต่อรอบ (บาท)', compute='_compute_total_depreciation_per_trip', store=True)

    # Labor
    labor_costs = fields.Integer(string='ค่าแรง', related='vehicle_type_id.labor_costs', store=True, readonly=False)
    working_days_per_month = fields.Integer(string='จำนวนวันทำงาน/เดือน', related='vehicle_type_id.working_days_per_month', store=True, readonly=False)
    driver_salary = fields.Float(string='เงินเดือน (บาท/เดือน)', related='vehicle_type_id.driver_salary', store=True, readonly=False)
    maintenance_cost = fields.Float(string='ค่าซ่อมบำรุง (บาท/เดือน)', related='vehicle_type_id.maintenance_cost', store=True, readonly=False)
    trips_per_day = fields.Integer(string='จำนวนรอบที่วิ่ง/วัน', related='vehicle_type_id.trips_per_day', store=True, readonly=False)
    labor_cost_per_trip = fields.Float(string='ค่าแรง พนง.ขับรถ/เที่ยว (บาท)', related='vehicle_type_id.labor_cost_per_trip', store=True, readonly=False)
    other_expenses = fields.Float(string='ค่าใช้จ่ายอื่นๆ (บาท/รอบ)', related='vehicle_type_id.other_expenses', store=True, readonly=False)
    total_labor_per_trip = fields.Float(string='ค่าแรงต่อรอบ (บาท)', compute='_compute_total_labor_per_trip', store=True)

    # Summary
    total_cost_per_trip = fields.Float(string='ราคาต้นทุน (บาท/รอบ)', compute='_compute_total_cost_per_trip', store=True)
    profit_per_trip = fields.Float(string='กำไร (บาท/รอบ)', compute='_compute_profit_per_trip', store=True)
    profit_per_trip_p = fields.Float(string='กำไร% (บาท/รอบ)')

    @api.onchange('delivery_type')
    def _onchange_delivery_type(self):
        if self.pickup_location or self.destination:
            old_pickup = self.pickup_location
            self.pickup_location = self.destination
            self.destination = old_pickup

    @api.onchange('vehicle_type_id')
    def _onchange_vehicle_type_id_profit(self):
        if self.vehicle_type_id and self.vehicle_type_id.profit_per_trip_p:
            self.profit_per_trip_p = self.vehicle_type_id.profit_per_trip_p

    @api.onchange('profit_per_trip_p')
    def _onchange_profit_per_trip_p(self):
        if self.profit_per_trip_p and self.total_cost_per_trip:
            self.profit_per_trip = self.total_cost_per_trip * (self.profit_per_trip_p / 100)
            self.shipping_cost_raw = self.total_cost_per_trip + self.profit_per_trip
            if self.shipping_cost_raw > 0:
                remainder = self.shipping_cost_raw % 100
                if remainder >= 50:
                    self.shipping_cost = math.ceil(self.shipping_cost_raw / 100) * 100
                else:
                    self.shipping_cost = math.floor(self.shipping_cost_raw / 100) * 100

    def _get_distance_km(self, pickup, destination):
        """ เรียก Google Routes API คืนระยะทาง (กม.) คืน 0.0 หากกรอกไม่ครบหรือเกิดข้อผิดพลาด """
        if not pickup or not destination:
            return 0.0
        try:
            google_api_key = "AIzaSyCHKkMOyDdI29v52SULcRx_OcB3i-MD7lw"
            url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": google_api_key,
                "X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,duration,condition,status",
            }
            payload = {
                "origins": [{"waypoint": {"address": pickup}}],
                "destinations": [{"waypoint": {"address": destination}}],
                "travelMode": "DRIVE",
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            data = response.json()
            _logger.info("Google Routes API [%s] -> %s", response.status_code, data)
            if response.status_code == 200 and data and "distanceMeters" in data[0]:
                return data[0]["distanceMeters"] / 1000.0
            # ไม่มี distanceMeters มักเกิดจากที่อยู่ไม่สมบูรณ์/หาเส้นทางไม่ได้ (condition=ROUTE_NOT_FOUND)
            _logger.warning(
                "Google Routes API: หาระยะทางไม่ได้ (ที่อยู่อาจไม่สมบูรณ์) "
                "ต้นทาง=%r ปลายทาง=%r ผลลัพธ์=%s", pickup, destination, data
            )
            return 0.0
        except Exception as e:
            _logger.error("Google Routes API Error: %s", e)
            return 0.0

    @api.depends('pickup_location', 'destination')
    def _compute_distance(self):
        for order in self:
            order.distance_km = order._get_distance_km(order.pickup_location, order.destination)

    @api.onchange('pickup_location', 'destination')
    def _onchange_locations_compute_distance(self):
        """ คำนวณระยะทาง + ค่าเที่ยว/เบี้ยเลี้ยงทันที เมื่อกรอกต้นทาง-ปลายทางในฟอร์ม (ไม่ต้องรอ save) """
        for order in self:
            order.distance_km = order._get_distance_km(order.pickup_location, order.destination)
            order._compute_trip_allowance()
            order._compute_daily_allowance()

    @api.depends('vehicle_type_id', 'distance_km')
    def _compute_trip_allowance(self):
        for record in self:
            record.trip_allowance = 0.0
            if not record.vehicle_type_id or not record.distance_km or record.distance_km >= 100:
                continue
            vehicle_name = record.vehicle_type_id.name or ''
            if '4 ล้อ' in vehicle_name:
                record.trip_allowance = 45.0
            elif '6 ล้อ' in vehicle_name:
                record.trip_allowance = 60.0
            elif '10 ล้อ' in vehicle_name:
                record.trip_allowance = 75.0

    @api.depends('distance_km')
    def _compute_daily_allowance(self):
        for record in self:
            if record.distance_km and record.distance_km >= 100:
                record.daily_allowance = 210.0
            else:
                record.daily_allowance = 0.0

    @api.depends('distance_km', 'fuel_consumption_rate')
    def _compute_fuel_used(self):
        for record in self:
            record.fuel_used_per_trip = (record.distance_km * 2) / record.fuel_consumption_rate if record.fuel_consumption_rate else 0.0

    @api.depends('fuel_used_per_trip', 'fuel_price_per_liter')
    def _compute_fuel_cost(self):
        for record in self:
            record.fuel_cost_per_trip = record.fuel_used_per_trip * record.fuel_price_per_liter

    @api.depends('vehicle')
    def _compute_vehicle_cost(self):
        for record in self:
            record.vehicle_cost = record.vehicle * 12 / 100 / 12 / 30 / 4 if record.vehicle else 0.0

    @api.depends('vehicle_cost', 'vehicle', 'salvage_value', 'depreciation_period')
    def _compute_depreciation_per_trip(self):
        for record in self:
            if record.vehicle and record.salvage_value:
                period = record.depreciation_period or 5
                record.depreciation_per_trip = record.vehicle_cost + (record.vehicle - record.salvage_value) / period / 12 / 30 / 4
            else:
                record.depreciation_per_trip = record.vehicle_cost

    @api.depends('annual_vehicle_tax_y')
    def _compute_annual_vehicle_tax(self):
        for record in self:
            record.annual_vehicle_tax = record.annual_vehicle_tax_y / 12 / 30 if record.annual_vehicle_tax_y else 0.0

    @api.depends('annual_insurance_class2')
    def _compute_annual_insurance_class1(self):
        for record in self:
            record.annual_insurance_class1 = record.annual_insurance_class2 / 365 if record.annual_insurance_class2 else 0.0

    @api.depends('annual_compulsory_insurance1')
    def _compute_annual_compulsory_insurance(self):
        for record in self:
            record.annual_compulsory_insurance = record.annual_compulsory_insurance1 / 365 if record.annual_compulsory_insurance1 else 0.0

    @api.depends('depreciation_per_trip', 'annual_vehicle_tax', 'annual_insurance_class1', 'annual_compulsory_insurance')
    def _compute_total_depreciation_per_trip(self):
        for record in self:
            record.total_depreciation_per_trip = (record.depreciation_per_trip + record.annual_vehicle_tax + record.annual_insurance_class1 + record.annual_compulsory_insurance) / 4

    @api.depends('labor_cost_per_trip', 'maintenance_cost', 'distance_km', 'other_expenses')
    def _compute_total_labor_per_trip(self):
        for record in self:
            record.total_labor_per_trip = record.labor_cost_per_trip + (record.maintenance_cost * record.distance_km * 2) + record.other_expenses

    @api.depends('fuel_cost_per_trip', 'total_depreciation_per_trip', 'total_labor_per_trip')
    def _compute_total_cost_per_trip(self):
        for record in self:
            record.total_cost_per_trip = record.fuel_cost_per_trip + record.total_depreciation_per_trip + record.total_labor_per_trip

    @api.depends('total_cost_per_trip', 'profit_per_trip_p')
    def _compute_profit_per_trip(self):
        for record in self:
            record.profit_per_trip = record.total_cost_per_trip * (record.profit_per_trip_p / 100) if record.profit_per_trip_p else 0.0

    @api.depends('distance_km', 'vehicle_type_id', 'total_cost_per_trip', 'profit_per_trip')
    def _compute_shipping_cost(self):
        for record in self:
            if not record.distance_km or not record.vehicle_type_id:
                record.shipping_cost_raw = 0.0
                record.shipping_cost = 0.0
                continue
            record.shipping_cost_raw = (record.total_cost_per_trip or 0.0) + (record.profit_per_trip or 0.0)
            if record.shipping_cost_raw > 0:
                remainder = record.shipping_cost_raw % 100
                record.shipping_cost = math.ceil(record.shipping_cost_raw / 100) * 100 if remainder >= 50 else math.floor(record.shipping_cost_raw / 100) * 100
            else:
                record.shipping_cost = 0.0

    def action_fix_allowances(self):
        for record in self:
            record._compute_trip_allowance()
            record._compute_daily_allowance()
            record._compute_total_labor_per_trip()
            record._compute_total_cost_per_trip()
            record._compute_profit_per_trip()
            record._compute_shipping_cost()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'สำเร็จ', 'message': 'คำนวณใหม่เรียบร้อยแล้ว', 'type': 'success', 'sticky': False},
        }
