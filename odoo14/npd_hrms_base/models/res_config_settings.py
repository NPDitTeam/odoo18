# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # รหัสพนักงาน
    hrms_employee_code_prefix = fields.Char(
        related='company_id.hrms_employee_code_prefix', readonly=False)
    hrms_employee_code_start = fields.Integer(
        related='company_id.hrms_employee_code_start', readonly=False)
    hrms_employee_code_padding = fields.Integer(
        related='company_id.hrms_employee_code_padding', readonly=False)

    # รอบตัดเงินเดือน
    hrms_cutoff_start_day = fields.Integer(
        related='company_id.hrms_cutoff_start_day', readonly=False)

    # ประกันสังคม
    hrms_sso_enabled = fields.Boolean(
        related='company_id.hrms_sso_enabled', readonly=False)
    hrms_sso_rate = fields.Float(
        related='company_id.hrms_sso_rate', readonly=False)
    hrms_sso_min_wage = fields.Float(
        related='company_id.hrms_sso_min_wage', readonly=False)
    hrms_sso_max_wage = fields.Float(
        related='company_id.hrms_sso_max_wage', readonly=False)

    # สิทธิ์วันลา
    hrms_leave_personal_paid_days = fields.Integer(
        related='company_id.hrms_leave_personal_paid_days', readonly=False)
    hrms_leave_personal_paid_after_months = fields.Integer(
        related='company_id.hrms_leave_personal_paid_after_months', readonly=False)
    hrms_leave_personal_unpaid_days = fields.Integer(
        related='company_id.hrms_leave_personal_unpaid_days', readonly=False)
    hrms_leave_sick_days = fields.Integer(
        related='company_id.hrms_leave_sick_days', readonly=False)
    hrms_leave_maternity_paid_days = fields.Integer(
        related='company_id.hrms_leave_maternity_paid_days', readonly=False)
    hrms_leave_maternity_unpaid_days = fields.Integer(
        related='company_id.hrms_leave_maternity_unpaid_days', readonly=False)
    hrms_leave_vacation_days = fields.Integer(
        related='company_id.hrms_leave_vacation_days', readonly=False)
    hrms_leave_vacation_after_years = fields.Integer(
        related='company_id.hrms_leave_vacation_after_years', readonly=False)
    hrms_leave_saturday_days = fields.Integer(
        related='company_id.hrms_leave_saturday_days', readonly=False)
    hrms_leave_emergency_days = fields.Integer(
        related='company_id.hrms_leave_emergency_days', readonly=False)

    # สิทธิหยุดวันเสาร์
    hrms_saturday_days_hq = fields.Integer(
        related='company_id.hrms_saturday_days_hq', readonly=False)
    hrms_saturday_days_branch = fields.Integer(
        related='company_id.hrms_saturday_days_branch', readonly=False)

    # การลงเวลา
    hrms_checkin_default_radius = fields.Integer(
        related='company_id.hrms_checkin_default_radius', readonly=False)
    hrms_checkin_require_gps = fields.Boolean(
        related='company_id.hrms_checkin_require_gps', readonly=False)
    hrms_allow_multi_login = fields.Boolean(
        related='company_id.hrms_allow_multi_login', readonly=False)
