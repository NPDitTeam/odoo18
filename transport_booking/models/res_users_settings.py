# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TransportUserSettings(models.Model):
    _name = 'transport.user.settings'
    _description = 'Transport User Tracking Settings'
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', string='ผู้ใช้', required=True, ondelete='cascade')

    # การติดตามตำแหน่ง
    tracking_enabled = fields.Boolean(
        string='เปิดการติดตาม',
        default=True,
        help='เปิด/ปิดการติดตามตำแหน่งรถขณะขนส่ง'
    )

    tracking_refresh_interval = fields.Integer(
        string='ช่วงเวลาติดตาม (นาที)',
        default=2,
        required=True,
        help='ความถี่ในการอัพเดทตำแหน่งบนแผนที่ (1-60 นาที) เพื่อประหยัดค่าใช้จ่าย Google Maps API'
    )

    high_accuracy_mode = fields.Boolean(
        string='โหมดความแม่นยำสูง',
        default=False,
        help='ใช้ GPS ความแม่นยำสูง (ใช้แบตเตอรี่มากขึ้น)'
    )

    # การแจ้งเตือน
    notify_on_arrival = fields.Boolean(
        string='แจ้งเตือนเมื่อถึงจุดหมาย',
        default=True,
        help='แจ้งเตือนเมื่อรถถึงจุดหมายปลายทาง'
    )

    notify_on_delay = fields.Boolean(
        string='แจ้งเตือนเมื่อล่าช้า',
        default=True,
        help='แจ้งเตือนเมื่อรถล่าช้ากว่าเวลาที่กำหนด'
    )

    notify_off_route = fields.Boolean(
        string='แจ้งเตือนออกนอกเส้นทาง',
        default=True,
        help='แจ้งเตือนเมื่อรถออกนอกเส้นทางที่กำหนด'
    )

    off_route_distance = fields.Integer(
        string='ระยะออกนอกเส้นทาง (เมตร)',
        default=500,
        help='ระยะทางที่ถือว่าออกนอกเส้นทาง'
    )

    # การแสดงผลแผนที่
    show_speed_indicator = fields.Boolean(
        string='แสดงความเร็ว',
        default=True,
        help='แสดงความเร็วปัจจุบันของรถ'
    )

    show_route_history = fields.Boolean(
        string='แสดงเส้นทาง',
        default=True,
        help='แสดงเส้นทางที่รถวิ่งผ่านมา'
    )

    map_type = fields.Selection([
        ('roadmap', 'แผนที่ถนน'),
        ('satellite', 'ภาพดาวเทียม'),
        ('hybrid', 'แบบผสม'),
        ('terrain', 'ภูมิประเทศ')
    ], string='ประเภทแผนที่', default='roadmap')

    # การบันทึกข้อมูล
    save_history = fields.Boolean(
        string='บันทึกประวัติ',
        default=True,
        help='บันทึกประวัติการเดินทาง'
    )

    history_retention_days = fields.Integer(
        string='เก็บประวัติ (วัน)',
        default=30,
        help='จำนวนวันที่เก็บประวัติการเดินทาง'
    )

    active = fields.Boolean(string='ใช้งาน', default=True)

    _sql_constraints = [
        ('user_id_unique', 'UNIQUE(user_id)', 'แต่ละผู้ใช้สามารถมีการตั้งค่าได้เพียงชุดเดียว'),
    ]

    @api.constrains('tracking_refresh_interval')
    def _check_refresh_interval(self):
        """ตรวจสอบเวลา refresh ต้องอยู่ในช่วงที่เหมาะสม"""
        for record in self:
            if record.tracking_refresh_interval < 1:
                raise ValidationError('⚠️ ช่วงเวลาติดตามต้องไม่น้อยกว่า 1 นาที')
            if record.tracking_refresh_interval > 60:
                raise ValidationError('⚠️ ช่วงเวลาติดตามต้องไม่เกิน 60 นาที')

    @api.constrains('off_route_distance')
    def _check_off_route_distance(self):
        """ตรวจสอบระยะออกนอกเส้นทาง"""
        for record in self:
            if record.off_route_distance < 50:
                raise ValidationError('⚠️ ระยะออกนอกเส้นทางต้องไม่น้อยกว่า 50 เมตร')
            if record.off_route_distance > 5000:
                raise ValidationError('⚠️ ระยะออกนอกเส้นทางต้องไม่เกิน 5,000 เมตร')

    @api.constrains('history_retention_days')
    def _check_history_retention(self):
        """ตรวจสอบจำนวนวันเก็บประวัติ"""
        for record in self:
            if record.history_retention_days < 1:
                raise ValidationError('⚠️ ต้องเก็บประวัติอย่างน้อย 1 วัน')
            if record.history_retention_days > 365:
                raise ValidationError('⚠️ เก็บประวัติได้ไม่เกิน 365 วัน')

    @api.model
    def get_user_settings(self, user_id=None):
        """ดึงการตั้งค่าของผู้ใช้ ถ้าไม่มีให้สร้างค่าเริ่มต้น"""
        if not user_id:
            user_id = self.env.user.id

        settings = self.search([('user_id', '=', user_id)], limit=1)
        if not settings:
            settings = self.create({'user_id': user_id})

        return {
            'tracking_enabled': settings.tracking_enabled,
            'tracking_refresh_interval': settings.tracking_refresh_interval,
            'high_accuracy_mode': settings.high_accuracy_mode,
            'notify_on_arrival': settings.notify_on_arrival,
            'notify_on_delay': settings.notify_on_delay,
            'notify_off_route': settings.notify_off_route,
            'off_route_distance': settings.off_route_distance,
            'show_speed_indicator': settings.show_speed_indicator,
            'show_route_history': settings.show_route_history,
            'map_type': settings.map_type,
            'save_history': settings.save_history,
            'history_retention_days': settings.history_retention_days,
        }

    def action_update_settings(self, vals):
        """อัพเดทการตั้งค่าผู้ใช้จาก Mobile App"""
        self.ensure_one()
        return self.write(vals)