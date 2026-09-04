# -*- coding: utf-8 -*-
"""ทะเบียนองค์กรผู้เช่าระบบ (hrms.tenant)

รองรับการปล่อยเช่าแบบ "แอปเดียวใช้ได้ทุกองค์กร" — ผู้ใช้กรอกรหัสองค์กรตอนเปิดแอป
ครั้งแรก แอปถามที่นี่ว่ารหัสนั้นต่อไปเซิร์ฟเวอร์ไหน และใช้ชื่อ/โลโก้/สีอะไร

ทำแบบนี้แทนการ build แอปแยกต่อลูกค้า เพราะรับลูกค้าใหม่ได้โดยไม่ต้องขึ้นสโตร์ใหม่
และไม่ต้องดูแลเวอร์ชันแยกทุกราย

``base_url`` ปล่อยว่างได้ถ้าองค์กรอยู่บนเซิร์ฟเวอร์เดียวกับทะเบียนนี้ — ระบบจะใช้
ที่อยู่ของตัวเองให้อัตโนมัติ ซึ่งเป็นกรณีปกติตอนยังไม่ได้แยกเครื่องให้ลูกค้า
"""
import re

from odoo import models, fields, api
from odoo.exceptions import ValidationError

CODE_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{1,31}$')


class HrmsTenant(models.Model):
    _name = 'hrms.tenant'
    _description = 'องค์กรผู้เช่าระบบ (สำหรับแอป HR)'
    _order = 'sequence, name'

    name = fields.Char(string='ชื่อองค์กร', required=True,
                       help='ชื่อที่แสดงบนหน้าล็อกอินของแอป')
    code = fields.Char(
        string='รหัสองค์กร', required=True, index=True,
        help='รหัสที่ผู้ใช้กรอกในแอป เช่น npd — ใช้ได้เฉพาะ a-z 0-9 _ - '
             'และไม่แยกตัวพิมพ์ใหญ่เล็ก')
    sequence = fields.Integer(string='ลำดับ', default=10)
    active = fields.Boolean(string='เปิดใช้งาน', default=True)

    base_url = fields.Char(
        string='ที่อยู่เซิร์ฟเวอร์',
        help='เช่น https://npd-solution.com — ปล่อยว่างถ้าใช้เซิร์ฟเวอร์เดียวกับที่ตั้งค่านี้')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company,
        help='ข้อมูลพนักงานที่องค์กรนี้เห็น ยึดตามบริษัทที่เลือก')

    logo = fields.Binary(string='โลโก้', attachment=True,
                         help='แสดงบนหน้าล็อกอินของแอป')
    color_primary = fields.Char(
        string='สีหลัก', default='#FFC107',
        help='รหัสสีแบบ #RRGGBB ใช้กับปุ่มและแถบหัวข้อ')
    color_secondary = fields.Char(
        string='สีรอง', default='#212121',
        help='รหัสสีแบบ #RRGGBB ใช้กับตัวอักษรและพื้นหลังเข้ม')

    support_phone = fields.Char(string='เบอร์ติดต่อฝ่ายบุคคล')
    note = fields.Text(string='หมายเหตุ')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'รหัสองค์กรนี้ถูกใช้แล้ว'),
    ]

    # ------------------------------------------------------------------
    # ตรวจความถูกต้อง
    # ------------------------------------------------------------------
    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if not CODE_RE.match(rec.code or ''):
                raise ValidationError(
                    'รหัสองค์กร "%s" ใช้ไม่ได้ — ต้องเป็นตัวพิมพ์เล็ก a-z ตัวเลข '
                    'ขีดกลาง หรือขีดล่าง ยาว 2-32 ตัว และขึ้นต้นด้วยตัวอักษรหรือตัวเลข'
                    % (rec.code or ''))

    @api.constrains('color_primary', 'color_secondary')
    def _check_colors(self):
        for rec in self:
            for value in (rec.color_primary, rec.color_secondary):
                if value and not re.match(r'^#[0-9A-Fa-f]{6}$', value):
                    raise ValidationError(
                        'รหัสสี "%s" ไม่ถูกต้อง ต้องอยู่ในรูป #RRGGBB เช่น #FFC107'
                        % value)

    @api.onchange('code')
    def _onchange_code(self):
        """พิมพ์ตัวใหญ่หรือเว้นวรรคมาก็ใช้ได้ — ปรับให้เป็นรูปมาตรฐานให้เลย"""
        for rec in self:
            if rec.code:
                rec.code = rec.code.strip().lower().replace(' ', '-')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].strip().lower().replace(' ', '-')
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().lower().replace(' ', '-')
        return super().write(vals)

    # ------------------------------------------------------------------
    # ใช้จาก API
    # ------------------------------------------------------------------
    def _effective_base_url(self):
        """ที่อยู่ที่แอปต้องใช้ยิง request ต่อจากนี้"""
        self.ensure_one()
        if self.base_url:
            return self.base_url.strip().rstrip('/')
        own = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return (own or '').rstrip('/')

    @api.model
    def api_resolve(self, code):
        """หาองค์กรจากรหัสที่ผู้ใช้กรอก — คืน None ถ้าไม่มีหรือถูกปิดใช้งาน"""
        code = (code or '').strip().lower()
        if not code:
            return None
        tenant = self.sudo().search([('code', '=', code)], limit=1)
        if not tenant:
            return None
        return {
            'code': tenant.code,
            'name': tenant.name,
            'base_url': tenant._effective_base_url(),
            'logo_url': '/api/hrms/v1/tenant/logo?code=%s' % tenant.code
                        if tenant.logo else '',
            'color_primary': tenant.color_primary or '#FFC107',
            'color_secondary': tenant.color_secondary or '#212121',
            'support_phone': tenant.support_phone or '',
        }
