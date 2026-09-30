# -*- coding: utf-8 -*-
"""ตั้งค่าเริ่มต้นตอนติดตั้ง

1. จดวันเวลาที่เริ่มใช้โปรอัตโนมัติ ใบที่สร้างก่อนหน้านี้จะไม่ถูกคำนวณใหม่
   (ของเดิมมีทั้งใบที่แก้มือไว้ถูกและผิด และหลายใบปิดงานไปแล้ว)
2. เดาเงื่อนไขจากชื่อแคมเปญที่มีอยู่แล้วให้ครั้งเดียว เช่น
   "โปร 2026 ส่งฟรีไม่เกิน 25 Km." -> ติ๊กโปรส่งฟรี + 25 กม.
   แคมเปญที่ชื่อไม่บอกกิโล (เช่น "โปรโมชั่นส่งฟรีตามเงื่อนไขที่บริษัทกำหนด")
   จะติ๊กให้แต่ปล่อยระยะเป็น 0 ให้คนกรอกเอง ระหว่างนั้นคิดค่าขนส่งตามปกติ
"""
import logging
import re

from odoo import fields

_logger = logging.getLogger(__name__)

# จับตัวเลขที่อยู่หน้าหน่วยกิโลเมตร รองรับ "25 Km." "25km" "25 กม."
KM_PATTERN = re.compile(r'(\d+(?:[.,]\d+)?)\s*(?:km|กม|กิโล)', re.IGNORECASE)
# คำที่บอกว่าเป็นโปรส่งฟรี (เขียนกันคนละแบบในแต่ละบริษัท)
FREE_WORDS = ('ส่งฟรี', 'จัดส่งฟรี', 'ฟรีค่าขนส่ง')


def post_init_hook(env):
    # Odoo 17 ขึ้นไปส่ง env มาให้ตรง ๆ ไม่ใช่ (cr, registry) เหมือน o14
    env['ir.config_parameter'].sudo().set_param(
        'npd_free_shipping_campaign.start_datetime',
        fields.Datetime.to_string(fields.Datetime.now()))

    for campaign in env['utm.campaign'].sudo().search([]):
        name = campaign.name or ''
        if not any(word in name for word in FREE_WORDS):
            continue
        values = {'npd_free_shipping': True}
        found = KM_PATTERN.search(name)
        if found:
            values['npd_free_shipping_max_km'] = float(
                found.group(1).replace(',', '.'))
        campaign.write(values)
        _logger.info('[FREE_SHIPPING] ตั้งค่าแคมเปญ "%s" -> ส่งฟรีไม่เกิน %s กม.',
                     name, values.get('npd_free_shipping_max_km', 'ยังไม่กำหนด'))
