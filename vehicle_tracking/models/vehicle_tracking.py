# -*- coding: utf-8 -*-

from odoo import models, fields, api
import requests
import json
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class VehicleTracking(models.Model):
    _name = 'gps.vehicle.tracking'
    _description = 'GPS Vehicle Tracking'
    _order = 'write_date desc'

    # Vehicle Information
    imei = fields.Char(string='IMEI', required=True, index=True)
    device_name = fields.Char(string='ชื่ออุปกรณ์')
    lpn = fields.Char(string='เลขทะเบียนรถ', index=True)
    fleet_name = fields.Char(string='ชื่อกลุ่มรถ')
    product_name = fields.Char(string='รุ่นอุปกรณ์')
    
    # Location Information
    latitude = fields.Float(string='ละติจูด', digits=(10, 6))
    longitude = fields.Float(string='ลองจิจูด', digits=(10, 6))
    altitude = fields.Float(string='ความสูง')
    course = fields.Float(string='ทิศทาง')
    utc_timestamp = fields.Datetime(string='เวลา (UTC)')
    recv_utc_timestamp = fields.Datetime(string='เวลารับข้อมูล')
    
    # Vehicle Status
    speed = fields.Float(string='ความเร็ว (กม./ชม.)')
    mileage = fields.Float(string='เลขไมล์ (ม.)')
    mileage_km = fields.Float(string='เลขไมล์ (กม.)', compute='_compute_mileage_km', store=True)
    engine_status = fields.Selection([
        ('0', 'ดับ'),
        ('1', 'ติด')
    ], string='สถานะเครื่องยนต์', default='0')
    gps_fix = fields.Selection([
        ('0', 'ไม่มีสัญญาณ'),
        ('1', 'มีสัญญาณ')
    ], string='สัญญาณ GPS', default='0')
    sos = fields.Boolean(string='SOS')
    acc_on_time = fields.Datetime(string='เวลาติด ACC')
    
    # Signal Information
    gsm = fields.Char(string='สัญญาณ GSM')
    gsm_level = fields.Char(string='ระดับสัญญาณ GSM')
    num_sat = fields.Char(string='จำนวนดาวเทียม')
    hdop = fields.Float(string='HDOP')
    lbs = fields.Char(string='LBS')
    
    # Battery Information
    ext_bat_status = fields.Integer(string='สถานะแบตเตอรี่สำรอง')
    car_battery = fields.Char(string='แบตเตอรี่รถ')
    battery_voltage = fields.Float(string='แรงดันแบตเตอรี่')
    supply_voltage = fields.Float(string='แรงดันไฟเลี้ยง')
    battery_level = fields.Float(string='ระดับแบตเตอรี่')
    
    # Other Information
    io = fields.Char(string='IO')
    stage = fields.Char(string='ขั้นตอน')
    expire_time = fields.Datetime(string='วันหมดอายุ')
    temperature = fields.Float(string='อุณหภูมิ')
    
    # Computed Fields
    status_text = fields.Char(string='สถานะ', compute='_compute_status_text')
    map_url = fields.Char(string='URL แผนที่', compute='_compute_map_url')

    @api.depends('mileage')
    def _compute_mileage_km(self):
        for record in self:
            record.mileage_km = record.mileage / 1000.0 if record.mileage else 0.0

    @api.depends('engine_status', 'speed', 'gps_fix')
    def _compute_status_text(self):
        for record in self:
            if record.engine_status == '1' and record.speed > 0:
                record.status_text = 'กำลังเคลื่อนที่'
            elif record.engine_status == '1' and record.speed == 0:
                record.status_text = 'จอด (เครื่องยนต์ติด)'
            else:
                record.status_text = 'จอด'

    @api.depends('latitude', 'longitude')
    def _compute_map_url(self):
        for record in self:
            if record.latitude and record.longitude:
                record.map_url = f"https://www.google.com/maps?q={record.latitude},{record.longitude}"
            else:
                record.map_url = False

    def action_refresh_data(self):
        """Refresh vehicle data from API"""
        self.ensure_one()
        return self.fetch_vehicle_data()

    @api.model
    def fetch_vehicle_data(self):
        """Fetch all vehicle data from DistarGPS API"""
        try:
            url = "https://api.distargps.com/gps/realtime2"
            headers = {
                'key': '77c7a1831c7d43b3ae302ac4ea922f79',
                'sign': '236453099ac29ca30c037574da652712',
                'x-key': 'ff218669ceb63d2d567c4f3616a0f21d',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, headers=headers, timeout=30)
            
            # Handle rate limiting (429 error)
            if response.status_code == 429:
                _logger.warning("API Rate limit exceeded. Please wait before trying again.")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'เรียก API บ่อยเกินไป',
                        'message': 'API มีการจำกัดจำนวนครั้ง กรุณารอสักครู่แล้วลองใหม่อีกครั้ง หรือเพิ่มช่วงเวลาของ Scheduled Action',
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data and isinstance(data['data'], list):
                self._process_api_data(data['data'])
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'สำเร็จ',
                        'message': f'อัพเดทข้อมูล {len(data["data"])} คันเรียบร้อยแล้ว',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise ValueError("Invalid API response format")
                
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error: {str(e)}"
            _logger.error(f"Error fetching vehicle data: {error_msg}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'เกิดข้อผิดพลาด',
                    'message': f'ไม่สามารถดึงข้อมูลได้: {error_msg}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            _logger.error(f"Error fetching vehicle data: {error_msg}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'เกิดข้อผิดพลาด',
                    'message': f'ไม่สามารถดึงข้อมูลได้: {error_msg}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _process_api_data(self, vehicles_data):
        """Process and update vehicle data from API"""
        for vehicle_data in vehicles_data:
            existing = self.search([('imei', '=', vehicle_data.get('imei'))], limit=1)
            
            values = {
                'imei': vehicle_data.get('imei'),
                'device_name': vehicle_data.get('deviceName'),
                'lpn': vehicle_data.get('lpn'),
                'fleet_name': vehicle_data.get('fleet_name'),
                'product_name': vehicle_data.get('product_name'),
                'latitude': vehicle_data.get('lat'),
                'longitude': vehicle_data.get('lon'),
                'altitude': vehicle_data.get('alt'),
                'course': vehicle_data.get('course'),
                'speed': vehicle_data.get('speed'),
                'mileage': vehicle_data.get('mileage'),
                'engine_status': str(vehicle_data.get('engineStatus')) if vehicle_data.get('engineStatus') is not None else '0',
                'gps_fix': str(vehicle_data.get('gpsFix')) if vehicle_data.get('gpsFix') is not None else '0',
                'sos': vehicle_data.get('sos', False),
                'gsm': vehicle_data.get('gsm'),
                'gsm_level': vehicle_data.get('gsm_level'),
                'num_sat': vehicle_data.get('numSat'),
                'hdop': vehicle_data.get('hdop'),
                'lbs': vehicle_data.get('lbs'),
                'ext_bat_status': vehicle_data.get('extBatStatus'),
                'car_battery': vehicle_data.get('carBattery'),
                'battery_voltage': vehicle_data.get('battery_voltage'),
                'supply_voltage': vehicle_data.get('supply_voltage'),
                'battery_level': vehicle_data.get('battery_level'),
                'io': vehicle_data.get('io'),
                'stage': vehicle_data.get('stage'),
                'temperature': vehicle_data.get('temperature'),
            }
            
            # Handle datetime fields
            if vehicle_data.get('utcTs'):
                try:
                    values['utc_timestamp'] = datetime.strptime(
                        vehicle_data['utcTs'], '%Y-%m-%dT%H:%M:%S.%fZ'
                    )
                except:
                    pass
                    
            if vehicle_data.get('recvUtcTs'):
                try:
                    values['recv_utc_timestamp'] = datetime.strptime(
                        vehicle_data['recvUtcTs'], '%Y-%m-%dT%H:%M:%S.%fZ'
                    )
                except:
                    pass
                    
            if vehicle_data.get('accOnTime'):
                try:
                    values['acc_on_time'] = datetime.strptime(
                        vehicle_data['accOnTime'], '%Y-%m-%dT%H:%M:%S.%fZ'
                    )
                except:
                    pass
                    
            if vehicle_data.get('expire_time'):
                try:
                    values['expire_time'] = datetime.strptime(
                        vehicle_data['expire_time'], '%Y-%m-%dT%H:%M:%S.%fZ'
                    )
                except:
                    pass
            
            if existing:
                existing.write(values)
            else:
                self.create(values)

    def action_view_on_map(self):
        """Open vehicle location on interactive map with auto-refresh"""
        self.ensure_one()
        if self.latitude and self.longitude:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/vehicle_tracking/map/{self.id}',
                'target': 'new',
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'คำเตือน',
                    'message': 'ไม่พบข้อมูล GPS',
                    'type': 'warning',
                }
            }
