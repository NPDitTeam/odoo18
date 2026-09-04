# -*- coding: utf-8 -*-
"""เวอร์ชันแอป HR — แทน get_latest_version_test.php เดิม

ของเดิมเก็บเลขเวอร์ชันกับ release notes ไว้ใน "โค้ด PHP" ต้องแก้ไฟล์บนเซิร์ฟเวอร์
ทุกครั้งที่ปล่อยเวอร์ชัน — ย้ายมาเป็นเรคคอร์ดใน Odoo ให้ฝ่ายไอทีแก้เองได้จากหน้าเว็บ

รูปแบบที่คืนให้แอปคงเดิมทุกคีย์ (version / android_url / ios_url / release_notes)
เพื่อให้แอปเวอร์ชันที่ติดตั้งอยู่แล้วอ่านได้โดยไม่ต้องอัปเดตก่อน
"""
from odoo import models, fields, api


class HrmsAppRelease(models.Model):
    _name = 'hrms.app.release'
    _description = 'เวอร์ชันแอป HR'
    _order = 'release_date desc, id desc'
    _rec_name = 'version'

    version = fields.Char(string='เวอร์ชัน', required=True, help='เช่น 1.3.8')
    build_number = fields.Integer(
        string='Build Number',
        help='เลข build ที่เทียบมากกว่า/น้อยกว่ากันได้ตรง ๆ (ไม่บังคับ)')
    release_date = fields.Date(
        string='วันที่ปล่อย', default=fields.Date.context_today, required=True)
    android_url = fields.Char(
        string='ลิงก์ Google Play',
        default='https://play.google.com/store/apps/details?id=com.npd.npd_hrms_app')
    ios_url = fields.Char(
        string='ลิงก์ App Store',
        default='https://apps.apple.com/us/app/npd-hrms-official/id6748937428')
    release_note = fields.Text(
        string='รายละเอียดการอัปเดต',
        help='พิมพ์บรรทัดละ 1 หัวข้อ — แอปจะแสดงเป็นรายการหัวข้อย่อยใน popup')
    is_mandatory = fields.Boolean(
        string='บังคับอัปเดต',
        help='ถ้าติ๊ก แอปเวอร์ชันเก่ากว่านี้จะใช้งานต่อไม่ได้จนกว่าจะอัปเดต')
    is_current = fields.Boolean(
        string='เป็นเวอร์ชันปัจจุบัน', default=True,
        help='ติ๊กเฉพาะเวอร์ชันที่ต้องการให้แอปมองเห็นว่าเป็นตัวล่าสุด')
    active = fields.Boolean(string='ใช้งาน', default=True)

    def write(self, vals):
        """ตั้งเวอร์ชันไหนเป็นปัจจุบัน → ปลดตัวอื่นให้อัตโนมัติ

        กันเคสที่มีหลายเรคคอร์ดติ๊ก is_current พร้อมกันแล้วแอปได้เวอร์ชันมั่ว
        """
        res = super().write(vals)
        if vals.get('is_current'):
            others = self.sudo().search([
                ('is_current', '=', True), ('id', 'not in', self.ids)])
            if others:
                super(HrmsAppRelease, others).write({'is_current': False})
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        current = records.filtered('is_current')
        if current:
            others = self.sudo().search([
                ('is_current', '=', True), ('id', 'not in', current.ids)])
            if others:
                super(HrmsAppRelease, others).write({'is_current': False})
        return records

    def _release_notes_list(self):
        """แปลง Text หลายบรรทัด → list ของสตริง (รูปแบบที่แอปคาดหวัง)"""
        self.ensure_one()
        if not self.release_note:
            return []
        return [
            line.strip().lstrip('-•').strip()
            for line in self.release_note.splitlines()
            if line.strip()
        ]

    @api.model
    def api_get_latest(self):
        """คืนรูปแบบเดียวกับ get_latest_version_test.php เป๊ะ ๆ"""
        release = self.sudo().search([('is_current', '=', True)], limit=1)
        if not release:
            release = self.sudo().search([], limit=1)
        if not release:
            return {
                'status': 'error',
                'message': 'ยังไม่ได้ประกาศเวอร์ชันแอปในระบบ',
                'version': '',
                'android_url': '',
                'ios_url': '',
                'release_notes': [],
            }
        return {
            'status': 'success',
            'version': release.version or '',
            'build_number': release.build_number or 0,
            'android_url': release.android_url or '',
            'ios_url': release.ios_url or '',
            'release_notes': release._release_notes_list(),
            'is_mandatory': release.is_mandatory,
            'message': 'Latest version information fetched successfully.',
        }
