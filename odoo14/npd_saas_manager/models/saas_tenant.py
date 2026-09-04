# -*- coding: utf-8 -*-
"""ศูนย์ควบคุมการปล่อยเช่าระบบ (ติดตั้งบน NPD_Logistics เท่านั้น)

ต่อยอดจาก ``hrms.tenant`` ที่แอปใช้ค้นหา "รหัสองค์กร → ต่อไปเซิร์ฟเวอร์ไหน"
โดยเพิ่มเรื่องสัญญาและการสร้าง/ดูแลฐานข้อมูลของลูกค้าแต่ละราย

หลักการ
-------
* ลูกค้าหนึ่งราย = หนึ่งฐานข้อมูล = หนึ่งโดเมนย่อย (แยกข้อมูลขาดจากกันจริง)
* สร้างจาก **DB ต้นแบบที่สะอาด** เสมอ ไม่โคลนจากฐานข้อมูลที่มีข้อมูลจริงของ NPD
  เพราะข้อมูลพนักงาน เงินเดือน และลูกค้าจะหลุดไปอยู่ในมือผู้เช่าทันที
  และยังติดไปกับ backup ของเขาแม้จะลบทีหลัง
* สัญญาถูก "เขียนลง" DB ลูกค้า ไม่ใช่ให้ DB ลูกค้าวิ่งมาถาม — ระบบลูกค้าจึงบังคับใช้
  สัญญาได้แม้ตัดขาดจากศูนย์ควบคุม และไม่มีจุดล้มเหลวร่วม
"""
import logging
import os
import re
import secrets
import shutil
import string
from contextlib import closing

from odoo import models, fields, api
from odoo.exceptions import UserError

import odoo
from odoo.service.db import database_identifier, _drop_conn
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

# ชื่อฐานข้อมูลที่ยอมให้ใช้ — กันทั้งอักขระที่ทำให้ SQL พังและชื่อที่ dbfilter ใช้ไม่ได้
DB_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{1,62}$')

# พารามิเตอร์สัญญาที่เขียนลงฐานข้อมูลของลูกค้า (ฝั่งนั้นอ่านด้วย npd_saas_client)
PARAM_PREFIX = 'npd_saas.'


class HrmsTenant(models.Model):
    _inherit = 'hrms.tenant'

    # ------------------------------------------------------------------
    # ฐานข้อมูลและที่อยู่
    # ------------------------------------------------------------------
    db_name = fields.Char(
        string='ชื่อฐานข้อมูล', copy=False,
        help='ชื่อ DB ของลูกค้ารายนี้ — ต้องตรงกับโดเมนย่อยถ้าใช้ dbfilter มาตรฐาน')
    subdomain = fields.Char(
        string='โดเมนย่อย',
        help='เช่น abc จะได้ที่อยู่ https://abc.<โดเมนหลัก>')
    is_control_plane = fields.Boolean(
        string='เป็นศูนย์ควบคุม', default=False, copy=False,
        help='ฐานข้อมูลนี้เป็นตัวจัดการเอง — ห้ามสั่งลบหรือระงับ')

    # ------------------------------------------------------------------
    # ตอบกลับให้แอป
    # ------------------------------------------------------------------
    @api.model
    def api_resolve(self, code):
        """เพิ่มชื่อฐานข้อมูลลงในคำตอบของ /tenant/resolve

        แอปกรอกได้แค่รหัสองค์กร ต้องได้ชื่อฐานกลับไปเพื่อแนบไปกับคำขอถัด ๆ ไป
        (หัวข้อความ ``X-Odoo-Db``) ไม่งั้นเซิร์ฟเวอร์ที่มีหลายฐานจะเลือกฐานไม่ถูก
        """
        data = super().api_resolve(code)
        if not data:
            return data
        tenant = self.sudo().search(
            [('code', '=', (code or '').strip().lower())], limit=1)
        data['db_name'] = tenant.db_name or ''
        return data

    # ------------------------------------------------------------------
    # สัญญา
    # ------------------------------------------------------------------
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('active', 'ใช้งาน'),
        ('grace', 'ผ่อนผัน'),
        ('suspended', 'ระงับชั่วคราว'),
        ('expired', 'หมดอายุ'),
        ('terminated', 'ยกเลิกแล้ว'),
    ], string='สถานะ', default='draft', required=True, copy=False)

    start_date = fields.Date(string='วันเริ่มสัญญา', copy=False)
    expire_date = fields.Date(string='วันหมดอายุ', copy=False)
    grace_days = fields.Integer(
        string='วันผ่อนผัน', default=7,
        help='หลังหมดอายุ ยังใช้งานได้อีกกี่วันก่อนถูกล็อก')
    days_left = fields.Integer(
        string='เหลืออีก (วัน)', compute='_compute_days_left')

    max_employees = fields.Integer(
        string='พนักงานสูงสุด', default=0, help='0 = ไม่จำกัด')
    # เก็บค่าไว้แทนการคำนวณสด — การอ่านจำนวนพนักงานต้องเปิด registry ของ DB ลูกค้า
    # ซึ่งหนักมาก ถ้าคำนวณทุกครั้งที่เปิดหน้ารายการ ระบบจะค้างเมื่อมีลูกค้าหลายราย
    employee_count = fields.Integer(
        string='พนักงานที่ใช้อยู่', readonly=True, copy=False)
    usage_checked_at = fields.Datetime(
        string='ตรวจการใช้งานเมื่อ', readonly=True, copy=False)
    over_quota = fields.Boolean(
        string='เกินโควตา', compute='_compute_over_quota', store=True)

    provisioned_at = fields.Datetime(string='สร้างระบบเมื่อ', readonly=True, copy=False)
    renewal_ids = fields.One2many(
        'saas.renewal', 'tenant_id', string='ประวัติการต่ออายุ')

    _sql_constraints = [
        ('db_name_uniq', 'unique(db_name)', 'ชื่อฐานข้อมูลนี้ถูกใช้กับองค์กรอื่นแล้ว'),
    ]

    # ------------------------------------------------------------------
    # คำนวณ
    # ------------------------------------------------------------------
    @api.depends('expire_date')
    def _compute_days_left(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.days_left = (rec.expire_date - today).days if rec.expire_date else 0

    @api.depends('employee_count', 'max_employees')
    def _compute_over_quota(self):
        for rec in self:
            rec.over_quota = bool(
                rec.max_employees and rec.employee_count > rec.max_employees)

    def action_refresh_usage(self):
        """อ่านจำนวนพนักงานที่ใช้งานอยู่จากฐานข้อมูลลูกค้า

        แยกเป็นปุ่ม/cron แทนการคำนวณสด เพราะต้องเปิด registry ของ DB ปลายทาง
        """
        for rec in self:
            if not rec.db_name or rec.state in ('draft', 'terminated'):
                continue
            try:
                with rec._tenant_env() as env:
                    rec.employee_count = env['employee.salary'].sudo().search_count(
                        [('status', '=', 'active')])
                    rec.usage_checked_at = fields.Datetime.now()
            except Exception:
                _logger.exception('SaaS: อ่านจำนวนพนักงานของ %s ไม่ได้', rec.name)
        return True

    @api.onchange('subdomain')
    def _onchange_subdomain(self):
        for rec in self:
            if not rec.subdomain:
                continue
            rec.subdomain = rec.subdomain.strip().lower()
            root = rec._root_domain()
            rec.base_url = 'https://%s.%s' % (rec.subdomain, root)
            if not rec.db_name:
                rec.db_name = rec.subdomain

    # ------------------------------------------------------------------
    # ตัวช่วย
    # ------------------------------------------------------------------
    @api.model
    def _root_domain(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'npd_saas.root_domain', 'npd-solution.com')

    @api.model
    def _template_db(self):
        name = self.env['ir.config_parameter'].sudo().get_param(
            'npd_saas.template_db', '')
        if not name:
            raise UserError(
                'ยังไม่ได้ตั้งค่า "ฐานข้อมูลต้นแบบ"\n\n'
                'ไปที่ ตั้งค่า → พารามิเตอร์ระบบ แล้วเพิ่มคีย์ npd_saas.template_db '
                'ให้ชี้ไปยัง DB ต้นแบบที่สะอาด (ไม่มีข้อมูลจริงของ NPD)')
        return name

    def _tenant_env(self):
        """เปิด Environment ไปยังฐานข้อมูลของลูกค้ารายนี้

        ใช้ registry ของ Odoo แทนการต่อ SQL ตรง เพื่อให้ cache ของ DB ปลายทาง
        ถูกล้างให้อัตโนมัติเมื่อเราแก้ค่า — ถ้าเขียน SQL ตรง ๆ ฐานข้อมูลนั้น
        จะยังอ่านค่าเก่าจาก cache จนกว่าจะรีสตาร์ท
        """
        self.ensure_one()
        if not self.db_name:
            raise UserError('องค์กร "%s" ยังไม่ได้ระบุชื่อฐานข้อมูล' % self.name)
        return _TenantEnv(self.db_name)

    def _assert_manageable(self):
        for rec in self:
            if rec.is_control_plane:
                raise UserError(
                    'องค์กร "%s" เป็นศูนย์ควบคุม ไม่อนุญาตให้สั่งงานที่กระทบ'
                    'ฐานข้อมูลตัวเอง' % rec.name)

    # ------------------------------------------------------------------
    # จัดการฐานข้อมูลเอง แทนการเรียก odoo.service.db
    # ------------------------------------------------------------------
    # ฟังก์ชัน exp_duplicate_database / exp_drop ของ Odoo ใช้ตรงนี้ไม่ได้ด้วยสองเหตุผล
    #   1. ทั้งคู่ถูกปิดเมื่อตั้ง list_db = False ซึ่งเป็นค่าที่ควรตั้งบนเครื่องจริง
    #      (ระบบ Odoo 14 เดิมเคยถูกเจาะผ่านหน้าจัดการฐานข้อมูลที่เปิดสาธารณะมาแล้ว)
    #   2. exp_drop เช็คกับ list_dbs() ซึ่งคืนเฉพาะ DB ที่ระบุด้วย -d ตอนรัน
    #      ถ้าไม่ตรงจะ "คืน False เงียบ ๆ" ทำให้ระบบรายงานว่าลบสำเร็จทั้งที่ยังอยู่
    @api.model
    def _check_db_name(self, name):
        if not name or not DB_NAME_RE.match(name):
            raise UserError(
                'ชื่อฐานข้อมูล "%s" ใช้ไม่ได้ — ใช้ได้เฉพาะ a-z A-Z 0-9 ขีดกลาง '
                'และขีดล่าง ยาว 2-63 ตัว และขึ้นต้นด้วยตัวอักษรหรือตัวเลข' % (name or ''))
        return name

    @api.model
    def _db_exists(self, name):
        with closing(odoo.sql_db.db_connect('postgres').cursor()) as cr:
            cr.execute('SELECT 1 FROM pg_database WHERE datname = %s', (name,))
            return bool(cr.fetchone())

    @api.model
    def _clone_database(self, template, target):
        self._check_db_name(template)
        self._check_db_name(target)
        odoo.sql_db.close_db(template)
        with closing(odoo.sql_db.db_connect('postgres').cursor()) as cr:
            cr._cnx.autocommit = True  # CREATE DATABASE อยู่ใน transaction ไม่ได้
            _drop_conn(cr, template)
            cr.execute(SQL(
                "CREATE DATABASE %s ENCODING 'unicode' TEMPLATE %s",
                database_identifier(cr, target),
                database_identifier(cr, template)))

        # DB ใหม่ต้องมี uuid ของตัวเอง ไม่งั้นจะถูกนับเป็นเครื่องเดียวกับต้นแบบ
        # และ neutralize ปิด cron/อีเมล กันระบบที่เพิ่งสร้างยิงงานหรือเมลออกไปเอง
        registry = odoo.modules.registry.Registry.new(target)
        with registry.cursor() as cr:
            tenv = api.Environment(cr, odoo.SUPERUSER_ID, {})
            tenv['ir.config_parameter'].init(force=True)
            odoo.modules.neutralize.neutralize_database(cr)

        from_fs = odoo.tools.config.filestore(template)
        to_fs = odoo.tools.config.filestore(target)
        if os.path.exists(from_fs) and not os.path.exists(to_fs):
            shutil.copytree(from_fs, to_fs)
        return True

    @api.model
    def _drop_database(self, name):
        self._check_db_name(name)
        odoo.modules.registry.Registry.delete(name)
        odoo.sql_db.close_db(name)
        with closing(odoo.sql_db.db_connect('postgres').cursor()) as cr:
            cr._cnx.autocommit = True
            _drop_conn(cr, name)
            cr.execute(SQL('DROP DATABASE %s', database_identifier(cr, name)))
        fs = odoo.tools.config.filestore(name)
        if os.path.exists(fs):
            shutil.rmtree(fs)
        # ยืนยันว่าหายจริง ไม่เชื่อค่าที่ฟังก์ชันคืนมาเฉย ๆ
        if self._db_exists(name):
            raise UserError('ลบฐานข้อมูล "%s" ไม่สำเร็จ — ยังมีอยู่' % name)
        return True

    # ------------------------------------------------------------------
    # เขียนสัญญาลงฐานข้อมูลลูกค้า
    # ------------------------------------------------------------------
    def _effective_state(self):
        """สถานะจริงที่ควรบังคับใช้ ณ วันนี้ (เผื่อ cron ยังไม่ทันวิ่ง)"""
        self.ensure_one()
        if self.state in ('draft', 'suspended', 'terminated'):
            return self.state
        if not self.expire_date:
            return self.state
        today = fields.Date.context_today(self)
        if today <= self.expire_date:
            return 'active'
        if (today - self.expire_date).days <= max(0, self.grace_days):
            return 'grace'
        return 'expired'

    def push_license(self):
        """ส่งสัญญาปัจจุบันลงฐานข้อมูลลูกค้า"""
        for rec in self:
            if not rec.db_name or rec.is_control_plane:
                continue
            values = {
                'state': rec._effective_state(),
                'expire_date': rec.expire_date and str(rec.expire_date) or '',
                'grace_days': str(rec.grace_days or 0),
                'max_employees': str(rec.max_employees or 0),
                'tenant_code': rec.code or '',
                'tenant_name': rec.name or '',
                'support_phone': rec.support_phone or '',
            }
            release = rec._current_app_release_values()
            try:
                with rec._tenant_env() as env:
                    Param = env['ir.config_parameter'].sudo()
                    for key, value in values.items():
                        Param.set_param(PARAM_PREFIX + key, value)
                    if rec.base_url:
                        Param.set_param('web.base.url', rec.base_url)
                    if release:
                        rec._apply_app_release(env, release)
            except UserError:
                raise
            except Exception as exc:
                raise UserError(
                    'เขียนสัญญาลงฐานข้อมูล "%s" ไม่สำเร็จ: %s' % (rec.db_name, exc))
        return True

    # ------------------------------------------------------------------
    # เวอร์ชันแอป — ประกาศที่ศูนย์ควบคุมแล้วส่งลงทุกฐานข้อมูล
    # ------------------------------------------------------------------
    # แอปมีตัวเดียวบนสโตร์ใช้ร่วมกันทุกองค์กร เวอร์ชันจึงต้องมีชุดเดียว
    # ถ้าปล่อยให้แต่ละองค์กรตั้งเอง จะเกิดกรณีบอกพนักงานให้อัปเดตไปเวอร์ชัน
    # ที่ไม่มีอยู่จริง หรือค้างเวอร์ชันเก่าจนใช้ API ใหม่ไม่ได้
    @api.model
    def _current_app_release_values(self):
        release = self.env['hrms.app.release'].sudo().search(
            [('is_current', '=', True)], limit=1)
        if not release:
            return None
        return {
            'version': release.version,
            'build_number': release.build_number,
            'release_date': release.release_date,
            'android_url': release.android_url or False,
            'ios_url': release.ios_url or False,
            'release_note': release.release_note or False,
            'is_mandatory': release.is_mandatory,
            'is_current': True,
            'active': True,
        }

    @api.model
    def _apply_app_release(self, tenant_env, values):
        Release = tenant_env['hrms.app.release'].sudo()
        existing = Release.with_context(active_test=False).search(
            [('version', '=', values['version'])], limit=1)
        if existing:
            existing.write(values)
        else:
            Release.create(values)

    def action_push_app_release(self):
        """ส่งเวอร์ชันแอปปัจจุบันไปยังลูกค้าทุกรายที่ยังใช้งานอยู่"""
        release = self._current_app_release_values()
        if not release:
            raise UserError(
                'ยังไม่ได้ประกาศเวอร์ชันปัจจุบัน\n\n'
                'ไปที่ ปล่อยเช่าระบบ → เวอร์ชันแอป HR แล้วติ๊ก "เวอร์ชันปัจจุบัน" ก่อน')
        tenants = self.sudo().search([
            ('is_control_plane', '=', False),
            ('db_name', '!=', False),
            ('state', 'in', ['active', 'grace']),
        ])
        sent = failed = 0
        for tenant in tenants:
            try:
                with tenant._tenant_env() as env:
                    tenant._apply_app_release(env, release)
                sent += 1
            except Exception:
                failed += 1
                _logger.exception('SaaS: ส่งเวอร์ชันแอปให้ %s ไม่สำเร็จ', tenant.name)
        message = 'ส่งเวอร์ชัน %s ให้ลูกค้า %d ราย' % (release['version'], sent)
        if failed:
            message += ' (ล้มเหลว %d ราย — ดูรายละเอียดใน log)' % failed
        return self._notify(message)

    # ------------------------------------------------------------------
    # ปุ่มสั่งงาน
    # ------------------------------------------------------------------
    def action_provision(self):
        """สร้างระบบให้ลูกค้าใหม่ — โคลน DB ต้นแบบแล้วเขียนสัญญาลงไป"""
        self.ensure_one()
        self._assert_manageable()
        if self.state != 'draft':
            raise UserError('องค์กรนี้สร้างระบบไปแล้ว (สถานะ: %s)' % self.state)
        if not self.db_name:
            raise UserError('กรุณาระบุชื่อฐานข้อมูลก่อน')
        if not self.expire_date:
            raise UserError('กรุณาระบุวันหมดอายุก่อนสร้างระบบ')

        template = self._template_db()
        self._check_db_name(self.db_name)
        if self.db_name == template:
            raise UserError('ชื่อฐานข้อมูลซ้ำกับ DB ต้นแบบ')
        if not self._db_exists(template):
            raise UserError('ไม่พบฐานข้อมูลต้นแบบ "%s"' % template)
        if self._db_exists(self.db_name):
            raise UserError('มีฐานข้อมูลชื่อ "%s" อยู่แล้ว' % self.db_name)

        _logger.info('SaaS: โคลน %s -> %s', template, self.db_name)
        self._clone_database(template, self.db_name)

        self.write({
            'state': 'active',
            'start_date': self.start_date or fields.Date.context_today(self),
            'provisioned_at': fields.Datetime.now(),
        })
        self.push_license()
        password = self._reset_admin_password()
        self._rename_company()
        return self._notify_credentials(password, title='สร้างระบบเรียบร้อย')

    # ------------------------------------------------------------------
    # บัญชีผู้ดูแลของระบบลูกค้า
    # ------------------------------------------------------------------
    # DB ทุกตัวถูกโคลนจากต้นแบบเดียวกัน จึงได้รหัสผ่านผู้ดูแลชุดเดียวกันทั้งหมด
    # ถ้าไม่เปลี่ยนตอนสร้าง ใครที่เคยเห็นรหัสของลูกค้ารายหนึ่งจะเข้าระบบของ
    # ลูกค้ารายอื่นได้ทันที — ต้องสุ่มใหม่ทุกครั้งที่สร้าง
    @api.model
    def _generate_password(self, length=16):
        alphabet = string.ascii_letters + string.digits + '!@#%^*-_=+'
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _reset_admin_password(self):
        """สุ่มรหัสผ่านผู้ดูแลของ DB ลูกค้าใหม่ แล้วคืนค่าให้แสดงครั้งเดียว

        ไม่เก็บลงฐานข้อมูลโดยเจตนา — เก็บรหัสผ่านแบบอ่านได้ไว้ที่ศูนย์ควบคุม
        เท่ากับว่าถ้าศูนย์ควบคุมถูกเจาะ ระบบลูกค้าทุกรายถูกเจาะตามทันที
        ถ้าทำหาย ให้กดปุ่มตั้งรหัสใหม่ได้ตลอด
        """
        self.ensure_one()
        password = self._generate_password()
        with self._tenant_env() as env:
            admin = env.ref('base.user_admin', raise_if_not_found=False)
            if not admin:
                raise UserError('ไม่พบบัญชีผู้ดูแลในฐานข้อมูล "%s"' % self.db_name)
            admin.sudo().write({'password': password})
        return password

    def action_reset_admin_password(self):
        self.ensure_one()
        self._assert_manageable()
        if self.state == 'draft' or not self.db_name:
            raise UserError('ต้องสร้างระบบให้ลูกค้าก่อน')
        password = self._reset_admin_password()
        return self._notify_credentials(password, title='ตั้งรหัสผ่านผู้ดูแลใหม่แล้ว')

    def _rename_company(self):
        """ตั้งชื่อบริษัทใน DB ลูกค้าให้ตรงกับชื่อองค์กร

        ต้นแบบมีชื่อว่า My Company ถ้าไม่เปลี่ยน ชื่อนี้จะไปโผล่บนเอกสารและ
        รายงานทุกใบของลูกค้า
        """
        self.ensure_one()
        try:
            with self._tenant_env() as env:
                company = env['res.company'].sudo().search([], limit=1, order='id')
                if company:
                    company.write({'name': self.name})
        except Exception:
            _logger.exception('SaaS: เปลี่ยนชื่อบริษัทใน %s ไม่สำเร็จ', self.db_name)

    def _notify_credentials(self, password, title):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': (
                    'ที่อยู่: %s\n'
                    'ผู้ดูแล: admin\n'
                    'รหัสผ่าน: %s\n'
                    'รหัสองค์กรสำหรับแอป: %s\n\n'
                    'คัดลอกเก็บไว้เดี๋ยวนี้ — ระบบไม่ได้บันทึกรหัสผ่านไว้ '
                    'ถ้าปิดหน้าต่างนี้แล้วต้องกดตั้งรหัสใหม่'
                ) % (self.base_url or '-', password, self.code or '-'),
                'type': 'warning',
                'sticky': True,
            },
        }

    def action_renew(self):
        """เปิดหน้าต่างต่ออายุ"""
        self.ensure_one()
        self._assert_manageable()
        return {
            'type': 'ir.actions.act_window',
            'name': 'ต่ออายุสัญญา',
            'res_model': 'saas.renew.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tenant_id': self.id},
        }

    def action_suspend(self):
        self._assert_manageable()
        self.write({'state': 'suspended'})
        self.push_license()
        return self._notify('ระงับการใช้งานแล้ว')

    def action_reactivate(self):
        self._assert_manageable()
        for rec in self:
            rec.state = rec._effective_state() if rec.expire_date else 'active'
            if rec.state in ('suspended', 'terminated'):
                rec.state = 'active'
        self.push_license()
        return self._notify('เปิดใช้งานอีกครั้งแล้ว')

    def action_terminate(self):
        """ยกเลิกสัญญา — ล็อกระบบแต่ยังไม่ลบฐานข้อมูล

        ไม่ลบ DB ทันทีโดยเจตนา เผื่อลูกค้ากลับมาต่อ หรือต้องส่งข้อมูลคืน
        การลบจริงต้องกดปุ่มลบแยกอีกครั้ง
        """
        self._assert_manageable()
        self.write({'state': 'terminated'})
        self.push_license()
        return self._notify('ยกเลิกสัญญาแล้ว — ฐานข้อมูลยังอยู่ กดปุ่มลบอีกครั้งหากต้องการลบถาวร')

    def action_drop_database(self):
        """ลบฐานข้อมูลถาวร — ทำได้เฉพาะที่ยกเลิกสัญญาแล้ว"""
        self.ensure_one()
        self._assert_manageable()
        if self.state != 'terminated':
            raise UserError(
                'ต้องยกเลิกสัญญาก่อนจึงจะลบฐานข้อมูลได้\n\n'
                'ขั้นตอนนี้ตั้งใจให้มีสองจังหวะ เพื่อกันการลบข้อมูลลูกค้าโดยพลาด')
        if not self.db_name:
            raise UserError('ไม่มีชื่อฐานข้อมูลให้ลบ')
        if not self._db_exists(self.db_name):
            self.db_name = False
            return self._notify('ไม่พบฐานข้อมูลนี้แล้ว — ล้างชื่อออกจากทะเบียนให้')
        _logger.warning('SaaS: ลบฐานข้อมูล %s ของ %s', self.db_name, self.name)
        self._drop_database(self.db_name)
        self.db_name = False
        return self._notify('ลบฐานข้อมูลเรียบร้อย')

    def action_open_tenant(self):
        self.ensure_one()
        if not self.base_url:
            raise UserError('ยังไม่ได้ตั้งที่อยู่เซิร์ฟเวอร์')
        return {'type': 'ir.actions.act_url', 'url': self.base_url, 'target': 'new'}

    def _notify(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'ศูนย์ควบคุมการเช่าระบบ', 'message': message,
                       'type': 'success', 'sticky': False},
        }

    # ------------------------------------------------------------------
    # งานตามเวลา
    # ------------------------------------------------------------------
    @api.model
    def _cron_check_subscriptions(self):
        """ตรวจวันหมดอายุทุกวัน แล้วเลื่อนสถานะ + เขียนลง DB ลูกค้า"""
        tenants = self.sudo().search([
            ('is_control_plane', '=', False),
            ('db_name', '!=', False),
            ('state', 'in', ['active', 'grace', 'expired']),
        ])
        for tenant in tenants:
            new_state = tenant._effective_state()
            if new_state != tenant.state:
                _logger.info('SaaS: %s เปลี่ยนสถานะ %s -> %s',
                             tenant.name, tenant.state, new_state)
                tenant.state = new_state
            try:
                tenant.push_license()
                tenant.action_refresh_usage()
            except Exception:
                # ลูกค้ารายเดียวมีปัญหา ต้องไม่ทำให้รายอื่นไม่ถูกตรวจ
                _logger.exception('SaaS: อัปเดตสัญญาของ %s ไม่สำเร็จ', tenant.name)
        return True


class _TenantEnv:
    """context manager เปิด Environment ไปยัง DB ของลูกค้า แล้ว commit ให้เมื่อจบ"""

    def __init__(self, db_name):
        self.db_name = db_name
        self.cr = None

    def __enter__(self):
        try:
            registry = odoo.modules.registry.Registry(self.db_name)
        except Exception as exc:
            raise UserError('เปิดฐานข้อมูล "%s" ไม่ได้: %s' % (self.db_name, exc))
        self.cr = registry.cursor()
        return api.Environment(self.cr, odoo.SUPERUSER_ID, {})

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.cr.rollback()
        else:
            self.cr.commit()
        self.cr.close()
        return False
