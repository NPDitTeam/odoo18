# -*- coding: utf-8 -*-
"""สัญญาการใช้งานของฐานข้อมูลนี้ (ฝั่งลูกค้า)

โมดูลนี้ติดตั้งอยู่ใน DB ของลูกค้าแต่ละราย ทำหน้าที่ "อ่านและบังคับใช้" สัญญาเท่านั้น
ตัวสัญญาถูกเขียนลงมาจากศูนย์ควบคุม (NPD_Logistics) ผ่านโมดูล npd_saas_manager

ทำไมเก็บใน ir.config_parameter ไม่ใช่ตารางของตัวเอง
--------------------------------------------------
ศูนย์ควบคุมต้องเขียนค่านี้ลง DB ลูกค้าได้โดยไม่ต้องพึ่งโมเดลของโมดูลนี้ ถ้าลูกค้า
ถอนโมดูลออกก็ยังเขียนได้ และค่าที่เก็บมีแค่ไม่กี่ตัว ไม่ต้องมีตารางแยก

สถานะที่เป็นไปได้
-----------------
* ``active``     ใช้งานได้ปกติ
* ``grace``      เลยวันหมดอายุแล้วแต่ยังอยู่ในช่วงผ่อนผัน — ใช้งานได้ แต่ขึ้นแบนเนอร์เตือน
* ``suspended``  ถูกระงับจากศูนย์ควบคุม (ค้างชำระ/ผิดเงื่อนไข)
* ``expired``    พ้นช่วงผ่อนผัน — ล็อกทั้งเว็บและแอป ข้อมูลยังอยู่ครบ
* ``terminated`` ยกเลิกสัญญา
"""
from odoo import models, fields, api

PARAM_PREFIX = 'npd_saas.'

# สถานะที่ยังให้ใช้งานได้
USABLE_STATES = ('active', 'grace')


class SaasLicense(models.AbstractModel):
    _name = 'saas.license'
    _description = 'สัญญาการใช้งานระบบ'

    @api.model
    def _param(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(
            PARAM_PREFIX + key, default)

    @api.model
    def get_status(self):
        """สรุปสถานะสัญญาปัจจุบัน — ใช้ทั้งฝั่งเว็บและ API

        DB ที่ไม่ได้ถูกปล่อยเช่า (เช่นเครื่องของ NPD เอง) จะไม่มีพารามิเตอร์เหล่านี้
        ให้ถือว่าใช้งานได้ตลอด ไม่งั้นระบบตัวเองจะล็อกตัวเองตั้งแต่ติดตั้ง
        """
        state = self._param('state')
        if not state:
            return {
                'managed': False,
                'state': 'active',
                'usable': True,
                'locked': False,
                'in_grace': False,
                'expire_date': False,
                'days_left': None,
                'tenant_name': '',
                'support_phone': '',
                'message': '',
            }

        expire_raw = self._param('expire_date')
        expire_date = fields.Date.to_date(expire_raw) if expire_raw else False
        days_left = None
        if expire_date:
            days_left = (expire_date - fields.Date.context_today(self)).days

        usable = state in USABLE_STATES
        return {
            'managed': True,
            'state': state,
            'usable': usable,
            'locked': not usable,
            'in_grace': state == 'grace',
            'expire_date': expire_raw,
            'days_left': days_left,
            'tenant_name': self._param('tenant_name'),
            'support_phone': self._param('support_phone'),
            'message': self._lock_message(state, expire_raw),
        }

    @api.model
    def _lock_message(self, state, expire_raw):
        contact = self._param('support_phone')
        suffix = ' กรุณาติดต่อผู้ให้บริการ%s' % (' โทร %s' % contact if contact else '')
        if state == 'suspended':
            return 'ระบบถูกระงับการใช้งานชั่วคราว' + suffix
        if state == 'expired':
            return ('สัญญาการใช้งานหมดอายุแล้ว%s ข้อมูลของท่านยังถูกเก็บไว้ครบถ้วน'
                    % (' เมื่อ %s' % expire_raw if expire_raw else '')) + suffix
        if state == 'terminated':
            return 'สัญญาการใช้งานถูกยกเลิกแล้ว' + suffix
        if state == 'grace':
            return ('สัญญาหมดอายุเมื่อ %s อยู่ในช่วงผ่อนผัน'
                    % expire_raw) + suffix
        return ''

    @api.model
    def is_locked(self):
        return self.get_status()['locked']

    @api.model
    def max_employees(self):
        """0 = ไม่จำกัด"""
        try:
            return int(self._param('max_employees', '0') or 0)
        except (TypeError, ValueError):
            return 0
