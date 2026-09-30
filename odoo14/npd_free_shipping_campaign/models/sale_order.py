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
    npd_free_shipping_zero_set = fields.Boolean(
        string='ระบบติ๊กค่าขนส่งพิเศษ 0 ให้จากโปร',
        copy=False,
        help='จดไว้ว่าช่อง "ใช้ค่าขนส่งพิเศษที่เป็น 0" ถูกติ๊กโดยโปร ไม่ใช่โดยผู้ใช้\n'
             'พอใบหลุดเงื่อนไขโปร ระบบจะปลดคืนเฉพาะอันที่ตัวเองติ๊กไว้',
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

    # ------------------------------------------------------------------
    # ล็อกค่าขนส่งเมื่อเข้าเงื่อนไขโปร
    # ------------------------------------------------------------------
    def _npd_free_shipping_lock_values(self):
        u"""ค่าที่ต้องบังคับให้ใบนี้ — คืน dict ว่างถ้าไม่ต้องเปลี่ยนอะไร

        เข้าโปร   : ติ๊กใช้ค่าขนส่งพิเศษที่เป็น 0 + ล้างค่าขนส่งพิเศษเป็น 0
        หลุดโปร   : ปลดติ๊กคืน เฉพาะใบที่ระบบเป็นคนติ๊กให้
        """
        self.ensure_one()
        applied = self._npd_free_shipping_state()[0]
        values = {}
        if applied:
            if not self.use_special_delivery_zero:
                values['use_special_delivery_zero'] = True
            if self.shipping_cost_m:
                values['shipping_cost_m'] = 0.0
            if not self.npd_free_shipping_zero_set:
                values['npd_free_shipping_zero_set'] = True
        elif self.npd_free_shipping_zero_set:
            # เคยเข้าโปรแล้วหลุด (เช่น แก้ปลายทางจนระยะทางเกิน) คืนค่าให้คิดปกติ
            values['use_special_delivery_zero'] = False
            values['npd_free_shipping_zero_set'] = False
        return values

    def _npd_apply_free_shipping_lock(self):
        for order in self:
            values = order._npd_free_shipping_lock_values()
            if values:
                _logger.info('[FREE_SHIPPING] %s: ปรับช่องค่าขนส่งตามโปร %s',
                             order.name, values)
                super(SaleOrder, order).write(values)

    @api.onchange('campaign_id', 'distance_km')
    def _onchange_npd_free_shipping(self):
        u"""ให้เห็นผลทันทีบนหน้าจอ ไม่ต้องรอบันทึก"""
        for order in self:
            values = order._npd_free_shipping_lock_values()
            for name, value in values.items():
                order[name] = value

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._npd_apply_free_shipping_lock()
        return orders

    def _npd_refresh_before_lock(self):
        u"""รอให้ฟิลด์คำนวณเสร็จก่อน ค่อยตัดสินว่าเข้าโปรหรือหลุดโปร

        ระยะทางเป็นฟิลด์คำนวณจากต้นทาง/ปลายทาง ตอนบันทึกการแก้ปลายทาง
        Odoo ยังไม่ได้คำนวณระยะใหม่ ถ้าอ่านเลยจะได้ค่าเก่า แล้วตัดสินผิด
        (เจอจริง: แก้ปลายทางจน 80 กม. เกินโปร 35 กม. แต่ช่อง
         "ใช้ค่าขนส่งพิเศษที่เป็น 0" ยังติ๊กค้างอยู่)
        """
        watched = ['distance_km', 'shipping_cost', 'shipping_cost_m']
        if hasattr(self.env, 'flush_all'):          # Odoo 17 ขึ้นไป
            self.env.flush_all()
        else:                                        # Odoo 14
            self.flush()
        if hasattr(self, 'invalidate_recordset'):
            self.invalidate_recordset(watched)
        else:
            self.invalidate_cache(watched, self.ids)

    def write(self, vals):
        res = super().write(vals)
        # กันวนซ้ำตอนที่ตัวเองเป็นคนเขียนสามช่องนี้
        if self.env.context.get('npd_free_shipping_locking'):
            return res
        self._npd_refresh_before_lock()
        self.with_context(
            npd_free_shipping_locking=True)._npd_apply_free_shipping_lock()
        return res
