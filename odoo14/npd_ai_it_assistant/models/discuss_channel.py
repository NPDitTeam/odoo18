# -*- coding: utf-8 -*-
"""จุดเชื่อมระหว่างห้องแชทกับ "ตัวช่วย AI-IT"

ใช้วิธีเดียวกับ OdooBot (mail_bot) คือดักที่ _message_post_after_hook แล้วให้บอทตอบกลับ
Odoo 18 ห้องแชทคือ discuss.channel (o14 คือ mail.channel)
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _message_post_after_hook(self, message, msg_vals):
        result = super()._message_post_after_hook(message, msg_vals)
        if len(self) == 1 and not self.env.context.get('npd_ai_it_bot'):
            try:
                self.env['npd.ai.it.session']._on_channel_message(self, message, msg_vals)
            except Exception:  # noqa: BLE001 - ห้ามให้ข้อความของพนักงานหายไป
                _logger.exception('ตัวช่วย AI-IT: ตอบกลับในห้อง %s ไม่สำเร็จ', self.id)
        return result
