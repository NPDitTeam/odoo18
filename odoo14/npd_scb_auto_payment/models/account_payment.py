# -*- coding: utf-8 -*-
u"""ตรวจสอบ "การโอนเงินจริง" ของใบรับชำระ (account.payment)

แนวคิด (แทนของเดิมที่ยึดใบแจ้งหนี้ + สร้างใบรับชำระให้อัตโนมัติ):

1. พนักงานสร้างใบรับชำระเองตามปกติ แล้วแนบ "สลิปโอนเงิน" ไว้ในเอกสารแนบ
2. AI (Gemini ตัวเดียวกับปุ่ม "ใช้วันที่จากสลิป") อ่านสลิป -> ได้ วันที่ / จำนวนเงิน /
   ชื่อผู้โอน
3. เอาค่าที่ได้ไปจับคู่กับ "รายการเดินบัญชีจริงของธนาคาร" (npd.scb.bank.statement
   ที่ดึงจากแท็บ statement_* ใน Google Sheet)
4. ข้อมูลจากธนาคารมาช้ากว่าจริง ~1 วัน จึงตรวจสอบเมื่อ "วันที่ในใบรับชำระ" ผ่านไปแล้ว
   อย่างน้อย 1 วัน (โอนวันนี้ -> ตรวจพรุ่งนี้)
5. ผลลัพธ์แสดงบนหน้ารับชำระ: โอนสำเร็จ / ไม่สำเร็จ (พร้อมเหตุผล)

เงื่อนไขที่ต้องตรงกัน: ชื่อบริษัทผู้โอน (ไทยหรืออังกฤษก็ได้) + จำนวนเงิน + วันที่
"""
import json
import logging
import re
from datetime import timedelta

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

# Odoo 18 ไม่มีสถานะ 'posted' ของใบรับชำระแล้ว ลงบันทึกแล้ว = in_process (รอกระทบยอด) / paid
POSTED_STATES = ['in_process', 'paid']

# ไฟล์แนบที่ส่งให้ AI อ่านได้ (สลิปมีทั้งรูปถ่ายและ PDF จากธนาคาร)
SLIP_MIMETYPES = (
    'image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp',
    'application/pdf',
)

# ค่าเริ่มต้นของการตั้งค่า (ทับได้ที่ ตรวจสอบการโอนเงิน > ตั้งค่า)
DEFAULTS = {
    'verify_enabled': True,
    'verify_lag_days': 1,
    # เลือก statement ที่จะเทียบ "ตามสมุดรายวันของใบรับชำระ"
    #   สมุดรายวันที่มีคำว่า 'ค่าประกัน' -> เงินเข้าบัญชี Kbank
    #   สมุดรายวันอื่น                  -> เงินเข้าบัญชี SCB
    'verify_bank_default': 'scb',
    'verify_bank_deposit': 'kbank',
    'verify_deposit_journal_keyword': u'ค่าประกัน',
    # ...แต่เป็นแค่ "ที่น่าจะใช่" ลูกค้าโอนเข้าบัญชีไหนก็ได้ ถ้าหาในธนาคารที่
    # คาดไว้ไม่เจอ ให้ขยายไปหาอีกธนาคารด้วย (ไม่งั้นจะขึ้นไม่สำเร็จทั้งที่เงินเข้าแล้ว)
    'verify_cross_bank_fallback': True,
    # Google Sheet รวม statement ของทุกบริษัทในเครือ ถ้าลูกค้าโอนเข้าบัญชี
    # บริษัทอื่น ให้แยกเป็นสถานะ "สำเร็จ แต่โอนคนละบริษัท" ไม่ปนกับ "โอนสำเร็จ"
    'verify_check_own_account': True,
    'verify_own_account_names': '',    # เว้นว่าง = ใช้ชื่อบริษัทใน Odoo
    'verify_own_account_numbers': '',  # ตั้งไว้จะแม่นกว่าเทียบชื่อ
    # สมุดรายวันที่ "ไม่มีเงินโอนเข้าจริง" (ตัดหนี้ในระบบ) -> ข้ามการตรวจไปเลย
    'verify_skip_journal_keywords': u'ลดหนี้',
    # วิธีชำระที่ "ไม่มีเงินเข้าบัญชีจริง" เช่น หักจากเงินประกันที่วางไว้ก่อนแล้ว
    # -> ข้ามเช่นกัน (ดูเฉพาะใบที่ใช้วิธีชำระเดียว)
    'verify_skip_method_keywords': u'หักเงินประกัน',
    # คำในเลขอ้างอิงของสลิปที่จะข้ามการตรวจ — ตอนนี้ว่างไว้
    #
    # เดิมตั้งเป็น 'REF' เพื่อข้ามสลิปจ่ายบิล เพราะ statement ฝั่ง SCB มีแต่แถว
    # สรุปยอดรวมรายวัน (channel BPAY เวลา 22:59 รายละเอียด "รับชำระค่าสินค้า
    # และบริการ CrossBank") ซึ่งไม่มีชื่อผู้โอนให้เทียบ
    # ตอนนี้ในชีตเพิ่มรายการแยกรายคนแล้ว (channel CBBP มีชื่อผู้โอนครบ ไม่มี
    # ยอดคงเหลือ) จึงเทียบได้ตามปกติ ไม่ต้องข้ามอีก
    'verify_skip_slip_keywords': u'',
    # ชื่อไฟล์ที่บอกได้เลยว่าไม่ใช่สลิป (พนักงานมักแนบ 50 ทวิ / ใบกำกับภาษี ปนมา)
    # ใช้กรองก่อนเรียก AI จะได้ไม่เปลืองโควตา ส่วนไฟล์ที่ชื่อไม่บอกอะไร
    # ให้ AI ดูรูปแล้วตัดสินจาก is_transfer_slip อีกชั้น
    'verify_skip_file_keywords': u'ทวิ,ภงด,ภ.ง.ด,หัก ณ ที่จ่าย,wht,'
                                 u'ใบกำกับ,ใบเสร็จ,ใบแจ้งหนี้,ใบวางบิล,invoice',
    'verify_amount_tolerance': 0.0,   # 0 = จำนวนเงินต้องตรงกันเป๊ะระดับสตางค์
    'verify_date_tolerance': 0,
    'verify_name_threshold': 0.6,
    'verify_ai_name_fallback': True,
    'verify_allow_no_name': True,
    'verify_batch_limit': 100,
    # เวลาบนสลิปเทียบกับเวลาที่ธนาคารบันทึก คลาดกันได้กี่นาที
    # ใช้ยืนยันกรณีที่ชื่อผู้โอนถอดเป็นอังกฤษแบบไม่เป็นมาตรฐานจนเทียบไม่ได้
    'verify_time_tolerance_min': 5,
    'verify_second_pass': True,
    'verify_second_pass_days': 3,
    'verify_retry_failed': 3,
}


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # ------------------------------------------------------------------
    # ผลการตรวจสอบการโอน
    # ------------------------------------------------------------------
    scb_verify_state = fields.Selection([
        ('to_check', u'รอตรวจสอบ'),
        ('no_slip', u'ยังไม่แนบสลิป'),
        ('waiting', u'รอข้อมูลจากธนาคาร'),
        ('success', u'โอนสำเร็จ'),
        # เงินเข้าจริง จับคู่ได้ครบ แต่เข้าบัญชีของบริษัทอื่นในเครือ
        # ไม่ใช่ "ไม่สำเร็จ" (เงินมาแล้ว) และไม่ใช่ "สำเร็จ" (บัญชีบริษัทเราไม่ได้รับ)
        ('other_company', u'สำเร็จ แต่โอนคนละบริษัท'),
        ('failed', u'ไม่สำเร็จ'),
        ('skipped', u'ไม่ต้องตรวจสอบ'),
    ], string=u"สถานะการโอน (ธนาคาร)", default='to_check', copy=False, index=True,
        readonly=True,
        help=u"ผลการจับคู่สลิปที่แนบไว้ กับรายการเดินบัญชีจริงของธนาคาร")
    scb_verify_bank = fields.Selection([
        ('scb', 'SCB'),
        ('kbank', 'Kbank'),
        ('ktb', u'กรุงไทย'),
    ], string=u"ธนาคารที่ตรวจ", compute='_compute_scb_verify_bank', store=True,
        help=u"statement ของธนาคารที่ระบบใช้เทียบกับใบรับชำระใบนี้ "
             u"— เลือกจากสมุดรายวัน (ตั้งกฎได้ที่หน้าตั้งค่า)")
    scb_verify_summary = fields.Char(
        string=u"ผลตรวจ", readonly=True, copy=False,
        help=u"ข้อความสั้นที่ทุกคนเห็น — ไม่บอกเกณฑ์การตรวจ")
    # รายละเอียดเต็มบอกว่าระบบเทียบอะไรบ้างและได้คะแนนเท่าไร ถ้าพนักงานทั่วไปเห็น
    # จะรู้ว่าต้องทำสลิปให้ "ผ่าน" อย่างไร จึงจำกัดให้เฉพาะผู้จัดการบัญชี
    scb_verify_reason = fields.Text(
        string=u"รายละเอียดผลตรวจ (ภายใน)", readonly=True, copy=False,
        groups="account.group_account_manager")
    scb_verify_datetime = fields.Datetime(
        string=u"ตรวจสอบเมื่อ", readonly=True, copy=False)
    scb_verify_attempts = fields.Integer(
        string=u"จำนวนครั้งที่ตรวจแล้วไม่สำเร็จ", readonly=True, copy=False, default=0,
        help=u"นับเฉพาะครั้งที่ผลออกมา 'ไม่สำเร็จ' — ระบบจะลองซ้ำให้อัตโนมัติจนครบเพดาน "
             u"ที่ตั้งไว้ (เผื่อรายการเดินบัญชีของวันนั้นเข้ามาไม่ครบตอนตรวจรอบแรก) "
             u"ครบแล้วจะหยุดและรอให้คนตรวจเอง\n"
             u"สถานะ 'รอข้อมูลจากธนาคาร' ไม่นับ และจะถูกตรวจซ้ำเรื่อย ๆ")
    scb_statement_id = fields.Many2one(
        'npd.scb.bank.statement', string=u"รายการเดินบัญชีที่จับคู่ได้",
        readonly=True, copy=False, ondelete='set null', index=True,
        help=u"ใช้เมื่อมีสลิปใบเดียว — ถ้าแนบหลายสลิป ดูรายการที่จับคู่ได้ของแต่ละใบ "
             u"ในตาราง \"ผลตรวจรายสลิป\"")
    scb_slip_ids = fields.One2many(
        'npd.scb.payment.slip', 'payment_id', string=u"ผลตรวจรายสลิป",
        readonly=True, copy=False,
        help=u"ลูกค้ามักโอนไม่ครบในครั้งเดียว พนักงานจึงแนบหลายสลิป "
             u"ระบบอ่านและจับคู่ให้ทีละไฟล์")

    # ---- ค่าที่ AI อ่านได้จากสลิป (เก็บไว้ไม่ต้องเรียก AI ซ้ำตอนตรวจรอบถัดไป) ----
    scb_slip_read = fields.Boolean(
        string=u"อ่านสลิปแล้ว", readonly=True, copy=False, default=False)
    scb_slip_date = fields.Date(string=u"วันที่จากสลิป", readonly=True, copy=False)
    scb_slip_amount = fields.Float(
        string=u"จำนวนเงินจากสลิป", digits=(16, 2), readonly=True, copy=False)
    scb_slip_sender = fields.Char(string=u"ชื่อผู้โอน (จากสลิป)", readonly=True, copy=False)
    scb_slip_sender_acc = fields.Char(string=u"บัญชีผู้โอน (จากสลิป)", readonly=True, copy=False)
    scb_slip_ref = fields.Char(string=u"เลขอ้างอิงจากสลิป", readonly=True, copy=False)
    # หมายเหตุ: ข้อมูลดิบจาก AI ย้ายไปเก็บรายสลิปที่ npd.scb.payment.slip.raw แล้ว
    # เพราะใบรับชำระใบเดียวมีได้หลายสลิป

    # ------------------------------------------------------------------
    # การตั้งค่า
    # ------------------------------------------------------------------
    @api.model
    def _scb_param(self, key):
        u"""อ่านค่าตั้งค่าจาก ir.config_parameter พร้อม fallback เป็นค่าเริ่มต้น"""
        default = DEFAULTS[key]
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'npd_scb_auto_payment.%s' % key)
        if raw in (None, False, ''):
            return default
        if isinstance(default, bool):
            return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
        try:
            return type(default)(raw)
        except (ValueError, TypeError):
            return default

    @api.model
    def _scb_verify_start_date(self):
        u"""วันที่เริ่มตรวจสอบ — ยึด "วันที่ในใบรับชำระ"

        ใบรับชำระที่ลงวันที่ก่อนวันนี้ จะไม่ถูกดึงมาตรวจอัตโนมัติ (กันระบบไล่ย้อนหลัง
        ทั้งฐานข้อมูลจนเปลืองโควตา AI) แต่ยังกดปุ่ม "ตรวจสอบการโอน" เองได้
        คืน None = ไม่จำกัด (ตรวจทุกใบ)
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'npd_scb_auto_payment.verify_start_date')
        if not raw:
            return None
        try:
            return fields.Date.to_date(str(raw)[:10])
        except (ValueError, TypeError):
            return None

    @api.model
    def _scb_skip_keywords(self):
        u"""คำในชื่อสมุดรายวันที่แปลว่า "ไม่มีเงินโอนเข้าจริง" -> ไม่ต้องตรวจ"""
        raw = self._scb_param('verify_skip_journal_keywords') or ''
        return [k.strip() for k in raw.split(',') if k.strip()]

    @api.model
    def _scb_slip_skip_reason(self, line):
        u"""คืน (คำที่เจอ, ค่าที่เจอคำนั้น) ถ้าสลิปใบนี้เป็นการ "จ่ายบิล" ที่ไม่ต้องตรวจ

        สลิปจ่ายบิลจะมีเลขอ้างอิงอย่าง "REF001" และฝั่งธนาคารบันทึกแค่
        "รับชำระค่าสินค้าและบริการ" โดยไม่มีชื่อผู้โอน — เทียบชื่อไม่ได้อยู่แล้ว
        ดูเฉพาะช่องเลขอ้างอิง ไม่สแกนทั้งก้อน เพื่อไม่ให้ชื่อบริษัทที่บังเอิญมีคำนี้
        ถูกข้ามไปด้วย
        """
        raw_keywords = self._scb_param('verify_skip_slip_keywords') or ''
        keywords = [k.strip() for k in raw_keywords.split(',') if k.strip()]
        if not keywords:
            return '', ''
        refs = [line.slip_ref or '']
        if line.raw:
            try:
                data = json.loads(line.raw) or {}
                refs += [str(data.get('bill_ref') or ''), str(data.get('reference') or '')]
            except (ValueError, TypeError):
                pass
        for value in refs:
            for keyword in keywords:
                if keyword.lower() in value.lower():
                    return keyword, value
        return '', ''

    def _scb_skip_reason(self):
        u"""คืนคำที่ทำให้ใบนี้ถูกข้าม หรือ '' ถ้าต้องตรวจตามปกติ

        เช่น "สมุดรายวันรับชำระลดหนี้" = การตัดหนี้ในระบบ ไม่ได้รับโอนเงินจริง
        statement ของธนาคารจึงไม่มีทางมีรายการนี้ ตรวจไปก็ขึ้น "ไม่สำเร็จ" เปล่า ๆ
        """
        self.ensure_one()
        journal_name = self.journal_id.name or ''
        for keyword in self._scb_skip_keywords():
            if keyword in journal_name:
                return keyword
        return ''

    def _scb_skip_method_reason(self):
        u"""คืนชื่อวิธีชำระ ถ้าใบนี้ไม่มีเงินโอนเข้าบัญชีจริง จึงไม่ต้องตรวจ

        เช่น "หักเงินประกันค่าเช่า" คือการหักจากเงินประกันที่ลูกค้าวางไว้ก่อนแล้ว
        ไม่มีเงินโอนเข้าบัญชีธนาคารในวันนั้นสักบาท statement จึงไม่มีทางมีรายการ
        ให้เทียบ ตรวจไปก็ขึ้น "ไม่สำเร็จ" เปล่า ๆ

        ดูเฉพาะใบที่ใช้วิธีชำระเดียว (payment_method_one_id) ส่วนใบที่แยกหลาย
        วิธีชำระยังต้องตรวจ เพราะมีส่วนที่เป็นเงินโอนจริงปนอยู่ด้วย
        """
        self.ensure_one()
        raw = self._scb_param('verify_skip_method_keywords') or ''
        keywords = [k.strip() for k in raw.split(',') if k.strip()]
        if not keywords or getattr(self, 'is_payment_multi', False):
            return ''
        method = getattr(self, 'payment_method_one_id', False)
        name = (method.name or '') if method else ''
        for keyword in keywords:
            if keyword in name:
                return name
        return ''

    @api.depends('journal_id', 'payment_type', 'partner_type')
    def _compute_scb_verify_bank(self):
        u"""ธนาคารที่ใช้เทียบ — เลือกจาก "สมุดรายวัน" ของใบรับชำระ

        เงินค่าประกันเข้าคนละบัญชีกับค่าเช่า/ค่าอื่น ๆ จึงต้องดู statement คนละแท็บ
          • สมุดรายวันที่ชื่อมีคำว่า 'ค่าประกัน'  -> Statement_Kbank
          • สมุดรายวันอื่น                        -> statement_SCB
        (คำที่ใช้ตรวจและธนาคารปลายทางปรับได้ที่หน้าตั้งค่า)

        อ่านค่าตั้งค่าครั้งเดียวนอกลูป เพราะ compute ทำงานทีละหลายเรคคอร์ด
        """
        keyword = (self._scb_param('verify_deposit_journal_keyword') or '').strip()
        deposit_bank = self._scb_param('verify_bank_deposit')
        default_bank = self._scb_param('verify_bank_default')
        skip_words = self._scb_skip_keywords()
        for payment in self:
            journal_name = payment.journal_id.name or ''
            if (payment.payment_type != 'inbound'
                    or payment.partner_type != 'customer'
                    or any(w in journal_name for w in skip_words)):
                # สมุดรายวันที่ไม่มีเงินโอนเข้าจริง -> ไม่มีธนาคารให้เทียบ
                payment.scb_verify_bank = False
                continue
            payment.scb_verify_bank = (
                deposit_bank if (keyword and keyword in journal_name) else default_bank)

    def _scb_verify_sources(self):
        u"""แท็บ statement ที่ใช้เทียบกับใบรับชำระใบนี้"""
        self.ensure_one()
        return [self.scb_verify_bank] if self.scb_verify_bank else []

    # ------------------------------------------------------------------
    # เอกสารแนบ (สลิป)
    # ------------------------------------------------------------------
    def _scb_get_slip_attachments(self):
        u"""ไฟล์สลิปที่แนบกับใบรับชำระนี้ (ทั้งแนบตรง และแนบผ่าน chatter)"""
        self.ensure_one()
        attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'account.payment'),
            ('res_id', '=', self.id),
        ])
        if self.message_ids:
            attachments |= self.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'mail.message'),
                ('res_id', 'in', self.message_ids.ids),
            ])
        return attachments.filtered(lambda a: a.mimetype in SLIP_MIMETYPES and a.datas)

    # ------------------------------------------------------------------
    # เรียก Gemini (ตัวเดียวกับปุ่ม "ใช้วันที่จากสลิป")
    # ------------------------------------------------------------------
    # gemini-2.5-flash นับ "thinking tokens" รวมใน maxOutputTokens ด้วย
    # ถ้าตั้งน้อยเกินไป JSON จะถูกตัดกลางคัน (เจอจริงในรอบสอง: '{"match_no": -1, ...' ค้าง)
    def _scb_gemini_call(self, parts, max_tokens=4096):
        u"""ยิงคำขอไป Gemini แล้วคืน dict ที่ parse จาก JSON ที่ตอบกลับมา"""
        api_key = self._get_gemini_api_key()
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        url = "%s?key=%s" % (GEMINI_API_URL, api_key)
        try:
            response = requests.post(
                url, headers={"content-type": "application/json"},
                json=payload, timeout=90)
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.Timeout:
            raise UserError(_(u"เรียก Gemini API ไม่ทันเวลา (timeout) กรุณาลองใหม่"))
        except requests.exceptions.ConnectionError:
            raise UserError(_(u"เชื่อมต่อ Gemini API ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ต"))
        except requests.exceptions.HTTPError as e:
            msg = str(e)
            try:
                msg = e.response.json().get('error', {}).get('message', msg)
            except Exception:  # noqa: BLE001
                pass
            raise UserError(_(u"Gemini API Error: %s") % msg)
        except Exception as e:  # noqa: BLE001
            raise UserError(_(u"เรียก Gemini API ไม่สำเร็จ: %s") % e)

        for cand in result.get('candidates', []):
            for part in cand.get('content', {}).get('parts', []):
                text = part.get('text') or ''
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    _logger.warning("SCB verify: Gemini ตอบไม่ใช่ JSON: %s", text[:500])
                    continue
                # บางครั้ง (เอกสารหลายรายการในรูปเดียว) Gemini ตอบเป็น array
                # ของ object แทนที่จะเป็น object เดียว — หยิบตัวแรกที่ใช้ได้
                if isinstance(data, list):
                    data = next((d for d in data if isinstance(d, dict)), None)
                    if data is None:
                        _logger.warning(
                            "SCB verify: Gemini ตอบเป็น list ที่ไม่มี object: %s",
                            text[:500])
                        continue
                if isinstance(data, dict):
                    return data
                _logger.warning("SCB verify: Gemini ตอบชนิดข้อมูลที่ใช้ไม่ได้: %s",
                                text[:500])
        return {}

    def _scb_slip_prompt(self):
        u"""คำสั่งให้ AI อ่านสลิป — ครอบคลุมสลิปหลายรูปแบบที่ลูกค้าใช้จริง

        รูปแบบที่ทดสอบแล้ว: SCB Payment Advice (ใบแจ้งการชำระเงิน), KBIZ,
        K PLUS (K+), Kept by krungsri, รายงาน IPP / INTERBANK TRANSFER ของกสิกร
        (ทั้งไฟล์ต้นฉบับและสแกนหมุน 90°), Bangkok Bank, ttb, LH Bank,
        MyMo by GSB, ธ.ก.ส. และรูปถ่ายจอมือถือ

        หลักคิดสำคัญ: ค่าที่อ่านได้จะถูกเอาไปเทียบกับ "รายการเดินบัญชีฝั่งผู้รับ"
        จึงต้องได้ (1) วันที่เงินเข้าบัญชีผู้รับ (2) ยอดที่เข้าบัญชีจริง
        (3) ชื่อผู้โอน — ไม่ใช่ชื่อผู้รับ
        """
        our_names = u''.join(
            u"     - %s\n" % n for n in self._get_company_name_candidates() if n)
        prompt = (
            u"คุณเป็นผู้เชี่ยวชาญอ่านสลิปโอนเงิน / ใบแจ้งการชำระเงิน (Payment Advice) / "
            u"รายงานการโอนเงินของธนาคาร ทั้งภาษาไทยและภาษาอังกฤษ\n"
            u"เอกสารอาจเป็นรูปถ่ายจอมือถือ (เอียง/สะท้อนแสง/จอแตก), ไฟล์สแกน, "
            u"หรือ PDF และ **อาจถูกหมุน 90 องศา** — ให้หมุนอ่านเองจนอ่านออก\n"
            u"อ่านแล้วตอบเป็น JSON เท่านั้น\n\n"

            u"########## 1) วันที่ ##########\n"
            u"ค่าที่ต้องการคือ **วันที่เงินเข้าบัญชีผู้รับ** เพราะจะเอาไปเทียบกับ\n"
            u"รายการเดินบัญชีของผู้รับ ไม่ใช่วันที่ผู้โอนกดโอน\n"
            u"ลำดับความสำคัญ:\n"
            u"  (ก) 'วันที่เงินเข้าบัญชี' / 'Received Date' / 'วันที่เงินถึงปลายทาง' / "
            u"'วันที่มีผล' / 'Value Date'  ← ใช้ก่อนเสมอถ้ามี\n"
            u"  (ข) 'วันที่ทำรายการ' / 'Transaction Date' / 'วันที่ทำรายการโอน'\n"
            u"  (ค) วันที่ใต้หัวข้อผลลัพธ์ เช่น 'โอนเงินสำเร็จ' / 'Transfer Completed' / "
            u"'ทำรายการสำเร็จ' / 'จ่ายบิลสำเร็จ' / 'รายการชำระบิลสำเร็จ' / 'สำเร็จ' / "
            u"'Transaction successful'\n"
            u"  (ง) 'วันที่หักบัญชี' / 'Deducted Date' — ใช้เป็นตัวสุดท้าย\n"
            u"**สำคัญ:** ถ้าเอกสารมีหลายวันที่ที่ไม่ตรงกัน (เช่นรายงาน IPP ที่ "
            u"'วันที่หักบัญชี 26-ก.ค.-2569' แต่ 'วันที่มีผล 27-ก.ค.-2569') "
            u"ให้ใส่ **ทุกวันที่ที่เป็นไปได้** ลงใน date_candidates โดยเรียง "
            u"วันที่เงินเข้าบัญชีผู้รับไว้ก่อน\n"
            u"ห้ามใช้: 'อัปเดตล่าสุด / Last Updated', 'วันที่พิมพ์', "
            u"'วันที่ - เวลา' ท้ายรายงาน, 'รายการมีผลตั้งแต่วันที่...ถึงวันที่' (ช่วงค้นหา)\n"
            u"ห้ามเอาตัวเลขจาก เวลา / เลขที่รายการ / จำนวนเงิน / เลขบัญชี "
            u"มาปนเป็นวัน-เดือน-ปีเด็ดขาด\n"
            u"แปลงเป็น DD/MM/YYYY (ค.ศ. 4 หลัก) เสมอ รองรับรูปแบบเหล่านี้:\n"
            u"  '27/07/2026' | '27 ก.ค. 2569' | '27 ก.ค. 69' | '27 ก.ค. 2026' |\n"
            u"  '25-ก.ค.-2569' | '25 Jul 26' | '13 Jun 26 11:45 AM' | "
            u"'24 ก.ค. 2569 08:44:43'\n"
            u"  - ตัดเวลาทิ้งเสมอจากช่อง date ('11:45 AM', '13.23 น.', ':44')\n"
            u"    **แต่ให้ตอบเวลาแยกไว้ในช่อง time ด้วย** รูปแบบ 24 ชั่วโมง 'HH:MM'\n"
            u"    (เวลาของวันที่ที่เลือกตามข้อ ก-ง เช่น '4 ส.ค. 69 08:45 น.' -> '08:45',\n"
            u"     '13:15 น.' -> '13:15', '11:45 AM' -> '11:45', '1:05 PM' -> '13:05')\n"
            u"    ถ้าไม่มีเวลาในสลิป ให้ตอบค่าว่าง\n"
            u"  - เดือนอังกฤษ (Jan..Dec) หรือไทย (ม.ค...ธ.ค. / มกราคม..ธันวาคม) -> 01-12\n"
            u"  - ปี 2 หลัก: ลอง 2000+YY ก่อน ถ้าเป็นอนาคตให้ตีเป็น พ.ศ. = (2500+YY)-543\n"
            u"    เช่น '69' -> 2569 พ.ศ. -> 2026 ค.ศ.  |  '26' -> 2026 ค.ศ.\n"
            u"  - ปี 4 หลัก >= 2500 เป็น พ.ศ. ให้ลบ 543 (2569 -> 2026)\n"
            u"  - ระวังสลิป ttb ที่เขียน 'เดือนไทย + ปี ค.ศ.' เช่น '27 ก.ค. 2026' "
            u"(ปีเป็น ค.ศ. อยู่แล้ว ห้ามลบ 543 ซ้ำ)\n\n"

            u"########## 2) จำนวนเงิน ##########\n"
            u"ค่าที่ต้องการคือ **ยอดที่เข้าบัญชีผู้รับจริง**\n"
            u"  - ปกติคือ 'จำนวนเงิน' / 'Amount' / 'จำนวนเงินทำรายการ' / "
            u"'จำนวนเงินรวมทั้งหมด' / 'ยอดรวมทั้งหมด' / 'Grand Total Amount'\n"
            u"  - **ค่าธรรมเนียมที่ผู้โอนเป็นคนจ่าย ไม่ต้องหักออกจากยอด** เช่น ttb "
            u"'ค่าธรรมเนียม (ผู้สั่งจ่าย) 10.00' -> ผู้รับได้เต็มจำนวน\n"
            u"  - ตอบเป็นตัวเลขล้วน ไม่มีคอมม่า ไม่มีสกุลเงิน เช่น 21550.00\n"
            u"  - ใส่ทุกยอดที่เป็นไปได้ลงใน amount_candidates (เรียงยอดที่มั่นใจสุดก่อน)\n"
            u"**ห้ามหยิบตัวเลขเหล่านี้มาเป็นจำนวนเงิน:**\n"
            u"  ค่าธรรมเนียม, ยอดคงเหลือ, ภาษีหัก ณ ที่จ่าย / ยอดภาษีที่ถูกหัก, "
            u"ยอดใบแจ้งหนี้ก่อน/หลัง VAT, อัตราภาษี, เลขบัญชี, เลขอ้างอิง, "
            u"เลข Biller ID / Tax ID, **ตัวเลขในโฆษณาท้ายสลิป** "
            u"(เช่น LH Bank มี 'ดอกเบี้ย 8.88% ต่อปี' — ไม่เกี่ยวกับรายการนี้)\n"
            u"รายงาน IPP / INTERBANK TRANSFER ของกสิกร: ให้ใช้คอลัมน์ 'จำนวนเงิน' "
            u"ของบรรทัดรายการ (= 'รวมจำนวนเงินทั้งหมด') ไม่ใช่ 'ยอดภาษีที่ถูกหัก', "
            u"'ค่าธรรมเนียมบริษัท', 'ยอดใบแจ้งหนี้ก่อน VAT' หรือ 'ยอดใบแจ้งนี้หลัง VAT'\n\n"

            u"########## 3) ชื่อผู้โอน (สำคัญที่สุด) ##########\n"
            u"ต้องเป็น **ผู้จ่ายเงิน** เท่านั้น อยู่ฝั่ง 'จาก' / 'From' / 'ผู้สั่งจ่าย' / "
            u"'รายละเอียดผู้จ่ายเงิน' / 'Sender Details' / 'บัญชีหักเงิน' / "
            u"'ชื่อบริษัท' (หัวรายงานของธนาคาร)\n"
            u"กฎเฉพาะที่มักอ่านผิด:\n"
            u"  • **SCB Payment Advice (ใบแจ้งการชำระเงิน)** มีชื่อบัญชี 2 ที่ ระวังสลับ!\n"
            u"      - 'เรียน ...' และ 'ชื่อบัญชี / Account Name' ใต้หัวธนาคาร = **ผู้รับ**\n"
            u"      - ผู้โอนอยู่ในกล่อง 'รายละเอียดผู้จ่ายเงิน / Sender Details' "
            u"และในประโยค 'ธนาคารได้โอนเงินจาก <ชื่อนี้> ให้กับท่าน'\n"
            u"  • **LH Bank / Kept / ttb** บรรทัดใต้ชื่อคนมักเป็น **ชื่อธนาคาร** "
            u"(เช่น 'แลนด์ แอนด์ เฮ้าส์', 'Krungsri', 'ไทยพาณิชย์') "
            u"ห้ามเอามาต่อท้ายชื่อผู้โอน ให้ใส่ในช่อง sender_bank แทน\n"
            u"  • **สลิปจ่ายบิล (Bill Payment / PromptPay / Biller ID)** ผู้โอนคือ "
            u"ชื่อบุคคลฝั่ง 'จาก' ส่วน 'REF001' / 'เลขที่อ้างอิง' ไม่ใช่ชื่อ\n"
            u"  • **รายงาน IPP หลายหน้า** ถ้าหน้านั้นไม่มีชื่อบริษัทผู้สั่งจ่าย "
            u"ให้ตั้ง sender_found = false (ห้ามเอาชื่อผู้รับมาตอบแทน)\n"
            u"  • ตอบชื่อเต็มตามที่เห็น ถ้ามีทั้งไทยและอังกฤษให้ใส่ทั้งคู่คั่นด้วย ' / '\n"
            u"    เช่น 'บจก.ทรัพย์ธารา ดีไซน์ แอนด์ คอนสตรัคชั่น / "
            u"SAPTHARA DESIGN&CONSTRUCTION CO.,LTD.'\n"
            u"  • ถ้าชื่อถูกตัดท้าย (เช่น 'นาย สุวรรณ ร') ให้ตอบตามที่เห็น ห้ามเดาต่อ\n\n"

            u"########## 4) ผู้รับเงิน / เลขบัญชี / เลขอ้างอิง ##########\n"
            u"  - ผู้รับ = ฝั่ง 'ไปยัง' / 'ถึง' / 'To' / 'ผู้รับเงิน' / "
            u"'ชื่อผู้รับเงิน' / 'เรียน'\n"
            u"  - เลขบัญชีตอบตามที่เห็น มาสก์ก็ได้ (เช่น 'xxx-x-x1838-x', "
            u"'XXX-XXX360-3', '037-7-xxx204')\n"
            u"  - เลขอ้างอิง = 'เลขที่รายการ' / 'Transaction ID' / 'รหัสอ้างอิง' / "
            u"'หมายเลขอ้างอิง' / 'รหัสทำรายการ' / 'เลขอ้างอิง'\n"
            u"  - **เลขอ้างอิงบิล (bill_ref)** = 'เลขที่อ้างอิง 1' / 'Reference 1' / "
            u"'Ref 1' / บรรทัดสั้น ๆ ใต้ชื่อผู้รับในสลิปจ่ายบิล เช่น 'REF001'\n"
            u"    ถ้าเป็นสลิปจ่ายบิล (Bill Payment / Biller ID / พร้อมเพย์บิล) "
            u"ให้ตั้ง is_bill_payment = true และตอบ bill_ref ตามที่เห็นเสมอ\n\n"
        )
        if our_names:
            prompt += (
                u"########## 5) บริษัทผู้รับเงิน (บริษัทของเรา) ##########\n"
                u"ชื่อต่อไปนี้คือ **ผู้รับเงิน** ห้ามตอบเป็น sender_name เด็ดขาด:\n"
                + our_names +
                u"  - ตั้ง recipient_matches_company = true ถ้าผู้รับในสลิปเป็นบริษัทนี้ "
                u"(ยอมรับคนละภาษา/สะกดต่าง/ชื่อถูกตัดท้าย เช่น 'NOPPADOL INTE')\n"
                u"  - ถ้าเผลออ่านชื่อนี้ไปอยู่ฝั่งผู้โอน แปลว่าอ่านสลับด้าน ให้กลับไปอ่านใหม่\n\n"
            )
        prompt += (
            u"########## รูปแบบคำตอบ (JSON เท่านั้น) ##########\n"
            u"{\n"
            u'  "found": true,\n'
            u'  "date": "DD/MM/YYYY",\n'
            u'  "date_candidates": ["DD/MM/YYYY"],\n'
            u'  "time": "HH:MM",\n'
            u'  "amount": 21550.00,\n'
            u'  "amount_candidates": [21550.00],\n'
            u'  "sender_name": "ชื่อผู้โอน (ไทย / อังกฤษ)",\n'
            u'  "sender_found": true,\n'
            u'  "sender_account": "เลขบัญชีผู้โอนตามที่เห็น",\n'
            u'  "sender_bank": "ชื่อธนาคารผู้โอน",\n'
            u'  "recipient_name": "ชื่อผู้รับเงิน",\n'
            u'  "recipient_account": "เลขบัญชีผู้รับ",\n'
            u'  "recipient_matches_company": true,\n'
            u'  "reference": "เลขอ้างอิง",\n'
            u'  "bill_ref": "เลขที่อ้างอิง 1 ของสลิปจ่ายบิล เช่น REF001",\n'
            u'  "is_bill_payment": false,\n'
            u'  "is_transfer_slip": true,\n'
            u'  "doc_type": "ประเภทเอกสาร ถ้าไม่ใช่สลิปโอนเงิน"\n'
            u"}\n\n"
            u"########## เอกสารที่ไม่ใช่สลิปโอนเงิน ##########\n"
            u"พนักงานมักแนบเอกสารอื่นปนมาด้วย ถ้าเป็นเอกสารประเภทนี้ให้ตั้ง\n"
            u"**is_transfer_slip = false** แล้วตอบ doc_type ว่าเป็นเอกสารอะไร\n"
            u"  - หนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ / ภ.ง.ด.3 / ภ.ง.ด.53)\n"
            u"  - ใบกำกับภาษี / ใบเสร็จรับเงิน / ใบแจ้งหนี้ / ใบวางบิล / ใบสั่งซื้อ\n"
            u"  - สัญญา, บัตรประชาชน, ทะเบียนบ้าน, หนังสือรับรองบริษัท, ภพ.20\n"
            u"  - เช็ค, ใบนำฝากเช็ค, รูปสินค้า, รูปหน้างาน, เอกสารเปล่า/อ่านไม่ออก\n"
            u"**ระวังสับสน:** หนังสือรับรองการหักภาษี ณ ที่จ่าย มี 'จำนวนเงินที่จ่าย', "
            u"'ภาษีที่หัก' และ 'วัน เดือน ปี ที่จ่าย' หน้าตาคล้ายสลิปมาก "
            u"แต่**ไม่ใช่หลักฐานการโอนเงิน** สังเกตหัวเอกสารว่าเขียนว่า "
            u"'หนังสือรับรองการหักภาษี ณ ที่จ่าย' / 'ตามมาตรา 50 ทวิ' / "
            u"'ผู้มีหน้าที่หักภาษี ณ ที่จ่าย' -> ต้องตั้ง is_transfer_slip = false\n"
            u"สลิปโอนเงินจริงต้องมีลักษณะอย่างน้อยข้อหนึ่ง: ระบุว่าโอนสำเร็จ, "
            u"มีเลขที่รายการ/รหัสอ้างอิงของธนาคาร, มีบัญชีต้นทาง-ปลายทาง, "
            u"หรือเป็นรายงานการโอนเงินที่ออกโดยธนาคาร\n\n"

            u"ถ้าอ่านค่าใดไม่ได้ ให้ใส่ค่าว่าง \"\" หรือ 0 และตั้ง *_found = false "
            u"(ห้ามเดา ห้ามแต่งค่าขึ้นมาเอง)"
        )
        return prompt

    @staticmethod
    def _scb_attachment_part(attachment):
        u"""แปลงไฟล์แนบ 1 ไฟล์เป็น inline_data ของ Gemini"""
        data = attachment.datas
        return {"inline_data": {
            "mime_type": attachment.mimetype or 'image/jpeg',
            "data": data.decode('utf-8') if isinstance(data, bytes) else data,
        }}

    def _scb_slip_parts(self, attachments=None):
        u"""แปลงไฟล์แนบเป็น parts ของ Gemini (ใช้ตอนตรวจซ้ำรอบสอง)"""
        self.ensure_one()
        parts = []
        for idx, att in enumerate(attachments or self._scb_get_slip_attachments(), 1):
            parts.append({"text": u"[ไฟล์ที่ %d] ชื่อไฟล์: %s" % (idx, att.name or '-')})
            parts.append(self._scb_attachment_part(att))
        return parts

    def _scb_read_one_slip(self, attachment):
        u"""ให้ AI อ่านสลิป "1 ไฟล์" -> คืน dict ค่าที่จะเขียนลง npd.scb.payment.slip

        อ่านทีละไฟล์เสมอ เพราะลูกค้ามักโอนไม่ครบในครั้งเดียว แล้วพนักงานแนบหลายสลิป
        ถ้าส่งรวมกันไปทีเดียว AI จะตอบค่าชุดเดียวและปนกันจนใช้ไม่ได้
        """
        self.ensure_one()
        parts = [
            {"text": u"ชื่อไฟล์: %s" % (attachment.name or '-')},
            self._scb_attachment_part(attachment),
            {"text": self._scb_slip_prompt()},
        ]
        result = self._scb_gemini_call(parts, max_tokens=4096)
        if not result:
            return {'state': 'unreadable',
                    'reason': _(u"AI อ่านสลิปไม่สำเร็จ (ไม่ได้ข้อมูลกลับมา)")}
        # ไม่ใช่สลิป (พนักงานมักแนบ 50 ทวิ / ใบกำกับภาษี ปนมา) -> ข้ามไฟล์นี้
        # ต้องไม่ใช่ 'unreadable' ไม่งั้นจะลากทั้งใบไปเป็น "ไม่สำเร็จ"
        if result.get('is_transfer_slip') is False:
            doc = (result.get('doc_type') or '').strip()
            return {'state': 'not_slip', 'raw': json.dumps(result, ensure_ascii=False),
                    'reason': _(u"ไฟล์นี้ไม่ใช่สลิป/หลักฐานการโอนเงิน%s "
                                u"— ไม่ต้องนำมาตรวจสอบ")
                    % (_(u" (%s)") % doc if doc else u'')}

        date_str = (result.get('date') or '').strip()
        # ใช้ตัวแปลงวันที่ชุดเดียวกับปุ่ม "ใช้วันที่จากสลิป" (รองรับ พ.ศ./เดือนไทย)
        slip_date = self._parse_slip_date(date_str) if date_str else None
        amounts = []
        for val in [result.get('amount')] + list(result.get('amount_candidates') or []):
            amt = self._scb_to_float(val)
            if amt > 0 and amt not in amounts:
                amounts.append(amt)
        return {
            'state': 'to_check',
            'slip_date': slip_date or False,
            'slip_time': (result.get('time') or '').strip() or False,
            'slip_amount': amounts[0] if amounts else 0.0,
            'slip_sender': (result.get('sender_name') or '').strip() or False,
            'slip_sender_acc': (result.get('sender_account') or '').strip() or False,
            'slip_ref': (result.get('reference') or '').strip() or False,
            'raw': json.dumps(result, ensure_ascii=False, indent=2),
            'reason': False,
        }

    def _scb_file_skip_reason(self, attachment):
        u"""คืนคำที่ทำให้รู้ว่าไฟล์นี้ไม่ใช่สลิป โดยดูจากชื่อไฟล์อย่างเดียว

        เป็นตัวกรองราคาถูกไว้ก่อนเรียก AI (พนักงานที่ตั้งชื่อไฟล์ว่า "50ทวิ.pdf"
        ไม่ต้องเสียโควตา AI) ส่วนไฟล์ที่ชื่อไม่บอกอะไร เช่น S__123.jpg
        ยังต้องให้ AI ดูรูปแล้วตัดสินอยู่ดี
        """
        raw = self._scb_param('verify_skip_file_keywords') or ''
        keywords = [k.strip().lower() for k in raw.split(',') if k.strip()]
        name = (attachment.name or '').lower()
        for keyword in keywords:
            if keyword in name:
                return keyword
        return ''

    def _scb_sync_slip_lines(self, force_reread=False):
        u"""สร้าง/อัปเดตบรรทัดผลตรวจให้ครบทุกไฟล์แนบ แล้วคืน recordset ของบรรทัด

        - ไฟล์ที่เคยอ่านแล้วจะไม่เรียก AI ซ้ำ (เว้นแต่สั่ง force_reread)
        - ไฟล์แนบที่ถูกลบไป บรรทัดของมันจะถูกลบตาม
        """
        self.ensure_one()
        Slip = self.env['npd.scb.payment.slip'].sudo()
        attachments = self._scb_get_slip_attachments()
        lines = Slip.search([('payment_id', '=', self.id)])

        stale = lines.filtered(lambda l: l.attachment_id not in attachments)
        if stale:
            stale.unlink()
            lines -= stale

        by_attachment = {l.attachment_id.id: l for l in lines}
        for attachment in attachments:
            line = by_attachment.get(attachment.id)
            # 'unreadable' อาจเกิดจาก AI ล่มชั่วคราว/JSON ถูกตัด ต้องลองอ่านใหม่
            # ส่วนสถานะอื่นอ่านสำเร็จแล้ว ไม่ต้องเปลืองโควตาอ่านซ้ำ
            if line and not force_reread and line.state != 'unreadable':
                continue
            # ชื่อไฟล์บอกได้ว่าไม่ใช่สลิป -> ข้ามไปเลย ไม่ต้องเปลืองโควตา AI
            keyword = self._scb_file_skip_reason(attachment)
            if keyword:
                vals = {'state': 'not_slip',
                        'reason': _(u"ชื่อไฟล์มีคำว่า \"%s\" — ไม่ใช่สลิปการโอน "
                                    u"จึงไม่ได้นำมาตรวจสอบ") % keyword}
            else:
                try:
                    vals = self._scb_read_one_slip(attachment)
                except UserError as e:
                    vals = {'state': 'unreadable',
                            'reason': _(u"อ่านสลิปไม่สำเร็จ: %s") % e}
            vals.setdefault('statement_id', False)
            if line:
                line.write(vals)
            else:
                vals.update(payment_id=self.id, attachment_id=attachment.id)
                by_attachment[attachment.id] = Slip.create(vals)

        return Slip.search([('payment_id', '=', self.id)])

    def _scb_ai_same_company(self, slip_name, bank_names, slip_account=None):
        u"""ถามความเห็น AI ว่า "ชื่อในสลิป" กับ "ชื่อในรายการธนาคาร" เป็นเจ้าเดียวกันไหม

        ใช้เป็นตัวช่วยเมื่อเทียบตัวอักษรแล้วไม่ผ่าน — เพราะธนาคารมักตัดชื่อให้สั้น
        และสลิปอาจเป็นคนละภาษากับที่ธนาคารบันทึก (ไทย/อังกฤษ)
        คืน index ของชื่อที่ตรง (int) หรือ None
        """
        names = [n for n in bank_names if n]
        if not slip_name or not names:
            return None
        listing = u''.join(u"  %d. %s\n" % (i, n) for i, n in enumerate(names))
        extra = u''
        if slip_account:
            extra = u"เลขบัญชีผู้โอนที่เห็นในสลิป (ถูกมาสก์บางส่วน): %s\n" % slip_account
        prompt = (
            u"เทียบว่า 'ชื่อในสลิปโอนเงิน' กับ 'ชื่อที่ธนาคารบันทึกไว้' เป็นคนหรือบริษัท "
            u"เดียวกันหรือไม่\n\n"
            u"**จำนวนเงินและวันที่ตรงกันแล้ว** เหลือแค่ยืนยันชื่อ — รายการเหล่านี้คือเงิน "
            u"ที่เข้าบัญชีจริงในวันและยอดเดียวกับสลิปเป๊ะ ๆ\n\n"
            u"ชื่อในสลิป: %s\n%s\n"
            u"ชื่อที่ธนาคารบันทึกไว้ (เลือกได้อย่างมาก 1 ข้อ):\n%s\n"
            u"กฎ:\n"
            u"- **ไทย vs อังกฤษให้ถอดเสียงเทียบกัน** ถือว่าเป็นคนเดียวกัน เช่น\n"
            u"    'นาย สาธิต' = 'SATHIT NAKSUWAN'      (ชื่อต้นถอดเสียงตรงกัน)\n"
            u"    'น.ส. สุรีย์ลักษณ์' = 'SUREELAK ...'\n"
            u"    'บจก. พี.เอ็ม.อี.ซี เมทัลเวิร์ค' = 'P.M.E.C METAL WORK CO.,LTD'\n"
            u"- **สลิปมักแสดงแค่ชื่อต้น ไม่มีนามสกุล** (ธนาคารกรุงเทพ/K+ ปิดบังไว้) "
            u"ถ้าชื่อต้นถอดเสียงตรงกัน ให้ถือว่าตรงกัน ไม่ต้องรอให้นามสกุลตรงด้วย\n"
            u"- ธนาคารมักตัดชื่อให้สั้น/ไม่ครบ (มี ++ หรือหายไปกลางคัน) "
            u"ถ้าเป็นคำขึ้นต้นที่ตรงกันถือว่าเป็นเจ้าเดียวกัน\n"
            u"- คำนำหน้า (นาย/นาง/น.ส./MR/MISS) และรูปแบบบริษัท "
            u"(บริษัท/หจก/จำกัด/CO.,LTD/สำนักงานใหญ่) ไม่ทำให้ต่างกัน\n"
            u"- ถ้ามีเลขบัญชีผู้โอนให้ดู ใช้เป็นตัวช่วยยืนยันได้ (เลขท้ายตรงกัน = คนเดียวกัน)\n"
            u"- ตอบ match_index = -1 เฉพาะเมื่อ **ชื่อคนละคนชัดเจน** เท่านั้น "
            u"(ชื่อต้นถอดเสียงแล้วคนละเสียงกัน) — ไม่ใช่เพราะข้อมูลไม่ครบ\n\n"
            u'ตอบ JSON: {"match_index": 0, "confident": true}'
        ) % (slip_name, extra, listing)
        try:
            res = self._scb_gemini_call([{"text": prompt}], max_tokens=1024)
        except UserError as e:
            _logger.warning("SCB verify: AI name match failed: %s", e)
            return None
        try:
            idx = int(res.get('match_index', -1))
        except (TypeError, ValueError):
            return None
        if 0 <= idx < len(names) and res.get('confident', True):
            return idx
        return None

    def _scb_second_opinion(self, line, dates, amounts, sources):
        u"""รอบสอง — ให้ AI ดู "รูปสลิป" คู่กับ "รายการเงินเข้าจริงในบัญชี" แล้วชี้เอง

        ใช้เมื่อรอบแรกจับคู่ไม่ได้ ซึ่งสาเหตุที่เจอบ่อยคือ
          • AI อ่านวันที่จากสลิปผิด (สลิปมีหลายวันที่ / รูปแบบ พ.ศ.-ค.ศ. ปนกัน)
          • ชื่อผู้โอนในสลิปกับที่ธนาคารบันทึกคนละภาษา หรือถูกตัดท้าย
        การส่งรายการจริงไปให้ดูพร้อมกัน ทำให้ AI เทียบได้ตรง ๆ แทนการเดา

        คืน dict {'statement': record, 'ai': dict} หรือ None
        """
        self.ensure_one()
        Statement = self.env['npd.scb.bank.statement'].sudo()
        window = self._scb_param('verify_second_pass_days')
        base = dates[0]

        rows = Statement.search([
            ('source', 'in', sources),
            ('deposit', '>', 0),
            ('date', '>=', base - timedelta(days=window)),
            ('date', '<=', base + timedelta(days=window)),
        ], order='date desc, time desc', limit=80)
        # รายการที่ "ยอดตรง" แต่หลุดนอกช่วงวัน — เผื่อกรณีอ่านวันที่ผิดไปไกล
        for amt in amounts:
            rows |= Statement.search([
                ('source', 'in', sources),
                ('deposit', '>=', amt - 0.01),
                ('deposit', '<=', amt + 0.01),
            ], order='date desc', limit=10)
        rows = rows.sorted(key=lambda r: (r.date or fields.Date.today(), r.time or ''),
                           reverse=True)
        if not rows:
            return None

        listing = u''.join(
            u"  %d. วันที่ %s %s | เงินเข้า %s | %s\n" % (
                i, r.date, r.time or '', '{:,.2f}'.format(r.deposit),
                r.description or u'(ธนาคารไม่ระบุรายละเอียด)')
            for i, r in enumerate(rows, 1))

        parts = self._scb_slip_parts(line.attachment_id)
        parts.append({"text": (
            u"งานนี้คือ **ตรวจทานรอบสอง** ระบบอ่านสลิปรอบแรกแล้วจับคู่กับบัญชีไม่ได้\n"
            u"สาเหตุที่พบบ่อยคือ อ่าน 'วันที่' ผิด หรือ 'ชื่อผู้โอน' เป็นคนละภาษากับ"
            u"ที่ธนาคารบันทึกไว้\n\n"
            u"ด้านบนคือรูป/ไฟล์สลิปการโอนเงิน\n"
            u"ด้านล่างคือ **รายการเงินเข้าจริงในบัญชีของผู้รับ** ที่ดึงมาจากธนาคาร:\n"
            u"%s\n"
            u"ให้ดูสลิปใหม่อย่างละเอียด แล้วตอบว่ารายการใดในลิสต์คือรายการเดียวกับสลิปนี้\n\n"
            u"เกณฑ์ตัดสิน (เรียงตามน้ำหนัก):\n"
            u"1. **จำนวนเงินต้องตรงกันเป๊ะ** — ถ้าไม่มีรายการไหนยอดตรง ให้ตอบ match_no = -1\n"
            u"   (อ่านยอดในสลิปใหม่ให้แน่ใจก่อน ระวังสับสนกับค่าธรรมเนียม/ภาษีหัก ณ ที่จ่าย/"
            u"ยอดคงเหลือ/ตัวเลขในโฆษณา)\n"
            u"2. **วันที่** ควรตรงกัน แต่คลาดกัน 1-2 วันได้ เพราะธนาคารอาจลงบัญชีข้ามวัน\n"
            u"   ถ้าวันที่ที่คุณอ่านได้ไม่ตรงกับรายการใดเลย ให้ย้อนอ่านวันที่ในสลิปใหม่ "
            u"— อาจอ่านสลับ พ.ศ./ค.ศ. หรือหยิบ 'วันที่พิมพ์/อัปเดตล่าสุด' มาผิด\n"
            u"3. **ชื่อผู้โอน** ให้เทียบแบบยืดหยุ่น ถือว่าตรงกันได้แม้:\n"
            u"   - คนละภาษา เช่น 'SAPTHARA DESIGN&CONSTRUCTION CO.,LTD.' = "
            u"'บจก. ทรัพย์ธารา ดีไซน์ แอนด์ คอนสตรัคชั่น'\n"
            u"   - ธนาคารตัดชื่อท้าย เช่น 'บจก. พี.เอ็ม.อี.ซี เม' = "
            u"'บจก. พี.เอ็ม.อี.ซี เมทัลเวิร์ค'\n"
            u"   - มี/ไม่มีคำว่า บริษัท/หจก/จำกัด/CO.,LTD\n"
            u"   - ธนาคารไม่ระบุชื่อเลย (จ่ายผ่านบิลเพย์เมนต์/เคาน์เตอร์เซอร์วิส) "
            u"— กรณีนี้ให้ตัดสินด้วยยอดเงินและวันที่แทน\n"
            u"4. ถ้ามีมากกว่า 1 รายการที่เข้าเกณฑ์เท่า ๆ กัน ให้ตอบ match_no = -1 "
            u"(ปลอดภัยกว่าเดาผิด)\n\n"
            u"ตอบ JSON เท่านั้น:\n"
            u"{\n"
            u'  "match_no": 3,\n'
            u'  "confident": true,\n'
            u'  "slip_date": "DD/MM/YYYY",\n'
            u'  "slip_amount": 21550.00,\n'
            u'  "slip_sender_name": "ชื่อผู้โอนที่อ่านได้จากสลิป",\n'
            u'  "reason": "อธิบายสั้น ๆ ว่าทำไมถึงเลือก/ไม่เลือก"\n'
            u"}\n"
            u"match_no = ลำดับในลิสต์ (1, 2, 3, ...) หรือ -1 ถ้าไม่มีรายการใดตรง"
        ) % listing})

        try:
            res = self._scb_gemini_call(parts, max_tokens=4096)
        except UserError as e:
            _logger.warning("SCB verify: second opinion failed: %s", e)
            return None
        if not res:
            return None
        try:
            no = int(res.get('match_no', -1))
        except (TypeError, ValueError):
            return None
        if not (1 <= no <= len(rows)) or not res.get('confident', True):
            return {'statement': None, 'ai': res}

        rec = rows[no - 1]
        # ป้องกัน AI ชี้มั่ว: ยอดของรายการที่เลือก ต้องตรงกับยอดที่อ่านได้จากสลิป
        # (ยอมรับทั้งยอดรอบแรกและยอดที่อ่านใหม่รอบสอง)
        tol = self._scb_param('verify_amount_tolerance')
        allowed = list(amounts)
        second_amt = self._scb_to_float(res.get('slip_amount'))
        if second_amt > 0:
            allowed.append(round(second_amt, 2))
        if not any(abs(rec.deposit - a) <= tol for a in allowed):
            _logger.info(
                "SCB verify: ปฏิเสธผลรอบสองของ payment %s — ยอดไม่ตรง "
                "(ธนาคาร %.2f / สลิป %s)", self.id, rec.deposit, allowed)
            return {'statement': None, 'ai': res}
        return {'statement': rec, 'ai': res}

    # ------------------------------------------------------------------
    # ตรรกะการตรวจสอบ
    # ------------------------------------------------------------------
    def _scb_verify_one(self, force_reread=False):
        u"""ตรวจสอบใบรับชำระ 1 ใบ -> เขียนผลลง scb_verify_* และคืน dict ผลลัพธ์"""
        self.ensure_one()
        Statement = self.env['npd.scb.bank.statement'].sudo()
        now = fields.Datetime.now()

        def release_slips(reason):
            u"""ปลดผลจับคู่เดิมออก เมื่อสรุปได้ว่าใบนี้ไม่ต้องตรวจ

            ถ้าปล่อยไว้ บรรทัดสลิปจะยังค้างว่า "จับคู่ได้" ทั้งที่หัวใบบอกว่า
            ไม่ต้องตรวจ และยังไปนับเป็นผู้ตัดเงินก้อนนั้นในใบอื่นด้วย
            """
            lines = self.scb_slip_ids.filtered(lambda l: l.state != 'skipped')
            if lines:
                lines.sudo().write({'state': 'skipped', 'statement_id': False,
                                    'reason': reason})

        def finish(state, reason, statement=None):
            vals = {
                'scb_verify_state': state,
                'scb_verify_summary': self._scb_public_summary(state),
                'scb_verify_reason': reason,
                'scb_verify_datetime': now,
                'scb_statement_id': statement.id if statement else False,
            }
            # นับเฉพาะครั้งที่ "ไม่สำเร็จ" เพื่อคุมจำนวนรอบที่ระบบจะลองซ้ำให้
            # (สถานะรออื่น ๆ ไม่นับ จะได้ตรวจซ้ำเรื่อย ๆ จนกว่าข้อมูลจะพร้อม)
            if state == 'failed':
                vals['scb_verify_attempts'] = (self.scb_verify_attempts or 0) + 1
            self.sudo().write(vals)
            return {'state': state, 'reason': reason}

        # ---- 0) ต้องลงบันทึกแล้วเท่านั้น ----
        # ใบร่างยังแก้จำนวนเงิน/วันที่/ลูกค้าได้อยู่ ถ้าตรวจตั้งแต่ตอนเป็นร่าง
        # ผลที่ได้จะใช้อ้างอิงไม่ได้ (แก้ทีหลังแล้วสถานะยังค้างว่า "โอนสำเร็จ")
        if self.state not in POSTED_STATES:
            return finish('waiting', _(
                u"ใบรับชำระยังไม่ได้ลงบันทึก — ระบบจะเริ่มตรวจสอบการโอน "
                u"หลังกด \"ลงบันทึก\" แล้วเท่านั้น"))

        # ---- 0.5) สมุดรายวันที่ไม่มีเงินโอนเข้าจริง -> ข้ามถาวร ----
        # เช่น "สมุดรายวันรับชำระลดหนี้" คือการตัดหนี้ในระบบ ไม่ได้รับโอนเงิน
        # statement ของธนาคารไม่มีทางมีรายการนี้ ตรวจไปก็ขึ้น "ไม่สำเร็จ" เปล่า ๆ
        skip_word = self._scb_skip_reason()
        if skip_word:
            release_slips(_(u"สมุดรายวัน \"%s\" ไม่ต้องตรวจการโอน")
                          % (self.journal_id.name or '-'))
            return finish('skipped', _(
                u"ไม่ต้องตรวจสอบการโอน — สมุดรายวัน \"%s\" เป็นการตัดหนี้ในระบบ "
                u"(เข้าเงื่อนไขคำว่า \"%s\") ไม่ได้มีการรับโอนเงินจริง "
                u"จึงไม่มีรายการในบัญชีธนาคารให้เทียบ"
            ) % (self.journal_id.name or '-', skip_word))

        # ---- 0.6) วิธีชำระที่ไม่มีเงินเข้าบัญชีจริง -> ข้ามเช่นกัน ----
        # เช่น "หักเงินประกันค่าเช่า" คือหักจากเงินประกันที่ลูกค้าวางไว้ก่อนแล้ว
        method_name = self._scb_skip_method_reason()
        if method_name:
            release_slips(_(u"วิธีชำระ \"%s\" ไม่มีเงินเข้าบัญชีจริง") % method_name)
            return finish('skipped', _(
                u"ไม่ต้องตรวจสอบการโอน — วิธีชำระ \"%s\" ไม่ได้มีเงินโอนเข้าบัญชี "
                u"ธนาคารจริง จึงไม่มีรายการเดินบัญชีให้เทียบ"
            ) % method_name)

        sources = self._scb_verify_sources()
        if not sources:
            return finish('waiting', _(
                u"ยังไม่ได้เลือกธนาคารที่จะตรวจสอบ — ตั้งค่าที่เมนู "
                u"ตรวจสอบการโอนเงิน > ตั้งค่า"))

        # ---- 1) อ่านสลิป "ทีละไฟล์" (ลูกค้าอาจโอนหลายครั้ง แนบหลายสลิป) ----
        try:
            lines = self._scb_sync_slip_lines(force_reread)
        except UserError as e:
            return finish('waiting', _(u"อ่านสลิปไม่สำเร็จ: %s") % e)
        if not lines:
            return finish('no_slip', _(
                u"ยังไม่ได้แนบสลิปการโอนเงินในเอกสารแนบ — กรุณาแนบไฟล์สลิป "
                u"(รูปภาพหรือ PDF) ที่หน้ารับชำระ แล้วระบบจะตรวจสอบให้อัตโนมัติ"))

        # ---- 2) ตรวจทีละสลิป แล้วค่อยสรุปรวม ----
        bank_labels = dict(Statement._fields['source'].selection)
        claimed = set()          # รายการธนาคารที่สลิปใบก่อนหน้าจับจองไปแล้ว
        for line in lines:
            self._scb_match_slip_line(line, sources, claimed)
            if line.statement_id:
                claimed.add(line.statement_id.id)

        self._scb_mark_duplicate_slips(lines)
        self._scb_update_slip_summary(lines)
        active = lines.filtered(
            lambda l: l.state not in ('skipped', 'not_slip', 'duplicate'))
        header = _(u"ตรวจสลิป %s ไฟล์ (เทียบกับ statement ของ %s ตามสมุดรายวัน \"%s\")") % (
            len(lines), u'/'.join(bank_labels.get(s, s) for s in sources),
            self.journal_id.name or '-')
        not_slip = lines.filtered(lambda l: l.state == 'not_slip')
        if not_slip:
            header += _(u"\nข้าม %s ไฟล์ที่ไม่ใช่สลิปการโอน: %s") % (
                len(not_slip),
                u', '.join(l.attachment_name or '-' for l in not_slip))
        duplicate = lines.filtered(lambda l: l.state == 'duplicate')
        if duplicate:
            header += _(u"\nข้าม %s ไฟล์ที่เป็นสลิปใบเดิมแนบซ้ำ: %s") % (
                len(duplicate),
                u', '.join(l.attachment_name or '-' for l in duplicate))
        detail = u'\n\n'.join(
            u"[%s] %s — %s\n%s" % (
                dict(line._fields['state'].selection).get(line.state, line.state),
                line.attachment_name or '-',
                '{:,.2f}'.format(line.slip_amount or 0.0),
                line.reason or '-')
            for line in lines)

        if not active:
            # แนบมาแต่ไม่มีไฟล์ไหนเป็นสลิปเลย = ยังไม่ได้แนบสลิป ต้องให้ไปแนบเพิ่ม
            # (ต่างจาก "ไม่ต้องตรวจ" ซึ่งแปลว่ารายการนี้ไม่ต้องตรวจตั้งแต่แรก)
            if lines.filtered(lambda l: l.state == 'not_slip'):
                return finish('no_slip', _(
                    u"%s\n\nไฟล์ที่แนบมาไม่มีไฟล์ไหนเป็นสลิป/หลักฐานการโอนเงินเลย "
                    u"— กรุณาแนบสลิปการโอนเพิ่ม\n\n%s") % (header, detail))
            return finish('skipped', header + u'\n\n' + detail)

        matched = active.filtered(lambda l: l.state == 'matched')
        if len(matched) == len(active):
            over, shared = self._scb_check_shared_statements(matched)
            if over:
                return finish('failed', u"%s\n\n%s\n\n%s" % (header, over, detail))
            total = sum(matched.mapped('slip_amount'))
            summary = _(u"จับคู่ครบทุกสลิป (%s ไฟล์) รวมเป็นเงิน %s") % (
                len(matched), '{:,.2f}'.format(total))
            if shared:
                summary += u"\n" + shared
            statement = matched[0].statement_id if len(matched) == 1 else None
            # เงินเข้าจริงแล้ว แต่เข้าบัญชีบริษัทอื่นในเครือหรือเปล่า
            foreign = self._scb_foreign_accounts(matched)
            if foreign:
                summary += u"\n\n" + _(
                    u"เงินเข้าบัญชีของ %s ซึ่งไม่ใช่บัญชีของ %s — "
                    u"ต้องโอนต่อ/ปรับบัญชีระหว่างกันเอง"
                ) % (u', '.join(foreign), self.company_id.name)
                return finish('other_company',
                              u"%s\n%s\n\n%s" % (header, summary, detail),
                              statement)
            return finish('success', u"%s\n%s\n\n%s" % (header, summary, detail),
                          statement)

        # ยังมีสลิปที่รอข้อมูลธนาคาร และไม่มีใบไหนที่ "ไม่พบ" -> รอต่อ
        waiting = active.filtered(lambda l: l.state == 'waiting')
        if waiting and not active.filtered(lambda l: l.state in ('not_found', 'unreadable')):
            return finish('waiting', header + u'\n\n' + detail)

        pending = len(active) - len(matched)
        return finish('failed', _(
            u"%s\n\nจับคู่ได้ %s จาก %s สลิป — ยังเหลือ %s สลิปที่ยังไม่พบรายการ\n\n%s"
        ) % (header, len(matched), len(active), pending, detail))

    def _scb_has_own_data(self, sources, date, day_tol=0):
        u"""มีรายการเดินบัญชี "ของบัญชีบริษัทเรา" ในวันนั้นแล้วหรือยัง

        ชีตรวม statement ของทุกบริษัทในเครือไว้ด้วยกัน และบางวันข้อมูลเข้ามา
        ไม่ครบทุกบัญชี ถ้าดูแค่ "มีแถวของวันนั้นไหม" จะเจอแถวของบริษัทอื่นแล้ว
        เข้าใจผิดว่าข้อมูลพร้อมแล้ว -> สรุปว่า "ไม่สำเร็จ" ทั้งที่ยังไม่มีอะไรให้เทียบ
        พอนับครบเพดานที่ตั้งไว้ cron ก็เลิกตรวจถาวร แม้ชีตจะเติมข้อมูลทีหลัง
        (เจอจริง: 12/08/2026 ทั้งชีตมี 3 แถว ซึ่งเป็นของอีกสองบริษัท
         บัญชีของบริษัทเรา 0 แถว)
        """
        self.ensure_one()
        rows = self.env['npd.scb.bank.statement'].sudo().search([
            ('source', 'in', sources),
            ('date', '>=', date - timedelta(days=day_tol)),
            ('date', '<=', date + timedelta(days=day_tol)),
        ])
        if not rows:
            return False
        if not self._scb_param('verify_check_own_account'):
            return True
        names = self._scb_own_account_names()
        numbers = self._scb_own_account_numbers()
        return any(r.belongs_to_company(names, numbers) for r in rows)

    def _scb_bill_rows_available(self, sources, date):
        u"""บัญชีของบริษัทเรามีรายการจ่ายบิล "แยกรายคน" ของวันนั้นแล้วหรือยัง

        ธนาคารส่งบิลเพย์เมนต์มาสองแบบในชีตเดียวกัน
          - แถวสรุปยอดรวมรายวัน: ลงเวลา 22:59 รายละเอียด "รับชำระค่าสินค้า
            และบริการ CrossBank" ไม่มีชื่อผู้โอน + **มี**ยอดคงเหลือ
          - รายการแยกรายคน: มีชื่อผู้โอนครบ + **ไม่มี**ยอดคงเหลือ
        ยอดคงเหลือจึงเป็นตัวแยกสองแบบนี้ออกจากกัน

        ตอนนี้ชีตทำรายการแยกรายคนให้ทีละบัญชี ยังไม่ครบทุกบริษัทในเครือ
        บัญชีที่ยังไม่มีจะเทียบสลิปจ่ายบิลไม่ได้เลย ต้องข้ามไปก่อน
        เช็คแบบนี้ทำให้ไม่ต้องตั้งค่าแยกรายบริษัท และพอชีตเพิ่มบัญชีเข้ามา
        ระบบจะเริ่มตรวจให้เองทันทีโดยไม่ต้องแก้โค้ด
        """
        self.ensure_one()
        rows = self.env['npd.scb.bank.statement'].sudo().search([
            ('source', 'in', sources),
            ('date', '=', date),
            ('deposit', '>', 0),
            ('counterparty', '!=', False),
            ('balance', '=', 0),
        ])
        if not rows:
            return False
        names = self._scb_own_account_names()
        numbers = self._scb_own_account_numbers()
        return any(r.belongs_to_company(names, numbers) for r in rows)

    def _scb_mark_duplicate_slips(self, lines):
        u"""หาสลิปใบเดิมที่ถูกแนบซ้ำ แล้วเปลี่ยนจาก "ไม่พบรายการ" เป็น "สลิปซ้ำ"

        พนักงานมักแนบสลิปใบเดียวกันสองรอบ (ถ่ายใหม่ / ได้มาทั้งทางไลน์และอีเมล)
        ใบหลังจะจับคู่ไม่ได้เพราะรายการเดินบัญชีถูกใบแรกจับจองไปแล้ว ผลคือทั้งใบ
        รับชำระขึ้น "ไม่สำเร็จ" และยอดรวมถูกนับซ้ำสองเท่า

        เช็คหลังจับคู่เสร็จแล้วเท่านั้น จึงปลอดภัยกว่าเดาตั้งแต่ต้น:
        ถ้าลูกค้าโอนยอดเท่ากันสองครั้งจริง ธนาคารจะมีสองรายการ สลิปทั้งคู่จะ
        จับคู่ได้เอง ไม่มีใบไหนตกมาถึงตรงนี้
        """
        self.ensure_one()
        matched = lines.filtered(lambda l: l.state == 'matched')
        pending = lines.filtered(lambda l: l.state == 'not_found')
        if not matched or not pending:
            return

        def key(line):
            return (line.slip_date, (line.slip_time or '').strip(),
                    round(line.slip_amount or 0.0, 2))

        twins = {}
        for line in matched:
            twins.setdefault(key(line), line)

        for line in pending:
            date, time, amount = key(line)
            if not date or not amount:
                continue
            twin = twins.get((date, time, amount))
            if not twin:
                continue
            # เลขอ้างอิงต่างกัน = คนละรายการจริง ไม่ใช่สลิปซ้ำ
            ref, twin_ref = (line.slip_ref or '').strip(), (twin.slip_ref or '').strip()
            if ref and twin_ref and ref != twin_ref:
                continue
            line.sudo().write({'state': 'duplicate', 'reason': _(
                u"สลิปใบนี้ซ้ำกับ \"%s\" (วันที่ %s เวลา %s ยอด %s เหมือนกัน) "
                u"ซึ่งจับคู่กับรายการเดินบัญชีไปแล้ว — ธนาคารมีเงินเข้าก้อนเดียว "
                u"จึงไม่นับซ้ำ"
            ) % (twin.attachment_name or '-', date, time or '-',
                 '{:,.2f}'.format(amount))})

    def _scb_own_account_names(self):
        u"""ชื่อเจ้าของบัญชีที่ถือว่าเป็น "บัญชีของบริษัทเรา"

        ค่าเริ่มต้นใช้ชื่อบริษัทใน Odoo (statement เขียนชื่อไม่เหมือนกันทุกธนาคาร
        เช่น SCB = "บริษัท นภดล กรุงเทพ จำกัด" / Kbank = "นภดล กรุงเทพ"
        แต่ตัดคำว่าบริษัท/จำกัดออกแล้วเท่ากัน) ถ้าธนาคารเขียนชื่อต่างจากนี้
        ให้เพิ่มเองได้ที่หน้าตั้งค่า
        """
        self.ensure_one()
        names = [self.company_id.name, self.company_id.partner_id.name]
        extra = self._scb_param('verify_own_account_names') or ''
        names += re.split(r'[,\n|]', extra)
        return [n.strip() for n in names if n and n.strip()]

    def _scb_own_account_numbers(self):
        u"""เลขบัญชีของบริษัทเรา — ใช้ตัดสินแทนการเทียบชื่อ เพราะแม่นกว่า

        ถ้าไม่ได้ตั้งค่าไว้ จะเดาเอาจากข้อมูลในชีต (ดู own_account_numbers)
        เพราะคอลัมน์ชื่อเจ้าของบัญชีเขียนผิดบริษัทอยู่บ้างในบล็อกรายการจ่ายบิล
        """
        self.ensure_one()
        extra = self._scb_param('verify_own_account_numbers') or ''
        numbers = [n.strip() for n in re.split(r'[,\n|]', extra) if n.strip()]
        if numbers:
            return numbers
        return list(self.env['npd.scb.bank.statement'].sudo()
                    .own_account_numbers(self._scb_own_account_names()))

    def _scb_foreign_accounts(self, lines):
        u"""ชื่อเจ้าของบัญชีที่ "ไม่ใช่บริษัทเรา" ในบรรดารายการที่จับคู่ได้

        Google Sheet รวม statement ของทุกบริษัทในเครือ ลูกค้าจึงอาจโอนเข้า
        บัญชีบริษัทอื่นได้ เงินเข้าจริงแต่เข้าผิดบริษัท
        """
        self.ensure_one()
        if not self._scb_param('verify_check_own_account'):
            return []
        names = self._scb_own_account_names()
        numbers = self._scb_own_account_numbers()
        foreign = []
        for st in lines.mapped('statement_id'):
            if not st.belongs_to_company(names, numbers):
                label = st.account_name or st.account_no or '-'
                if label not in foreign:
                    foreign.append(label)
        return foreign

    def _scb_bank_portion(self):
        u"""ยอดที่ "เข้าบัญชีธนาคารจริง" ของใบรับชำระนี้

        ใบรับชำระใบเดียวอาจรวมหลายวิธีชำระไว้ด้วยกัน (Payment Multi) เช่น
            11,271.92 = เงินโอนธนาคาร SCB 7,386.86 + หักเงินประกันค่าเช่า 3,885.06
        การเทียบกับเงินเข้าธนาคารต้องนับเฉพาะบรรทัดที่เป็น **เงินโอนธนาคาร**

        ห้ามนับ type='cash' ด้วย เพราะวิธีชำระอย่าง "หักเงินประกันค่าเช่า" ถูก
        ตั้ง type เป็น cash ไว้ ทั้งที่ไม่มีเงินเข้าบัญชีจริงสักบาท ถ้านับรวมจะ
        ทำให้ยอดพองแล้วไปฟ้องว่า "ตัดเงินเข้าเกิน" ทั้งที่ไม่ได้เกิน
        (ภาษีหัก ณ ที่จ่ายก็ถูกกันออกด้วยหลักเดียวกัน — type='other')

        ใบที่ไม่ได้แยกวิธีชำระ ถือว่าเป็นเงินโอนทั้งใบตามเดิม
        """
        self.ensure_one()
        if getattr(self, 'is_payment_multi', False) and getattr(self, 'paid_ids', False):
            # o18: account.paid.line เก็บชนิดวิธีชำระที่ payment_method_type และยอดที่ amount
            bank_lines = self.paid_ids.filtered(
                lambda l: l.payment_method_type == 'bank')
            return sum(bank_lines.mapped('amount'))
        return abs(self.amount)

    def _scb_check_shared_statements(self, lines):
        u"""ตรวจว่าเงินเข้าก้อนเดียวถูกตัดไปเกินตัวหรือไม่

        ลูกค้ามัก "โอนรวมมาก้อนเดียว" แล้วเอาไปตัดหลายใบรับชำระ เช่น
        เงินเข้า 124.47 = ใบ 51.85 + ใบ 72.62 — กรณีนี้ถูกต้อง ไม่ใช่บันทึกซ้ำ
        เกณฑ์ที่ใช้จึงไม่ใช่ "ห้ามใช้ซ้ำ" แต่เป็น
            ผลรวมยอดโอนของทุกใบที่ตัดเงินก้อนนี้  <=  เงินที่เข้าจริง

        ต้องคิด "ทั้งกลุ่ม" ไม่ใช่ทีละก้อน เพราะความสัมพันธ์เป็นแบบหลายต่อหลาย
        เงินเข้าก้อนหนึ่งถูกหลายใบตัดได้ และใบหนึ่งก็ตัดเงินหลายก้อนได้
        ถ้าเทียบยอด "ทั้งใบ" กับเงินเข้า "ทีละก้อน" จะฟ้องว่าเกินทั้งที่ยอดตรง เช่น
            เงินเข้า 233.00 + 2,084.83 = 2,317.83
            ใบ A 2,200.00 + ใบ B 117.83 = 2,317.83  (พอดีเป๊ะ)
        แต่พอเทียบใบ A (2,200) กับก้อน 233.00 ก้อนเดียวจะกลายเป็น "เกิน" ทันที

        คืน (ข้อความเตือนถ้าเกิน, ข้อความหมายเหตุถ้าใช้ร่วมกันแบบถูกต้อง)
        """
        self.ensure_one()
        Slip = self.env['npd.scb.payment.slip'].sudo()
        tol = max(self._scb_param('verify_amount_tolerance'), 0.01)

        # ไล่หากลุ่มที่เกี่ยวข้องกันจนครบ (ใบ <-> เงินเข้า สลับกันไปมา)
        statements = lines.mapped('statement_id')
        payments = self
        for _round in range(10):    # กันวนไม่รู้จบ กลุ่มจริงเล็กมาก
            linked = Slip.search([
                ('statement_id', 'in', statements.ids), ('state', '=', 'matched'),
            ]).mapped('payment_id').filtered(
                # นับ other_company ด้วย — เงินก้อนนั้นถูกตัดไปแล้วเหมือนกัน
                lambda p: p.id == self.id
                or p.scb_verify_state in ('success', 'other_company'))
            spread = Slip.search([
                ('payment_id', 'in', payments.ids), ('state', '=', 'matched'),
            ]).mapped('statement_id')
            if not (linked - payments) and not (spread - statements):
                break
            payments |= linked
            statements |= spread

        others = payments - self
        if not others:
            return u'', u''

        total_in = sum(statements.mapped('deposit'))
        allocated = sum(p._scb_bank_portion() for p in payments)
        names = u', '.join(p.display_name or str(p.id) for p in others)
        detail = _(u"เงินเข้า %s รายการ รวม %s / ตัดโดย %s ใบ รวม %s") % (
            len(statements), '{:,.2f}'.format(total_in),
            len(payments), '{:,.2f}'.format(allocated))

        if allocated > total_in + tol:
            return _(
                u"เงินเข้าก้อนเดียวกันถูกตัดไปแล้วโดย %s — %s ซึ่ง **เกิน** "
                u"ยอดที่เข้าจริง %s — กรุณาตรวจสอบว่าบันทึกรับชำระซ้ำหรือไม่"
            ) % (names, detail, '{:,.2f}'.format(total_in)), u''
        return u'', _(
            u"ลูกค้าโอนรวมมาแล้วตัดหลายใบ — ใบนี้ %s ร่วมกับ %s (%s)"
        ) % ('{:,.2f}'.format(self._scb_bank_portion()), names, detail)

    def _scb_match_slip_line(self, line, sources, claimed):
        u"""จับคู่ "สลิป 1 ใบ" กับรายการเดินบัญชี แล้วเขียนผลลงบรรทัดนั้น

        :param claimed: set ของ statement id ที่สลิปใบอื่นในใบรับชำระเดียวกัน
                        จับจองไปแล้ว — กันไม่ให้สลิป 2 ใบชี้รายการเงินเข้าอันเดียวกัน
        """
        self.ensure_one()
        Statement = self.env['npd.scb.bank.statement'].sudo()

        Alias = self.env['npd.scb.counterparty.alias'].sudo()

        def done(state, reason, statement=None):
            line.sudo().write({
                'state': state,
                'reason': reason,
                'statement_id': statement.id if statement else False,
            })
            # จับคู่ได้แล้ว -> จำไว้ว่าชื่อผู้โอนที่ธนาคารบันทึก = ลูกค้ารายนี้
            # ครั้งหน้าที่ลูกค้าคนเดิมโอนมาจะเทียบได้ทันที ไม่ต้องพึ่ง AI อีก
            # จำเฉพาะรายการที่เข้าบัญชีของบริษัทเรา — ถ้าจำชื่อจากบัญชีบริษัทอื่น
            # ด้วย การจับคู่ผิดครั้งเดียวจะกลายเป็นชื่อที่ระบบเชื่อถาวร แล้วผิดซ้ำ
            if state == 'matched' and statement and statement.belongs_to_company(
                    self._scb_own_account_names(), self._scb_own_account_numbers()):
                Alias.remember(self.partner_id, statement, payment=self)
            return state

        # ไฟล์ที่ไม่ใช่หลักฐานการโอน -> ข้ามไปเลย ไม่นับว่าตรวจไม่ผ่าน
        if line.state == 'not_slip':
            return done('not_slip', line.reason or _(u"ไฟล์นี้ไม่ใช่สลิปการโอน"))

        if line.state == 'unreadable':
            return done('unreadable', line.reason or _(u"อ่านสลิปไม่ได้"))

        # สลิปจ่ายบิล (เลขอ้างอิงอย่าง REF001) -> ไม่ต้องตรวจ
        # ธนาคารบันทึกว่า "รับชำระค่าสินค้าและบริการ" โดยไม่ระบุชื่อผู้โอน
        keyword, ref_value = self._scb_slip_skip_reason(line)
        if keyword:
            return done('skipped', _(
                u"สลิปนี้เป็นการ \"จ่ายบิล\" (พบคำว่า \"%s\" ในเลขอ้างอิง: %s) — "
                u"ธนาคารไม่ระบุชื่อผู้โอน จึงเทียบไม่ได้"
            ) % (keyword, ref_value))

        raw = {}
        if line.raw:
            try:
                raw = json.loads(line.raw) or {}
            except (ValueError, TypeError):
                raw = {}

        amounts = []
        if line.slip_amount:
            amounts.append(round(line.slip_amount, 2))
        # ยอดสำรองจากสลิป (เช่น ยอดก่อน/หลังค่าธรรมเนียม) ที่ AI อ่านไว้
        for val in (raw.get('amount_candidates') or []):
            amt = self._scb_to_float(val)
            if amt > 0 and amt not in amounts:
                amounts.append(amt)

        # วันที่สำรอง — สลิปโอนข้ามธนาคาร (IPP/SMART) มัก "วันที่หักบัญชี"
        # กับ "วันที่เงินเข้าบัญชี" คนละวัน จึงลองจับคู่ทุกวันที่ที่ AI อ่านได้
        dates = []
        if line.slip_date:
            dates.append(line.slip_date)
        for val in (raw.get('date_candidates') or []):
            d = self._parse_slip_date(str(val)) if val else None
            if d and d not in dates:
                dates.append(d)

        notes = []
        if not amounts:
            return done('not_found', _(
                u"AI อ่านจำนวนเงินจากสลิปใบนี้ไม่ได้ — ตรวจสอบไม่ได้"))
        if not dates:
            if not self.date:
                return done('not_found', _(
                    u"ไม่มีวันที่ให้ใช้ตรวจสอบ (ทั้งในสลิปและในใบรับชำระ)"))
            dates = [self.date]
            notes.append(_(u"AI อ่านวันที่จากสลิปไม่ได้ — ใช้วันที่ในใบรับชำระแทน"))
        if len(dates) > 1:
            notes.append(_(u"สลิปมีหลายวันที่ (%s) — ลองจับคู่ให้ทุกวัน")
                         % u', '.join(str(d) for d in dates))

        # ยังไม่ถึงเวลาตรวจ (ข้อมูลธนาคารมาช้ากว่าจริง)
        lag = self._scb_param('verify_lag_days')
        ready_date = max(dates) + timedelta(days=lag)
        if fields.Date.context_today(self) < ready_date:
            return done('waiting', _(
                u"ข้อมูลการโอนของธนาคารมาช้ากว่าจริง %s วัน — "
                u"รายการวันที่ %s จะตรวจสอบได้ตั้งแต่วันที่ %s"
            ) % (lag, max(dates), ready_date))

        slip_sender = line.slip_sender or ''
        # ชื่อที่ยอมรับได้ = ชื่อในสลิป + ชื่อลูกค้าใน Odoo + ชื่อที่ระบบเคยจำไว้
        # ตัวสุดท้ายคือทางออกของชื่อที่ธนาคารถอดเสียงแบบไม่เป็นมาตรฐาน
        known = Alias.names_for_partner(self.partner_id)
        if known:
            notes.append(_(u"ใช้ชื่อที่ระบบจำไว้ประกอบ %s รายการ") % len(known))
        own_names = self._scb_own_account_names()
        own_numbers = self._scb_own_account_numbers()
        match_kwargs = {
            # ส่งไปเป็นตัวตัดสินเมื่อหลายแถวได้คะแนนเท่ากัน — เลือกแถวที่เข้า
            # บัญชีบริษัทเราก่อน ไม่ใช่แถวที่บังเอิญเจอก่อน
            'own_names': own_names,
            'own_numbers': own_numbers,
            'amount': amounts,
            'names': [n for n in [slip_sender, self.partner_id.name] + known if n],
            'sources': sources,
            'amount_tol': self._scb_param('verify_amount_tolerance'),
            'day_tol': self._scb_param('verify_date_tolerance'),
            'name_threshold': self._scb_param('verify_name_threshold'),
            'account_hint': line.slip_sender_acc,
            'time_hint': line.slip_time,
            'time_tol': self._scb_param('verify_time_tolerance_min'),
        }
        amount_label = u' / '.join('{:,.2f}'.format(a) for a in amounts)

        def usable(records):
            u"""ตัดรายการที่สลิปใบอื่นในใบรับชำระเดียวกันจับจองไปแล้วออก"""
            return records.filtered(lambda r: r.id not in claimed)

        # ธนาคารที่เดาจากสมุดรายวันเป็นแค่ "ที่น่าจะใช่" — ลูกค้าโอนเข้าบัญชีไหน
        # ก็ได้ (เจอจริง: ใบสมุดรายวันค่าประกันแต่เงินเข้า SCB และกลับกัน)
        # จึงค้นในธนาคารที่คาดไว้ก่อน ถ้าไม่เจอค่อยขยายไปธนาคารอื่นที่ตั้งค่าไว้
        search_sets = [sources]
        if self._scb_param('verify_cross_bank_fallback'):
            wider = sources + [s for s in Statement.statement_codes()
                               if s not in sources]
            if len(wider) > len(sources):
                search_sets.append(wider)

        # เงินเข้าที่เข้า "บัญชีของบริษัทเรา" น่าเชื่อถือกว่าเสมอ ถ้าเจอรายการที่
        # เข้าบัญชีบริษัทอื่นก่อน ต้องค้นต่อให้ครบก่อนค่อยยอมรับตัวนั้น
        # (เจอจริง: ยอด 2,200 วันเดียวกันมีทั้งในบัญชีเราและบัญชีบริษัทอื่น
        #  ตัวที่เจอก่อนเป็นของบริษัทอื่น เลยจับคู่ผิดแล้วจำชื่อผิดไว้ด้วย)
        def accept(statement, matched_date):
            if matched_date != dates[0]:
                notes.append(_(u"จับคู่ได้ด้วยวันที่สำรองจากสลิป (%s)") % matched_date)
            if statement.source not in sources:
                notes.append(_(
                    u"เงินเข้าบัญชี %s ไม่ใช่ %s ที่คาดจากสมุดรายวัน"
                ) % (statement.source.upper(),
                     u'/'.join(s.upper() for s in sources)))
            return done('matched', self._scb_success_reason(
                statement, amount_label, matched_date, slip_sender, notes), statement)

        match, slip_date = None, dates[0]
        foreign_hit = None      # รายการที่ตรงแต่เข้าบัญชีบริษัทอื่น (ไว้ใช้ทีหลัง)
        for srcs in search_sets:
            match_kwargs['sources'] = srcs
            for d in dates:
                result = Statement.find_incoming_match(date=d, **match_kwargs)
                statement = result['statement']
                if result['matched'] and statement.id not in claimed:
                    if statement.belongs_to_company(own_names, own_numbers):
                        return accept(statement, d)
                    if foreign_hit is None:
                        foreign_hit = (statement, d)
                if match is None or (usable(result['amount_date_candidates'])
                                     and not usable(match['amount_date_candidates'])):
                    match, slip_date = result, d
        # ขั้นถัดไป (AI รอบสอง / เทียบชื่อ) ให้ใช้ชุดที่กว้างที่สุดที่ค้นไปแล้ว
        sources = match_kwargs['sources']

        # ค้นครบแล้วไม่มีรายการที่เข้าบัญชีเราเลย จึงค่อยยอมรับของบริษัทอื่น
        if foreign_hit is not None:
            return accept(*foreign_hit)

        candidates = usable(match['amount_date_candidates'])

        # รอบสอง: ให้ AI ดูสลิปใบนี้เทียบกับรายการในบัญชีโดยตรง
        if self._scb_param('verify_second_pass'):
            second = self._scb_second_opinion(line, dates, amounts, sources)
            rec = (second or {}).get('statement')
            if rec is not None and rec and rec.id not in claimed:
                ai = second.get('ai') or {}
                self._scb_apply_second_pass(line, ai)
                notes.append(_(
                    u"รอบแรกจับคู่ไม่ได้ — ยืนยันโดย AI รอบสอง: %s")
                    % (ai.get('reason') or '-'))
                return done('matched', self._scb_success_reason(
                    rec, '{:,.2f}'.format(rec.deposit), rec.date,
                    line.slip_sender or slip_sender, notes), rec)
            if second and (second.get('ai') or {}).get('reason'):
                notes.append(_(u"ตรวจซ้ำรอบสองแล้วยังไม่พบรายการที่ตรง: %s")
                             % second['ai']['reason'])

        if not candidates:
            if not match['has_data_for_date'] or not self._scb_has_own_data(
                    sources, slip_date, self._scb_param('verify_date_tolerance')):
                return done('waiting', _(
                    u"ยังไม่มีรายการเดินบัญชีของบัญชีบริษัทเราในวันที่ %s "
                    u"(ข้อมูลจากธนาคารยังมาไม่ครบ) — ระบบจะตรวจให้อัตโนมัติอีกครั้ง"
                ) % slip_date + self._scb_notes_text(notes))
            # สลิปจ่ายบิล + บัญชีเรายังไม่มีรายการแยกรายคนของวันนั้น = เทียบไม่ได้
            # จริง ๆ ไม่ใช่ "ตรวจไม่ผ่าน" (ดูคำอธิบายใน _scb_bill_rows_available)
            if (raw.get('is_bill_payment')
                    and not self._scb_bill_rows_available(sources, slip_date)):
                return done('skipped', _(
                    u"สลิปนี้เป็นการ \"จ่ายบิล\" และรายการเดินบัญชีของบริษัทเรา "
                    u"วันที่ %s ยังมีแต่แถวสรุปยอดรวมรายวัน (ไม่มีชื่อผู้โอน) "
                    u"ยังไม่มีรายการแยกรายคน จึงเทียบไม่ได้ — เมื่อชีตเพิ่มรายการ "
                    u"แยกรายคนของบัญชีนี้แล้ว ระบบจะตรวจให้เองอัตโนมัติ"
                ) % slip_date + self._scb_notes_text(notes))
            reason = _(
                u"ไม่พบรายการเงินเข้าที่ตรงกับสลิปใบนี้\n"
                u"• จำนวนเงินจากสลิป: %s\n"
                u"• วันที่: %s\n"
                u"• ผู้โอน: %s"
            ) % (amount_label, slip_date, slip_sender or '-')
            other = usable(match['amount_candidates'])
            if other:
                reason += _(u"\n\nพบรายการที่ยอดตรงกันแต่คนละวัน: %s") % u', '.join(
                    u'%s (%s)' % (r.date, r.description or '-') for r in other[:5])
            else:
                reason += _(u"\n\nไม่พบรายการเงินเข้ายอดนี้ในบัญชีเลย")
            return done('not_found', reason + self._scb_notes_text(notes))

        # พบรายการที่ตรงยอด+วันที่ แต่ชื่อไม่ผ่าน -> ให้ AI ช่วยเทียบข้ามภาษาอีกที
        named = candidates.filtered(lambda r: r.counterparty)
        if slip_sender and named and self._scb_param('verify_ai_name_fallback'):
            # ส่ง description เต็ม (มีรหัสธนาคาร + เลขบัญชีย่อ) ให้ AI ใช้ประกอบ
            bank_names = [r.description or r.counterparty for r in named]
            idx = self._scb_ai_same_company(
                slip_sender, bank_names, slip_account=line.slip_sender_acc)
            if idx is not None:
                rec = named[idx]
                notes.append(_(u"ชื่อผู้โอนยืนยันโดย AI (เทียบข้ามภาษา/ชื่อถูกตัดท้าย)"))
                return done('matched', self._scb_success_reason(
                    rec, amount_label, slip_date, slip_sender, notes), rec)

        # ธนาคารไม่ระบุชื่อผู้โอน (เช่น จ่ายผ่านบิลเพย์เมนต์/CrossBank)
        unnamed = candidates.filtered(lambda r: not r.counterparty)
        if unnamed and self._scb_param('verify_allow_no_name'):
            if len(candidates) == 1:
                notes.append(_(
                    u"ธนาคารไม่ได้ระบุชื่อผู้โอนในรายการนี้ (เช่น ชำระผ่านบิลเพย์เมนต์) — "
                    u"ยืนยันด้วยจำนวนเงินและวันที่"))
                return done('matched', self._scb_success_reason(
                    candidates[0], amount_label, slip_date, slip_sender, notes),
                    candidates[0])
            return done('not_found', _(
                u"พบรายการเงินเข้า %s รายการที่ยอด %s วันที่ %s ตรงกัน "
                u"แต่ชื่อผู้โอนไม่ตรง/ธนาคารไม่ได้ระบุชื่อ จึงชี้ชัดไม่ได้ว่าเป็นรายการใด "
                u"— กรุณาตรวจสอบด้วยตนเอง\n"
                u"• ชื่อในสลิป: %s\n"
                u"• รายการที่พบ: %s"
            ) % (len(candidates), amount_label, slip_date, slip_sender or '-',
                 u' | '.join(r.description or '-' for r in candidates[:5]))
                + self._scb_notes_text(notes))

        bank_names_txt = u', '.join(
            u'"%s"' % (r.counterparty or r.description or '-') for r in candidates[:5])
        return done('not_found', _(
            u"ชื่อผู้โอนไม่ตรงกับรายการของธนาคาร\n"
            u"• ชื่อในสลิป: %s\n"
            u"• ชื่อในรายการธนาคาร: %s\n"
            u"• จำนวนเงิน %s และวันที่ %s ตรงกัน\n"
            u"(คะแนนความเหมือนสูงสุด %.2f ต่ำกว่าเกณฑ์ %.2f)"
        ) % (slip_sender or '-', bank_names_txt, amount_label, slip_date,
             match['score'], self._scb_param('verify_name_threshold'))
            + self._scb_notes_text(notes))

    def _scb_update_slip_summary(self, lines):
        u"""สรุปค่าจากทุกสลิปมาไว้ที่หัวใบรับชำระ (ใช้แสดงในตาราง/ค้นหา)

        จำนวนเงิน = ผลรวมทุกสลิป เพราะลูกค้าอาจโอนแยกหลายครั้ง
        """
        self.ensure_one()
        # ไฟล์ที่ไม่ใช่สลิป (50 ทวิ / ใบกำกับภาษี) มียอดกับวันที่เหมือนกัน
        # ถ้าเอามารวมด้วย ยอดกับชื่อผู้โอนที่หัวใบจะเพี้ยน
        lines = lines.filtered(lambda l: l.state not in ('not_slip', 'duplicate'))
        dates = [l.slip_date for l in lines if l.slip_date]
        senders = []
        for line in lines:
            name = (line.slip_sender or '').strip()
            if name and name not in senders:
                senders.append(name)
        self.sudo().write({
            'scb_slip_read': bool(lines),
            'scb_slip_date': max(dates) if dates else False,
            'scb_slip_amount': sum(lines.mapped('slip_amount')),
            'scb_slip_sender': u' / '.join(senders) or False,
            'scb_slip_sender_acc': lines[0].slip_sender_acc if lines else False,
            'scb_slip_ref': u' / '.join(
                l.slip_ref for l in lines if l.slip_ref) or False,
        })

    def _scb_apply_second_pass(self, line, ai):
        u"""เขียนค่าที่ AI อ่านใหม่ในรอบสองทับของเดิม (ระดับสลิป)

        รอบสองได้เห็นรายการจริงในบัญชีประกอบ ค่าที่อ่านได้จึงน่าเชื่อถือกว่ารอบแรก
        (โดยเฉพาะ "วันที่" ที่รอบแรกมักอ่านผิดจากสลิปที่มีหลายวันที่)
        """
        vals = {}
        raw_date = (ai.get('slip_date') or '').strip() if ai.get('slip_date') else ''
        parsed = self._parse_slip_date(raw_date) if raw_date else None
        if parsed and parsed != line.slip_date:
            vals['slip_date'] = parsed
        amount = self._scb_to_float(ai.get('slip_amount'))
        if amount > 0 and round(amount, 2) != round(line.slip_amount or 0.0, 2):
            vals['slip_amount'] = round(amount, 2)
        sender = (ai.get('slip_sender_name') or '').strip()
        if sender and sender != (line.slip_sender or ''):
            vals['slip_sender'] = sender
        if vals:
            line.sudo().write(vals)

    @api.model
    def _scb_public_summary(self, state):
        u"""ข้อความสั้นที่พนักงานทั่วไปเห็น — บอกว่าต้องทำอะไรต่อ แต่ไม่บอกเกณฑ์

        เจตนา: ไม่เปิดเผยว่าระบบเทียบอะไรบ้าง (ชื่อ/ยอด/วันที่/เวลา/เลขบัญชี)
        และไม่บอกคะแนน เพื่อไม่ให้เดาได้ว่าต้องทำสลิปอย่างไรจึงจะ "ผ่าน"
        รายละเอียดเต็มดูได้เฉพาะผู้จัดการบัญชี
        """
        return {
            'success': _(u"โอนสำเร็จ — ตรวจสอบกับรายการเดินบัญชีของธนาคารแล้ว"),
            'other_company': _(u"เงินเข้าแล้ว แต่เข้าบัญชีของบริษัทอื่นในเครือ "
                               u"— กรุณาแจ้งฝ่ายบัญชีปรับบัญชีระหว่างกัน"),
            'failed': _(u"ตรวจสอบไม่ผ่าน — กรุณาแจ้งฝ่ายบัญชีตรวจสอบ"),
            'waiting': _(u"รอข้อมูลจากธนาคาร ระบบจะตรวจให้อัตโนมัติอีกครั้ง"),
            'no_slip': _(u"ยังไม่ได้แนบสลิปการโอนเงิน"),
            'skipped': _(u"รายการนี้ไม่ต้องตรวจสอบการโอน"),
            'to_check': _(u"รอตรวจสอบ"),
        }.get(state, '')

    @staticmethod
    def _scb_notes_text(notes):
        return (u"\n\nหมายเหตุ:\n" + u'\n'.join(u"• %s" % n for n in notes)) if notes else ''

    def _scb_success_reason(self, statement, amount_label, slip_date, sender, notes):
        return _(
            u"จับคู่กับรายการเงินเข้าของธนาคารได้\n"
            u"• ธนาคาร: %s  วันที่ %s %s\n"
            u"• เงินเข้า: %s\n"
            u"• รายละเอียดจากธนาคาร: %s\n"
            u"• ผู้โอนตามสลิป: %s"
        ) % (
            dict(statement._fields['source'].selection).get(statement.source, statement.source),
            statement.date, statement.time or '',
            '{:,.2f}'.format(statement.deposit),
            statement.description or '-',
            sender or '-',
        ) + self._scb_notes_text(notes)

    # ------------------------------------------------------------------
    # ปุ่ม / cron
    # ------------------------------------------------------------------
    def action_scb_verify_transfer(self):
        u"""ปุ่ม "ตรวจสอบการโอน" บนหน้ารับชำระ — อ่านสลิปแล้วจับคู่กับธนาคารทันที"""
        self.ensure_one()
        res = self._scb_verify_one(force_reread=self.env.context.get('scb_force_reread', False))
        state_label = dict(self._fields['scb_verify_state'].selection).get(res['state'])
        # พนักงานทั่วไปเห็นเฉพาะข้อความสรุป ไม่เห็นเกณฑ์การตรวจ
        message = res['reason'] if self.env.user.has_group(
            'account.group_account_manager') else self._scb_public_summary(res['state'])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(u"ผลตรวจสอบการโอน: %s") % state_label,
                'message': message,
                'type': 'success' if res['state'] == 'success' else (
                    'warning' if res['state'] in ('waiting', 'other_company')
                    else 'danger'),
                'sticky': res['state'] != 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_scb_show_detail(self):
        u"""ไอคอนในตาราง "ผลตรวจสอบการโอน" -> เปิด popup ดูรายละเอียดผลตรวจ

        รายละเอียดเต็ม (เกณฑ์/คะแนน) ถูกจำกัดด้วย groups ที่ตัวฟิลด์อยู่แล้ว
        พนักงานทั่วไปจึงเห็นแค่สรุปกับผลรายสลิป ไม่เห็นว่าระบบเทียบอะไร
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _(u"ผลตรวจสอบการโอน — %s") % (self.name or ''),
            'res_model': 'account.payment',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'npd_scb_auto_payment.view_account_payment_scb_detail_form').id, 'form')],
            'target': 'new',
        }

    def action_scb_verify_selected(self):
        u"""ตรวจสอบการโอนของใบที่ติ๊กเลือกไว้ (เรียกจากเมนู Action ของตาราง)

        อัปเดตสถานะ "บนใบเดิม" ไม่สร้างรายการใหม่ — กดซ้ำได้เรื่อย ๆ เพื่อดูสถานะ
        ล่าสุดหลังรายการเดินบัญชีถูก sync เข้ามาเพิ่ม
        ใช้ค่าที่ AI เคยอ่านจากสลิปไว้แล้ว (ไม่อ่านซ้ำ) จึงไม่เปลืองโควตา
        ถ้าต้องการให้ AI อ่านสลิปใหม่ ให้เปิดใบนั้นแล้วกด "ตรวจสอบการโอนใหม่"
        """
        labels = dict(self._fields['scb_verify_state'].selection)
        tally, skipped, errors = {}, 0, 0
        for payment in self:
            if (payment.payment_type != 'inbound'
                    or payment.partner_type != 'customer'
                    or payment.state not in POSTED_STATES):
                skipped += 1
                continue
            # ต้องครอบด้วย savepoint ไม่งั้นถ้าใบใดพังระดับฐานข้อมูล
            # PostgreSQL จะ abort ทั้ง transaction แล้วใบที่เหลือ (รวมถึงใบที่
            # จับคู่สำเร็จ) จะเขียนลงไม่ได้เลย — savepoint จะ rollback เฉพาะใบที่พัง
            try:
                with self.env.cr.savepoint():
                    res = payment._scb_verify_one()
                tally[res['state']] = tally.get(res['state'], 0) + 1
            except Exception:  # noqa: BLE001 - ใบเดียวพังต้องไม่ล้มทั้งชุด
                self.env.clear()   # ทิ้ง cache ที่ค้างจากใบที่ถูก rollback
                _logger.exception("SCB verify: ตรวจใบรับชำระ id=%s ไม่สำเร็จ", payment.id)
                errors += 1

        parts = [u"%s %s ใบ" % (labels.get(k, k), v) for k, v in tally.items()]
        if skipped:
            parts.append(_(u"ข้าม %s ใบ (ไม่ใช่เงินรับจากลูกค้า หรือยังไม่ลงบันทึก)")
                         % skipped)
        if errors:
            parts.append(_(u"ผิดพลาด %s ใบ") % errors)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(u"ตรวจสอบการโอนเรียบร้อย"),
                'message': u' · '.join(parts) or _(u"ไม่มีใบที่ตรวจได้"),
                'type': 'success' if not errors else 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_scb_reset_verify(self):
        u"""ล้างผลตรวจของใบที่เลือก ให้กลับไปเป็น "รอตรวจสอบ"

        ใช้เมื่อผลเก่าค้างอยู่จนแก้ไม่ตก เช่น ตรวจไม่สำเร็จจนครบเพดานแล้ว cron
        เลิกตรวจให้ หรือค่าที่ AI เคยอ่านไว้ผิดจนจับคู่ไม่ได้สักที

        ลบเฉพาะ "ผลตรวจ" เท่านั้น — ใบรับชำระ ไฟล์แนบ และรายการทางบัญชี
        ไม่ถูกแตะต้อง รอบถัดไประบบจะให้ AI อ่านสลิปใหม่แล้วตรวจให้เอง
        """
        Slip = self.env['npd.scb.payment.slip'].sudo()
        lines = Slip.search([('payment_id', 'in', self.ids)])
        line_count = len(lines)
        lines.unlink()
        self.sudo().write({
            'scb_verify_state': 'to_check',
            'scb_verify_summary': self._scb_public_summary('to_check'),
            'scb_verify_reason': False,
            'scb_verify_datetime': False,
            'scb_verify_attempts': 0,
            'scb_statement_id': False,
            'scb_slip_read': False,
            'scb_slip_date': False,
            'scb_slip_amount': 0.0,
            'scb_slip_sender': False,
            'scb_slip_sender_acc': False,
            'scb_slip_ref': False,
        })
        _logger.info(u"SCB: ล้างผลตรวจ %s ใบ (ลบผลรายสลิป %s บรรทัด) โดย %s",
                     len(self), line_count, self.env.user.display_name)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(u"ล้างผลตรวจเรียบร้อย"),
                'message': _(
                    u"ล้างผลตรวจ %s ใบ (ลบผลรายสลิป %s บรรทัด) — "
                    u"ระบบจะตรวจให้ใหม่ในรอบถัดไป หรือกด "
                    u"\"ตรวจสอบการโอนอีกครั้ง\" เพื่อตรวจทันที"
                ) % (len(self), line_count),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_scb_verify_transfer_again(self):
        u"""ตรวจใหม่ทั้งหมด — บังคับให้ AI อ่านสลิปซ้ำ (ใช้เมื่อเปลี่ยนไฟล์แนบ)

        รีเซ็ตตัวนับด้วย เพื่อให้ระบบกลับมาลองซ้ำอัตโนมัติได้อีกรอบ
        (กรณีที่เคยชนเพดานไปแล้ว)
        """
        self.ensure_one()
        self.sudo().write({'scb_verify_attempts': 0})
        return self.with_context(scb_force_reread=True).action_scb_verify_transfer()

    @api.model
    def _scb_pending_domain(self):
        u"""ใบรับชำระที่ถึงคิวตรวจสอบ (ยึด "วันที่ในใบรับชำระ" ทั้งขอบบนและขอบล่าง)

        - ต้อง "ลงบันทึก (posted)" แล้วเท่านั้น — ใบร่างยังแก้ยอด/วันที่ได้อยู่
          การตีตราว่าโอนสำเร็จตั้งแต่ตอนเป็นร่างจึงไม่มีความหมาย
        - ขอบล่าง = วันที่เริ่มตรวจสอบที่ตั้งไว้ (ไม่ไล่ย้อนหลังเกินจุดนี้)
        - ขอบบน   = วันนี้ - จำนวนวันที่ข้อมูลธนาคารมาช้า (โอนวันนี้ -> ตรวจพรุ่งนี้)

        สถานะที่เข้าคิว:
          • รอตรวจสอบ / ยังไม่แนบสลิป / รอข้อมูลจากธนาคาร -> ตรวจซ้ำเรื่อย ๆ
          • ไม่สำเร็จ -> ตรวจซ้ำจนครบเพดานที่ตั้งไว้ (รายการเดินบัญชีของวันนั้น
            อาจเข้ามาไม่ครบตอนตรวจรอบแรก) ครบแล้วหยุด รอให้คนตรวจเอง
          • โอนสำเร็จ -> ไม่ตรวจซ้ำอีก
        """
        lag = self._scb_param('verify_lag_days')
        cutoff = fields.Date.context_today(self) - timedelta(days=lag)
        domain = [
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state', 'in', POSTED_STATES),
            ('date', '<=', cutoff),
        ]
        start = self._scb_verify_start_date()
        if start:
            domain.append(('date', '>=', start))
        domain += self._scb_state_domain()
        return domain

    @api.model
    def _scb_state_domain(self):
        u"""ส่วนของ domain ที่คัดตามสถานะการโอน (ใช้ร่วมกับหน้าตั้งค่า)"""
        pending = ('to_check', 'no_slip', 'waiting', False)
        retry = self._scb_param('verify_retry_failed')
        if retry > 0:
            return ['|',
                    ('scb_verify_state', 'in', pending),
                    '&', ('scb_verify_state', '=', 'failed'),
                         ('scb_verify_attempts', '<', retry)]
        return [('scb_verify_state', 'in', pending)]

    @api.model
    def _cron_scb_verify_transfers(self):
        u"""Scheduled Action: ตรวจสอบใบรับชำระที่ยังไม่ได้ตรวจ (ทีละชุด)"""
        if not self._scb_param('verify_enabled'):
            return
        limit = self._scb_param('verify_batch_limit')
        payments = self.sudo().search(self._scb_pending_domain(),
                                      order='date asc, id asc', limit=limit)
        _logger.info("SCB verify: เริ่มตรวจสอบ %s ใบรับชำระ", len(payments))
        for payment in payments:
            # savepoint กันไม่ให้ใบที่พังทำ transaction ทั้งก้อนใช้ต่อไม่ได้
            try:
                with self.env.cr.savepoint():
                    payment._scb_verify_one()
                self.env.cr.commit()
            except Exception as e:  # noqa: BLE001 - หนึ่งใบพังต้องไม่ล้มทั้ง cron
                self.env.clear()
                _logger.exception("SCB verify: ตรวจสอบใบรับชำระ id=%s ไม่สำเร็จ", payment.id)
                try:
                    with self.env.cr.savepoint():
                        payment.sudo().write({
                            'scb_verify_state': 'waiting',
                            'scb_verify_summary': self._scb_public_summary('waiting'),
                            'scb_verify_reason': _(u"ตรวจสอบไม่สำเร็จ: %s") % e,
                            'scb_verify_datetime': fields.Datetime.now(),
                        })
                    self.env.cr.commit()
                except Exception:  # noqa: BLE001
                    self.env.cr.rollback()
                    _logger.exception(
                        "SCB verify: บันทึกสถานะของ id=%s ไม่สำเร็จ", payment.id)

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------
    @staticmethod
    def _scb_to_float(value):
        if value in (None, '', False):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        s = re.sub(r'[^\d.\-]', '', str(value))
        try:
            return float(s) if s not in ('', '-', '.', '-.') else 0.0
        except (ValueError, TypeError):
            return 0.0

    def action_draft(self):
        u"""กลับเป็นร่าง = ต้องตรวจสอบการโอนใหม่

        ล้างผลจับคู่ของทุกสลิปด้วย เพื่อปล่อยรายการเงินเข้าที่เคยจับจองไว้
        แต่ยังเก็บค่าที่ AI อ่านได้ไว้ จะได้ไม่ต้องเรียก AI ซ้ำตอนตรวจใหม่
        """
        res = super(AccountPayment, self).action_draft()
        self.sudo().write({
            'scb_verify_state': 'to_check',
            'scb_verify_reason': False,
            'scb_statement_id': False,
            'scb_verify_attempts': 0,
        })
        self.mapped('scb_slip_ids').sudo().write({
            'state': 'to_check', 'reason': False, 'statement_id': False,
        })
        return res
