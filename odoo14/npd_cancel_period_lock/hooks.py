# -*- coding: utf-8 -*-
from odoo import fields

from .models.cancel_lock_mixin import (
    PARAM_CUTOFF, compute_cutoff, get_lock_day, next_cron_call, thai_now,
)


def pre_init_hook(env):
    """ตั้งวันตัดงวดไว้ก่อน ฟิลด์ใหม่ที่ถูกคำนวณตอนติดตั้งจะได้ขึ้นสถานะถูกต้องในรอบเดียว"""
    cutoff = compute_cutoff(thai_now().date(), get_lock_day(env))
    env['ir.config_parameter'].sudo().set_param(PARAM_CUTOFF, fields.Date.to_string(cutoff))


def post_init_hook(env):
    env['account.move']._cron_update_cancel_lock()
    # รอบถัดไป = วันที่ 15 ที่จะถึง เวลา 00:05 น. ตามเวลาประเทศไทย
    cron = env.ref('npd_cancel_period_lock.cron_update_cancel_lock', raise_if_not_found=False)
    if cron:
        cron.write({'nextcall': next_cron_call(thai_now(), get_lock_day(env))})
