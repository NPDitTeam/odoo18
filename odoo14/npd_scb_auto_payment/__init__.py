# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import fields

from . import models

_logger = logging.getLogger(__name__)

START_DATE_KEY = 'npd_scb_auto_payment.verify_start_date'


def _scb_default_start_date():
    """ค่าเริ่มต้นของ "เริ่มตรวจสอบใบรับชำระตั้งแต่วันที่" = พรุ่งนี้

    เริ่มนับจากวันพรุ่งนี้ = ตัดขาดจากของเก่าทั้งหมด ระบบจะตรวจเฉพาะใบรับชำระ
    ที่บันทึกตั้งแต่วันพรุ่งนี้เป็นต้นไป ใบเก่าไม่ถูกแตะ ไม่เปลืองโควตา AI
    """
    return fields.Date.today() + timedelta(days=1)


def _scb_set_default_start_date(env):
    """ตั้ง "วันที่เริ่มตรวจสอบ" ตอนติดตั้งใหม่ ถ้ายังไม่เคยตั้งไว้

    ถ้าไม่ตั้งอะไรเลย ค่าว่าง = ไม่จำกัดย้อนหลัง -> cron จะกวาดใบรับชำระเก่า
    ทั้งฐานข้อมูลมาตรวจ และเรียก AI อ่านสลิปทีละใบจนโควตาหมด
    ผู้ใช้แก้วันที่ย้อนหลัง (หรือล้างค่าให้ว่าง) ได้เองที่หน้าตั้งค่า
    """
    icp = env['ir.config_parameter'].sudo()
    if icp.get_param(START_DATE_KEY):
        return
    start = fields.Date.to_string(_scb_default_start_date())
    icp.set_param(START_DATE_KEY, start)
    _logger.info(
        "npd_scb_auto_payment: ตั้งวันที่เริ่มตรวจสอบการโอนเป็น %s (พรุ่งนี้) "
        "— ตรวจเฉพาะใบรับชำระใหม่ ไม่ไล่ย้อนหลัง แก้ได้ที่หน้าตั้งค่า", start)
