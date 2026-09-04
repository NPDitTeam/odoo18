# -*- coding: utf-8 -*-
"""ส่วนขยาย res.branch สำหรับงาน HR

Odoo 14 มีโมเดลสาขาแยกของตัวเอง (hr.branch.custom) และตารางรัศมีเช็คอินอีกตัว
(hr.checkin.distance) ที่ sync กับ PHP — ทั้งคู่ยุบมาไว้บน res.branch ตัวเดียว
เพื่อให้สาขาฝั่ง HR กับฝั่งขาย/บัญชี/สต๊อกเป็นตัวเดียวกัน (คิดค่าคอมสาขาได้ตรง)
"""
from odoo import models, fields, api


class ResBranch(models.Model):
    _inherit = 'res.branch'

    # ------------------------------------------------------------------
    # ธงบอกประเภทสาขา
    # ------------------------------------------------------------------
    hr_use_in_hrms = fields.Boolean(
        string='ใช้ในระบบ HR', default=True,
        help='ติ๊กออกเพื่อซ่อนสาขานี้จากรายการเลือกฝั่งงานบุคคล')
    hr_is_head_office = fields.Boolean(
        string='เป็นสำนักงานใหญ่',
        help='ใช้กำหนดสิทธิหยุดวันเสาร์เริ่มต้น และแยกเงื่อนไขค่าคอม Sales สำนักงานใหญ่')
    hr_is_rental_branch = fields.Boolean(
        string='สาขาปล่อยเช่า',
        help='สาขานี้มีธุรกิจปล่อยเช่า — เปิดใช้ค่าคอมยอดเช่าและค่าเที่ยวคนขับ')

    # ------------------------------------------------------------------
    # พิกัดสำหรับเช็คอิน (แทน hr.checkin.distance เดิม)
    # ------------------------------------------------------------------
    hr_checkin_latitude = fields.Char(string='ละติจูด')
    hr_checkin_longitude = fields.Char(string='ลองจิจูด')
    hr_checkin_radius = fields.Integer(
        string='รัศมีที่อนุญาตให้เช็คอิน (เมตร)',
        help='เว้น 0 = ใช้ค่าเริ่มต้นของบริษัท')
    hr_allow_offsite_checkin = fields.Boolean(
        string='อนุญาตลงเวลานอกรัศมี',
        help='สาขาที่งานเป็นการออกนอกสถานที่ประจำ เช่น หน่วยขนส่ง')

    hr_map_link = fields.Char(
        string='เปิดแผนที่', compute='_compute_hr_map_link')

    @api.depends('hr_checkin_latitude', 'hr_checkin_longitude')
    def _compute_hr_map_link(self):
        for rec in self:
            if rec.hr_checkin_latitude and rec.hr_checkin_longitude:
                rec.hr_map_link = (
                    'https://www.google.com/maps?q=%s,%s&z=17'
                    % (rec.hr_checkin_latitude, rec.hr_checkin_longitude))
            else:
                rec.hr_map_link = False

    def action_open_checkin_map(self):
        """เปิดหน้าแผนที่ที่วาดวงกลมรัศมีเช็คอินให้เห็น และแก้พิกัดได้

        ไม่ใช้ลิงก์ google.com/maps ตรง ๆ เพราะแสดงได้แค่หมุด มองไม่เห็นว่ารัศมี
        ที่ตั้งไว้ครอบถึงตรงไหน ทำให้ตั้งค่าแบบเดา แล้วพนักงานเช็คอินไม่ผ่าน
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/hrms/checkin_map/%s' % self.id,
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Helper ที่ฝั่ง API / payroll เรียกใช้
    # ------------------------------------------------------------------
    def _hr_effective_radius(self, company=None):
        """รัศมีเช็คอินที่ใช้จริง — ของสาขาก่อน ถ้าไม่ตั้งค่าใช้ของบริษัท"""
        self.ensure_one()
        if self.hr_checkin_radius:
            return self.hr_checkin_radius
        company = company or self.company_ids[:1] or self.env.company
        return company.hrms_checkin_default_radius or 50

    @api.model
    def _hr_find_by_name(self, name, company=None):
        """หาสาขาจากชื่อ ถ้าไม่มีให้สร้าง — ใช้ตอนนำเข้าข้อมูลเก่าจาก Odoo 14/PHP

        ใช้ bypass_branch_company_filter เพราะโค้ดนำเข้ามักรันด้วย sudo/cron
        ที่ยังไม่มี allowed company ครบ ทำให้ _search ของ res.branch กรองทิ้ง
        """
        if not name:
            return False
        name = name.strip()
        Branch = self.with_context(bypass_branch_company_filter=True).sudo()
        branch = Branch.search([('name', '=', name)], limit=1)
        if not branch:
            branch = Branch.create({
                'name': name,
                'company_ids': [(6, 0, (company or self.env.company).ids)],
            })
        return branch.id
