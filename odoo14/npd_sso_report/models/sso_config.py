# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

DEFAULT_SSO_BRANCH = '000000'


class NpdSsoReportConfig(models.Model):
    """ค่าตั้งต้นรายงานประกันสังคม รายบริษัท (ดึงจาก o14 ผ่านตัวซิงก์ HR จนกว่าจะตัดระบบ)"""
    _name = 'npd.sso.report.config'
    _description = 'กำหนดค่ารายงานประกันสังคม'
    _order = 'company_id'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', string='บริษัท', required=True)
    employer_account = fields.Char(
        string='เลขที่บัญชีนายจ้าง (สปส.)', size=10,
        help='เลข 10 หลักของบริษัทที่ สปส. ออกให้ ใช้ขึ้นต้นชื่อไฟล์')
    wage_source = fields.Selection([
        ('salary', 'เงินเดือน + เงินเพิ่มประจำ (ค่าครองชีพ/ตำแหน่ง/ประสบการณ์/วิชาชีพ)'),
        ('gross', 'รวมรายได้ทั้งเดือน'),
    ], string='ช่อง "ค่าจ้าง" ดึงจาก', default='salary', required=True,
        help='ไฟล์ที่ยื่นจริงใช้เงินเดือน + เงินเพิ่มประจำ — เงินสมทบใช้ยอดประกันสังคมในสลิปเสมอ')
    branch_line_ids = fields.One2many('npd.sso.report.branch', 'config_id', string='รหัสสาขา สปส.')
    note = fields.Text(string='หมายเหตุ')

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)', 'บริษัทนี้มีการกำหนดค่าอยู่แล้ว'),
    ]

    @api.constrains('employer_account')
    def _check_employer_account(self):
        for rec in self:
            if rec.employer_account and not re.fullmatch(r'\d{10}', rec.employer_account):
                raise ValidationError(_('เลขที่บัญชีนายจ้างต้องเป็นตัวเลข 10 หลัก'))

    def sso_branch_code_for(self, branch):
        """รหัสสาขา สปส. ของสาขาเรา — ไม่ได้จับคู่ไว้ = สาขาตั้งต้น (000000)"""
        self.ensure_one()
        for line in self.branch_line_ids:
            if branch and branch in line.branch_ids:
                return line.sso_branch_code
        default = self.branch_line_ids.filtered('is_default')[:1]
        return default.sso_branch_code if default else DEFAULT_SSO_BRANCH


class NpdSsoReportBranch(models.Model):
    """จับคู่รหัสสาขา สปส. กับสาขาของเรา (หนึ่งรหัสได้หลายสาขา)"""
    _name = 'npd.sso.report.branch'
    _description = 'รหัสสาขาประกันสังคม'
    _order = 'config_id, sso_branch_code'

    config_id = fields.Many2one('npd.sso.report.config', required=True, ondelete='cascade')
    sso_branch_code = fields.Char(string='รหัสสาขา สปส.', size=6, required=True)
    branch_ids = fields.Many2many('res.branch', string='สาขาของเรา')
    is_default = fields.Boolean(
        string='สาขาตั้งต้น', help='พนักงานที่สาขาไม่ได้จับคู่กับรหัสใด จะเข้ารหัสนี้')
    note = fields.Char(string='หมายเหตุ')

    _sql_constraints = [
        ('code_uniq', 'unique(config_id, sso_branch_code)', 'รหัสสาขา สปส. ซ้ำในบริษัทเดียวกัน'),
    ]

    @api.onchange('sso_branch_code')
    def _onchange_code(self):
        for rec in self:
            if rec.sso_branch_code and rec.sso_branch_code.isdigit():
                rec.sso_branch_code = rec.sso_branch_code.zfill(6)

    @api.constrains('sso_branch_code')
    def _check_code(self):
        for rec in self:
            if not re.fullmatch(r'\d{6}', rec.sso_branch_code or ''):
                raise ValidationError(_('รหัสสาขา สปส. ต้องเป็นตัวเลข 6 หลัก (เช่น 000000, 200002)'))

    @api.constrains('branch_ids', 'config_id')
    def _check_branch_once(self):
        for rec in self:
            others = rec.config_id.branch_line_ids - rec
            dup = rec.branch_ids & others.mapped('branch_ids')
            if dup:
                raise ValidationError(_('สาขา %s ถูกจับคู่กับรหัสสาขาอื่นในบริษัทเดียวกันแล้ว')
                                      % ', '.join(dup.mapped('name')))
