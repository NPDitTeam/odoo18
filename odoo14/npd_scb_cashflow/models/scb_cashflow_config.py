# -*- coding: utf-8 -*-
import base64
import re
import json
import logging
import time
from urllib.parse import quote

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SHEETS_SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly'
SHEETS_VALUES_URL = 'https://sheets.googleapis.com/v4/spreadsheets/%s/values'
DEFAULT_TOKEN_URI = 'https://oauth2.googleapis.com/token'


class GoogleSheetsError(Exception):
    """ข้อผิดพลาดจาก Google (ข้อความมี status เช่น PERMISSION_DENIED ให้ _friendly_sheet_error อ่าน)"""


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=')


class GoogleSheetsClient(object):
    """เรียก Google Sheets API (อ่านอย่างเดียว) ด้วย Service Account

    o14 ใช้ google-api-python-client แต่ใน container ของ o18 ต้อง pip install เอง
    และหายเมื่อสร้าง container ใหม่ จึงเซ็น JWT เองด้วย cryptography (Odoo มีอยู่แล้ว)
    """

    def __init__(self, info):
        self.info = info
        self._token = None
        self._token_exp = 0

    def _access_token(self):
        now = int(time.time())
        if self._token and now < self._token_exp - 60:
            return self._token
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        token_uri = self.info.get('token_uri') or DEFAULT_TOKEN_URI
        header = {'alg': 'RS256', 'typ': 'JWT'}
        if self.info.get('private_key_id'):
            header['kid'] = self.info['private_key_id']
        claims = {
            'iss': self.info.get('client_email'),
            'scope': SHEETS_SCOPE,
            'aud': token_uri,
            'iat': now,
            'exp': now + 3600,
        }
        signing_input = b'.'.join([
            _b64url(json.dumps(header, separators=(',', ':')).encode()),
            _b64url(json.dumps(claims, separators=(',', ':')).encode()),
        ])
        key = serialization.load_pem_private_key(
            (self.info.get('private_key') or '').encode(), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        assertion = b'.'.join([signing_input, _b64url(signature)]).decode()
        resp = requests.post(token_uri, data={
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': assertion,
        }, timeout=30)
        if resp.status_code != 200:
            raise GoogleSheetsError('%s %s' % (resp.status_code, resp.text[:1000]))
        data = resp.json()
        self._token = data['access_token']
        self._token_exp = now + int(data.get('expires_in') or 3600)
        return self._token

    def _get(self, url, params=None):
        resp = requests.get(url, params=params, timeout=60, headers={
            'Authorization': 'Bearer %s' % self._access_token()})
        if resp.status_code != 200:
            raise GoogleSheetsError('%s %s' % (resp.status_code, resp.text[:1000]))
        return resp.json()

    def get_values(self, spreadsheet_id, data_range):
        url = (SHEETS_VALUES_URL % quote(spreadsheet_id, safe='')) + '/' + quote(data_range, safe='')
        return self._get(url).get('values', []) or []

    def batch_get(self, spreadsheet_id, ranges):
        url = (SHEETS_VALUES_URL % quote(spreadsheet_id, safe='')) + ':batchGet'
        return self._get(url, [('ranges', r) for r in ranges]).get('valueRanges', []) or []


class ScbCashflowConfig(models.Model):
    _name = 'npd.scb.cashflow.config'
    _description = 'ตั้งค่ากระแสเงินสดธนาคาร'

    name = fields.Char('ชื่อ', default='SCB Cash Flow Settings', required=True)
    # ID ของสเปรดชีต = ส่วนที่อยู่ระหว่าง /d/ กับ /edit ใน URL
    spreadsheet_id = fields.Char(
        'Spreadsheet ID', required=True,
        default='1_7Zr-dtaMrBd_urcFdTmhYVE92MQNyG30mfIXFxgHV0',
        help='ส่วนที่อยู่ใน URL ระหว่าง /d/ และ /edit\n'
             'เช่น https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit')
    data_range = fields.Char('ช่วงข้อมูลสรุปรายวัน', default='A2:K', required=True,
                             help='ช่วงข้อมูลของแต่ละแท็บ (ไม่รวมหัวตาราง) เช่น A2:K\n'
                                  'ใช้ร่วมกันทั้ง 3 ธนาคาร (SCB / Kbank / กรุงไทย)')
    service_account_json = fields.Text(
        'Service Account JSON',
        help='วางเนื้อหาไฟล์ JSON ของ Service Account ทั้งไฟล์ที่นี่\n'
             'ดาวน์โหลดจาก Google Cloud Console > IAM & Admin > Service Accounts > Keys > Add key > JSON')
    service_account_email = fields.Char(
        'อีเมล Service Account', compute='_compute_service_account_email', store=False,
        help='แชร์ Google Sheet ให้กับอีเมลนี้ (สิทธิ์ Viewer)')
    auto_sync = fields.Boolean('ดึงสรุปรายวันอัตโนมัติ', default=True,
                               help='ให้ Scheduled Action ดึงข้อมูลอัตโนมัติหรือไม่')
    last_sync = fields.Datetime('ดึงสรุปรายวันล่าสุดเมื่อ', readonly=True)
    last_error = fields.Text('ข้อผิดพลาดล่าสุด (สรุปรายวัน)', readonly=True)

    # ------------------------------------------------------------------
    # แท็บ "รายการเดินบัญชี" (statement) — คนละชุดกับแท็บสรุปรายวันด้านบน
    # คอลัมน์: A เลขบัญชี | B ชื่อบัญชี | C ประเภท | D สกุลเงิน | E รหัสสาขา |
    #          F วันที่ | G เวลา | H Tr Code | I Tr Description | J Channel |
    #          K เลขที่เช็ค | L Withdrawal | M Deposit | N ยอดคงเหลือ | O รายละเอียด
    # ใช้เป็นข้อมูลอ้างอิงให้ระบบตรวจสอบการโอนจากสลิป (npd_scb_auto_payment)
    # ------------------------------------------------------------------
    statement_sheet_scb = fields.Char(
        'แท็บ Statement (SCB)', default='statement_SCB',
        help='ชื่อแท็บรายการเดินบัญชีของ SCB ในสเปรดชีตเดียวกัน\nเว้นว่าง = ไม่ดึงธนาคารนี้')
    statement_sheet_kbank = fields.Char(
        'แท็บ Statement (Kbank)', default='Statement_Kbank',
        help='ชื่อแท็บรายการเดินบัญชีของ Kbank\nเว้นว่าง = ไม่ดึงธนาคารนี้')
    statement_sheet_ktb = fields.Char(
        'แท็บ Statement (กรุงไทย)', default='',
        help='ชื่อแท็บรายการเดินบัญชีของกรุงไทย\nเว้นว่าง = ไม่ดึงธนาคารนี้')
    # ช่วงข้อมูลแยกต่อธนาคาร เพราะแต่ละธนาคาร export คอลัมน์ไม่เท่ากัน
    statement_range = fields.Char(
        'ช่วงข้อมูล (SCB)', default='A2:O',
        help='คอลัมน์ A ถึง O\n'
             'เลขบัญชี | ชื่อบัญชี | ประเภทบัญชี | สกุลเงิน | รหัสสาขา | วันที่ | เวลา |\n'
             'Tr Code | Tr Description | Channel | เลขที่เช็ค | Withdrawal | Deposit |\n'
             'ยอดคงเหลือ | รายละเอียด')
    statement_range_kbank = fields.Char(
        'ช่วงข้อมูล (Kbank)', default='A2:I',
        help='คอลัมน์ A ถึง I (คนละผังกับ SCB)\n'
             'วันที่ | เวลา | รายการ | ถอนเงิน | ฝากเงิน | ยอดคงเหลือ | ช่องทาง |\n'
             'รายละเอียด | บริษัท')
    statement_range_ktb = fields.Char(
        'ช่วงข้อมูล (กรุงไทย)', default='A2:O',
        help='ค่าเริ่มต้นใช้ผังเดียวกับ SCB (A ถึง O) '
             'ถ้าแท็บกรุงไทยคอลัมน์ไม่เหมือน SCB ต้องแก้โค้ดเพิ่มผังใหม่')
    statement_auto_sync = fields.Boolean(
        'ดึงรายการเดินบัญชีอัตโนมัติ', default=True,
        help='ให้ Scheduled Action ดึงรายการเดินบัญชีอัตโนมัติหรือไม่')
    statement_last_sync = fields.Datetime('ดึงรายการเดินบัญชีล่าสุดเมื่อ', readonly=True)
    statement_last_error = fields.Text('ข้อผิดพลาดล่าสุด (รายการเดินบัญชี)', readonly=True)
    statement_last_result = fields.Text(
        'ผลการดึงล่าสุด (รายธนาคาร)', readonly=True,
        help='สรุปว่าแต่ละแท็บดึงมาได้กี่แถว หรือถูกข้ามเพราะอะไร')

    @api.depends('service_account_json')
    def _compute_service_account_email(self):
        for rec in self:
            email = False
            if rec.service_account_json:
                try:
                    email = json.loads(rec.service_account_json).get('client_email')
                except Exception:
                    email = False
            rec.service_account_email = email

    @staticmethod
    def _extract_sheet_id(val):
        """รับได้ทั้ง ID ล้วน หรือ URL เต็มของ Google Sheet แล้วตัดเอาเฉพาะ ID"""
        val = (val or '').strip()
        m = re.search(r'/spreadsheets/d/([a-zA-Z0-9\-_]+)', val)
        return m.group(1) if m else val

    @api.onchange('spreadsheet_id')
    def _onchange_spreadsheet_id(self):
        if self.spreadsheet_id:
            self.spreadsheet_id = self._extract_sheet_id(self.spreadsheet_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('spreadsheet_id'):
                vals['spreadsheet_id'] = self._extract_sheet_id(vals['spreadsheet_id'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('spreadsheet_id'):
            vals['spreadsheet_id'] = self._extract_sheet_id(vals['spreadsheet_id'])
        return super().write(vals)

    @api.model
    def _get_config(self):
        """คืนค่ารายการตั้งค่า (singleton) สร้างใหม่ถ้ายังไม่มี"""
        config = self.search([], limit=1)
        if not config:
            config = self.create({'name': 'SCB Cash Flow Settings'})
        return config

    @api.model
    def action_open_config(self):
        config = self._get_config()
        return {
            'type': 'ir.actions.act_window',
            'name': _('ตั้งค่ากระแสเงินสดธนาคาร'),
            'res_model': 'npd.scb.cashflow.config',
            'view_mode': 'form',
            'res_id': config.id,
            'target': 'current',
        }

    @api.model
    def _get_sheets_service(self, config=None):
        """สร้างตัวเรียก Google Sheets จาก Service Account JSON ที่ตั้งค่าไว้

        ใช้ร่วมกันระหว่างการดึง "สรุปรายวัน" และ "รายการเดินบัญชี (statement)"
        คืน GoogleSheetsClient (get_values / batch_get)
        """
        config = config or self._get_config()
        if not config.service_account_json:
            raise UserError(_(
                "ยังไม่ได้ตั้งค่า Service Account JSON\n"
                "กรุณาไปที่ บัญชี > การกำหนดค่า > ตั้งค่ากระแสเงินสดธนาคาร "
                "แล้ววาง JSON key ก่อน"))
        if not config.spreadsheet_id:
            raise UserError(_("กรุณาระบุ Spreadsheet ID ในหน้าตั้งค่าก่อน"))

        try:
            info = json.loads(config.service_account_json)
        except Exception:
            raise UserError(_("Service Account JSON ไม่ถูกต้อง (invalid JSON)"))
        if not info.get('client_email') or not info.get('private_key'):
            raise UserError(_("Service Account JSON ไม่มี client_email หรือ private_key"))
        return GoogleSheetsClient(info)

    def action_sync_statements_now(self):
        """ปุ่ม 'ดึงรายการเดินบัญชี' — อ่านแท็บ statement ทุกธนาคารที่ตั้งค่าไว้"""
        self.ensure_one()
        self.env['npd.scb.bank.statement']._sync_statements()
        self.invalidate_recordset()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('รายการเดินบัญชีธนาคาร'),
                'message': self.statement_last_result or _('ดึงข้อมูลเรียบร้อย'),
                'type': 'warning' if self.statement_last_error else 'success',
                'sticky': bool(self.statement_last_error),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_sync_now(self):
        self.ensure_one()
        count = self.env['npd.scb.cashflow']._sync_from_sheet()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('กระแสเงินสดธนาคาร'),
                'message': _('ดึงข้อมูลสำเร็จ %s แถว (ทุกธนาคาร).') % count,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
