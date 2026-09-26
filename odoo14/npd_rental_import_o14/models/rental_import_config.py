# -*- coding: utf-8 -*-
"""การเชื่อมต่อไปฐาน ERP ฝั่ง Odoo 14

ฝั่ง 14 แยกฐานต่อบริษัท (Intertrading / Bangkok / S Group) ฝั่ง 18 รวมเป็น
ฐานเดียวหลายบริษัท จึงต้องมีรายการเชื่อมต่อหนึ่งแถวต่อหนึ่งฐาน แล้วบอกว่า
ฐานนั้นตรงกับบริษัทไหนของฝั่ง 18
"""
import logging
import xmlrpc.client

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RentalImportConfig(models.Model):
    _name = 'npd.rental.import.config'
    _description = 'การเชื่อมต่อฐาน ERP Odoo 14'
    _order = 'sequence, id'

    name = fields.Char(string='ชื่อการเชื่อมต่อ', required=True)
    sequence = fields.Integer(default=10)
    url = fields.Char(string='ที่อยู่เซิร์ฟเวอร์', required=True,
                      default='https://npderp.com')
    db_name = fields.Char(string='ชื่อฐานข้อมูล', required=True)
    username = fields.Char(string='ผู้ใช้', required=True)
    password = fields.Char(string='รหัสผ่าน', required=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัทฝั่ง 18', required=True,
        help='ฐานนี้ตรงกับบริษัทไหนของฝั่ง 18 — ใบและสินค้าที่ยกมาจะลงบริษัทนี้')
    active = fields.Boolean(default=True)

    uid_cache = fields.Integer(string='uid ฝั่ง 14', readonly=True, copy=False)
    last_result = fields.Text(string='ผลการทำงานล่าสุด', readonly=True, copy=False)
    last_run = fields.Datetime(string='ทำงานล่าสุดเมื่อ', readonly=True, copy=False)

    # ------------------------------------------------------------------
    def _login(self, force=False):
        self.ensure_one()
        if self.uid_cache and not force:
            return self.uid_cache
        try:
            common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % self.url)
            uid = common.authenticate(self.db_name, self.username,
                                      self.password, {})
        except Exception as error:
            raise UserError(
                _('ต่อไปฝั่ง 14 ไม่ได้ (%s / %s): %s')
                % (self.url, self.db_name, error))
        if not uid:
            raise UserError(
                _('ล็อกอินฝั่ง 14 ไม่ผ่าน — ตรวจชื่อผู้ใช้/รหัสผ่านของฐาน %s')
                % self.db_name)
        self.sudo().uid_cache = uid
        return uid

    def execute_kw(self, model, method, args, kwargs=None):
        """เรียกเมธอดบนฝั่ง 14 — uid หมดอายุแล้วล็อกอินใหม่ให้เองหนึ่งครั้ง"""
        self.ensure_one()
        kwargs = kwargs or {}
        uid = self._login()
        proxy = xmlrpc.client.ServerProxy('%s/xmlrpc/2/object' % self.url)
        try:
            return proxy.execute_kw(self.db_name, uid, self.password,
                                    model, method, args, kwargs)
        except xmlrpc.client.Fault:
            uid = self._login(force=True)
            return proxy.execute_kw(self.db_name, uid, self.password,
                                    model, method, args, kwargs)

    def search_read_all(self, model, domain, fields_list, batch=200):
        """อ่านทีละชุด ไม่ดึงมากองในหน่วยความจำทีเดียว"""
        self.ensure_one()
        offset, out = 0, []
        while True:
            rows = self.execute_kw(
                model, 'search_read', [domain, fields_list],
                {'offset': offset, 'limit': batch, 'order': 'id'})
            if not rows:
                break
            out.extend(rows)
            offset += len(rows)
            if len(rows) < batch:
                break
        return out

    # ------------------------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        count = self.execute_kw('sale.order', 'search_count', [[
            ('npd_so_type', '=', 'rent'),
            ('renewal_bill_status', '=', 'renew'),
        ]])
        message = _('ต่อได้ — ฐาน %s มีใบเช่าต่ออายุ %s ใบ') % (self.db_name, count)
        self.sudo().write({'last_result': message,
                           'last_run': fields.Datetime.now()})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('ทดสอบการเชื่อมต่อ'), 'message': message,
                       'type': 'success', 'sticky': False},
        }

    def _note(self, text):
        """เก็บผลไว้ให้คนกดดูย้อนหลังได้ ไม่ใช่หายไปกับ log"""
        self.ensure_one()
        _logger.info('[RENTAL IMPORT %s] %s', self.db_name, text)
        self.sudo().write({'last_result': text,
                           'last_run': fields.Datetime.now()})

    # ------------------------------------------------------------------
    @api.model
    def _o18_company_ids(self):
        return self.env['res.company'].sudo().search([]).ids
