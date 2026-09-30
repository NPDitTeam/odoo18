# -*- coding: utf-8 -*-
"""ค่าขนส่งเป็น 0 เมื่อใบสั่งขายอยู่ในโปรส่งฟรีและระยะทางไม่เกินเงื่อนไข"""
import logging
import math

from odoo import api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

# วันเวลาที่เริ่มใช้โปรอัตโนมัติ — ใบที่สร้างก่อนหน้านี้ไม่ถูกแตะ
CUTOFF_PARAM = 'npd_free_shipping_campaign.start_datetime'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ทั้งสองช่องไม่เก็บลงฐาน (ไม่ store) โดยตั้งใจ
    # ถ้าเก็บ Odoo จะต้องคำนวณและ "เขียนทับใบสั่งขายทุกใบ" ตอนติดตั้ง
    # (ฐาน S Group มีสองหมื่นกว่าใบ) ซึ่งทั้งช้า ชนกับคนที่กำลังใช้งาน
    # และทำให้ write_date ของเอกสารเก่าขยับทั้งฐาน จนตัวซิงก์ไป Odoo 18
    # เข้าใจผิดว่าทุกใบเพิ่งถูกแก้ไข
    npd_free_shipping_applied = fields.Boolean(
        string='ใช้โปรส่งฟรี',
        compute='_compute_npd_free_shipping',
        help='ระบบตั้งให้เองเมื่อแคมเปญเป็นโปรส่งฟรีและระยะทางไม่เกินเงื่อนไข',
    )
    npd_free_shipping_normal_cost = fields.Float(
        string='ค่าขนส่งปกติก่อนใช้โปร',
        compute='_compute_npd_free_shipping',
        digits=(16, 2),
        help='ค่าขนส่งที่ต้องจ่ายถ้าไม่มีโปร ไว้เทียบว่าโปรนี้ช่วยลูกค้าไปเท่าไร',
    )
    npd_free_shipping_note = fields.Char(
        string='สถานะโปรส่งฟรี',
        compute='_compute_npd_free_shipping_note',
    )
    npd_free_shipping_warn = fields.Boolean(
        string='โปรส่งฟรีแต่ยังไม่เข้าเงื่อนไข',
        compute='_compute_npd_free_shipping_note',
        help='แคมเปญเป็นโปรส่งฟรี แต่ใบนี้ไม่เข้าเงื่อนไข (ระยะเกิน หรือยังไม่ได้ตั้งค่า)',
    )

    # ------------------------------------------------------------------
    @api.model
    def _npd_free_shipping_cutoff(self):
        """ใบที่สร้างก่อนเวลานี้ไม่เข้าโปรอัตโนมัติ

        ของเดิมมีทั้งใบที่แก้ค่าขนส่งมือไว้ถูกและผิด และหลายใบปิดงานไปแล้ว
        ถ้าคำนวณย้อนหลังให้ ตัวเลขที่ปิดไปแล้วจะขยับ จึงเริ่มนับจากวันติดตั้ง
        """
        return self.env['ir.config_parameter'].sudo().get_param(CUTOFF_PARAM)

    def _npd_free_shipping_state(self):
        """คืน (เข้าโปรไหม, แคมเปญ, ระยะสูงสุด) ของใบนี้"""
        self.ensure_one()
        campaign = self.campaign_id
        if not campaign or not campaign.npd_free_shipping:
            return False, campaign, 0.0
        limit = campaign.npd_free_shipping_max_km or 0.0
        if float_compare(limit, 0.0, precision_digits=2) <= 0:
            # ยังไม่ได้กรอกเงื่อนไขระยะทาง ไม่เดาให้ คิดค่าขนส่งตามปกติ
            return False, campaign, 0.0

        cutoff = self._npd_free_shipping_cutoff()
        if cutoff and self.create_date and str(self.create_date) < cutoff:
            return False, campaign, limit

        within = float_compare(self.distance_km or 0.0, limit, precision_digits=2) <= 0
        return bool(within and self.distance_km), campaign, limit

    @api.depends('campaign_id', 'campaign_id.npd_free_shipping',
                 'campaign_id.npd_free_shipping_max_km', 'distance_km',
                 'shipping_cost_raw')
    def _compute_npd_free_shipping(self):
        for record in self:
            applied, _campaign, _limit = record._npd_free_shipping_state()
            record.npd_free_shipping_applied = applied
            record.npd_free_shipping_normal_cost = (
                record._npd_round_shipping(record.shipping_cost_raw) if applied else 0.0)

    @api.depends('npd_free_shipping_applied', 'npd_free_shipping_normal_cost',
                 'campaign_id', 'campaign_id.npd_free_shipping',
                 'campaign_id.npd_free_shipping_max_km', 'distance_km')
    def _compute_npd_free_shipping_note(self):
        for record in self:
            applied, campaign, limit = record._npd_free_shipping_state()
            record.npd_free_shipping_warn = bool(
                campaign and campaign.npd_free_shipping and not applied)
            if applied:
                record.npd_free_shipping_note = (
                    'ค่าขนส่งใบนี้เป็น 0 เพราะใช้โปร "%s" — ระยะทาง %s กม. '
                    'ไม่เกิน %s กม. ตามเงื่อนไข (ปกติคิด %s บาท)' % (
                        campaign.name,
                        '{:,.2f}'.format(record.distance_km or 0.0),
                        '{:,.2f}'.format(limit),
                        '{:,.2f}'.format(record.npd_free_shipping_normal_cost)))
            elif campaign and campaign.npd_free_shipping and limit > 0:
                record.npd_free_shipping_note = (
                    'ระยะทาง %s กม. เกินเงื่อนไขโปร "%s" (ส่งฟรีไม่เกิน %s กม.) '
                    'จึงคิดค่าขนส่งตามปกติ' % (
                        '{:,.2f}'.format(record.distance_km or 0.0),
                        campaign.name, '{:,.2f}'.format(limit)))
            elif campaign and campaign.npd_free_shipping:
                record.npd_free_shipping_note = (
                    'แคมเปญ "%s" ติ๊กว่าเป็นโปรส่งฟรี แต่ยังไม่ได้กรอกระยะทางสูงสุด '
                    'จึงยังคิดค่าขนส่งตามปกติ' % campaign.name)
            else:
                record.npd_free_shipping_note = False

    # ------------------------------------------------------------------
    @staticmethod
    def _npd_round_shipping(raw):
        """ปัดเศษแบบเดียวกับที่โมดูลขนส่งใช้ (เศษตั้งแต่ 50 ปัดขึ้นร้อย)"""
        raw = raw or 0.0
        if raw <= 0:
            return 0.0
        return (math.ceil(raw / 100) * 100 if raw % 100 >= 50
                else math.floor(raw / 100) * 100)

    # depends ต้องครอบของเดิมฝั่ง 18 ให้ครบ เพราะประกาศทับของเดิมทั้งชุด
    @api.depends('distance_km', 'vehicle_type_id', 'total_cost_per_trip',
                 'profit_per_trip',
                 'campaign_id', 'campaign_id.npd_free_shipping',
                 'campaign_id.npd_free_shipping_max_km')
    def _compute_shipping_cost(self):
        """คิดค่าขนส่งตามเดิมก่อน แล้วค่อยทับเป็น 0 ถ้าเข้าโปร

        ทับเฉพาะ "ค่าขนส่งหลังปัดเศษ" ซึ่งเป็นตัวที่ส่งต่อไปฐานโลจิสติกส์
        ส่วนค่าก่อนปัดเศษคงไว้ตามจริง จะได้ยังเห็นว่าต้นทุนเที่ยวนี้เท่าไร
        """
        super()._compute_shipping_cost()
        for record in self:
            applied, campaign, limit = record._npd_free_shipping_state()
            if not applied:
                continue
            if float_compare(record.shipping_cost or 0.0, 0.0, precision_digits=2) != 0:
                _logger.info(
                    '[FREE_SHIPPING] %s: โปร "%s" ระยะ %.2f/%.2f กม. '
                    'ค่าขนส่ง %.2f -> 0',
                    record.name, campaign.name, record.distance_km or 0.0,
                    limit, record.shipping_cost or 0.0)
            record.shipping_cost = 0.0
