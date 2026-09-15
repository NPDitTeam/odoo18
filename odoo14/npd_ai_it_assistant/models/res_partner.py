# -*- coding: utf-8 -*-
u"""ไฟแสดงสถานะของ "ตัวช่วย AI-IT" ในกล่องแชท

จุดกลมข้างรูปโปรไฟล์ในแชทมาจากฟิลด์ im_status ของ res.partner ซึ่งปกติคำนวณจาก
ตาราง bus_presence (คนนั้นเปิดหน้าจอค้างไว้ไหม) แต่บอทไม่มี res.users จึงไม่มี
presence ให้คำนวณ ค่าที่ได้เลยเป็น 'im_partner' แล้วหน้าจอไม่ขึ้นจุดอะไรเลย

ที่นี่จึงยึดความหมายใหม่สำหรับบอทตัวนี้โดยเฉพาะ:
    online  = เรียก AI ได้ (ตั้งค่า Gemini API key ไว้แล้ว)  -> จุดเขียว
    offline = เรียก AI ไม่ได้ (ยังไม่ได้ตั้ง key)             -> จุดแดง

สีเขียว/แดงมาจาก SCSS ของโมดูลนี้ (ปกติ Odoo ใช้สีธีมกับสีเทา)
"""
from odoo import models

BOT_XMLID = 'npd_ai_it_assistant.partner_ai_it_bot'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _compute_im_status(self):
        result = super(ResPartner, self)._compute_im_status()
        bot = self.env.ref(BOT_XMLID, raise_if_not_found=False)
        if not bot:
            return result
        bot_in_set = self.filtered(lambda partner: partner.id == bot.id)
        if not bot_in_set:
            return result
        status = 'online' if self.env['npd.ai.it.gemini'].is_available() else 'offline'
        for partner in bot_in_set:
            partner.im_status = status
        return result
