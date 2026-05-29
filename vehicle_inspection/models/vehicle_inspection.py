# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime
import logging
import base64

_logger = logging.getLogger(__name__)


class VehicleInspection(models.Model):
    """รายการตรวจสอบสภาพรถ"""
    _name = 'vehicle.inspection'
    _description = 'Vehicle Inspection'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'inspection_date desc, id desc'

    name = fields.Char('เลขที่เอกสาร', required=True, copy=False, readonly=True, 
                       default=lambda self: _('New'))
    
    # ===== ข้อมูลรถที่ตรวจสอบ (ใหม่) =====
    vehicle_id = fields.Many2one('fleet.vehicle', string='ป้ายทะเบียนรถ', required=True,
                                 tracking=True, ondelete='restrict',
                                 domain="[('license_plate', '!=', 'ไม่มีทะเบียน')]",
                                 help='เลือกป้ายทะเบียนรถที่ต้องการตรวจสอบ')
    license_plate = fields.Char('ทะเบียนรถ', related='vehicle_id.license_plate', store=True)
    category_id = fields.Many2one('fleet.vehicle.model.category', string='ประเภทรถ', 
                                  required=True, tracking=True,
                                  help='ประเภทรถ (หมวดหมู่) จะถูกดึงมาจากข้อมูลรถอัตโนมัติ')
    category_name = fields.Char('ชื่อประเภทรถ', related='category_id.name', store=True)
    
    # ข้อมูลผู้ตรวจสอบ
    driver_id = fields.Many2one('vehicle.driver', string='ผู้ตรวจสอบ', required=True, 
                                tracking=True, ondelete='restrict')
    driver_name = fields.Char('ชื่อผู้ตรวจสอบ', related='driver_id.name', store=True)
    branch_id = fields.Many2one('res.branch', string='สาขา', tracking=True)
    
    # วันที่ตรวจสอบ
    inspection_date = fields.Datetime('วันที่ตรวจสอบ', required=True, 
                                      default=fields.Datetime.now, tracking=True)
    inspection_date_thai = fields.Char('วันที่ (ไทย)', compute='_compute_date_thai', store=True)
    
    # รายการตรวจเช็ค
    inspection_line_ids = fields.One2many('vehicle.inspection.line', 'inspection_id', 
                                          string='รายการตรวจเช็ค')
    
    # รายการบำรุงรักษา
    maintenance_line_ids = fields.One2many('vehicle.inspection.maintenance', 'inspection_id',
                                           string='รายการบำรุงรักษา')
    
    # หมายเหตุทั่วไป
    general_note = fields.Text('หมายเหตุ (ความผิดปกติอื่นๆที่ตรวจพบ)')
    
    # สถานะ
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'ยืนยัน'),
        ('approved', 'อนุมัติ'),
    ], string='สถานะ', default='draft', tracking=True)
    
    # ผู้ยืนยัน
    confirmed_by_name = fields.Char('ผู้ยืนยัน', readonly=True, tracking=True)
    
    # สถิติ
    total_items = fields.Integer('จำนวนรายการทั้งหมด', compute='_compute_statistics', store=True)
    checked_items = fields.Integer('รายการที่ตรวจแล้ว', compute='_compute_statistics', store=True)
    issue_count = fields.Integer('จำนวนปัญหาที่พบ', compute='_compute_statistics', store=True)
    
    # สิทธิ์ผู้ใช้ (Computed fields)
    can_confirm = fields.Boolean('สามารถยืนยัน', compute='_compute_user_permissions')
    can_approve = fields.Boolean('สามารถอนุมัติ', compute='_compute_user_permissions')
    can_reset = fields.Boolean('สามารถกลับเป็นร่าง', compute='_compute_user_permissions')

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """เมื่อเลือกรถ ให้ดึงหมวดหมู่มาอัตโนมัติจาก fleet.vehicle.category_id"""
        if self.vehicle_id and self.vehicle_id.category_id:
            self.category_id = self.vehicle_id.category_id
        else:
            self.category_id = False

    @api.depends_context('uid')
    def _compute_user_permissions(self):
        """คำนวณสิทธิ์ของผู้ใช้ปัจจุบัน"""
        current_user = self.env.user
        for record in self:
            record.can_confirm = current_user.can_confirm_vehicle_inspection
            record.can_approve = current_user.can_approve_vehicle_inspection
            record.can_reset = current_user.can_reset_vehicle_inspection

    @api.depends('inspection_date')
    def _compute_date_thai(self):
        """แปลงวันที่เป็นรูปแบบไทย"""
        thai_months = ['', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
                       'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
        for record in self:
            if record.inspection_date:
                dt = fields.Datetime.context_timestamp(record, record.inspection_date)
                thai_year = dt.year + 543
                record.inspection_date_thai = f"{dt.day} {thai_months[dt.month]} {thai_year} {dt.strftime('%H:%M')}"
            else:
                record.inspection_date_thai = ''

    @api.depends('inspection_line_ids', 'inspection_line_ids.is_checked', 'inspection_line_ids.note')
    def _compute_statistics(self):
        for record in self:
            lines = record.inspection_line_ids
            record.total_items = len(lines)
            record.checked_items = len(lines.filtered(lambda l: l.is_checked))
            record.issue_count = len(lines.filtered(lambda l: l.note))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('vehicle.inspection') or _('New')
            # ถ้ามี vehicle_id แต่ไม่มี category_id ให้ดึง category จาก fleet.vehicle.category_id โดยตรง
            if vals.get('vehicle_id') and not vals.get('category_id'):
                vehicle = self.env['fleet.vehicle'].browse(vals['vehicle_id'])
                if vehicle.category_id:
                    vals['category_id'] = vehicle.category_id.id
        return super().create(vals_list)

    def unlink(self):
        """ป้องกันการลบรายการตรวจสอบ ยกเว้นสถานะร่าง"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('❌ ไม่สามารถลบรายการตรวจสอบสภาพรถได้\nสามารถลบได้เฉพาะสถานะ "ร่าง" เท่านั้น'))
        return super().unlink()

    def action_confirm(self):
        """ยืนยันรายการตรวจสอบ - อัพเดทชื่อผู้ตรวจสอบเป็นชื่อผู้ login"""
        if not self.env.user.can_confirm_vehicle_inspection:
            raise UserError(_('❌ คุณไม่มีสิทธิ์ยืนยันรายการตรวจสอบสภาพรถ\nกรุณาติดต่อผู้ดูแลระบบ'))
        # อัพเดทชื่อผู้ตรวจสอบเป็นชื่อผู้ login ที่กดยืนยัน
        self.write({
            'state': 'confirmed',
            'confirmed_by_name': self.env.user.name,
        })

    def action_approve(self):
        """อนุมัติรายการตรวจสอบ"""
        if not self.env.user.can_approve_vehicle_inspection:
            raise UserError(_('❌ คุณไม่มีสิทธิ์อนุมัติรายการตรวจสอบสภาพรถ\nกรุณาติดต่อผู้ดูแลระบบ'))
        self.write({'state': 'approved'})

    def action_draft(self):
        """กลับเป็นร่าง"""
        if not self.env.user.can_reset_vehicle_inspection:
            raise UserError(_('❌ คุณไม่มีสิทธิ์เปลี่ยนสถานะรายการตรวจสอบสภาพรถกลับเป็นร่าง\nกรุณาติดต่อผู้ดูแลระบบ'))
        self.write({'state': 'draft'})


class VehicleInspectionLine(models.Model):
    """รายการตรวจเช็ค (ข้อ 1-20)"""
    _name = 'vehicle.inspection.line'
    _description = 'Vehicle Inspection Line'
    _order = 'sequence, id'

    inspection_id = fields.Many2one('vehicle.inspection', string='การตรวจสอบ', 
                                    required=True, ondelete='cascade')
    sequence = fields.Integer('ลำดับ', default=10)
    item_no = fields.Char('ข้อที่', required=True)
    name = fields.Char('รายการตรวจเช็ค', required=True)
    standard = fields.Char('ค่ามาตรฐาน')
    is_checked = fields.Boolean('ตรวจสอบแล้ว', default=False)
    note = fields.Text('อาการชำรุด/หมายเหตุ')
    image = fields.Binary('รูปภาพ', attachment=True)
    image_filename = fields.Char('ชื่อไฟล์รูป')


class VehicleInspectionMaintenance(models.Model):
    """รายการบำรุงรักษา (ข้อ 21-24)"""
    _name = 'vehicle.inspection.maintenance'
    _description = 'Vehicle Inspection Maintenance'
    _order = 'sequence, id'

    inspection_id = fields.Many2one('vehicle.inspection', string='การตรวจสอบ', 
                                    required=True, ondelete='cascade')
    sequence = fields.Integer('ลำดับ', default=10)
    item_no = fields.Char('ข้อที่', required=True)
    name = fields.Char('รายการ', required=True)
    
    is_due = fields.Selection([
        ('due', 'ครบกำหนด'),
        ('not_due', 'ยังไม่ครบกำหนด'),
    ], string='สถานะ')
    
    current_mileage = fields.Char('เลขไมล์ปัจจุบัน')
    last_change_mileage = fields.Char('เลขไมล์ที่เปลี่ยนครั้งล่าสุด')
