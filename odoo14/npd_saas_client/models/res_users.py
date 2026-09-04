# -*- coding: utf-8 -*-
"""กันไม่ให้เข้าใช้ระบบเมื่อสัญญาหมดอายุ/ถูกระงับ"""
from odoo import models, api
from odoo.exceptions import AccessDenied


class ResUsers(models.Model):
    _inherit = 'res.users'

    @classmethod
    def _login(cls, db, credential, user_agent_env):
        """ตรวจสัญญาก่อนอนุญาตให้ล็อกอินเข้าหน้าเว็บ

        ยกเว้นเฉพาะ ``__system__`` (uid 1) ซึ่งล็อกอินผ่านหน้าเว็บไม่ได้อยู่แล้ว
        จึงไม่ใช่ช่องทางหลบเลี่ยง — แต่เปิดไว้ให้สคริปต์ของศูนย์ควบคุมเข้ามาปลดล็อกได้

        เจตนาคือเมื่อหมดอายุแล้วต้องปลดล็อกจากศูนย์ควบคุมเท่านั้น ไม่ใช่ให้ผู้ดูแล
        ฝั่งลูกค้าปลดเอง มิฉะนั้นการบังคับใช้สัญญาจะไม่มีผลจริง
        """
        uid = super()._login(db, credential, user_agent_env)
        if not uid or uid == 1:
            return uid

        with cls.pool.cursor() as cr:
            env = api.Environment(cr, 1, {})
            status = env['saas.license'].get_status()
            if status['locked']:
                raise AccessDenied(status['message'])
        return uid
