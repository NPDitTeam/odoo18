from odoo import api, fields, models


class ShippingCost(models.Model):
    _name = 'shipping.cost'
    _description = 'การตั้งค่าค่าขนส่ง'

    name = fields.Char(string='ชื่อ', compute='_compute_name', store=True)
    vehicle_type = fields.Selection([
        ('4wheels', '🚚 รถบรรทุก 4 ล้อ'),
        ('6wheels', '🚛 รถบรรทุก 6 ล้อ'),
        ('6wheels_s', '🚛 รถบรรทุก 6 ล้อเฮี๊ยบ'),
        ('10wheels', '🚛 รถบรรทุก 10 ล้อ'),
    ], string='ประเภทรถ', required=True)
    fuel_price_per_liter = fields.Float(string='ค่าน้ำมันเชื้อเพลิง (บาท/ลิตร)')
    fuel_consumption_rate = fields.Float(string='อัตราสิ้นเปลืองเชื้อเพลิง (กม./ลิตร)')
    vehicle = fields.Float(string='ต้นทุนค่ารถ')
    salvage_value = fields.Float(string='มูลค่าซาก (บาท)')
    depreciation_period = fields.Integer(string='ระยะเวลาค่าเสื่อมราคา (ปี)')
    labor_costs = fields.Integer(string='ค่าแรง')
    working_days_per_month = fields.Integer(string='จำนวนวันทำงานต่อเดือน')
    driver_salary = fields.Float(string='เงินเดือน (บาท/เดือน)')
    maintenance_cost = fields.Float(string='ค่าซ่อมบำรุง (บาท/เดือน)')
    trips_per_day = fields.Integer(string='จำนวนรอบที่วิ่ง/วัน')
    labor_cost_per_trip = fields.Float(string='คิดค่าแรงให้ พนง.ขับรถต่อเที่ยว (บาท)')
    other_expenses = fields.Float(string='ค่าใช้จ่ายอื่นๆ (บาท/รอบ)')
    profit_per_trip_p = fields.Float(string='กำไร% (บาท/รอบ)')
    annual_insurance_class2 = fields.Float(string='ค่าเบี้ยประกันชั้น')
    annual_compulsory_insurance1 = fields.Float(string='ค่าประกัน พรบ')
    annual_vehicle_tax_y = fields.Float(string='ค่าภาษีป้ายวงกลม (บาท/ปี)')

    @api.depends('vehicle_type')
    def _compute_name(self):
        vehicle_names = {
            '4wheels': '🚚 รถบรรทุก 4 ล้อ',
            '6wheels': '🚛 รถบรรทุก 6 ล้อ',
            '6wheels_s': '🚛 รถบรรทุก 6 ล้อเฮี๊ยบ',
            '10wheels': '🚛 รถบรรทุก 10 ล้อ',
        }
        for record in self:
            record.name = vehicle_names.get(record.vehicle_type, 'ไม่ระบุ')
