# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
import logging
import requests
import json

_logger = logging.getLogger(__name__)


# ==================== บริษัทรถร่วม ====================
class VehiclePartnerCompany(models.Model):
    _name = 'vehicle.partner.company'
    _description = 'Vehicle Partner Company'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char('ชื่อบริษัท', required=True, tracking=True)
    code = fields.Char('รหัสบริษัท', copy=False, tracking=True)
    company_type = fields.Selection([
        ('partner', 'รถร่วม'),
        # ('rental', 'รถเช่า'),
    ], string='ประเภทบริษัท', default='partner', required=True, tracking=True)
    persona = fields.Selection([
        ('person', 'บุคคล'),
        ('corporation', 'นิติบุคคล'),
    ], string='ประเภทผู้บริการ', default='person', required=True, tracking=True)

    contact_person = fields.Char('ผู้ติดต่อ')
    phone = fields.Char('เบอร์โทรศัพท์')
    email = fields.Char('อีเมล')
    street = fields.Char('ที่อยู่')
    city = fields.Char('เมือง/อำเภอ')
    state_id = fields.Many2one('res.country.state', string='จังหวัด')
    tax_id = fields.Char('เลขประจำตัวผู้เสียภาษี')
    active = fields.Boolean('Active', default=True)
    vehicle_ids = fields.One2many('fleet.vehicle', 'partner_company_id', string='รถทั้งหมด')
    vehicle_count = fields.Integer('จำนวนรถ', compute='_compute_vehicle_count')
    note = fields.Html('หมายเหตุ')
    branch_id = fields.Many2one('res.branch', string='สาขา')

    @api.depends('vehicle_ids')
    def _compute_vehicle_count(self):
        for record in self:
            record.vehicle_count = len(record.vehicle_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('vehicle.partner.company') or 'VPC-NEW'
        return super().create(vals_list)

    def action_view_vehicles(self):
        return {
            'name': f'รถของ {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle',
            'view_mode': 'list,form',
            'domain': [('partner_company_id', '=', self.id)],
        }


# ==================== ประเภทน้ำมันเครื่อง ====================
class VehicleEngineOilType(models.Model):
    _name = 'vehicle.engine.oil.type'
    _description = 'ประเภทน้ำมันเครื่อง'
    _order = 'sequence, name'

    name = fields.Char('ชื่อ', required=True, help='เช่น 5W-30, 10W-40')
    sequence = fields.Integer('ลำดับ', default=10)
    active = fields.Boolean('ใช้งาน', default=True)
    description = fields.Text('รายละเอียด')


# ==================== ประเภทน้ำมันเกียร์ ====================
class VehicleGearOilType(models.Model):
    _name = 'vehicle.gear.oil.type'
    _description = 'ประเภทน้ำมันเกียร์'
    _order = 'sequence, name'

    name = fields.Char('ชื่อ', required=True, help='เช่น 75W-90, 80W-90, ATF')
    sequence = fields.Integer('ลำดับ', default=10)
    active = fields.Boolean('ใช้งาน', default=True)
    description = fields.Text('รายละเอียด')


# ==================== ประเภทน้ำมันเชื้อเพลิง ====================
class VehicleFuelType(models.Model):
    _name = 'vehicle.fuel.type'
    _description = 'ประเภทน้ำมันเชื้อเพลิง'
    _order = 'sequence, name'

    name = fields.Char('ชื่อ', required=True, help='เช่น ดีเซล B7, เบนซิน 95, NGV, LPG')
    sequence = fields.Integer('ลำดับ', default=10)
    active = fields.Boolean('ใช้งาน', default=True)
    description = fields.Text('รายละเอียด')


# ==================== ประเภทน้ำมันเบรก ====================
class VehicleBrakeFluidType(models.Model):
    _name = 'vehicle.brake.fluid.type'
    _description = 'ประเภทน้ำมันเบรก'
    _order = 'sequence, name'

    name = fields.Char('ชื่อ', required=True, help='เช่น DOT 3, DOT 4, DOT 5.1')
    sequence = fields.Integer('ลำดับ', default=10)
    active = fields.Boolean('ใช้งาน', default=True)
    description = fields.Text('รายละเอียด')


# ==================== ประเภทสารหล่อเย็น ====================
class VehicleCoolantType(models.Model):
    _name = 'vehicle.coolant.type'
    _description = 'ประเภทสารหล่อเย็น'
    _order = 'sequence, name'

    name = fields.Char('ชื่อ', required=True, help='เช่น Ethylene Glycol, Propylene Glycol')
    sequence = fields.Integer('ลำดับ', default=10)
    active = fields.Boolean('ใช้งาน', default=True)
    description = fields.Text('รายละเอียด')


# ==================== ขยาย Fleet Vehicle ====================
class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    vehicle_check_status = fields.Selection([
        ('available', '✅ รถพร้อมใช้'),
        ('reserved', '📋 ติดจอง'),
        ('in_delivery', '🚚 กำลังจัดส่ง'),
    ], string='สถานะการจอง', default='available', required=True, tracking=True,
        readonly=True,  # 🔒 ล็อกไม่ให้แก้ไข
        help='สถานะการจองรถ (อัพเดทโดยระบบอัตโนมัติ)')

    vehicle_type_t = fields.Selection([
        ('car', '🚗 รถยนต์ 4 ล้อ'),
        ('motorcycle', '🏍️ มอเตอร์ไซค์ 2 ล้อ'),
        ('4wheels', '🚚 รถบรรทุก 4 ล้อ'),
        ('6wheels', '🚛 รถบรรทุก 6 ล้อ'),
        ('6wheels_s', '🚛 รถบรรทุก 6 ล้อเฮี๊ยบ'),
        ('10wheels', '🚛 รถบรรทุก 10 ล้อ'),
        ('trailer', '🚛 รถพ่วง'),
        ('pickup', '🛻 รถกระบะ'),
        ('van', '🚐 รถตู้'),
        ('container', '📦 รถตู้คอนเทนเนอร์'),
        ('forklift', '🏗️ รถโฟล์คลิฟท์'),
        ('other', 'อื่นๆ'),
    ], string='ประเภทรถ', default='4wheels', required=True)

    payload_capacity = fields.Float('น้ำหนักบรรทุกสูงสุด (ตัน)', digits=(10, 2))
    registration_year = fields.Integer('ปีที่จดทะเบียน')
    engine_number = fields.Char('หมายเลขเครื่องยนต์')
    chassis_number = fields.Char('หมายเลขตัวถัง')
    vehicle_price = fields.Float('ราคารถ', digits=(12, 2))

    # ข้อมูลน้ำมันเครื่อง
    engine_oil_type_id = fields.Many2one('vehicle.engine.oil.type', string='ประเภทน้ำมันเครื่อง', help='ประเภทน้ำมันเครื่องที่แนะนำสำหรับรถคันนี้')
    engine_oil_capacity = fields.Float('ปริมาณน้ำมันเครื่อง (ลิตร)', digits=(10, 2), help='ความจุน้ำมันเครื่องทั้งหมด')
    last_oil_change_date = fields.Date('เปลี่ยนน้ำมันเครื่องล่าสุด', help='วันที่เปลี่ยนน้ำมันเครื่องครั้งล่าสุด')
    next_oil_change_date = fields.Date('เปลี่ยนน้ำมันเครื่องครั้งถัดไป', compute='_compute_next_oil_change_date', store=True, help='วันที่ต้องเปลี่ยนน้ำมันเครื่องครั้งถัดไป (อัตโนมัติ +1 ปี)')

    # ข้อมูลน้ำมันเกียร์
    gear_oil_type_id = fields.Many2one('vehicle.gear.oil.type', string='ประเภทน้ำมันเกียร์', help='ประเภทน้ำมันเกียร์ที่แนะนำ')
    gear_oil_capacity = fields.Float('ปริมาณน้ำมันเกียร์ (ลิตร)', digits=(10, 2))
    last_gear_oil_change_date = fields.Date('เปลี่ยนน้ำมันเกียร์ล่าสุด')

    # ข้อมูลน้ำมันเชื้อเพลิง
    fuel_type_id = fields.Many2one('vehicle.fuel.type', string='ประเภทน้ำมันเชื้อเพลิง', help='ประเภทเชื้อเพลิงที่ใช้')
    fuel_tank_capacity = fields.Float('ความจุถังน้ำมัน (ลิตร)', digits=(10, 2))
    avg_fuel_consumption = fields.Float('อัตราสิ้นเปลืองเฉลี่ย (กม./ลิตร)', digits=(10, 2))

    # ข้อมูลน้ำมันเบรก
    brake_fluid_type_id = fields.Many2one('vehicle.brake.fluid.type', string='ประเภทน้ำมันเบรก', help='ประเภทน้ำมันเบรกที่แนะนำ')
    last_brake_fluid_change_date = fields.Date('เปลี่ยนน้ำมันเบรกล่าสุด')

    # ข้อมูลสารหล่อเย็น
    coolant_type_id = fields.Many2one('vehicle.coolant.type', string='ประเภทสารหล่อเย็น', help='ประเภทสารหล่อเย็นที่แนะนำ')
    coolant_capacity = fields.Float('ปริมาณสารหล่อเย็น (ลิตร)', digits=(10, 2))
    last_coolant_change_date = fields.Date('เปลี่ยนสารหล่อเย็นล่าสุด')

    # น้ำมันพวงมาลัยเพาเวอร์
    power_steering_fluid = fields.Char('น้ำมันพวงมาลัยเพาเวอร์', help='ยี่ห้อ/ประเภทน้ำมันพวงมาลัย')
    last_power_steering_change_date = fields.Date('เปลี่ยนน้ำมันพวงมาลัยล่าสุด')

    # วันเปลี่ยนครั้งถัดไป (compute)
    next_gear_oil_change_date = fields.Date('เปลี่ยนน้ำมันเกียร์ครั้งถัดไป', compute='_compute_next_fluid_change_dates', store=True)
    next_brake_fluid_change_date = fields.Date('เปลี่ยนน้ำมันเบรกครั้งถัดไป', compute='_compute_next_fluid_change_dates', store=True)
    next_coolant_change_date = fields.Date('เปลี่ยนสารหล่อเย็นครั้งถัดไป', compute='_compute_next_fluid_change_dates', store=True)
    next_power_steering_change_date = fields.Date('เปลี่ยนน้ำมันพวงมาลัยครั้งถัดไป', compute='_compute_next_fluid_change_dates', store=True)

    ownership = fields.Selection([
        ('own', 'รถของบริษัท'),
        ('partner', 'รถร่วม'),
        ('rental', 'รถเช่า'),
        ('executive', 'รถผู้บริหาร'),
        ('special', 'รถพิเศษ'),
        ('customer_credit', 'รถลูกค้าสินเชื่อ'),
    ], string='ความเป็นเจ้าของ', default='own', tracking=True, required=True)

    owner_name = fields.Char('ชื่อเจ้าของรถ', tracking=True)
    model_name_display = fields.Char('ชื่อโมเดลรถ', compute='_compute_model_name_display', store=True)
    partner_company_id = fields.Many2one('vehicle.partner.company', string='บริษัทรถร่วม')

    # ข้อมูลเพิ่มเติม
    driver_r_id = fields.Many2one('vehicle.driver', string='คนขับ')
    has_gps = fields.Boolean('GPS', default=False, help='มีอุปกรณ์ GPS ติดตั้งหรือไม่')
    affiliation = fields.Char('สังกัด', help='หน่วยงานหรือแผนกที่รถสังกัด')
    title_holder = fields.Char('ผู้ถือกรรมสิทธิ์', help='ชื่อผู้ถือกรรมสิทธิ์รถ')
    branch_id = fields.Many2one('res.branch', string='สาขา', help='สาขาที่รถประจำการ')
    has_fuel_card = fields.Boolean('บัตรเติมน้ำมัน', default=False, help='มีบัตรเติมน้ำมันหรือไม่')
    vehicle_rating = fields.Selection([
        ('0', 'ไม่ให้คะแนน'),
        ('1', '⭐'),
        ('2', '⭐⭐'),
        ('3', '⭐⭐⭐'),
        ('4', '⭐⭐⭐⭐'),
        ('5', '⭐⭐⭐⭐⭐'),
    ], string='การประเมิน', default='0', help='ให้คะแนนสภาพรถ 1-5 ดาว')

    vehicle_status = fields.Selection([
        ('available', 'พร้อมใช้งาน'),
        ('maintenance', 'ระหว่างซ่อม'),
        ('retired', 'ปลดระวาง'),
    ], string='สถานะการใช้งาน', default='available', tracking=True, required=True)

    current_driver_id = fields.Many2one('vehicle.driver', string='คนขับปัจจุบัน')

    # เอกสาร
    document_ids = fields.One2many('vehicle.document', 'vehicle_id', string='เอกสาร')
    document_count = fields.Integer('จำนวนเอกสาร', compute='_compute_document_count')
    tax_expiry_date = fields.Date('วันหมดอายุภาษี')
    insurance_expiry_date = fields.Date('วันหมดอายุประกัน')
    compulsory_insurance_expiry = fields.Date('วันหมดอายุ พ.ร.บ.')

    # เพิ่มฟิลด์สถานะ (ใส่ต่อจาก compulsory_insurance_expiry)
    tax_expiry_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้หมดอายุ'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดการต่ออายุ'),
    ], string='สถานะภาษีรถ', compute='_compute_expiry_statuses', store=True)

    insurance_expiry_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้หมดอายุ'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดการต่ออายุ'),
    ], string='สถานะประกันภัย', compute='_compute_expiry_statuses', store=True)

    compulsory_insurance_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้หมดอายุ'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดการต่ออายุ'),
    ], string='สถานะ พ.ร.บ.', compute='_compute_expiry_statuses', store=True)

    next_oil_change_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้หมดอายุ'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดเปลี่ยนน้ำมันเครื่อง'),
    ], string='สถานะเปลี่ยนน้ำมันเครื่อง', compute='_compute_expiry_statuses', store=True)

    next_gear_oil_change_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้ถึงกำหนด'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดเปลี่ยนน้ำมันเกียร์'),
    ], string='สถานะเปลี่ยนน้ำมันเกียร์', compute='_compute_expiry_statuses', store=True)

    next_brake_fluid_change_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้ถึงกำหนด'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดเปลี่ยนน้ำมันเบรก'),
    ], string='สถานะเปลี่ยนน้ำมันเบรก', compute='_compute_expiry_statuses', store=True)

    next_coolant_change_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้ถึงกำหนด'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดเปลี่ยนสารหล่อเย็น'),
    ], string='สถานะเปลี่ยนสารหล่อเย็น', compute='_compute_expiry_statuses', store=True)

    next_power_steering_change_status = fields.Selection([
        ('no_data', '❓ ไม่มีข้อมูล'),
        ('valid', '✅ ปกติ'),
        ('expiring_soon', '⚠️ ใกล้ถึงกำหนด'),
        ('due', '🔔 ครบกำหนด'),
        ('overdue', '❌ เกินกำหนดเปลี่ยนน้ำมันพวงมาลัย'),
    ], string='สถานะเปลี่ยนน้ำมันพวงมาลัย', compute='_compute_expiry_statuses', store=True)

    # เพิ่มฟังก์ชันคำนวณ
    def _get_expiry_status(self, expiry_date):
        """
        คำนวณสถานะวันหมดอายุ:
        - no_data: ไม่ได้ระบุวันที่
        - valid: ยังเหลือมากกว่า 30 วัน (1 เดือน)
        - expiring_soon: เหลือ 1-30 วัน (⚠️ ใกล้หมดอายุ)
        - due: ครบกำหนดวันนี้
        - overdue: เลยกำหนดไปแล้ว
        """
        if not expiry_date:
            return 'no_data'

        today = date.today()
        days_until_expiry = (expiry_date - today).days

        # ตรวจสอบสถานะ
        if days_until_expiry < 0:
            # เลยกำหนดไปแล้ว
            return 'overdue'
        elif days_until_expiry == 0:
            # ครบกำหนดวันนี้
            return 'due'
        elif days_until_expiry <= 30:
            # เหลือ 1-30 วัน (ใกล้หมดอายุ - 1 เดือน)
            return 'expiring_soon'
        else:
            # ยังเหลือมากกว่า 30 วัน (1 เดือน)
            return 'valid'

    @api.depends('model_id')
    def _compute_model_name_display(self):
        for record in self:
            record.model_name_display = record.model_id.name if record.model_id else False

    @api.depends('last_oil_change_date')
    def _compute_next_oil_change_date(self):
        """คำนวณวันเปลี่ยนน้ำมันเครื่องครั้งถัดไป = ครั้งล่าสุด + 1 ปี"""
        for record in self:
            if record.last_oil_change_date:
                record.next_oil_change_date = record.last_oil_change_date + relativedelta(years=1)
            else:
                record.next_oil_change_date = False

    @api.depends('last_gear_oil_change_date', 'last_brake_fluid_change_date', 'last_coolant_change_date', 'last_power_steering_change_date')
    def _compute_next_fluid_change_dates(self):
        """คำนวณวันเปลี่ยนของเหลวแต่ละประเภทครั้งถัดไป"""
        for record in self:
            # น้ำมันเกียร์ +2 ปี
            if record.last_gear_oil_change_date:
                record.next_gear_oil_change_date = record.last_gear_oil_change_date + relativedelta(years=2)
            else:
                record.next_gear_oil_change_date = False
            # น้ำมันเบรก +2 ปี
            if record.last_brake_fluid_change_date:
                record.next_brake_fluid_change_date = record.last_brake_fluid_change_date + relativedelta(years=2)
            else:
                record.next_brake_fluid_change_date = False
            # สารหล่อเย็น +2 ปี
            if record.last_coolant_change_date:
                record.next_coolant_change_date = record.last_coolant_change_date + relativedelta(years=2)
            else:
                record.next_coolant_change_date = False
            # น้ำมันพวงมาลัย +2 ปี
            if record.last_power_steering_change_date:
                record.next_power_steering_change_date = record.last_power_steering_change_date + relativedelta(years=2)
            else:
                record.next_power_steering_change_date = False

    @api.depends('tax_expiry_date', 'insurance_expiry_date', 'compulsory_insurance_expiry',
                 'next_oil_change_date', 'next_gear_oil_change_date', 'next_brake_fluid_change_date',
                 'next_coolant_change_date', 'next_power_steering_change_date')
    def _compute_expiry_statuses(self):
        """คำนวณสถานะวันหมดอายุทุกรายการ"""
        for record in self:
            record.tax_expiry_status = record._get_expiry_status(record.tax_expiry_date)
            record.insurance_expiry_status = record._get_expiry_status(record.insurance_expiry_date)
            record.compulsory_insurance_status = record._get_expiry_status(record.compulsory_insurance_expiry)
            record.next_oil_change_status = record._get_expiry_status(record.next_oil_change_date)
            record.next_gear_oil_change_status = record._get_expiry_status(record.next_gear_oil_change_date)
            record.next_brake_fluid_change_status = record._get_expiry_status(record.next_brake_fluid_change_date)
            record.next_coolant_change_status = record._get_expiry_status(record.next_coolant_change_date)
            record.next_power_steering_change_status = record._get_expiry_status(record.next_power_steering_change_date)

    # ===== Scheduled Action (Cron Job) =====
    @api.model
    def _cron_update_expiry_statuses(self):
        """Cron job สำหรับอัพเดทสถานะวันหมดอายุทุกวัน"""
        vehicles = self.search([])
        for vehicle in vehicles:
            vehicle._compute_expiry_statuses()
        _logger.info(f"✓ อัพเดทสถานะวันหมดอายุรถ {len(vehicles)} คัน")

    # รูปรถ
    vehicle_image_ids = fields.One2many('vehicle.image', 'vehicle_id', string='รูปรถ')

    # การซ่อมบำรุง
    maintenance_request_ids = fields.One2many('vehicle.maintenance.request', 'vehicle_id', string='การแจ้งซ่อม')
    maintenance_history_ids = fields.One2many('vehicle.maintenance.history', 'vehicle_id', string='ประวัติการซ่อม')
    maintenance_count = fields.Integer('จำนวนการซ่อม', compute='_compute_maintenance_count')

    @api.depends('document_ids')
    def _compute_document_count(self):
        for record in self:
            record.document_count = len(record.document_ids)

    @api.depends('maintenance_request_ids', 'maintenance_history_ids')
    def _compute_maintenance_count(self):
        for record in self:
            record.maintenance_count = len(record.maintenance_request_ids) + len(record.maintenance_history_ids)

    def action_view_documents(self):
        return {
            'name': f'เอกสารของ {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.document',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id}
        }

    def action_view_maintenance(self):
        return {
            'name': f'การซ่อมของ {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.maintenance.request',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id}
        }


# ==================== เอกสารรถ ====================
class VehicleDocument(models.Model):
    _name = 'vehicle.document'
    _description = 'Vehicle Document'
    _order = 'expiry_date desc'

    name = fields.Char('ชื่อเอกสาร', required=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ', required=True, ondelete='cascade')
    license_plate = fields.Char(related='vehicle_id.license_plate', string='ทะเบียนรถ', store=True)

    document_type = fields.Selection([
        ('tax', 'ภาษีรถยนต์'),
        ('compulsory_insurance', 'พ.ร.บ.'),
        ('insurance', 'ประกันภัย'),
        ('registration', 'ทะเบียนรถ'),
        ('license', 'ใบอนุญาตพิเศษ'),
        ('other', 'อื่นๆ'),
    ], string='ประเภทเอกสาร', required=True)

    document_number = fields.Char('เลขที่เอกสาร')
    issue_date = fields.Date('วันที่ออกเอกสาร')
    expiry_date = fields.Date('วันหมดอายุ')

    status = fields.Selection([
        ('valid', 'ใช้งานได้'),
        ('expiring_soon', 'ใกล้หมดอายุ'),
        ('expired', 'หมดอายุ'),
    ], string='สถานะ', compute='_compute_status', store=True)

    cost = fields.Float('ค่าใช้จ่าย')
    note = fields.Text('หมายเหตุ')

    @api.depends('expiry_date')
    def _compute_status(self):
        today = date.today()
        for record in self:
            if not record.expiry_date:
                record.status = 'valid'
            elif record.expiry_date < today:
                record.status = 'expired'
            elif record.expiry_date <= today + timedelta(days=30):
                record.status = 'expiring_soon'
            else:
                record.status = 'valid'


# ==================== รูปรถ ====================
class VehicleImage(models.Model):
    _name = 'vehicle.image'
    _description = 'Vehicle Image'
    _order = 'sequence, id'

    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ', required=True, ondelete='cascade')
    name = fields.Char('คำอธิบาย')
    image = fields.Image('รูปภาพ', required=True, max_width=1920, max_height=1920)
    sequence = fields.Integer('ลำดับ', default=10)


# ==================== ผู้ขับขี่ ====================
class VehicleDriver(models.Model):
    _name = 'vehicle.driver'
    _description = 'Vehicle Driver'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    image_1920 = fields.Image("Image", max_width=1920, max_height=1920)
    image_1024 = fields.Image("Image 1024", related="image_1920", max_width=1024, max_height=1024, store=True)
    image_512 = fields.Image("Image 512", related="image_1920", max_width=512, max_height=512, store=True)
    image_256 = fields.Image("Image 256", related="image_1920", max_width=256, max_height=256, store=True)
    image_128 = fields.Image("Image 128", related="image_1920", max_width=128, max_height=128, store=True)

    name = fields.Char('ชื่อ-นามสกุล', required=True, tracking=True)
    code = fields.Char('รหัสพนักงาน', copy=False)
    employee_code = fields.Char(
        'รหัสพนักงาน (HR)',
        required=True, copy=False, tracking=True,
        help='อิงจากรหัสพนักงานในระบบ HR (เช่น 0817, 0264) — '
             'ใช้สำหรับเชื่อมโยงคนขับกับพนักงานในระบบ HR'
    )
    pin = fields.Char('PIN 6 หลัก', size=6, required=True, tracking=True,
                      help='PIN 6 หลักสำหรับการล็อกอิน (ห้ามซ้ำ)')
    phone = fields.Char('เบอร์โทรศัพท์', required=True)
    email = fields.Char('อีเมล')
    citizen_id = fields.Char('เลขบัตรประชาชน')
    birth_date = fields.Date('วันเกิด')

    # ใบขับขี่
    license_number = fields.Char('เลขที่ใบขับขี่', required=True)
    license_type = fields.Selection([
        ('t1', 'ท.1 (รถยนต์ส่วนบุคคลไม่เกิน 7 ที่นั่ง)'),
        ('t2', 'ท.2 (รถยนต์ส่วนบุคคลเกิน 7 ที่นั่ง / รถบรรทุกส่วนบุคคล)'),
        ('t3', 'ท.3 (รถสาธารณะ / รถบรรทุกสาธารณะ)'),
        ('t4', 'ท.4 (รถจักรยานยนต์)'),
    ], string='ประเภทใบขับขี่', required=True)
    license_issue_date = fields.Date('วันที่ออกใบขับขี่')
    license_expiry_date = fields.Date('วันหมดอายุใบขับขี่', required=True)

    license_status = fields.Selection([
        ('valid', 'ใช้งานได้'),
        ('expiring_soon', 'ใกล้หมดอายุ'),
        ('expired', 'หมดอายุ'),
    ], string='สถานะใบขับขี่', compute='_compute_license_status', store=True)

    employment_status = fields.Selection([
        ('employed', 'พนักงานประจำ'),
        ('partner', 'คนขับรถร่วม'),
        ('inactive', 'ไม่ทำงาน'),
    ], string='สถานะการทำงาน', default='employed', tracking=True)

    active = fields.Boolean('Active', default=True)
    partner_company_id = fields.Many2one('vehicle.partner.company', string='บริษัทรถร่วม')

    # ประวัติ
    accident_ids = fields.One2many('driver.accident.history', 'driver_id', string='ประวัติอุบัติเหตุ')
    trip_ids = fields.One2many('driver.trip.history', 'driver_id', string='ประวัติการขับรถ')
    rating_avg = fields.Float('คะแนนเฉลี่ย', digits=(3, 2))

    vehicle_id = fields.Many2one('fleet.vehicle', string='รถที่ขับประจำ')
    note = fields.Html('หมายเหตุ')
    branch_id = fields.Many2one('res.branch', string='สาขา')
    said_date = fields.Datetime('วันที่มอบหมาย')

    _sql_constraints = [
        ('pin_unique', 'UNIQUE(pin)', '⚠️ PIN นี้ถูกใช้งานแล้ว กรุณาใช้ PIN อื่น'),
    ]

    @api.constrains('pin')
    def _check_pin(self):
        for record in self:
            if record.pin:
                # ตรวจสอบว่า PIN เป็นตัวเลขเท่านั้น
                if not record.pin.isdigit():
                    raise ValidationError('❌ PIN ต้องเป็นตัวเลขเท่านั้น')
                # ตรวจสอบว่า PIN มีความยาว 6 หลัก
                if len(record.pin) != 6:
                    raise ValidationError('❌ PIN ต้องเป็นตัวเลข 6 หลักเท่านั้น')

    @api.depends('license_expiry_date')
    def _compute_license_status(self):
        """
        คำนวณสถานะใบขับขี่:
        - expired: หมดอายุแล้ว (วันหมดอายุ < วันที่ปัจจุบัน)
        - expiring_soon: ใกล้หมดอายุ (เหลือเวลา <= 30 วัน)
        - valid: ใช้งานได้ (เหลือเวลามากกว่า 30 วัน)
        """
        today = date.today()
        for record in self:
            if not record.license_expiry_date:
                # ถ้าไม่มีวันหมดอายุ ให้ถือว่าใช้งานได้
                record.license_status = 'valid'
            elif record.license_expiry_date < today:
                # หมดอายุแล้ว
                record.license_status = 'expired'
            elif record.license_expiry_date <= today + timedelta(days=30):
                # ใกล้หมดอายุ (เหลือเวลา <= 30 วัน)
                record.license_status = 'expiring_soon'
            else:
                # ใช้งานได้ปกติ
                record.license_status = 'valid'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('vehicle.driver') or 'DRV-NEW'
        return super().create(vals_list)


# ==================== ประวัติอุบัติเหตุ ====================
class DriverAccidentHistory(models.Model):
    _name = 'driver.accident.history'
    _description = 'Driver Accident History'
    _order = 'accident_date desc'

    driver_id = fields.Many2one('vehicle.driver', string='คนขับ', required=True, ondelete='cascade')
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถที่เกิดเหตุ')
    accident_date = fields.Datetime('วันเวลาที่เกิดเหตุ', required=True)
    location = fields.Char('สถานที่เกิดเหตุ')
    description = fields.Text('รายละเอียด', required=True)
    severity = fields.Selection([
        ('minor', 'เล็กน้อย'),
        ('moderate', 'ปานกลาง'),
        ('major', 'ร้ายแรง'),
    ], string='ความรุนแรง', required=True)
    damage_cost = fields.Float('ค่าเสียหาย')
    note = fields.Text('หมายเหตุ')


# ==================== ประวัติการขับรถ ====================
class DriverTripHistory(models.Model):
    _name = 'driver.trip.history'
    _description = 'Driver Trip History'
    _order = 'start_date desc'

    driver_id = fields.Many2one('vehicle.driver', string='คนขับ', required=True, ondelete='cascade')
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ', required=True)
    transport_order_id = fields.Many2one('transport.order', string='คำสั่งขนส่ง')

    start_date = fields.Datetime('เวลาออกเดินทาง', required=True)
    end_date = fields.Datetime('เวลาถึงปลายทาง')
    origin = fields.Char('ต้นทาง', required=True)
    destination = fields.Char('ปลายทาง', required=True)
    distance = fields.Float('ระยะทาง (กม.)', required=True)

    # Check-in/Check-out
    checkin_time = fields.Datetime('เวลา Check-in รับสินค้า')
    checkout_time = fields.Datetime('เวลา Check-out ส่งสินค้า')

    status = fields.Selection([
        ('scheduled', 'กำหนดการ'),
        ('in_progress', 'กำลังเดินทาง'),
        ('completed', 'เสร็จสิ้น'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='scheduled', required=True)

    note = fields.Text('หมายเหตุ')


# ==================== การแจ้งซ่อม ====================
class VehicleMaintenanceRequest(models.Model):
    _name = 'vehicle.maintenance.request'
    _description = 'Vehicle Maintenance Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc'

    name = fields.Char('เลขที่แจ้งซ่อม', required=True, copy=False, readonly=True, default='New')
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ', required=True, tracking=True)
    license_plate = fields.Char(related='vehicle_id.license_plate', string='ทะเบียนรถ', store=True)

    requester_id = fields.Many2one('res.users', string='ผู้แจ้งซ่อม', default=lambda self: self.env.user, required=True)
    request_date = fields.Datetime('วันที่แจ้งซ่อม', default=fields.Datetime.now, required=True)

    problem_category = fields.Selection([
        ('engine', 'เครื่องยนต์'),
        ('transmission', 'ระบบเกียร์'),
        ('brake', 'ระบบเบรก'),
        ('electrical', 'ระบบไฟฟ้า'),
        ('tire', 'ยาง'),
        ('body', 'ตัวถัง'),
        ('other', 'อื่นๆ'),
    ], string='หมวดหมู่ปัญหา', required=True)

    problem_description = fields.Text('รายละเอียดปัญหา', required=True)
    priority = fields.Selection([
        ('0', 'ปกติ'),
        ('1', 'ด่วน'),
        ('2', 'ด่วนมาก'),
    ], string='ความเร่งด่วน', default='0', required=True)

    state = fields.Selection([
        ('draft', 'แจ้งซ่อม'),
        ('waiting_approval', 'รออนุมัติ'),
        ('pending', 'รอการซ่อม'),
        ('in_progress', 'กำลังซ่อม'),
        ('done', 'ซ่อมเสร็จ'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='draft', required=True, tracking=True)

    # ระบบการอนุมัติ
    approval_state = fields.Selection([
        ('no_approval', 'ไม่ต้องอนุมัติ'),
        ('waiting', 'รออนุมัติ'),
        ('approved', 'อนุมัติแล้ว'),
        ('rejected', 'ปฏิเสธ/ให้แก้ไข'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะการอนุมัติ', default='no_approval', tracking=True)

    approval_ids = fields.One2many(
        'maintenance.approval',
        'maintenance_request_id',
        string='การอนุมัติ'
    )
    approval_count = fields.Integer('จำนวนการอนุมัติ', compute='_compute_approval_count')

    # ฟิลด์เพื่อเช็คว่าถูกใช้ในประวัติการซ่อมแล้วหรือยัง
    is_used_in_history = fields.Boolean(
        'ถูกใช้ในประวัติแล้ว',
        default=False,
        tracking=True,
        help='ถูกเลือกในประวัติการซ่อมแล้ว จะไม่สามารถเลือกซ้ำได้'
    )
    history_id = fields.Many2one(
        'vehicle.maintenance.history',
        string='ประวัติการซ่อมที่เชื่อมโยง',
        readonly=True,
        help='ประวัติการซ่อมที่เชื่อมโยงกับการแจ้งซ่อมนี้'
    )

    assigned_to_id = fields.Many2one('res.users', string='มอบหมายให้')
    estimated_cost = fields.Float('ค่าใช้จ่ายโดยประมาณ')
    actual_cost = fields.Float('ค่าใช้จ่ายจริง')
    start_date = fields.Datetime('วันเวลาเริ่มซ่อม')
    completion_date = fields.Datetime('วันเวลาที่ซ่อมเสร็จ')
    note = fields.Html('หมายเหตุ')

    @api.depends('approval_ids')
    def _compute_approval_count(self):
        """คำนวณจำนวนผู้อนุมัติ"""
        for record in self:
            record.approval_count = len(record.approval_ids)

    def write(self, vals):
        """ป้องกันการแก้ไขเมื่ออนุมัติแล้ว ยกเว้นฟิลด์ที่อนุญาต"""
        for record in self:
            # ถ้าสถานะการอนุมัติเป็น 'approved' แล้ว
            if record.approval_state == 'approved':
                # รายการฟิลด์ที่อนุญาตให้แก้ไขได้แม้อนุมัติแล้ว
                allowed_fields = {
                    'actual_cost',  # ค่าใช้จ่ายจริง
                    'completion_date',  # วันเวลาที่ซ่อมเสร็จ
                    'state',  # สถานะการซ่อม (สำหรับ workflow)
                    'start_date',  # วันเวลาเริ่มซ่อม (สำหรับ action_start)
                    'is_used_in_history',  # สำหรับเชื่อมโยงกับประวัติการซ่อม
                    'history_id',  # สำหรับเชื่อมโยงกับประวัติการซ่อม
                    'message_follower_ids',  # สำหรับ chatter
                    'message_ids',  # สำหรับ chatter
                    'activity_ids',  # สำหรับ activities
                }

                # ตรวจสอบว่ามีการแก้ไขฟิลด์ที่ไม่อนุญาตหรือไม่
                restricted_fields = set(vals.keys()) - allowed_fields

                if restricted_fields:
                    # ถ้ามีการแก้ไขฟิลด์ที่ไม่อนุญาต ให้แสดง error
                    raise ValidationError(
                        '❌ ไม่สามารถแก้ไขได้เนื่องจากได้รับการอนุมัติแล้ว\n'
                        'สามารถแก้ไขได้เฉพาะ: ค่าใช้จ่ายจริง และ วันเวลาที่ซ่อมเสร็จ'
                    )

        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.maintenance.request') or 'MR-NEW'
        return super().create(vals_list)

    def action_confirm(self):
        """ยืนยันการแจ้งซ่อม - เปิด wizard เลือกผู้อนุมัติ"""
        self.ensure_one()

        # ลบการอนุมัติเก่าถ้ามี (กรณีส่งอนุมัติใหม่)
        if self.approval_ids:
            self.approval_ids.unlink()

        return {
            'name': 'ส่งอนุมัติการแจ้งซ่อม',
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_maintenance_request_id': self.id,
            }
        }

    def action_view_approvals(self):
        """ดูรายการการอนุมัติ"""
        self.ensure_one()
        return {
            'name': f'การอนุมัติ: {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.approval',
            'view_mode': 'list,form',
            'domain': [('maintenance_request_id', '=', self.id)],
            'context': {'default_maintenance_request_id': self.id}
        }

    def action_start(self):
        """เริ่มการซ่อม - ต้องได้รับการอนุมัติก่อน"""
        self.ensure_one()

        # ตรวจสอบการอนุมัติ
        if self.approval_ids and self.approval_state != 'approved':
            raise ValidationError('❌ ต้องได้รับการอนุมัติก่อนจึงจะเริ่มซ่อมได้')

        self.write({'state': 'in_progress', 'start_date': fields.Datetime.now()})
        self.vehicle_id.write({'vehicle_status': 'maintenance'})

    def action_done(self):
        if not self.actual_cost:
            raise ValidationError('กรุณากรอกค่าใช้จ่ายจริง')

        self.env['vehicle.maintenance.history'].create({
            'name': self.name,
            'vehicle_id': self.vehicle_id.id,
            'problem_category': self.problem_category,
            'description': self.problem_description,
            'cost': self.actual_cost,
            'maintenance_date': self.start_date,
            'completed_date': fields.Datetime.now(),
            'maintenance_request_id': self.id,
        })

        self.write({'state': 'done', 'completion_date': fields.Datetime.now()})
        self.vehicle_id.write({'vehicle_status': 'available'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        if self.vehicle_id.vehicle_status == 'maintenance':
            self.vehicle_id.write({'vehicle_status': 'available'})


# ==================== รายการแจ้งซ่อม ====================
class VehicleMaintenanceHistory(models.Model):
    _name = 'vehicle.maintenance.history'
    _description = 'Vehicle Maintenance History'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'maintenance_date desc'
    _rec_name = 'name'

    name = fields.Char('เลขที่', required=True, copy=False, readonly=True, default='New')
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ', required=True, ondelete='cascade')
    license_plate = fields.Char(related='vehicle_id.license_plate', string='ทะเบียนรถ', store=True)

    state = fields.Selection([
        ('draft', 'แบบร่าง'),
        ('confirmed', 'ยืนยันแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='draft', required=True, tracking=True)

    problem_category = fields.Selection([
        ('engine', 'เครื่องยนต์'),
        ('transmission', 'ระบบเกียร์'),
        ('brake', 'ระบบเบรก'),
        ('electrical', 'ระบบไฟฟ้า'),
        ('tire', 'ยาง'),
        ('body', 'ตัวถัง'),
        ('oil_change', 'เปลี่ยนถ่ายน้ำมัน'),
        ('other', 'อื่นๆ'),
    ], string='หมวดหมู่')

    description = fields.Text('รายการซ่อม/บำรุงรักษา', required=True)
    maintenance_date = fields.Datetime('วันเวลาเริ่มซ่อม', default=fields.Datetime.now, required=True)
    completed_date = fields.Datetime('วันเวลาซ่อมเสร็จ')
    cost = fields.Float('ค่าใช้จ่าย', required=True)

    service_provider = fields.Selection([
        ('internal', 'ช่างภายใน'),
        ('external', 'ศูนย์บริการภายนอก'),
    ], string='ผู้ให้บริการ', required=True, default='internal')

    technician_id = fields.Many2one('res.users', string='ช่างผู้ซ่อม')
    service_center = fields.Char('ชื่อศูนย์บริการ')
    maintenance_request_id = fields.Many2one(
        'vehicle.maintenance.request',
        string='การแจ้งซ่อม',
        domain="[('approval_state', '=', 'approved'), ('is_used_in_history', '=', False)]",
        help='แสดงเฉพาะการแจ้งซ่อมที่ได้รับการอนุมัติแล้ว และยังไม่ถูกใช้ในประวัติการซ่อม'
    )
    note = fields.Html('หมายเหตุ')

    @api.onchange('maintenance_request_id')
    def _onchange_maintenance_request_id(self):
        """ดึงข้อมูลจากการแจ้งซ่อมมาเติมอัตโนมัติ"""
        if self.maintenance_request_id:
            request = self.maintenance_request_id
            # ดึงค่าใช้จ่ายจริงจากการแจ้งซ่อม
            if request.actual_cost:
                self.cost = request.actual_cost
            # ดึงข้อมูลอื่นๆ ที่เป็นประโยชน์
            if not self.vehicle_id:
                self.vehicle_id = request.vehicle_id
            if not self.problem_category:
                self.problem_category = request.problem_category
            if not self.description:
                self.description = request.problem_description
            if not self.maintenance_date and request.start_date:
                self.maintenance_date = request.start_date
            if not self.completed_date and request.completion_date:
                self.completed_date = request.completion_date

    @api.constrains('maintenance_request_id')
    def _check_maintenance_request_approved(self):
        """ตรวจสอบว่าการแจ้งซ่อมต้องได้รับการอนุมัติแล้ว และยังไม่ถูกใช้"""
        for record in self:
            # ข้ามการตรวจสอบถ้าสถานะเป็น cancelled
            if record.state == 'cancelled':
                continue

            if record.maintenance_request_id:
                request = record.maintenance_request_id

                # ตรวจสอบว่าได้รับการอนุมัติหรือยัง
                if request.approval_state != 'approved':
                    raise ValidationError(
                        f'❌ ไม่สามารถเชื่อมโยงกับการแจ้งซ่อม {request.name} ได้\n'
                        f'เนื่องจากยังไม่ได้รับการอนุมัติ\n'
                        f'สถานะปัจจุบัน: {dict(request._fields["approval_state"].selection).get(request.approval_state)}'
                    )

                # ตรวจสอบว่าถูกใช้ไปแล้วหรือยัง (ยกเว้นตัวเอง)
                if request.is_used_in_history and request.history_id and request.history_id.id != record.id:
                    raise ValidationError(
                        f'❌ ไม่สามารถเชื่อมโยงกับการแจ้งซ่อม {request.name} ได้\n'
                        f'เนื่องจากถูกใช้ในประวัติการซ่อม {request.history_id.name} แล้ว'
                    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.maintenance.history') or 'MH-NEW'
        return super().create(vals_list)

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100):
        """ค้นหาและแสดงข้อมูล"""
        args = args or []
        domain = [
            '|',
            ('name', operator, name),
            ('vehicle_id.license_plate', operator, name),
        ]
        return super()._name_search(name, args + domain, operator=operator, limit=limit)

    def name_get(self):
        """แสดง display name สำหรับ dropdown"""
        result = []
        for record in self:
            display_name = f"[{record.name}] {record.vehicle_id.license_plate or 'N/A'} - {record.description[:30]}"
            result.append((record.id, display_name))
        return result

    def action_confirm_usage(self):
        """ยืนยันการใช้งาน - ทำเครื่องหมายว่าการแจ้งซ่อมถูกใช้แล้ว"""
        self.ensure_one()

        if not self.maintenance_request_id:
            raise ValidationError('❌ กรุณาเลือกการแจ้งซ่อมก่อนยืนยัน')

        # เปลี่ยนสถานะเป็นยืนยันแล้ว
        self.write({'state': 'confirmed'})

        # ทำเครื่องหมายว่าการแจ้งซ่อมถูกใช้แล้ว
        self.maintenance_request_id.write({
            'is_used_in_history': True,
            'history_id': self.id,
        })

        # ส่งข้อความแจ้งเตือน
        self.message_post(
            body=f"✅ ยืนยันการใช้งานแล้ว - เชื่อมโยงกับการแจ้งซ่อม {self.maintenance_request_id.name}",
            subject='ยืนยันการใช้งานการแจ้งซ่อม',
            message_type='notification'
        )

        # อัปเดตสถานะการแจ้งซ่อมเป็น done (ถ้ายังไม่ done)
        if self.maintenance_request_id.state != 'done':
            self.maintenance_request_id.write({'state': 'done'})

        _logger.info(f"✅ ยืนยันการใช้งาน: {self.name} เชื่อมโยงกับ {self.maintenance_request_id.name}")

        return True

    def action_cancel(self):
        """ยกเลิกประวัติการซ่อม"""
        self.ensure_one()

        if self.state == 'cancelled':
            raise ValidationError('❌ ประวัติการซ่อมนี้ถูกยกเลิกไปแล้ว')

        # เปลี่ยนสถานะเป็นยกเลิก
        self.write({'state': 'cancelled'})

        # ปลดล็อกการแจ้งซ่อม (ถ้ามี)
        if self.maintenance_request_id and self.maintenance_request_id.is_used_in_history:
            self.maintenance_request_id.write({
                'is_used_in_history': False,
                'history_id': False,
            })

            # ส่งข้อความแจ้งเตือน
            self.message_post(
                body=f"❌ ยกเลิกประวัติการซ่อม - ปลดล็อกการแจ้งซ่อม {self.maintenance_request_id.name}",
                subject='ยกเลิกประวัติการซ่อม',
                message_type='notification'
            )

            _logger.info(f"❌ ยกเลิก: {self.name} ปลดล็อก {self.maintenance_request_id.name}")

        return True

    def action_set_to_draft(self):
        """กลับไปเป็นแบบร่าง"""
        self.ensure_one()

        if self.state == 'draft':
            raise ValidationError('❌ ประวัติการซ่อมนี้อยู่ในสถานะแบบร่างอยู่แล้ว')

        # ปลดล็อกการแจ้งซ่อม (ถ้ามี)
        if self.maintenance_request_id and self.maintenance_request_id.is_used_in_history:
            self.maintenance_request_id.write({
                'is_used_in_history': False,
                'history_id': False,
            })

        self.write({'state': 'draft'})

        self.message_post(
            body=f"🔄 กลับไปสถานะแบบร่าง",
            subject='เปลี่ยนสถานะ',
            message_type='notification'
        )

        return True

    def unlink(self):
        """เมื่อลบประวัติการซ่อม ให้ตรวจสอบสถานะก่อน"""
        for record in self:
            # ถ้ายืนยันแล้ว ไม่อนุญาตให้ลบ
            if record.state == 'confirmed':
                raise ValidationError(
                    f'❌ ไม่สามารถลบประวัติการซ่อม {record.name} ได้\n'
                    f'เนื่องจากถูกยืนยันแล้ว กรุณายกเลิกก่อนหากต้องการลบ'
                )

            # ปลดล็อกการแจ้งซ่อม (สำหรับสถานะ draft)
            if record.maintenance_request_id and record.maintenance_request_id.is_used_in_history:
                record.maintenance_request_id.write({
                    'is_used_in_history': False,
                    'history_id': False,
                })
                _logger.info(f"🔓 ปลดล็อกการแจ้งซ่อม {record.maintenance_request_id.name}")

        return super().unlink()


# ==================== ประวัติการแจ้งเตือน ====================
class NotificationHistory(models.Model):
    _name = 'notification.history'
    _description = 'Notification History'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    maintenance_id = fields.Many2one('vehicle.maintenance.notification', string='การซ่อม', ondelete='cascade')
    # ฟิลด์เลือกเอง (ไม่ auto-populate)
    problem_category = fields.Selection([
        ('engine', 'เครื่องยนต์'),
        ('transmission', 'ระบบเกียร์'),
        ('brake', 'ระบบเบรก'),
        ('electrical', 'ระบบไฟฟ้า'),
        ('tire', 'ยาง'),
        ('oil_change', 'เปลี่ยนถ่ายน้ำมัน'),
        ('body', 'ตัวถัง'),
        ('other', 'อื่นๆ'),
    ], string='หมวดหมู่ปัญหา')
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ', readonly=True)
    license_plate = fields.Char(string='ทะเบียนรถ', compute='_compute_license_plate', store=True)
    notification_type = fields.Selection([
        ('maintenance', 'การซ่อมบำรุง'),
        ('document', 'เอกสาร'),
        ('other', 'อื่นๆ'),
    ], string='ประเภทการแจ้งเตือน', default='maintenance')
    title = fields.Char('หัวเรื่อง', required=True)
    message = fields.Html('ข้อความ')
    note = fields.Text('หมายเหตุ')
    recipient_ids = fields.Many2many('res.users', string='ผู้รับแจ้งเตือน')
    status = fields.Selection([
        ('sent', 'ส่งแล้ว'),
        ('read', 'อ่านแล้ว'),
        ('unread', 'ยังไม่อ่าน'),
    ], string='สถานะ', default='sent')
    read_date = fields.Datetime('วันที่อ่าน')
    is_read = fields.Boolean('อ่านแล้ว', default=False)

    def mark_as_read(self):
        """ทำเครื่องหมายว่าอ่านแล้ว และลบ Activity"""
        # Update status
        self.write({
            'is_read': True,
            'status': 'read',
            'read_date': datetime.now()
        })

        # ลบ Activity ที่เกี่ยวข้อง
        try:
            activities = self.env['mail.activity'].search([
                ('res_model', '=', 'notification.history'),
                ('res_id', '=', self.id),
            ])
            if activities:
                activities.unlink()
                _logger.info(f"✓ ลบ Activity สำเร็จ")
        except Exception as e:
            _logger.warning(f"⚠️ ลบ Activity ล้มเหลว: {str(e)}")

    @api.depends('vehicle_id')
    def _compute_license_plate(self):
        """Auto-populate ทะเบียนรถจากรถที่เลือก"""
        for record in self:
            if record.vehicle_id:
                record.license_plate = record.vehicle_id.license_plate
            else:
                record.license_plate = ''

    def action_open_notification_list(self):
        """เปิดหน้า ประวัติการแจ้งเตือน"""
        return {
            'type': 'ir.actions.act_window',
            'name': '📝 ประวัติการแจ้งเตือน',
            'res_model': 'notification.history',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'target': 'main',
        }


# ==================== การแจ้งเตือนการซ่อมบำรุง ====================
class VehicleMaintenanceHistoryNotification(models.Model):
    _name = 'vehicle.maintenance.notification'
    _description = 'Vehicle Maintenance Notification'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    maintenance_id = fields.Many2one('vehicle.maintenance.history', string='การซ่อม', ondelete='cascade')
    # ฟิลด์เลือกเอง (ไม่ auto-populate)
    problem_category = fields.Selection([
        ('engine', 'เครื่องยนต์'),
        ('transmission', 'ระบบเกียร์'),
        ('brake', 'ระบบเบรก'),
        ('electrical', 'ระบบไฟฟ้า'),
        ('tire', 'ยาง'),
        ('oil_change', 'เปลี่ยนถ่ายน้ำมัน'),
        ('body', 'ตัวถัง'),
        ('other', 'อื่นๆ'),
    ], string='หมวดหมู่ปัญหา')
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ')
    license_plate = fields.Char(string='ทะเบียนรถ', compute='_compute_license_plate_noti', store=True)
    category_icon = fields.Char('ไอคอนหมวดหมู่', compute='_compute_category_icon', store=False)
    notification_enabled = fields.Boolean('เปิดการแจ้งเตือน', default=False)
    notification_interval = fields.Integer('แจ้งเตือนทุก (วัน)', default=30)
    notification_start_date = fields.Date('วันที่เริ่มแจ้งเตือน', default=fields.Date.context_today)
    notification_end_date = fields.Date('วันสิ้นสุดการแจ้งเตือน', compute='_compute_notification_end_date', store=True)
    notification_last_sent = fields.Datetime('ส่งแจ้งเตือนครั้งสุดท้าย', readonly=True)
    notification_count = fields.Integer('จำนวนครั้งที่ส่ง', default=0, readonly=True)
    notification_history_ids = fields.One2many('notification.history', 'maintenance_id', string='ประวัติการแจ้งเตือน')
    note = fields.Text('หมายเหตุ')
    recipient_ids = fields.Many2many('res.users', string='ผู้รับแจ้งเตือน')

    @api.depends('notification_start_date', 'notification_interval')
    def _compute_notification_end_date(self):
        for record in self:
            if record.notification_start_date:
                record.notification_end_date = record.notification_start_date + timedelta(
                    days=record.notification_interval
                )

    @api.depends('vehicle_id')
    def _compute_license_plate_noti(self):
        """Auto-populate ทะเบียนรถจากรถที่เลือก"""
        for record in self:
            if record.vehicle_id:
                record.license_plate = record.vehicle_id.license_plate
            else:
                record.license_plate = ''

    @api.depends('problem_category')
    def _compute_category_icon(self):
        """ได้ icon จากหมวดหมู่ปัญหา"""
        category_icons = {
            'engine': '🔧',
            'transmission': '⚙️',
            'brake': '🛑',
            'electrical': '⚡',
            'tire': '🛞',
            'oil_change': '🛢️',
            'body': '🚗',
            'other': '📋',
        }
        for record in self:
            record.category_icon = category_icons.get(record.problem_category, '📦')

    def name_get(self):
        """แสดงชื่อพร้อมกับหมวดหมู่ปัญหา"""
        result = []
        category_map = {
            'engine': '🔧 เครื่องยนต์',
            'transmission': '⚙️ ระบบเกียร์',
            'brake': '🛑 ระบบเบรก',
            'electrical': '⚡ ระบบไฟฟ้า',
            'tire': '🛞 ยาง',
            'oil_change': '🛢️ เปลี่ยนถ่ายน้ำมัน',
            'body': '🚗 ตัวถัง',
            'other': '📋 อื่นๆ',
        }
        for record in self:
            category_display = category_map.get(record.problem_category, record.problem_category or 'N/A')
            description = record.maintenance_id.description[:40] if record.maintenance_id.description else 'N/A'
            display_name = f"{category_display} - {description}"
            result.append((record.id, display_name))
        return result

    def action_send_notification_if_interval_complete(self):
        """ส่งแจ้งเตือนถ้าครบการแจ้งเตือน (ตามช่วงวัน)"""
        from datetime import timedelta

        for record in self:
            # ตรวจสอบว่าเปิดการแจ้งเตือนหรือไม่
            if not record.notification_enabled:
                raise ValidationError('❌ ต้องเปิดการแจ้งเตือนก่อน')

            today = date.today()

            # ตรวจสอบว่าอยู่ในช่วงการแจ้งเตือนหรือไม่
            if record.notification_start_date > today or record.notification_end_date < today:
                raise ValidationError(
                    f'❌ ไม่อยู่ในช่วงการแจ้งเตือน ({record.notification_start_date} - {record.notification_end_date})')

            # ตรวจสอบว่าถึงเวลาส่งแจ้งเตือนหรือไม่
            should_send = False
            message = ''

            if not record.notification_last_sent:
                # ส่งครั้งแรก
                should_send = True
                message = '📤 ส่งแจ้งเตือนครั้งแรก'
            else:
                last_sent_date = record.notification_last_sent.date()
                days_since_last = (today - last_sent_date).days

                if days_since_last >= record.notification_interval:
                    should_send = True
                    message = f'📤 ส่งแจ้งเตือนอีกครั้ง (ผ่านไป {days_since_last} วันแล้ว)'
                else:
                    remaining_days = record.notification_interval - days_since_last
                    raise ValidationError(f'⏳ ยังไม่ครบการแจ้งเตือน เหลือ {remaining_days} วัน')

            if should_send:
                record.action_send_notification()
                _logger.info(f"✓ {message}")

    def action_send_notification(self):
        """ส่งแจ้งเตือนในระบบ Odoo"""
        for record in self:
            if record.notification_enabled:
                try:
                    maintenance = record.maintenance_id

                    # สร้างข้อมูลแจ้งเตือน
                    title = f"🔧 การซ่อมบำรุงรถ: {maintenance.vehicle_id.license_plate}"
                    message = f"""
                    <b>รายการซ่อม:</b> {maintenance.description}<br/>
                    <b>ค่าใช้จ่าย:</b> ฿ {maintenance.cost:,.2f}<br/>
                    <b>วันเวลาเริ่มซ่อม:</b> {maintenance.maintenance_date.strftime('%d/%m/%Y %H:%M:%S') if maintenance.maintenance_date else '-'}<br/>
                    <b>วันเวลาซ่อมเสร็จ:</b> {maintenance.completed_date.strftime('%d/%m/%Y %H:%M:%S') if maintenance.completed_date else 'กำลังซ่อม'}<br/>
                    <b>ผู้ให้บริการ:</b> {maintenance.service_center if maintenance.service_provider == 'external' else 'ช่างภายใน'}<br/>
                    <b>ช่างผู้ซ่อม:</b> {maintenance.technician_id.name or '-'}
                    """

                    # หา recipients
                    recipients = record.recipient_ids if record.recipient_ids else self.env.user

                    # สร้าง Notification History
                    notification_history = self.env['notification.history'].create({
                        'maintenance_id': record.id,
                        'problem_category': record.problem_category,
                        'vehicle_id': maintenance.vehicle_id.id,
                        'notification_type': 'maintenance',
                        'title': title,
                        'message': message,
                        'note': record.note,
                        'recipient_ids': [(6, 0, recipients.ids)],
                        'status': 'sent',
                    })

                    # สร้าง Activity Notification สำหรับแต่ละผู้รับ
                    for recipient in recipients:
                        try:
                            # สร้าง Activity link ไปยัง notification.history
                            self.env['mail.activity'].create({
                                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                                'note': message,
                                'summary': title,
                                'res_model_id': self.env['ir.model'].search(
                                    [('model', '=', 'notification.history')]).id,
                                'res_id': notification_history.id,
                                'user_id': recipient.id,
                            })
                            _logger.info(f"✓ สร้าง Activity สำเร็จ: {recipient.name}")
                        except Exception as e:
                            _logger.warning(f"⚠️ สร้าง Activity ล้มเหลว: {str(e)}")

                    # อัปเดตข้อมูลการส่ง
                    record.write({
                        'notification_last_sent': datetime.now(),
                        'notification_count': record.notification_count + 1
                    })

                    _logger.info(f"✓ ส่งแจ้งเตือนสำเร็จ: {maintenance.name}")

                except Exception as e:
                    _logger.error(f"✗ ข้อผิดพลาดในการส่งแจ้งเตือน: {str(e)}")

    @api.model
    def _cron_send_maintenance_notifications(self):
        """ตรวจสอบและส่งแจ้งเตือนการซ่อมบำรุงอัตโนมัติ"""
        today = fields.Date.today()

        # ค้นหาข้อมูลแจ้งเตือนที่เปิดใช้งาน
        notifications = self.search([
            ('notification_enabled', '=', True),
            ('notification_start_date', '<=', today),
            ('notification_end_date', '>=', today),
        ])

        for notification in notifications:
            # ตรวจสอบว่าถึงเวลาส่งแจ้งเตือนหรือไม่
            if notification.notification_last_sent:
                last_sent_date = notification.notification_last_sent.date()
                days_since_last = (today - last_sent_date).days

                if days_since_last >= notification.notification_interval:
                    notification.action_send_notification()
                    _logger.info(f"📤 ส่งแจ้งเตือนซ้ำ: {notification.maintenance_id.name}")
            else:
                # ส่งครั้งแรก
                notification.action_send_notification()
                _logger.info(f"📤 ส่งแจ้งเตือนครั้งแรก: {notification.maintenance_id.name}")

        _logger.info(f"✓ ตรวจสอบและส่งแจ้งเตือน {len(notifications)} รายการ")
        return True