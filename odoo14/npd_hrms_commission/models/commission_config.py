# -*- coding: utf-8 -*-
"""ตั้งค่าค่าคอมมิชชั่น (ฝั่งบุคคล)

พอร์ตจาก Odoo 14 — เปลี่ยนสาขาไปชี้ ``res.branch`` และเพิ่ม ``company_id``
เพื่อให้บริษัทที่เช่าระบบตั้งอัตราของตัวเองได้

หมายเหตุสำคัญ: โมดูลนี้เป็น "ผู้ใช้" ค่าคอม ไม่ใช่ผู้คำนวณยอดขาย
ยอดขาย/ยอดเช่าที่ใช้เป็นฐานมาจากโมดูล ``npd_commission_report`` ฝั่ง ERP
(``npd.commission.report`` / ``npd.commission.report.sales``)
"""
from odoo import models, fields, api

SALE_COMM_TYPE = [
    ('sale_branch', 'ค่าคอม Sale สาขา'),
    ('sale_headoffice', 'ค่าคอม Sale สำนักงานใหญ่'),
]


class CommissionRateConfig(models.Model):
    _name = 'commission.rate.config'
    _description = 'ตั้งค่าอัตราคอมมิชชั่น Sales (ตามขั้นยอดขาย)'
    _order = 'comm_type asc, min_amount asc'

    sequence = fields.Integer(string='ลำดับ', default=10)
    comm_type = fields.Selection(
        SALE_COMM_TYPE, string='ประเภท', required=True, default='sale_branch')
    min_amount = fields.Float(string='ยอดขั้นต่ำ', required=True, digits=(16, 2))
    rate = fields.Float(string='อัตราคอมมิชชั่น (%)', required=True, digits=(16, 2))
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)

    @api.model
    def get_rate_for_amount(self, amount, comm_type='sale_branch', company=None):
        """อัตราของขั้นสูงสุดที่ยอดถึง — ไม่ถึงขั้นไหนเลยได้ 0%"""
        company = company or self.env.company
        configs = self.sudo().search([
            ('comm_type', '=', comm_type),
            ('company_id', '=', company.id),
        ], order='min_amount desc')
        for config in configs:
            if (amount or 0.0) >= config.min_amount:
                return config.rate
        return 0.0


class CommissionRateBranchSales(models.Model):
    _name = 'commission.rate.branch.sales'
    _description = 'ตั้งค่าอัตราค่าคอมสาขา / Sales'

    name = fields.Char(string='ชื่อ', default='ค่าเริ่มต้น', required=True)
    comm_type = fields.Selection(
        SALE_COMM_TYPE, string='ประเภท', required=True, default='sale_branch')
    branch_rate = fields.Float(
        string='ค่าคอมสาขา (%)', digits=(16, 2), default=6.0, required=True)
    sales_rate = fields.Float(
        string='ค่าคอม Sales (%)', digits=(16, 2), default=2.0, required=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)

    @api.model
    def get_rates(self, comm_type='sale_branch', company=None):
        """(branch_rate, sales_rate) ของประเภทที่ระบุ

        ไม่พบประเภทนั้น → ใช้รายการแรกที่มี → สุดท้ายค่าเริ่มต้น 6% / 2%
        """
        company = company or self.env.company
        domain = [('company_id', '=', company.id)]
        config = self.sudo().search(
            domain + [('comm_type', '=', comm_type)], limit=1)
        if not config:
            config = self.sudo().search(domain, limit=1)
        return (config.branch_rate, config.sales_rate) if config else (6.0, 2.0)


class CommissionBranchConfig(models.Model):
    _name = 'commission.branch.config'
    _description = 'ตั้งค่าสัดส่วนค่าคอมมิชชั่นสาขา'
    _order = 'branch_id asc'
    _rec_name = 'branch_id'

    branch_id = fields.Many2one(
        'res.branch', string='สาขา', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)
    line_ids = fields.One2many(
        'commission.branch.config.line', 'config_id', string='รายชื่อพนักงาน')
    total_ratio = fields.Float(
        string='สัดส่วนรวมทั้งสาขา', digits=(16, 2),
        compute='_compute_total_ratio', store=True)
    employee_count = fields.Integer(
        string='จำนวนพนักงาน', compute='_compute_total_ratio', store=True)

    _sql_constraints = [
        ('branch_company_uniq', 'unique(branch_id, company_id)',
         'สาขานี้ถูกตั้งค่าแล้ว ไม่สามารถสร้างซ้ำได้'),
    ]

    @api.depends('line_ids', 'line_ids.ratio')
    def _compute_total_ratio(self):
        for rec in self:
            rec.total_ratio = sum(rec.line_ids.mapped('ratio'))
            rec.employee_count = len(rec.line_ids)

    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        """เลือกสาขาแล้วดึงพนักงานที่ยังใช้งานในสาขานั้นมาเป็นรายการ"""
        if not self.branch_id:
            self.line_ids = [(5, 0, 0)]
            return
        employees = self.env['employee.salary'].search([
            ('branch_id', '=', self.branch_id._origin.id),
            ('status', '=', 'active'),
        ])
        self.line_ids = [(5, 0, 0)] + [
            (0, 0, {'employee_id': emp.id, 'ratio': 0.0}) for emp in employees]

    def action_refresh_employees(self):
        """ดึงพนักงานใหม่เข้ามาเพิ่ม โดยไม่ลบ/ไม่แก้สัดส่วนของคนเดิม"""
        for rec in self:
            existing = set(rec.line_ids.mapped('employee_id').ids)
            employees = self.env['employee.salary'].search([
                ('branch_id', '=', rec.branch_id.id),
                ('status', '=', 'active'),
            ])
            new_lines = [
                (0, 0, {'employee_id': emp.id, 'ratio': 0.0})
                for emp in employees if emp.id not in existing
            ]
            if new_lines:
                rec.write({'line_ids': new_lines})
        return True

    @api.model
    def get_ratio_for_employee(self, branch, employee):
        """สัดส่วนของพนักงานคนนี้ในสาขา — ไม่มี = 0"""
        if not branch or not employee:
            return 0.0
        line = self.env['commission.branch.config.line'].sudo().search([
            ('config_id.branch_id', '=', branch.id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        return line.ratio if line else 0.0

    @api.model
    def get_total_ratio_for_branch(self, branch):
        if not branch:
            return 0.0
        config = self.sudo().search([('branch_id', '=', branch.id)], limit=1)
        return config.total_ratio if config else 0.0


class CommissionBranchConfigLine(models.Model):
    _name = 'commission.branch.config.line'
    _description = 'สัดส่วนค่าคอมมิชชั่นสาขา — รายพนักงาน'
    _order = 'id asc'

    config_id = fields.Many2one(
        'commission.branch.config', string='ตั้งค่าสาขา',
        required=True, ondelete='cascade')
    branch_id = fields.Many2one(
        'res.branch', related='config_id.branch_id', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', related='config_id.company_id', store=True, readonly=True)
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True, ondelete='cascade')
    employee_code = fields.Char(
        related='employee_id.employee_code', store=True, readonly=True)
    position_name = fields.Char(
        string='ตำแหน่ง', related='employee_id.position_id.name',
        store=True, readonly=True)
    ratio = fields.Float(string='สัดส่วน', required=True, default=0.0, digits=(16, 2))


class CommissionSaleHeadOffice(models.Model):
    _name = 'commission.sale.headoffice'
    _description = 'รายชื่อ Sales สำนักงานใหญ่'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True, ondelete='cascade')
    employee_code = fields.Char(
        related='employee_id.employee_code', store=True, readonly=True)
    branch_id = fields.Many2one(
        'res.branch', related='employee_id.branch_id', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', related='employee_id.company_id', store=True, readonly=True)

    _sql_constraints = [
        ('employee_uniq', 'unique(employee_id)',
         'พนักงานคนนี้อยู่ในรายชื่อค่าคอม Sales สำนักงานใหญ่แล้ว'),
    ]

    @api.model
    def is_headoffice_employee(self, employee):
        """อยู่ในรายชื่อ Sales สำนักงานใหญ่ไหม

        Odoo 14 ต้อง push รายชื่อนี้ข้ามไปทุก company DB ด้วย psycopg2
        เพราะรายงานอยู่คนละฐาน — Odoo 18 อยู่ฐานเดียวกันแล้วจึงอ่านตรงได้
        """
        if not employee:
            return False
        return bool(self.sudo().search_count([('employee_id', '=', employee.id)]))
