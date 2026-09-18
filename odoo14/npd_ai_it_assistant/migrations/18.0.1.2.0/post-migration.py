# -*- coding: utf-8 -*-
u"""ให้สิทธิ์หัวข้อ "ช่วยปิดงบ" กับผู้ใช้ชุดตั้งต้น สำหรับฐานที่ติดตั้งโมดูลไปแล้ว

post_init_hook ทำงานเฉพาะตอนติดตั้งใหม่ ฐานที่ติดตั้งโมดูลนี้ไปก่อนหน้าจึงต้อง
อาศัย migration ตัวนี้ตอนสั่ง -u  รายชื่อผู้ใช้อยู่ที่ CLOSING_HELP_LOGINS ใน hooks.py
(คนที่ไม่มีในฐานนั้นจะถูกข้ามให้เอง)
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.npd_ai_it_assistant.hooks import grant_closing_help_users


def migrate(cr, version):
    if not version:
        return
    grant_closing_help_users(api.Environment(cr, SUPERUSER_ID, {}))
