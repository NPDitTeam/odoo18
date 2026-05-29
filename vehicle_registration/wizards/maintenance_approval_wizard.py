# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class MaintenanceApprovalWizard(models.TransientModel):
    """Wizard สำหรับส่งอนุมัติการแจ้งซ่อม"""
    _name = 'maintenance.approval.wizard'
    _description = 'Maintenance Approval Wizard'

    maintenance_request_id = fields.Many2one(
        'vehicle.maintenance.request',
        string='การแจ้งซ่อม',
        required=True,
        readonly=True
    )
    
    # ข้อมูลแสดง
    vehicle_id = fields.Many2one(related='maintenance_request_id.vehicle_id', string='รถ')
    license_plate = fields.Char(related='maintenance_request_id.license_plate', string='ทะเบียนรถ')
    problem_category = fields.Selection(related='maintenance_request_id.problem_category', string='หมวดหมู่')
    problem_description = fields.Text(related='maintenance_request_id.problem_description', string='รายละเอียดปัญหา')
    
    approver_ids = fields.Many2many(
        'res.users',
        string='เลือกผู้อนุมัติ',
        required=True,
        domain="[('is_approver', '=', True)]",
        help='เลือกผู้อนุมัติได้สูงสุด 2 คน'
    )
    
    approval_reason = fields.Text(
        'เหตุผลในการส่งอนุมัติ',
        required=True,
        help='ระบุเหตุผลที่ต้องการส่งอนุมัติการแจ้งซ่อม'
    )
    
    @api.constrains('approver_ids')
    def _check_approver_limit(self):
        """ตรวจสอบว่าเลือกผู้อนุมัติไม่เกิน 2 คน"""
        for wizard in self:
            if len(wizard.approver_ids) > 2:
                raise ValidationError('❌ สามารถเลือกผู้อนุมัติได้ไม่เกิน 2 คน')
            if len(wizard.approver_ids) < 1:
                raise ValidationError('❌ กรุณาเลือกผู้อนุมัติอย่างน้อย 1 คน')
    
    def action_send_approval(self):
        """ส่งอนุมัติไปยังผู้อนุมัติ"""
        self.ensure_one()
        
        request = self.maintenance_request_id
        
        # ตรวจสอบจำนวนผู้อนุมัติ
        if len(self.approver_ids) > 2:
            raise ValidationError('❌ สามารถเลือกผู้อนุมัติได้ไม่เกิน 2 คน')
        
        # สร้างการอนุมัติสำหรับแต่ละผู้อนุมัติ
        sequence = 1
        approval_records = []
        
        for approver in self.approver_ids:
            approval = self.env['maintenance.approval'].create({
                'maintenance_request_id': request.id,
                'approver_id': approver.id,
                'sequence': sequence,
                'approval_reason': self.approval_reason,
                'state': 'pending',
            })
            approval_records.append(approval)
            sequence += 1
            
            # สร้าง activity สำหรับผู้อนุมัติ
            request.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=approver.id,
                summary=f'รออนุมัติการแจ้งซ่อม: {request.name}',
                note=f"""
                <b>รถ:</b> {request.license_plate}<br/>
                <b>หมวดหมู่:</b> {dict(request._fields['problem_category'].selection).get(request.problem_category)}<br/>
                <b>ปัญหา:</b> {request.problem_description}<br/>
                <b>เหตุผล:</b> {self.approval_reason}
                """
            )
        
        # อัปเดตสถานะการแจ้งซ่อม
        request.write({
            'approval_state': 'waiting',  # แก้จาก 'pending' เป็น 'waiting'
            'state': 'waiting_approval'  # แก้จาก 'draft' เป็น 'waiting_approval'
        })
        
        # ส่งข้อความแจ้งเตือน
        request.message_post(
            body=f"📤 ส่งอนุมัติไปยัง: {', '.join(self.approver_ids.mapped('name'))}<br/>"
                 f"<b>เหตุผล:</b> {self.approval_reason}",
            subject='ส่งอนุมัติการแจ้งซ่อม',
            message_type='notification'
        )
        
        _logger.info(f"✅ ส่งอนุมัติ {request.name} ไปยัง {len(self.approver_ids)} คน")
        
        return {'type': 'ir.actions.act_window_close'}


class MaintenanceApprovalRejectWizard(models.TransientModel):
    """Wizard สำหรับให้แก้ไขการแจ้งซ่อม"""
    _name = 'maintenance.approval.reject.wizard'
    _description = 'Maintenance Approval Reject Wizard'

    approval_id = fields.Many2one(
        'maintenance.approval',
        string='การอนุมัติ',
        required=True,
        readonly=True
    )
    
    maintenance_request_id = fields.Many2one(
        'vehicle.maintenance.request',
        string='การแจ้งซ่อม',
        required=True,
        readonly=True
    )
    
    # ข้อมูลแสดง
    vehicle_id = fields.Many2one(related='maintenance_request_id.vehicle_id', string='รถ')
    license_plate = fields.Char(related='maintenance_request_id.license_plate', string='ทะเบียนรถ')
    problem_category = fields.Selection(related='maintenance_request_id.problem_category', string='หมวดหมู่')
    problem_description = fields.Text(related='maintenance_request_id.problem_description', string='รายละเอียดปัญหา')
    
    rejection_reason = fields.Text(
        'เหตุผลในการให้แก้ไข',
        required=True,
        help='ระบุเหตุผลที่ต้องการให้แก้ไขการแจ้งซ่อม'
    )
    
    approval_note = fields.Text(
        'หมายเหตุเพิ่มเติม',
        help='หมายเหตุเพิ่มเติมจากผู้อนุมัติ (ไม่บังคับ)'
    )
    
    def action_reject(self):
        """บันทึกการให้แก้ไข"""
        self.ensure_one()
        
        approval = self.approval_id
        request = self.maintenance_request_id
        
        # อัปเดตสถานะการอนุมัติ
        approval.write({
            'state': 'rejected',
            'approval_date': fields.Datetime.now(),
            'rejection_reason': self.rejection_reason,
            'approval_note': self.approval_note,
        })
        
        # อัปเดตสถานะการแจ้งซ่อม
        request.write({
            'approval_state': 'rejected',
            'state': 'draft'  # กลับไปแก้ไข
        })
        
        # ส่งข้อความแจ้งเตือนให้ผู้แจ้ง
        request.message_post(
            body=f"❌ {approval.approver_id.name} ให้แก้ไขการแจ้งซ่อม<br/>"
                 f"<b>เหตุผล:</b> {self.rejection_reason}<br/>"
                 f"<b>หมายเหตุ:</b> {self.approval_note or '-'}",
            subject='ให้แก้ไขการแจ้งซ่อม',
            message_type='notification',
            partner_ids=request.requester_id.partner_id.ids
        )
        
        # สร้าง activity สำหรับผู้แจ้ง
        request.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=request.requester_id.id,
            summary=f'แก้ไขการแจ้งซ่อม: {request.name}',
            note=f"""
            <b>ผู้อนุมัติ:</b> {approval.approver_id.name}<br/>
            <b>เหตุผลในการให้แก้ไข:</b> {self.rejection_reason}<br/>
            <b>หมายเหตุ:</b> {self.approval_note or '-'}
            """
        )
        
        # ลบ activity ของผู้อนุมัติคนอื่น
        request.activity_ids.filtered(
            lambda a: a.user_id.id != request.requester_id.id and a.activity_type_id.id == self.env.ref('mail.mail_activity_data_todo').id
        ).unlink()
        
        _logger.info(f"❌ {approval.approver_id.name} ให้แก้ไข {request.name}")
        
        return {'type': 'ir.actions.act_window_close'}
