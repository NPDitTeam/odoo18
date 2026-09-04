# -*- coding: utf-8 -*-
"""หน้าตั้งค่าการปล่อยเช่าระบบ

เดิมค่าพวกนี้ต้องไปพิมพ์เองที่ ตั้งค่า → เทคนิค → พารามิเตอร์ระบบ ซึ่งหายาก
และพิมพ์คีย์ผิดแล้วไม่มีอะไรเตือน — ระบบจะฟ้องตอนกดสร้างระบบให้ลูกค้าเท่านั้น
"""
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    saas_template_db = fields.Char(
        string='ฐานข้อมูลต้นแบบ',
        config_parameter='npd_saas.template_db',
        help='ชื่อ DB ที่ใช้โคลนให้ลูกค้าใหม่ทุกราย — ต้องเป็นฐานข้อมูลสะอาด '
             'ที่ไม่มีข้อมูลจริงของบริษัท')
    saas_root_domain = fields.Char(
        string='โดเมนหลัก',
        config_parameter='npd_saas.root_domain',
        help='เช่น npd-solution.com — ลูกค้าจะได้ที่อยู่เป็น <โดเมนย่อย>.<โดเมนหลัก>')

    saas_template_ok = fields.Boolean(
        string='พบฐานข้อมูลต้นแบบ', compute='_compute_saas_status')
    saas_template_note = fields.Char(compute='_compute_saas_status')
    saas_tenant_count = fields.Integer(
        string='ลูกค้าที่ใช้งานอยู่', compute='_compute_saas_status')

    @api.depends('saas_template_db')
    def _compute_saas_status(self):
        Tenant = self.env['hrms.tenant'].sudo()
        for rec in self:
            name = (rec.saas_template_db or '').strip()
            exists = bool(name) and Tenant._db_exists(name)
            rec.saas_template_ok = exists
            if not name:
                rec.saas_template_note = 'ยังไม่ได้ระบุ — กดสร้างระบบให้ลูกค้าไม่ได้'
            elif not exists:
                rec.saas_template_note = 'ไม่พบฐานข้อมูลชื่อนี้บนเซิร์ฟเวอร์'
            else:
                rec.saas_template_note = 'พร้อมใช้งาน'
            rec.saas_tenant_count = Tenant.search_count([
                ('is_control_plane', '=', False),
                ('state', 'in', ['active', 'grace']),
            ])

    @api.constrains('saas_root_domain')
    def _check_root_domain(self):
        for rec in self:
            domain = (rec.saas_root_domain or '').strip()
            if domain and ('/' in domain or ':' in domain or ' ' in domain):
                raise ValidationError(
                    'โดเมนหลักต้องเป็นชื่อโดเมนล้วน ๆ เช่น npd-solution.com '
                    'ไม่ต้องใส่ https:// หรือเครื่องหมาย /')

    saas_app_version = fields.Char(
        string='เวอร์ชันแอปปัจจุบัน', compute='_compute_saas_app_version')

    def _compute_saas_app_version(self):
        release = self.env['hrms.app.release'].sudo().search(
            [('is_current', '=', True)], limit=1)
        for rec in self:
            rec.saas_app_version = release.version if release else ''

    def action_open_tenants(self):
        return self.env['ir.actions.actions']._for_xml_id(
            'npd_saas_manager.action_hrms_tenant_saas')

    def action_open_app_release(self):
        return self.env['ir.actions.actions']._for_xml_id(
            'npd_hrms_base.action_hrms_app_release')

    def action_push_app_release(self):
        """ส่งเวอร์ชันแอปปัจจุบันไปให้ลูกค้าทุกรายทันที

        ปกติจะถูกส่งพร้อมสัญญาโดย cron รายวันอยู่แล้ว ปุ่มนี้ไว้ใช้ตอนเพิ่งปล่อย
        เวอร์ชันใหม่แล้วไม่อยากรอถึงรอบถัดไป
        """
        return self.env['hrms.tenant'].sudo().action_push_app_release()
