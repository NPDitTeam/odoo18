# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ✅ เพิ่มฟิลด์ checkbox สำหรับแสดงทุกสาขา

    show_all_transport_booking_branches = fields.Boolean(
        string='แสดงทุกสาขา ของการจองคิวรถ',
        default=False,
        help='หากเลือก จะแสดงข้อมูลจากทุกสาขา / หากไม่เลือก จะแสดงเฉพาะสาขาของตัวเองเท่านั้น'
    )

    @api.model
    def get_branch_domain(self):
        """คืนค่า domain สำหรับกรอง branch ตามการตั้งค่าของผู้ใช้"""
        user = self.env.user

        if user.show_all_transport_booking_branches:
            # แสดงทุกสาขา
            return []
        else:
            # แสดงเฉพาะสาขาของตัวเอง
            if user.branch_id:
                return [('branch_id', '=', user.branch_id.id)]
            else:
                # ถ้าไม่มี branch กำหนด แสดงทั้งหมด
                return []



