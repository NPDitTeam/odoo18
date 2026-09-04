# -*- coding: utf-8 -*-
"""กำหนดสิทธิหยุดวันเสาร์ (รายสาขา + override รายบุคคล)

พอร์ตจาก Odoo 14 โดยเปลี่ยนสองอย่าง:
  1. สาขาชี้ไป res.branch แทน hr.branch.custom
  2. ค่าเริ่มต้น (HQ 2 ครั้ง / สาขา 1 ครั้ง) อ่านจาก res.company แทน constant ในโค้ด
     และตัดสินว่าเป็นสำนักงานใหญ่จากธง res.branch.hr_is_head_office แทนการเดาจากชื่อ
"""
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class SaturdayLeaveConfig(models.Model):
    _name = 'saturday.leave.config'
    _description = 'กำหนดสิทธิหยุดวันเสาร์'
    _order = 'branch_id'
    _rec_name = 'branch_id'

    branch_id = fields.Many2one(
        'res.branch', string='สาขา', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)
    days_allowed = fields.Integer(
        string='สิทธิหยุดวันเสาร์/เดือน (ครั้ง)', default=1, required=True,
        help='ค่าเริ่มต้นของทั้งสาขา — ปรับรายบุคคลได้ที่ตารางพนักงานด้านล่าง')
    employee_line_ids = fields.One2many(
        'saturday.leave.employee', 'config_id',
        string='สิทธิหยุดวันเสาร์รายบุคคล (override)')
    employee_override_count = fields.Integer(
        string='พนักงาน (คน)', compute='_compute_employee_override_count')

    _sql_constraints = [
        ('branch_company_uniq', 'unique(branch_id, company_id)',
         'สาขานี้มีการตั้งค่าสิทธิหยุดวันเสาร์อยู่แล้ว'),
    ]

    @api.depends('employee_line_ids')
    def _compute_employee_override_count(self):
        for rec in self:
            rec.employee_override_count = len(rec.employee_line_ids)

    def write(self, vals):
        """แก้ค่าระดับสาขา → cascade ไปบรรทัดพนักงานที่ยังเป็นค่า default เดิม

        บรรทัดที่ตั้งค่าเฉพาะคนไว้ (ค่าต่างจาก default เดิม) จะไม่ถูกแตะ
        """
        cascade_map = {}
        if 'days_allowed' in vals:
            new_val = vals['days_allowed']
            for rec in self:
                if rec.days_allowed != new_val:
                    cascade_map[rec.id] = (rec.days_allowed, new_val)
        res = super().write(vals)
        for rec in self:
            if rec.id in cascade_map:
                old_val, new_val = cascade_map[rec.id]
                lines = rec.employee_line_ids.filtered(
                    lambda line: line.days_allowed == old_val)
                if lines:
                    lines.write({'days_allowed': new_val})
        return res

    # ------------------------------------------------------------------
    # ค่าเริ่มต้นตามชนิดสาขา
    # ------------------------------------------------------------------
    @api.model
    def _default_days_for_branch(self, branch, company=None):
        company = company or self.env.company
        if branch.hr_is_head_office:
            return company.hrms_saturday_days_hq or 2
        return company.hrms_saturday_days_branch or 1

    @api.model
    def _seed_missing_branches(self, company=None):
        """สร้าง config ให้สาขาที่ยังไม่มี (ไม่แตะค่าที่ผู้ใช้ปรับไว้แล้ว)"""
        company = company or self.env.company
        branches = self.env['res.branch'].sudo().with_context(
            bypass_branch_company_filter=True).search([
                ('hr_use_in_hrms', '=', True),
                '|', ('company_ids', '=', False), ('company_ids', 'in', company.ids),
            ])
        existing = set(self.sudo().search(
            [('company_id', '=', company.id)]).mapped('branch_id').ids)
        for branch in branches:
            if branch.id not in existing:
                self.sudo().create({
                    'branch_id': branch.id,
                    'company_id': company.id,
                    'days_allowed': self._default_days_for_branch(branch, company),
                })

    @api.model
    def _seed_employee_lines(self, configs=None):
        """ดึงพนักงานตามสาขามาลงตาราง override

        - คนที่ยังไม่มีบรรทัด → สร้างใหม่ (ค่าเริ่มต้น = ค่าของสาขา)
        - คนที่ย้ายสาขา → ย้ายบรรทัดตามสาขาใหม่ โดยคงค่า days_allowed เดิมที่ตั้งไว้
        """
        EmpLine = self.env['saturday.leave.employee'].sudo()
        Employee = self.env['employee.salary'].sudo()
        if configs is None:
            configs = self.sudo().search([])
        for cfg in configs:
            if not cfg.branch_id:
                continue
            employees = Employee.search([
                ('branch_id', '=', cfg.branch_id.id),
                ('company_id', '=', cfg.company_id.id),
            ])
            for emp in employees:
                line = EmpLine.search([('employee_id', '=', emp.id)], limit=1)
                if not line:
                    EmpLine.create({
                        'config_id': cfg.id,
                        'employee_id': emp.id,
                        'days_allowed': cfg.days_allowed,
                    })
                elif line.config_id.id != cfg.id:
                    line.config_id = cfg.id

    @api.model
    def action_sync_and_open(self):
        """เมนู: seed config สาขา → seed พนักงานตามสาขา → เปิดตาราง

        Odoo 14 ต้องดึงสาขาจาก PHP ก่อน — Odoo 18 สาขาอยู่ใน DB เดียวกันแล้ว
        จึง seed ได้ตรง ๆ
        """
        self._seed_missing_branches()
        self._seed_employee_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'กำหนดสิทธิหยุดวันเสาร์',
            'res_model': 'saturday.leave.config',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_pull_employees(self):
        """ดึงพนักงานในสาขานี้มาลงตาราง override เฉพาะคนที่ยังไม่มี"""
        self.ensure_one()
        self._seed_employee_lines(self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'saturday.leave.config',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # API สำหรับแอป
    # ------------------------------------------------------------------
    @api.model
    def api_get_saturday_quota(self, employee_code):
        """สิทธิหยุดวันเสาร์/เดือน ตามรหัสพนักงาน

        ลำดับการตัดสิน: (1) override รายบุคคล → (2) ค่าของสาขา → (3) ค่าเริ่มต้นตามชนิดสาขา
        คงลายเซ็นเดิมจาก Odoo 14 เพราะแอปเรียกเมธอดนี้อยู่แล้ว
        """
        company = self.env.company
        fallback = company.hrms_saturday_days_branch or 1
        if not employee_code:
            return fallback
        emp = self.env['employee.salary'].sudo().search(
            [('employee_code', '=', str(employee_code))], limit=1)
        if not emp:
            return fallback
        emp_company = emp.company_id or company

        emp_line = self.env['saturday.leave.employee'].sudo().search(
            [('employee_id', '=', emp.id)], limit=1)
        if emp_line:
            return emp_line.days_allowed

        if emp.branch_id:
            cfg = self.sudo().search([
                ('branch_id', '=', emp.branch_id.id),
                ('company_id', '=', emp_company.id),
            ], limit=1)
            if cfg:
                return cfg.days_allowed
            return self._default_days_for_branch(emp.branch_id, emp_company)
        return emp_company.hrms_saturday_days_branch or 1


class SaturdayLeaveEmployee(models.Model):
    _name = 'saturday.leave.employee'
    _description = 'สิทธิหยุดวันเสาร์รายบุคคล'
    _order = 'employee_id'
    _rec_name = 'employee_id'

    config_id = fields.Many2one(
        'saturday.leave.config', string='สาขา (config)',
        required=True, ondelete='cascade')
    branch_id = fields.Many2one(
        'res.branch', string='สาขา', related='config_id.branch_id', store=True)
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True, readonly=True)
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True, ondelete='cascade')
    employee_code = fields.Char(
        string='รหัสพนักงาน', related='employee_id.employee_code', store=True)
    days_allowed = fields.Integer(
        string='สิทธิหยุดวันเสาร์/เดือน (ครั้ง)', default=1, required=True)

    _sql_constraints = [
        ('emp_uniq', 'unique(employee_id)',
         'พนักงานคนนี้ถูกตั้งค่าสิทธิหยุดวันเสาร์รายบุคคลไว้แล้ว'),
    ]
