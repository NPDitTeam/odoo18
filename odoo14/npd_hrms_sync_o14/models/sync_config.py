# -*- coding: utf-8 -*-
"""การตั้งค่าเชื่อมต่อไปยัง Odoo 14 และตัวเรียก JSON-RPC

คุยกับฝั่ง 14 ผ่าน JSON-RPC ไม่ใช่ REST เพราะเซิร์ฟเวอร์ 14 ให้บริการหลายฐาน
โดยไม่ได้ตั้ง dbfilter เส้นทาง REST ของโมดูลเสริมจึงตอบ 404 ส่วน JSON-RPC
รับชื่อฐานมาในตัวคำขออยู่แล้ว จึงใช้ได้แน่นอนไม่ว่าจะมีกี่ฐาน

ไม่เก็บรหัสผ่านไว้ในโค้ด ให้กรอกที่หน้าจอ และควรสร้างผู้ใช้แยกสำหรับงานซิงก์
ที่มีสิทธิ์อ่านอย่างเดียว ไม่ควรใช้บัญชีผู้ดูแลระบบ
"""
import json
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

# ฝั่ง 14 ต้องอ่านทีละมาก ๆ แต่ถ้าขอทีเดียวหมดจะกินหน่วยความจำและหลุด timeout
# 500 แถวต่อรอบเป็นค่าที่เร็วพอและไม่ทำให้ฝั่งนั้นหนัก
RPC_BATCH_SIZE = 500
RPC_TIMEOUT = 180

# เลขล็อกของ advisory lock — คงที่ ห้ามเปลี่ยน ไม่งั้นรอบเก่ากับรอบใหม่
# จะถือคนละล็อกแล้วรันซ้อนกันได้
SYNC_LOCK_KEY = 8814021


class HrmsSyncConfig(models.Model):
    _name = 'npd.hrms.sync.config'
    _description = 'การเชื่อมต่อ Odoo 14 สำหรับซิงก์ข้อมูล HR'
    _order = 'id desc'

    name = fields.Char(string='ชื่อการเชื่อมต่อ', required=True,
                       default='Odoo 14 — ฐาน HRMS')
    url = fields.Char(string='ที่อยู่เซิร์ฟเวอร์', required=True,
                      default='https://npderp.com',
                      help='ใส่แค่โดเมน ไม่ต้องมี /jsonrpc ต่อท้าย')
    db_name = fields.Char(string='ชื่อฐานข้อมูล', required=True, default='HRMS')
    username = fields.Char(string='ผู้ใช้', required=True,
                           help='ควรเป็นผู้ใช้ที่สร้างไว้สำหรับงานซิงก์โดยเฉพาะ '
                                'และให้สิทธิ์อ่านอย่างเดียว')
    password = fields.Char(string='รหัสผ่าน', required=True,
                           help='เก็บไว้ในฐานนี้เท่านั้น ไม่ถูกส่งไปที่อื่น')
    active = fields.Boolean(string='ใช้งาน', default=True)

    uid_cache = fields.Integer(string='uid ฝั่ง 14', readonly=True, copy=False,
                               help='ได้จากการล็อกอินครั้งล่าสุด เก็บไว้ใช้ซ้ำ')
    last_sync = fields.Datetime(string='ซิงก์ล่าสุดเมื่อ', readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'ยังไม่ได้ทดสอบ'),
        ('ok', 'เชื่อมต่อได้'),
        ('error', 'เชื่อมต่อไม่ได้'),
    ], string='สถานะ', default='draft', readonly=True, copy=False)
    state_message = fields.Text(string='ข้อความล่าสุด', readonly=True, copy=False)

    fallback_company_id = fields.Many2one(
        'res.company', string='บริษัทสำรอง (เมื่อฝั่ง 14 ไม่ระบุ)',
        help='ฝั่ง 14 มีพนักงานบางคนที่ช่องบริษัทว่างไว้ '
             'แต่ฝั่ง 18 บังคับว่าทุกคนต้องสังกัดบริษัท\n'
             'ถ้าไม่ตั้งค่านี้ Odoo จะใส่บริษัทหลักให้เองเงียบ ๆ '
             'ทำให้คนไปกองผิดบริษัทโดยไม่มีใครรู้\n'
             'ตั้งไว้ให้ชัดว่าจะให้ไปอยู่บริษัทไหน '
             'แล้วระบบจะแจ้งรายชื่อทุกรอบเพื่อให้ไปแก้ให้ถูกบริษัทต่อไป')

    recent_days = fields.Integer(
        string='รอบประจำวันดึงย้อนหลังกี่วัน', default=7,
        help='ใช้กับข้อมูลที่เกิดทุกวันและมีจำนวนมาก — ลงเวลา ใบลา '
             'และใบขอลงเวลาย้อนหลัง\n\n'
             'รอบแรกดึงทั้งหมด ส่วนรอบประจำวันหลังจากนั้นจะอ่านเฉพาะรายการที่ '
             'ถูกสร้างหรือแก้ไขภายในกี่วันล่าสุดตามที่ตั้งไว้ เพราะรายการเก่า '
             'ที่ผ่านรอบทำเงินเดือนไปแล้วจะไม่มีใครแก้อีก\n\n'
             'ช่วยให้รอบประจำวันเหลือไม่กี่นาที แทนที่จะต้องอ่านเจ็ดหมื่นแถว '
             'ทุกคืนเพื่อพบว่าแทบไม่มีอะไรเปลี่ยน\n\n'
             'ใส่ 0 = อ่านทั้งหมดทุกรอบเหมือนเดิม\n'
             'ปุ่ม "ดึงใหม่ทั้งหมด" ไม่สนค่านี้ อ่านครบทุกแถวเสมอ')

    payroll_recent_months = fields.Integer(
        string='รอบประจำวันดึงสลิปย้อนหลังกี่งวด', default=1,
        help='ใช้กับสลิปเงินเดือน ซึ่งนับเป็น "งวด" ไม่ใช่วันที่แก้ไข\n\n'
             'รอบแรกดึงสลิปครบทุกงวดไปแล้ว งวดที่ปิดจ่ายไปแล้วถือว่าจบ '
             'รอบประจำวันจึงตามดูเฉพาะงวดล่าสุดตามจำนวนที่ตั้งไว้\n\n'
             '1 = เฉพาะงวดปัจจุบัน (ค่าเริ่มต้น)\n'
             '2 = งวดปัจจุบันกับงวดก่อนหน้า — เผื่อกรณีแก้สลิปงวดก่อนย้อนหลัง '
             'เพราะวันจ่ายจริงคือวันที่ 28 ของงวดนั้น ก่อนถึงวันจ่ายยังแก้ได้อยู่\n\n'
             'งวดนับตามรอบตัด 25 ถึง 24 ตั้งแต่วันที่ 25 ถือว่าเข้างวดถัดไปแล้ว\n'
             'ปุ่ม "ดึงใหม่ทั้งหมด" ไม่สนค่านี้ อ่านครบทุกงวดเสมอ')

    stop_after_date = fields.Date(
        string='ดึงข้อมูลถึงวันที่ (แล้วหยุดเอง)',
        help='พอเลยวันนี้ไปแล้ว งานตั้งเวลาจะหยุดดึงและปิดตัวเองทันที\n'
             'ตั้งไว้เป็นวันสุดท้ายก่อนตัดไปใช้ระบบใหม่ จะได้ไม่มีใครลืมปิด\n'
             'แล้วข้อมูลเก่าไหลทับของใหม่ที่พนักงานเริ่มใช้แล้ว\n'
             'เว้นว่าง = ดึงไปเรื่อย ๆ จนกว่าจะปิดเอง')

    sync_from_date = fields.Date(
        string='ดึงข้อมูลย้อนหลังถึงวันที่',
        help='ใช้กับตารางที่มีวันที่ เช่น การลงเวลา สลิปเงินเดือน\n'
             'เว้นว่าง = ดึงทั้งหมดเท่าที่มี\n'
             'รอบแรกแนะนำให้ใส่ เพื่อไม่ให้ใช้เวลานานเกินไป')

    _sql_constraints = [
        ('url_db_uniq', 'unique(url, db_name)',
         'มีการตั้งค่าสำหรับเซิร์ฟเวอร์และฐานนี้อยู่แล้ว'),
    ]

    # ------------------------------------------------------------------
    @api.model
    def _get_active(self):
        """การเชื่อมต่อที่ใช้งานอยู่ (ต้องมีตัวเดียว)"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            raise UserError(_(
                'ยังไม่ได้ตั้งค่าการเชื่อมต่อไปยัง Odoo 14\n'
                'ไปที่ บุคคล > ตั้งค่า > ดึงข้อมูลจาก Odoo 14 '
                'แล้วสร้างการเชื่อมต่อก่อน'))
        return config

    # ------------------------------------------------------------------
    def _endpoint(self):
        return '%s/jsonrpc' % (self.url or '').rstrip('/')

    def _call(self, service, method, args):
        """เรียก JSON-RPC ดิบ — คืนค่าที่อยู่ใน result"""
        self.ensure_one()
        if requests is None:
            raise UserError(_('เซิร์ฟเวอร์นี้ยังไม่ได้ติดตั้งไลบรารี requests'))
        payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {'service': service, 'method': method, 'args': args},
            'id': 1,
        }
        try:
            response = requests.post(
                self._endpoint(), json=payload, timeout=RPC_TIMEOUT,
                headers={'Content-Type': 'application/json'})
            response.raise_for_status()
            data = response.json()
        except Exception as error:
            raise UserError(_('ติดต่อ Odoo 14 ไม่ได้: %s') % error)

        if data.get('error'):
            details = data['error'].get('data') or {}
            message = details.get('message') or data['error'].get('message') \
                or json.dumps(data['error'], ensure_ascii=False)
            raise UserError(_('Odoo 14 ตอบกลับว่าผิดพลาด: %s') % message)
        return data.get('result')

    def _login(self, force=False):
        """ล็อกอินเอา uid — ใช้ตัวที่เก็บไว้ถ้ามี จะได้ไม่ต้องล็อกอินทุกครั้ง"""
        self.ensure_one()
        if self.uid_cache and not force:
            return self.uid_cache
        uid = self._call('common', 'login',
                         [self.db_name, self.username, self.password])
        if not uid:
            raise UserError(_(
                'ล็อกอินเข้า Odoo 14 ไม่สำเร็จ — ตรวจชื่อผู้ใช้ รหัสผ่าน '
                'และชื่อฐาน "%s" อีกครั้ง') % self.db_name)
        # sudo เพราะถูกเรียกทั้งจาก cron และจากปุ่มบนหน้าจอ
        self.sudo().write({'uid_cache': uid})
        return uid

    def execute_kw(self, model, method, args, kwargs=None):
        """เรียกเมธอดบนโมเดลฝั่ง 14

        ถ้า uid ที่เก็บไว้ใช้ไม่ได้แล้ว จะล็อกอินใหม่ให้เองหนึ่งครั้งแล้วลองซ้ำ
        ไม่ต้องรอให้คนมากดเอง
        """
        self.ensure_one()
        kwargs = kwargs or {}
        uid = self._login()
        try:
            return self._call('object', 'execute_kw',
                              [self.db_name, uid, self.password,
                               model, method, args, kwargs])
        except UserError:
            uid = self._login(force=True)
            return self._call('object', 'execute_kw',
                              [self.db_name, uid, self.password,
                               model, method, args, kwargs])

    def search_read_batched(self, model, domain, fields_list, order='id'):
        """อ่านทีละชุดแล้วส่งออกมาเรื่อย ๆ ไม่ดึงมากองในหน่วยความจำทีเดียว"""
        self.ensure_one()
        offset = 0
        while True:
            rows = self.execute_kw(
                model, 'search_read', [domain, fields_list],
                {'limit': RPC_BATCH_SIZE, 'offset': offset, 'order': order})
            if not rows:
                break
            yield rows
            if len(rows) < RPC_BATCH_SIZE:
                break
            offset += RPC_BATCH_SIZE

    def remote_fields(self, model):
        """ชื่อฟิลด์ทั้งหมดของโมเดลฝั่ง 14 พร้อมชนิดและปลายทางของ m2o"""
        self.ensure_one()
        return self.execute_kw(model, 'fields_get', [],
                               {'attributes': ['type', 'relation', 'store']})

    # ------------------------------------------------------------------
    def action_test_connection(self):
        """ปุ่มทดสอบ — บอกให้ชัดว่าต่อได้ไหม และเห็นข้อมูลกี่คน"""
        self.ensure_one()
        try:
            self._login(force=True)
            version = self._call('common', 'version', [])
            count = self.execute_kw('employee.salary', 'search_count', [[]])
            message = _(
                'เชื่อมต่อสำเร็จ\nเซิร์ฟเวอร์: %s\nมองเห็นพนักงาน %s คน'
            ) % (version.get('server_version', '-'), count)
            self.sudo().write({'state': 'ok', 'state_message': message})
        except Exception as error:
            self.sudo().write({'state': 'error', 'state_message': str(error)})
            raise
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('ทดสอบการเชื่อมต่อ'), 'message': message,
                       'type': 'success', 'sticky': False},
        }

    def action_sync_now(self):
        """ปุ่มดึงข้อมูลเดี๋ยวนี้ — ดึงทุกหัวข้อที่เปิดไว้ แล้วเปิดใบบันทึกผลให้ดู"""
        self.ensure_one()
        log = self.env['npd.hrms.sync.engine'].run_sync(self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'npd.hrms.sync.log',
            'res_id': log.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_sync_full(self):
        """ดึงใหม่ทั้งหมด ไม่สนว่าเคยดึงไปแล้ว — ใช้ตอนตั้งระบบครั้งแรก
        หรือตอนสงสัยว่าข้อมูลบางส่วนหลุดไป
        """
        self.ensure_one()
        log = self.env['npd.hrms.sync.engine'].run_sync(self, incremental=False)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'npd.hrms.sync.log',
            'res_id': log.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_check_completeness(self):
        """ตรวจว่าข้อมูลที่ยกมาครบและตรงกับฝั่ง 14 จริงไหม ทุกหัวข้อ"""
        self.ensure_one()
        check = self.env['npd.hrms.sync.check'].run_check(self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'npd.hrms.sync.check',
            'res_id': check.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_map_companies(self):
        """เปิดหน้าจับคู่บริษัท พร้อมเดาให้ก่อนหนึ่งรอบ"""
        self.ensure_one()
        self.env['npd.hrms.sync.company.map'].autofill()
        return {
            'type': 'ir.actions.act_window',
            'name': _('จับคู่บริษัท Odoo 14 กับ Odoo 18'),
            'res_model': 'npd.hrms.sync.company.map',
            'view_mode': 'list,form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    @api.model
    def cron_sync(self):
        """งานตั้งเวลา — ดึงเฉพาะของที่เปลี่ยนตั้งแต่รอบที่แล้ว

        กันรอบซ้อนกันด้วยล็อกระดับฐาน ถ้ารอบก่อนยังไม่จบ รอบนี้ข้ามไปเงียบ ๆ
        ดีกว่าปล่อยให้สองรอบเขียนทับกัน
        """
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            _logger.info('[HRMS-SYNC] ยังไม่ได้ตั้งค่าการเชื่อมต่อ ข้ามรอบนี้')
            return

        # เลยวันสุดท้ายที่ตั้งไว้แล้ว = ตัดไปใช้ระบบใหม่เรียบร้อย
        # ต้องหยุดถาวร ไม่ใช่แค่ข้ามรอบนี้ เพราะถ้าปล่อยให้รันต่อ ข้อมูลเก่า
        # จากฝั่ง 14 จะไหลมาทับสิ่งที่พนักงานเริ่มบันทึกบนระบบใหม่แล้ว
        today = fields.Date.context_today(config)
        if config.stop_after_date and today > config.stop_after_date:
            cron = self.env.ref('npd_hrms_sync_o14.ir_cron_hrms_sync_o14',
                                raise_if_not_found=False)
            if cron and cron.active:
                cron.sudo().write({'active': False})
                _logger.warning(
                    '[HRMS-SYNC] เลยวันสุดท้ายที่ตั้งไว้ (%s) แล้ว '
                    'ปิดงานตั้งเวลาถาวร ถ้าต้องการดึงอีกให้เปิดเองที่หน้าตั้งค่า',
                    config.stop_after_date)
            return
        self.env.cr.execute('SELECT pg_try_advisory_lock(%s)', (SYNC_LOCK_KEY,))
        if not self.env.cr.fetchone()[0]:
            _logger.info('[HRMS-SYNC] รอบก่อนยังทำงานอยู่ ข้ามรอบนี้')
            return
        try:
            self.env['npd.hrms.sync.engine'].run_sync(config, incremental=True)
        finally:
            self.env.cr.execute('SELECT pg_advisory_unlock(%s)', (SYNC_LOCK_KEY,))
