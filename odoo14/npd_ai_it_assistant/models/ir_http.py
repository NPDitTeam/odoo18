# -*- coding: utf-8 -*-
u"""ส่ง id ของ partner บอทไปให้ฝั่งเบราว์เซอร์

ฝั่ง JS ต้องรู้ว่า partner ตัวไหนคือ "ตัวช่วย AI-IT" เพื่อจะได้ทำเครื่องหมาย
บนจุดสถานะ แล้วให้ SCSS ย้อมสีเขียว/แดงเฉพาะของบอท ไม่ไปโดนผู้ใช้คนอื่น
"""
from odoo import models

BOT_XMLID = 'npd_ai_it_assistant.partner_ai_it_bot'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super(IrHttp, self).session_info()
        bot = self.env.ref(BOT_XMLID, raise_if_not_found=False)
        result['npd_ai_it_bot_partner_id'] = bot.id if bot else False
        return result
