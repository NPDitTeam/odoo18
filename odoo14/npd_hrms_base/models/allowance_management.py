# -*- coding: utf-8 -*-
"""จัดการค่าเบี้ยเลี้ยง — ประกาศประเภท/ราคาเบี้ยเลี้ยงต่อสาขา แล้วให้แอปดึงไปแสดง

พอร์ตจาก Odoo 14 โดยเปลี่ยน branch_ids ไปชี้ res.branch และเพิ่ม company_id
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ALLOWANCE_STATES = [
    ('รออนุมัติ', 'รออนุมัติ'),
    ('อนุมัติ', 'อนุมัติ'),
    ('ไม่อนุมัติ', 'ไม่อนุมัติ'),
    ('ยกเลิก', 'ยกเลิก'),
]


class AllowanceManagement(models.Model):
    _name = 'allowance.management'
    _description = 'จัดการค่าเบี้ยเลี้ยง'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='ชื่อรายการ', required=True,
        default=lambda self: _('ค่าเบี้ยเลี้ยง %s')
        % fields.Date.context_today(self).strftime('%Y-%m-%d'))
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)
    branch_ids = fields.Many2many(
        'res.branch', 'allowance_management_branch_rel',
        'allowance_id', 'branch_id', string='สาขา', required=True,
        help='เลือกได้มากกว่า 1 สาขา กรณีที่ประเภทและราคาเหมือนกัน')
    line_ids = fields.One2many(
        'allowance.management.line', 'allowance_id',
        string='รายการประเภทค่าเบี้ยเลี้ยง')
    state = fields.Selection(
        ALLOWANCE_STATES, string='สถานะ', default='รออนุมัติ',
        readonly=True, tracking=True)
    reason = fields.Text(string='เหตุผลจากผู้อนุมัติ')
    approved_by = fields.Many2one('res.users', string='ผู้อนุมัติ', readonly=True)
    approved_at = fields.Datetime(string='วันที่อนุมัติ', readonly=True)
    created_at = fields.Datetime(
        string='วันที่สร้าง', default=fields.Datetime.now, readonly=True)

    # ------------------------------------------------------------------
    # ปุ่มดำเนินการ
    # ------------------------------------------------------------------
    def action_approve(self):
        for rec in self:
            if rec.state != 'รออนุมัติ':
                raise UserError(
                    "สามารถอนุมัติได้เฉพาะรายการที่สถานะ 'รออนุมัติ' เท่านั้น")
            if not rec.line_ids:
                raise UserError('กรุณาเพิ่มรายการประเภทค่าเบี้ยเลี้ยงก่อนอนุมัติ')
            if not rec.branch_ids:
                raise UserError('กรุณาเลือกสาขาก่อนอนุมัติ')
            rec.sudo().write({
                'state': 'อนุมัติ',
                'approved_by': self.env.user.id,
                'approved_at': fields.Datetime.now(),
                'reason': '',
            })

    def action_reject(self):
        self.ensure_one()
        if self.state != 'รออนุมัติ':
            raise UserError(
                "สามารถไม่อนุมัติได้เฉพาะรายการที่สถานะ 'รออนุมัติ' เท่านั้น")
        return {
            'type': 'ir.actions.act_window',
            'name': 'ไม่อนุมัติรายการค่าเบี้ยเลี้ยง',
            'res_model': 'allowance.management.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_allowance_id': self.id},
        }

    def action_cancel(self):
        for rec in self:
            rec.sudo().write({
                'state': 'ยกเลิก',
                'approved_by': self.env.user.id,
                'approved_at': fields.Datetime.now(),
            })

    def action_reset_draft(self):
        for rec in self:
            rec.sudo().write({
                'state': 'รออนุมัติ',
                'approved_by': False,
                'approved_at': False,
                'reason': '',
            })

    # ------------------------------------------------------------------
    # API สำหรับแอป
    # ------------------------------------------------------------------
    @api.model
    def api_get_allowances_by_employee_code(self, employee_code):
        """รายการประเภทค่าเบี้ยเลี้ยงที่พนักงานคนนี้เบิกได้ (อิงสาขาของเขา)

        ราคาเลือกตามสัญชาติ: ไทย → amount, อื่น ๆ (รวมไม่ระบุ) → amount_foreign
        คงลายเซ็นเดิมจาก Odoo 14 เพราะแอปเรียกเมธอดนี้อยู่แล้ว
        """
        if not employee_code:
            return []
        emp = self.env['employee.salary'].sudo().search(
            [('employee_code', '=', str(employee_code))], limit=1)
        if not emp or not emp.branch_id:
            return []
        records = self.sudo().search([
            ('state', '=', 'อนุมัติ'),
            ('branch_ids', 'in', [emp.branch_id.id]),
            ('company_id', '=', (emp.company_id or self.env.company).id),
        ])
        is_foreign = emp.nationality != 'ไทย'
        result = []
        seen = set()
        for rec in records:
            for line in rec.line_ids:
                key = (line.name or '').strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                amount_val = line.amount_foreign if is_foreign else line.amount
                has_amount = bool(amount_val and amount_val > 0)
                result.append({
                    'name': line.name or '',
                    'amount': float(amount_val) if has_amount else None,
                    'has_amount': has_amount,
                    'note': line.note or '',
                })
        return result


class AllowanceManagementLine(models.Model):
    _name = 'allowance.management.line'
    _description = 'รายการประเภทค่าเบี้ยเลี้ยง'
    _order = 'id asc'

    allowance_id = fields.Many2one(
        'allowance.management', string='จัดการค่าเบี้ยเลี้ยง',
        required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='allowance_id.company_id', store=True, readonly=True)
    name = fields.Char(string='ประเภทค่าเบี้ยเลี้ยง', required=True)
    amount = fields.Float(
        string='ราคา (บาท) ไทย',
        help='สำหรับพนักงานสัญชาติไทย — เว้นว่างได้ ผู้ใช้แอปจะกรอกเองตอนเลือก')
    amount_foreign = fields.Float(
        string='ราคา (บาท) ต่างชาติ',
        help='สำหรับพนักงานสัญชาติต่างชาติ — เว้นว่างได้ ผู้ใช้แอปจะกรอกเองตอนเลือก')
    note = fields.Text(string='หมายเหตุ')
    state = fields.Selection(
        related='allowance_id.state', store=True, readonly=True)


class AllowanceManagementRejectWizard(models.TransientModel):
    _name = 'allowance.management.reject.wizard'
    _description = 'Wizard ไม่อนุมัติค่าเบี้ยเลี้ยง'

    allowance_id = fields.Many2one(
        'allowance.management', string='รายการ', required=True)
    reason = fields.Text(string='เหตุผลในการไม่อนุมัติ', required=True)

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.reason:
            raise UserError('กรุณากรอกเหตุผล')
        self.allowance_id.sudo().write({
            'state': 'ไม่อนุมัติ',
            'reason': self.reason,
            'approved_by': self.env.user.id,
            'approved_at': fields.Datetime.now(),
        })
