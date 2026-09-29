# -*- coding: utf-8 -*-
"""ปิดปุ่มสั่งงานขนส่งบนหน้าจอ Odoo เป็นรายสาขา

งานขนส่งเดินได้สองทาง คือผ่านแอปคนขับ กับกดเองบนหน้าจอ Odoo บางสาขาอยาก
บังคับให้ใช้แอปอย่างเดียว จะได้มีรูป พิกัด และลายเซ็นครบทุกเที่ยว จึงต้อง
ปิดปุ่มฝั่ง Odoo เฉพาะสาขานั้น

เป็นรายการ "สาขาที่ห้าม" ไม่ใช่ "สาขาที่อนุญาต" เพราะปกติทุกสาขาใช้ได้อยู่แล้ว
คนตั้งค่าคิดในรูปแบบ "จะปิดสาขาไหน" ไม่ใช่ต้องไล่เปิดทีละสาขาทั้ง 33 สาขา
ค่าว่าง = ยังไม่ปิดใคร ทุกสาขาทำงานเหมือนเดิม

เก็บรายการไว้ที่บริษัท แต่ใช้ร่วมกันทุกบริษัท เพราะสาขาในระบบนี้ผูกอยู่กับ
ทั้ง 5 บริษัทผ่าน company_ids การแยกรายการตามบริษัทจึงไม่มีความหมาย และเคย
ทำให้ตั้งค่าที่บริษัทหนึ่งแล้วใบจองไปอ่านรายการของอีกบริษัทที่ว่างอยู่
"""
from odoo import api, fields, models


class ResCompanyOdooBookingPolicy(models.Model):
    _inherit = 'res.company'

    npd_odoo_blocked_branch_ids = fields.Many2many(
        'res.branch',
        'res_company_npd_odoo_blocked_branch_rel',
        'company_id', 'branch_id',
        string='สาขาที่ห้ามสั่งงานขนส่งผ่านหน้าจอ Odoo',
        help='ปล่อยว่าง = ทุกสาขากดปุ่ม "เริ่มขนส่ง" และ "เสร็จสิ้น" '
             'บนหน้าจอ Odoo ได้ตามปกติ\n'
             'ใส่ชื่อสาขา = สาขานั้นจะไม่เห็นปุ่มทั้งสอง '
             'ต้องสั่งงานผ่านแอปคนขับเท่านั้น\n'
             'หมายเหตุ: รายการนี้ใช้ร่วมกันทุกบริษัท ตั้งที่บริษัทไหนก็มีผลเหมือนกัน '
             'เพราะสาขาในระบบนี้ผูกอยู่กับทุกบริษัท')


class VehicleBookingOdooActionPolicy(models.Model):
    _inherit = 'vehicle.booking'

    allow_odoo_action = fields.Boolean(
        string='สั่งงานผ่าน Odoo ได้',
        compute='_compute_allow_odoo_action',
        help='ใช้ซ่อน/แสดงปุ่มเริ่มขนส่งและเสร็จสิ้น ตามการตั้งค่าของบริษัท')

    @api.depends('branch_id')
    def _compute_allow_odoo_action(self):
        blocked = self.env['res.company'].sudo().search([]).mapped(
            'npd_odoo_blocked_branch_ids')
        for record in self:
            # ไม่มีสาขาในใบจอง = ตัดสินไม่ได้ว่าถูกปิดหรือเปล่า ปล่อยให้กดได้
            # ดีกว่าบล็อกงานจริงเพราะข้อมูลไม่ครบ
            record.allow_odoo_action = (
                not blocked
                or not record.branch_id
                or record.branch_id not in blocked
            )
