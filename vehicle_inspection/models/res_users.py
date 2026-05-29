# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    """เพิ่มสิทธิ์การจัดการรายการตรวจสอบสภาพรถ"""
    _inherit = 'res.users'

    # สิทธิ์การจัดการรายการตรวจสอบสภาพรถ
    can_confirm_vehicle_inspection = fields.Boolean(
        string='ยืนยันรายการตรวจสอบสภาพรถ',
        default=False,
        help='อนุญาตให้ยืนยันรายการตรวจสอบสภาพรถได้'
    )
    can_approve_vehicle_inspection = fields.Boolean(
        string='อนุมัติรายการตรวจสอบสภาพรถ',
        default=False,
        help='อนุญาตให้อนุมัติรายการตรวจสอบสภาพรถได้'
    )
    can_reset_vehicle_inspection = fields.Boolean(
        string='กลับเป็นร่างรายการตรวจสอบสภาพรถ',
        default=False,
        help='อนุญาตให้เปลี่ยนสถานะรายการตรวจสอบสภาพรถกลับเป็นร่างได้'
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'can_confirm_vehicle_inspection',
            'can_approve_vehicle_inspection',
            'can_reset_vehicle_inspection',
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            'can_confirm_vehicle_inspection',
            'can_approve_vehicle_inspection',
            'can_reset_vehicle_inspection',
        ]
