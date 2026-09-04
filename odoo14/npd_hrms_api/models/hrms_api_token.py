# -*- coding: utf-8 -*-
"""Token สำหรับแอป HR

ระบบเดิมไม่มีการยืนยันตัวตนเลย — ใครก็ตามที่รู้ URL ยิง
``leave_requests.php?user_id=123`` ก็อ่านประวัติการลาของคนอื่นได้ทันที
(บาง endpoint มี HTTP Basic แต่ user/pass ฝังอยู่ในโค้ดแอปที่ decompile ได้)

ที่นี่ล็อกอินสำเร็จแล้วได้ token ที่:
  * ผูกกับพนักงานคนเดียว → ดึงข้อมูลของคนอื่นไม่ได้
  * ผูกกับ device_id → คัดลอก token ไปใช้เครื่องอื่นไม่ได้
  * มีวันหมดอายุ และเพิกถอนจากหน้า Odoo ได้ทันที
"""
import logging
import secrets
from datetime import timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# อายุ token — พนักงานลงเวลาทุกวัน 30 วันจึงไม่ต้องล็อกอินใหม่บ่อยจนน่ารำคาญ
TOKEN_LIFETIME_DAYS = 30


class HrmsApiToken(models.Model):
    _name = 'hrms.api.token'
    _description = 'Token แอป HR'
    _order = 'create_date desc'
    _rec_name = 'employee_id'

    token = fields.Char(string='Token', required=True, index=True, copy=False)
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True,
        ondelete='cascade', index=True)
    employee_code = fields.Char(
        related='employee_id.employee_code', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', related='employee_id.company_id', store=True, readonly=True)
    device_id = fields.Char(string='Device ID', index=True)
    user_agent = fields.Char(string='อุปกรณ์ (User-Agent)')
    ip_address = fields.Char(string='IP ที่ล็อกอิน')
    expires_at = fields.Datetime(string='หมดอายุ', required=True, index=True)
    last_used_at = fields.Datetime(string='ใช้งานล่าสุด')
    revoked = fields.Boolean(string='ถูกเพิกถอน', default=False)
    is_valid = fields.Boolean(string='ใช้งานได้', compute='_compute_is_valid')

    _sql_constraints = [
        ('token_uniq', 'unique(token)', 'Token ซ้ำ'),
    ]

    @api.depends('revoked', 'expires_at')
    def _compute_is_valid(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_valid = bool(
                not rec.revoked and rec.expires_at and rec.expires_at > now)

    # ------------------------------------------------------------------
    @api.model
    def _issue(self, employee, device_id=None, user_agent=None, ip_address=None):
        """ออก token ใหม่ให้พนักงาน

        พนักงานที่ไม่ได้อนุญาตให้เข้าหลายเครื่อง → เพิกถอน token เดิมทั้งหมดก่อน
        ป้องกันการใช้บัญชีร่วมกันด้วยการส่ง token ต่อ
        """
        if not employee.allow_multi_login:
            existing = self.sudo().search([
                ('employee_id', '=', employee.id), ('revoked', '=', False)])
            if existing:
                existing.write({'revoked': True})
        return self.sudo().create({
            'token': secrets.token_urlsafe(48),
            'employee_id': employee.id,
            'device_id': device_id or False,
            'user_agent': (user_agent or '')[:255] or False,
            'ip_address': ip_address or False,
            'expires_at': fields.Datetime.now() + timedelta(days=TOKEN_LIFETIME_DAYS),
            'last_used_at': fields.Datetime.now(),
        })

    @api.model
    def _resolve(self, token, device_id=None):
        """คืนพนักงานเจ้าของ token — คืน recordset ว่างถ้า token ใช้ไม่ได้"""
        if not token:
            return self.env['employee.salary']
        record = self.sudo().search([('token', '=', token)], limit=1)
        if not record or not record.is_valid:
            return self.env['employee.salary']
        # token ผูกกับเครื่อง — ส่งมาจากเครื่องอื่นถือว่าใช้ไม่ได้
        if record.device_id and device_id and record.device_id != device_id:
            _logger.warning(
                'HRMS API: token ของ %s ถูกใช้จากอุปกรณ์อื่น (%s != %s)',
                record.employee_code, device_id, record.device_id)
            return self.env['employee.salary']
        if record.employee_id.status != 'active':
            return self.env['employee.salary']
        record.last_used_at = fields.Datetime.now()
        return record.employee_id

    def action_revoke(self):
        self.write({'revoked': True})
        return True

    @api.model
    def _cron_purge_expired(self):
        """ลบ token ที่หมดอายุเกิน 90 วัน — ไม่ให้ตารางบวมและลดข้อมูลค้าง"""
        cutoff = fields.Datetime.now() - timedelta(days=90)
        stale = self.sudo().search([('expires_at', '<', cutoff)])
        count = len(stale)
        stale.unlink()
        _logger.info('HRMS API: ลบ token หมดอายุ %d รายการ', count)
        return True
