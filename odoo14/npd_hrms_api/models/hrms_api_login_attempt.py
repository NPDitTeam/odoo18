# -*- coding: utf-8 -*-
"""จำกัดจำนวนครั้งการเดา PIN

จำเป็นเพราะแอปล็อกอินด้วย PIN 6 หลักอย่างเดียว = ความเป็นไปได้แค่ 1,000,000 แบบ
ถ้ายิงได้ไม่จำกัด สคริปต์เดาสุ่มจะเจอ PIN ที่ใช้งานจริงภายในไม่กี่ชั่วโมง
(ระบบ PHP เดิมเปิด endpoint นี้ทิ้งไว้โดยไม่มีการจำกัดเลย)

นับแยกตาม device_id + IP เพราะ PIN ผิดไม่บอกว่าเป็นพนักงานคนไหน
จึงล็อกรายบุคคลไม่ได้ — ต้องล็อกที่ต้นทางที่ยิงมาแทน
"""
import logging
from datetime import timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BLOCK_MINUTES = 15
WINDOW_MINUTES = 15


class HrmsApiLoginAttempt(models.Model):
    _name = 'hrms.api.login.attempt'
    _description = 'ประวัติการล็อกอินผิดของแอป HR'
    _order = 'last_attempt_at desc'
    _rec_name = 'source_key'

    source_key = fields.Char(
        string='ต้นทาง', required=True, index=True,
        help='device_id + IP ที่ยิงคำขอเข้ามา')
    device_id = fields.Char(string='Device ID')
    ip_address = fields.Char(string='IP')
    attempts = fields.Integer(string='ครั้งที่ผิดติดกัน', default=0)
    first_attempt_at = fields.Datetime(string='ผิดครั้งแรกเมื่อ')
    last_attempt_at = fields.Datetime(string='ผิดครั้งล่าสุดเมื่อ')
    blocked_until = fields.Datetime(string='บล็อกถึง')

    _sql_constraints = [
        ('source_key_uniq', 'unique(source_key)', 'ต้นทางนี้มีรายการอยู่แล้ว'),
    ]

    @api.model
    def _source_key(self, device_id, ip_address):
        return '%s|%s' % (device_id or '-', ip_address or '-')

    @api.model
    def _check_blocked(self, device_id, ip_address):
        """คืนจำนวนวินาทีที่ต้องรอ — 0 ถ้ายังยิงได้"""
        record = self.sudo().search(
            [('source_key', '=', self._source_key(device_id, ip_address))], limit=1)
        if not record or not record.blocked_until:
            return 0
        now = fields.Datetime.now()
        if record.blocked_until <= now:
            return 0
        return int((record.blocked_until - now).total_seconds())

    @api.model
    def _register_failure(self, device_id, ip_address):
        """บันทึกการล็อกอินผิด — บล็อกเมื่อผิดครบ MAX_ATTEMPTS ครั้งในหน้าต่างเวลา"""
        now = fields.Datetime.now()
        key = self._source_key(device_id, ip_address)
        record = self.sudo().search([('source_key', '=', key)], limit=1)
        if not record:
            self.sudo().create({
                'source_key': key,
                'device_id': device_id or False,
                'ip_address': ip_address or False,
                'attempts': 1,
                'first_attempt_at': now,
                'last_attempt_at': now,
            })
            return

        # ผิดครั้งล่าสุดนานเกินหน้าต่างเวลาแล้ว → เริ่มนับใหม่
        if (record.last_attempt_at
                and record.last_attempt_at < now - timedelta(minutes=WINDOW_MINUTES)):
            record.write({
                'attempts': 1, 'first_attempt_at': now,
                'last_attempt_at': now, 'blocked_until': False,
            })
            return

        attempts = record.attempts + 1
        vals = {'attempts': attempts, 'last_attempt_at': now}
        if attempts >= MAX_ATTEMPTS:
            vals['blocked_until'] = now + timedelta(minutes=BLOCK_MINUTES)
            _logger.warning(
                'HRMS API: บล็อกการล็อกอินจาก %s เพราะใส่ PIN ผิด %d ครั้ง',
                key, attempts)
        record.write(vals)

    @api.model
    def _register_success(self, device_id, ip_address):
        record = self.sudo().search(
            [('source_key', '=', self._source_key(device_id, ip_address))], limit=1)
        if record:
            record.unlink()

    @api.model
    def _cron_purge(self):
        """ลบรายการที่เงียบไปเกิน 7 วัน"""
        cutoff = fields.Datetime.now() - timedelta(days=7)
        stale = self.sudo().search([('last_attempt_at', '<', cutoff)])
        stale.unlink()
        return True
