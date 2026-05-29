# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class MaintenanceApproval(models.Model):
    """การอนุมัติการแจ้งซ่อม"""
    _name = 'maintenance.approval'
    _description = 'Maintenance Approval'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char('เลขที่การอนุมัติ', required=True, copy=False, readonly=True, default='New')
    sequence = fields.Integer('ลำดับ', default=1)
    
    maintenance_request_id = fields.Many2one(
        'vehicle.maintenance.request',
        string='การแจ้งซ่อม',
        required=True,
        ondelete='cascade',
        tracking=True
    )
    
    approver_id = fields.Many2one(
        'res.users',
        string='ผู้อนุมัติ',
        required=True,
        domain="[('is_approver', '=', True)]",
        tracking=True
    )
    
    state = fields.Selection([
        ('pending', 'รอการอนุมัติ'),
        ('approved', 'อนุมัติ'),
        ('rejected', 'ให้แก้ไข'),
    ], string='สถานะ', default='pending', required=True, tracking=True)
    
    approval_date = fields.Datetime('วันที่อนุมัติ/ปฏิเสธ', readonly=True, tracking=True)
    approval_reason = fields.Text('เหตุผลในการส่งอนุมัติ', help='เหตุผลที่ผู้แจ้งซ่อมระบุตอนส่งอนุมัติ')
    approval_note = fields.Text('หมายเหตุการอนุมัติ', help='หมายเหตุจากผู้อนุมัติ (ไม่บังคับ)')
    rejection_reason = fields.Text('เหตุผลในการให้แก้ไข', help='เหตุผลที่ผู้อนุมัติให้แก้ไข')
    
    # ข้อมูลจาก request (สำหรับแสดงใน form)
    vehicle_id = fields.Many2one(related='maintenance_request_id.vehicle_id', string='รถ', store=True)
    license_plate = fields.Char(related='maintenance_request_id.license_plate', string='ทะเบียนรถ', store=True)
    problem_category = fields.Selection(related='maintenance_request_id.problem_category', string='หมวดหมู่', store=True)
    problem_description = fields.Text(related='maintenance_request_id.problem_description', string='รายละเอียดปัญหา')
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('maintenance.approval') or 'APR-NEW'
        return super().create(vals_list)
    
    def action_approve(self):
        """อนุมัติการแจ้งซ่อม"""
        self.ensure_one()
        
        if self.approver_id.id != self.env.user.id:
            raise ValidationError('❌ คุณไม่มีสิทธิ์อนุมัติรายการนี้')
        
        self.write({
            'state': 'approved',
            'approval_date': fields.Datetime.now()
        })
        
        # ตรวจสอบว่าทุก approval อนุมัติหรือยัง
        request = self.maintenance_request_id
        all_approvals = request.approval_ids
        
        if all(approval.state == 'approved' for approval in all_approvals):
            # ถ้าอนุมัติครบทุกคนแล้ว ให้เปลี่ยนสถานะเป็น pending
            request.write({
                'approval_state': 'approved',
                'state': 'pending'
            })
            _logger.info(f"✅ การแจ้งซ่อม {request.name} ได้รับการอนุมัติครบทุกคน")
        
        # สร้าง activity notification
        request.message_post(
            body=f"✅ {self.approver_id.name} ได้อนุมัติการแจ้งซ่อม",
            subject='การอนุมัติการแจ้งซ่อม',
            message_type='notification'
        )
        
        return True
    
    def action_reject(self):
        """ให้แก้ไขการแจ้งซ่อม - เปิด wizard"""
        self.ensure_one()
        
        if self.approver_id.id != self.env.user.id:
            raise ValidationError('❌ คุณไม่มีสิทธิ์ดำเนินการรายการนี้')
        
        return {
            'name': 'ให้แก้ไขการแจ้งซ่อม',
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.approval.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_approval_id': self.id,
                'default_maintenance_request_id': self.maintenance_request_id.id,
            }
        }
    
    def name_get(self):
        """แสดงชื่อที่อ่านง่าย"""
        result = []
        for record in self:
            display_name = f"[{record.sequence}] {record.approver_id.name}"
            if record.state == 'approved':
                display_name += " ✅"
            elif record.state == 'rejected':
                display_name += " ❌"
            else:
                display_name += " ⏳"
            result.append((record.id, display_name))
        return result
