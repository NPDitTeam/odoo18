# -*- coding: utf-8 -*-
"""บทสนทนาของ "ตัวช่วย AI-IT"

หนึ่ง session = หนึ่งเรื่องที่พนักงานแจ้งเข้ามา เก็บสถานะไว้ว่าคุยถึงขั้นไหนแล้ว
เพราะแชทเป็นการคุยหลายรอบ (ถามเลขเอกสาร -> ถามจำนวนสต๊อกจริง -> ยืนยัน -> ทำ)

จุดที่ต้องระวัง: ตัวจัดการข้อความถูกเรียกอยู่ "ภายในทรานแซกชันเดียวกับการส่ง
ข้อความของพนักงาน" ถ้าปล่อยให้ error หลุดออกไป ข้อความที่พนักงานเพิ่งพิมพ์จะถูก
rollback หายไปทั้งข้อความ ทุกอย่างจึงต้องอยู่ใน savepoint และห้ามโยน error ออก
"""
import json
import logging
import re
from datetime import date, datetime, timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.misc import html_escape

# ป้ายชื่อของสองวิธีปัดเศษ VAT — เอามาจากที่เดียวกับตัวคำนวณ จะได้ไม่เขียนซ้ำ
# แล้วเพี้ยนกันทีหลัง (ดู ai_it_vat_fix.py)
from .ai_it_vat_fix import MODE_HOW as VAT_MODE_HOW
from .ai_it_vat_fix import MODE_NAME as VAT_MODE_NAME
from .ai_it_vat_fix import MODE_WHO as VAT_MODE_WHO

_logger = logging.getLogger(__name__)

BOT_XMLID = 'npd_ai_it_assistant.partner_ai_it_bot'

# เก็บประวัติแชทไว้กี่วัน (0 = ไม่ล้าง)
CHAT_HISTORY_DAYS_PARAM = 'npd_ai_it_assistant.chat_history_days'
CHAT_HISTORY_DAYS_DEFAULT = '14'

# หัวข้อไหนเริ่มบทสนทนาที่ขั้นตอนใด (หัวข้อที่ยังไม่มี handler จะตกไปที่เมนู)
TOPIC_START_STATE = {
    'stock_not_enough': 'ask_doc',
    'invoice_date_fix': 'ask_url',
    'return_date_fix': 'ask_return_doc',
    'rental_status_fix': 'ask_rental_doc',
    'vat_round_fix': 'ask_vat_doc',
}

# ไอคอนประจำหัวข้อ ใช้เป็นจุดสังเกตหัวเรื่องในแชท
TOPIC_ICONS = {
    'stock_not_enough': '📦',
    'invoice_date_fix': '📅',
    'return_date_fix': '↩️',
    'rental_status_fix': '🔄',
    'vat_round_fix': '🧮',
}

# หัวข้อ 5 — คำที่พนักงานใช้เลือกวิธีปัดเศษ VAT
# ตอบเป็นเลข 1/2 ก็ได้ (จัดการแยกในตัวอ่านคำตอบ) หรือพิมพ์เป็นคำก็ได้
VAT_TOTAL_WORDS = {'ยอดรวม', 'แบบยอดรวม', 'รวม', 'แบบรวม', 'คิดจากยอดรวม',
                   'จากยอดรวม', 'total'}
VAT_LINE_WORDS = {'รายบรรทัด', 'แบบรายบรรทัด', 'บรรทัด', 'แบบบรรทัด',
                  'ทีละบรรทัด', 'ถอย', 'ถอยกลับ', 'ย้อนกลับ', 'คืนค่าเดิม',
                  'ค่าเดิม', 'แบบเดิม', 'เหมือนเดิม', 'undo', 'revert', 'line'}

CANCEL_WORDS = {'ยกเลิก', 'เลิก', 'จบ', 'ไม่ต้อง', 'cancel', 'exit', 'quit', 'stop', 'no'}
CONFIRM_WORDS = {'ยืนยัน', 'ตกลง', 'ทำเลย', 'ok', 'okay', 'confirm', 'yes', 'y', 'ใช่'}
# ใช้ตอนถามว่าจะให้ตัดสต๊อกต่อให้เลยไหม (หลังเติมสต๊อกเสร็จ)
CONTINUE_WORDS = {'ทำต่อ', 'ต่อ', 'ตัดต่อ', 'ตัดเลย', 'ตัดสต๊อก', 'ตัดสต็อก',
                  'ตัดสต๊อกเลย', 'ตัดสต็อกเลย', 'ทำเลย', 'เอาเลย', 'ตกลง',
                  'continue', 'next', 'go', 'ok', 'okay', 'yes', 'y'}
# พิมพ์คำเหล่านี้เมื่อไรก็ได้ เพื่อกลับไปเลือกหัวข้อใหม่โดยไม่ต้องกลับไปที่แท็บ
RESTART_WORDS = {'เริ่มใหม่', 'เริ่มต้นใหม่', 'เริ่ม', 'ทำใหม่', 'เมนู', 'หัวข้อ',
                 'เลือกหัวข้อ', 'ช่วยด้วย', 'menu', 'restart', 'reset', 'start', 'help'}

# คำลงท้ายสุภาพ/เครื่องหมายวรรคตอน ที่ต้องตัดทิ้งก่อนเทียบคำสั่ง
# (พนักงานพิมพ์ "ยืนยันครับ" / "เริ่มใหม่ค่ะ" กันเป็นปกติ)
POLITE_SUFFIXES = ('ครับผม', 'ครับ', 'คับ', 'ค่ะ', 'คะ', 'ค่า', 'จ้า', 'จ้ะ',
                   'นะ', 'น่ะ', 'ฮะ', 'เลย', 'ด้วย')

# ใช้อ่านวันที่ที่พนักงานพิมพ์เป็นเดือนภาษาไทย
THAI_MONTHS = {
    'มกราคม': 1, 'ม.ค.': 1, 'มค': 1,
    'กุมภาพันธ์': 2, 'ก.พ.': 2, 'กพ': 2,
    'มีนาคม': 3, 'มี.ค.': 3, 'มีค': 3,
    'เมษายน': 4, 'เม.ย.': 4, 'เมย': 4,
    'พฤษภาคม': 5, 'พ.ค.': 5, 'พค': 5,
    'มิถุนายน': 6, 'มิ.ย.': 6, 'มิย': 6,
    'กรกฎาคม': 7, 'ก.ค.': 7, 'กค': 7,
    'สิงหาคม': 8, 'ส.ค.': 8, 'สค': 8,
    'กันยายน': 9, 'ก.ย.': 9, 'กย': 9,
    'ตุลาคม': 10, 'ต.ค.': 10, 'ตค': 10,
    'พฤศจิกายน': 11, 'พ.ย.': 11, 'พย': 11,
    'ธันวาคม': 12, 'ธ.ค.': 12, 'ธค': 12,
}


def _command_forms(text):
    """คืนรูปแบบทั้งหมดของข้อความที่เอาไปเทียบกับชุดคำสั่งได้

    ตัดช่องว่างและเครื่องหมายวรรคตอนออก แล้วไล่ตัดคำลงท้ายทีละชั้น
    เก็บทุกชั้นไว้ ("ทำเลยครับ" -> {"ทำเลยครับ", "ทำเลย", "ทำ"}) เพื่อไม่ให้
    การตัดคำลงท้ายไปทำลายคำสั่งที่ลงท้ายด้วยคำเดียวกันอย่าง "ทำเลย"
    """
    value = (text or '').strip().lower().strip('.,;:!?"\'()[]-–—').replace(' ', '')
    forms = {value}
    stripped = True
    while stripped:
        stripped = False
        for suffix in POLITE_SUFFIXES:
            if value.endswith(suffix) and len(value) > len(suffix):
                value = value[:-len(suffix)]
                forms.add(value)
                stripped = True
    return forms


def _is_command(text, words):
    return bool(_command_forms(text) & words)


def _fmt(value):
    """แสดงจำนวนแบบอ่านง่าย: 10.0 -> 10, 10.5 -> 10.5, 8519.34 -> 8,519.34"""
    value = float(value or 0.0)
    if abs(value - round(value)) < 0.005:
        return '{:,}'.format(int(round(value)))
    return '{:,.2f}'.format(value)


def _baht(value):
    """จำนวนเงิน — คงทศนิยม 2 ตำแหน่งเสมอ เพราะเรื่องนี้คุยกันที่ระดับสตางค์"""
    return '{:,.2f}'.format(float(value or 0.0))


# ======================================================================
# ตัวช่วยจัดรูปแบบข้อความในแชท
#
# กล่องแชทของ Odoo แคบมาก ข้อความยาว ๆ ติดกันจะอ่านไม่ออก จึงวางเป็นบล็อก
# สั้น ๆ คั่นด้วยบรรทัดว่าง + ใช้ป้ายกำกับสีจาง (Bootstrap) แทนการยัด emoji
# ทุกบรรทัด  ตัวสร้างข้อความทุกตัวต้อง escape ค่าที่มาจากผู้ใช้/ฐานข้อมูลเอง
# ======================================================================
BR = '<br/>'


def _dt(value):
    """วันที่แบบไทย 13/08/2026 (ว่าง = —)"""
    return value.strftime('%d/%m/%Y') if value else '—'


def _title(text, icon=''):
    return '<b>%s%s</b>' % ('%s ' % icon if icon else '', text)


def _kv(label, value):
    """บรรทัดป้ายกำกับ–ค่า: ป้ายสีจาง ตามด้วยค่า"""
    return '<span class="text-muted">%s</span> %s' % (label, value)


def _hint(text):
    """ข้อความประกอบ: สีจางเพื่อลดความเด่น แต่ "ห้ามย่อขนาดฟอนต์"

    เคยใช้คลาส small (80%) แล้วอ่านไม่ออกในกล่องแชทที่แคบอยู่แล้ว
    ใช้แค่สีจางก็แยกจากเนื้อหาหลักได้พอ
    """
    return '<span class="text-muted">%s</span>' % text


def _rows(*parts):
    """หลายบรรทัดที่อยู่ในบล็อกเดียวกัน (ชิดกัน)

    ใช้ <div> ต่อบรรทัดแทน <br/> เพราะควบคุมระยะห่างได้ด้วยคลาส Bootstrap
    """
    return ''.join('<div>%s</div>' % p for p in parts if p)


def _block(*groups):
    """หลายบล็อก คั่นด้วยระยะห่าง ให้กวาดตาอ่านทีละก้อนได้"""
    return ''.join('<div class="mb-2">%s</div>' % g for g in groups if g)


def _indent(text):
    """ย่อหน้าเข้าไปหนึ่งขั้น

    ห้ามใช้ &nbsp; ย่อหน้า — html_sanitize ของ Odoo แปลงเป็นช่องว่างธรรมดา
    แล้วเบราว์เซอร์ยุบรวมเหลือช่องเดียว ย่อหน้าจึงหายหมด (ทดสอบแล้ว)
    """
    return '<div class="ms-3">%s</div>' % text


def _bullets(items):
    return '<ul class="mb-0 ps-4">%s</ul>' % ''.join(
        '<li>%s</li>' % item for item in items)


# ป้ายสถานะเอกสารเป็นภาษาไทย (ของเดิมในระบบเป็นอังกฤษ อ่านในแชทแล้วสะดุด)
STATE_LABELS = {
    'draft': 'ฉบับร่าง',
    'posted': 'ลงบันทึกแล้ว',
    'cancel': 'ยกเลิกแล้ว',
}
# ต่อท้ายทุกข้อความที่รอคำตอบ พนักงานจะได้เห็นทางออกทุกขั้นตอน
COMMANDS_FOOTER = _hint('พิมพ์ "เริ่มใหม่" เพื่อเปลี่ยนหัวข้อ · '
                        '"ยกเลิก" เพื่อออกจากรายการนี้ (ใช้ได้ตลอด)')

PAYMENT_LABELS = {
    'not_paid': 'ยังไม่ชำระ',
    'in_payment': 'อยู่ระหว่างชำระ',
    'paid': 'ชำระแล้ว',
    'partial': 'ชำระบางส่วน',
    'reversed': 'กลับรายการแล้ว',
    'blocked': 'ระงับการชำระ',
    'invoicing_legacy': 'ระบบเก่า',
}


class NpdAiItSessionLine(models.Model):
    _name = 'npd.ai.it.session.line'
    _description = 'ตัวช่วย AI-IT : รายการสินค้าที่ถูกเติมสต๊อก'
    _order = 'id'

    session_id = fields.Many2one('npd.ai.it.session', string='บทสนทนา',
                                 required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='สินค้า')
    qty_needed = fields.Float(string='ต้องตัด')
    qty_before = fields.Float(string='สต๊อกก่อนเติม')
    qty_added = fields.Float(string='เติมเพิ่ม')
    qty_after = fields.Float(string='สต๊อกหลังเติม')


class NpdAiItSession(models.Model):
    _name = 'npd.ai.it.session'
    _description = 'ตัวช่วย AI-IT : บทสนทนา'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', string='พนักงาน', required=True, index=True,
                              default=lambda self: self.env.user)
    channel_id = fields.Many2one('discuss.channel', string='ห้องแชท', index=True, ondelete='cascade')
    topic_id = fields.Many2one('npd.ai.it.topic', string='หัวข้อ')
    state = fields.Selection([
        ('menu', 'กำลังเลือกหัวข้อ'),
        ('ask_doc', 'รอเลขเอกสาร'),
        ('ask_qty', 'รอจำนวนสต๊อกจริง'),
        ('confirm', 'รอการยืนยัน'),
        ('ask_cut', 'เติมสต๊อกแล้ว รอสั่งตัดสต๊อกต่อ'),
        ('ask_url', 'รอ URL ของเอกสาร'),
        ('ask_return_doc', 'รอเลขที่ใบคืน'),
        ('ask_return_date', 'รอวันที่คืนใหม่'),
        ('ask_rental_doc', 'รอเลขที่ใบสั่งขาย'),
        ('confirm_status', 'รอยืนยันการแก้สถานะการเช่า'),
        ('ask_vat_doc', 'รอใบแจ้งหนี้ที่จะแก้การปัดเศษ VAT'),
        ('ask_vat_mode', 'รอเลือกวิธีปัดเศษ VAT'),
        ('confirm_vat', 'รอยืนยันการแก้การปัดเศษ VAT'),
        ('ask_date', 'รอวันที่ใหม่'),
        ('ask_reason', 'รอหมายเหตุว่าแก้เพราะอะไร'),
        ('confirm_date', 'รอยืนยันการแก้วันที่'),
        ('confirm_cancel', 'รอยืนยันการยกเลิกเอกสาร'),
        ('done', 'ดำเนินการแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='menu', required=True, index=True)

    branch_id = fields.Many2one('res.branch', string='สาขา')
    location_id = fields.Many2one('stock.location', string='คลังปลายทางที่เติม')
    document_ref = fields.Char(string='เลขที่เอกสาร')
    document_model = fields.Char(string='โมเดลเอกสาร')
    document_id = fields.Integer(string='ไอดีเอกสาร')
    data_json = fields.Text(string='ข้อมูลระหว่างสนทนา', default='{}')
    change_note = fields.Char(
        string='หมายเหตุ (แก้เพราะอะไร)',
        help='เหตุผลที่พนักงานระบุตอนขอแก้วันที่ บันทึกคู่กับประวัติของเอกสาร',
    )
    summary = fields.Text(string='สรุปผล')
    line_ids = fields.One2many('npd.ai.it.session.line', 'session_id', string='รายการที่เติม')

    @api.depends('topic_id.name', 'document_ref')
    def _compute_display_name(self):
        for session in self:
            label = session.topic_id.name or 'ตัวช่วย AI-IT'
            if session.document_ref:
                label = '%s [%s]' % (label, session.document_ref)
            session.display_name = label

    # ------------------------------------------------------------------
    # ล้างประวัติแชทเก่า (เรียกจาก ir.cron ทุกวัน)
    # ------------------------------------------------------------------
    @api.model
    def _chat_history_days(self):
        """เก็บประวัติแชทไว้กี่วัน (ตั้งค่าทับได้ที่ System Parameters)"""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            CHAT_HISTORY_DAYS_PARAM, CHAT_HISTORY_DAYS_DEFAULT)
        try:
            days = int(raw)
        except (TypeError, ValueError):
            days = int(CHAT_HISTORY_DAYS_DEFAULT)
        return days if days > 0 else 0

    @api.model
    def _cron_clean_chat_history(self, limit=2000):
        u"""ลบข้อความในห้องแชทของบอทที่เก่ากว่า N วัน

        ห้องแชทของบอทสะสมข้อความเร็วมาก (บอทตอบยาวและตอบทุกครั้ง) ถ้าปล่อยไว้
        กล่องแชทจะโหลดช้าขึ้นเรื่อย ๆ  ลบเฉพาะ "ข้อความ" เท่านั้น —
        ตาราง npd.ai.it.history ที่เป็นหลักฐานว่าใครแก้อะไรยังอยู่ครบ

        ตัด limit ต่อรอบไว้ กันทรานแซกชันใหญ่เกินจนล็อกตารางข้อความทั้งระบบ
        รอบถัดไปของ cron จะเก็บส่วนที่เหลือต่อเอง
        """
        days = self._chat_history_days()
        if not days:
            _logger.info('ตัวช่วย AI-IT: ปิดการล้างประวัติแชทไว้ (%s = 0)',
                         CHAT_HISTORY_DAYS_PARAM)
            return 0

        bot = self._bot_partner()
        if not bot:
            return 0

        channels = self.env['discuss.channel'].sudo().search([
            ('channel_member_ids.partner_id', '=', bot.id),
        ])
        if not channels:
            return 0

        cutoff = fields.Datetime.now() - timedelta(days=days)
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', 'in', channels.ids),
            ('date', '<', cutoff),
        ], limit=limit, order='id')
        count = len(messages)
        if count:
            messages.unlink()
            _logger.info('ตัวช่วย AI-IT: ล้างข้อความแชทเก่ากว่า %d วัน จำนวน %d ข้อความ',
                         days, count)

        # บทสนทนาที่ค้างคามาเกิน N วัน ถือว่าเลิกไปแล้ว ปิดทิ้งด้วย
        # ไม่งั้นพนักงานพิมพ์อะไรมาใหม่ ระบบจะไปต่อจากขั้นตอนเก่าที่ข้อความหายไปแล้ว
        stale = self.sudo().search([
            ('state', 'not in', ('done', 'cancelled')),
            ('write_date', '<', cutoff),
        ])
        if stale:
            stale.write({'state': 'cancelled'})
            _logger.info('ตัวช่วย AI-IT: ปิดบทสนทนาค้างเก่า %d รายการ', len(stale))
        return count

    # ------------------------------------------------------------------
    # ตัวช่วยทั่วไป
    # ------------------------------------------------------------------
    @api.model
    def _bot_partner(self):
        return self.env.ref(BOT_XMLID, raise_if_not_found=False)

    def _get_data(self):
        self.ensure_one()
        try:
            data = json.loads(self.data_json or '{}')
        except (ValueError, TypeError):
            data = {}
        return data if isinstance(data, dict) else {}

    def _set_data(self, data):
        self.ensure_one()
        self.sudo().write({'data_json': json.dumps(data, ensure_ascii=False)})

    def _post_bot(self, body_html, commands=None):
        """ให้บอทพูดในห้องแชท

        commands = None (ค่าเริ่มต้น) -> ต่อท้ายด้วยคำสั่งที่ใช้ได้ตลอดให้อัตโนมัติ
        เมื่อบทสนทนายัง "รอคำตอบ" อยู่ พนักงานจะได้เห็นทางออกทุกขั้นตอน
        ไม่ต้องจำจากข้อความแรกข้อความเดียว

        ส่งค่า False เองเมื่อข้อความนั้นจะตามด้วยข้อความถัดไปทันที (จะได้ไม่ซ้ำ)
        """
        self.ensure_one()
        if commands is None:
            # 'menu' ไม่ต้องต่อท้าย เพราะตัวมันเองคือหน้าเลือกหัวข้ออยู่แล้ว
            commands = self.state not in ('done', 'cancelled', 'menu')
        if commands:
            body_html = _block(body_html, COMMANDS_FOOTER)
        channel = self.channel_id.sudo()
        bot = self._bot_partner()
        if not channel or not bot:
            return
        channel.with_context(
            mail_create_nosubscribe=True,
            npd_ai_it_bot=True,
        ).message_post(
            # Odoo 18 escape body ที่เป็น str ทั้งก้อน — ตัวสร้างข้อความทุกตัว escape
            # ค่าที่มาจากผู้ใช้/ฐานข้อมูลเองแล้ว (html_escape) จึงห่อ Markup ได้
            body=Markup(body_html),
            author_id=bot.id,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    @api.model
    def _post_bot_in_channel(self, channel, body_html):
        """ให้บอทพูดในห้องแชท โดยยังไม่มี session (ใช้ตอนแสดงเมนู/แจ้ง error)"""
        bot = self._bot_partner()
        if not channel or not bot:
            return
        channel.sudo().with_context(
            mail_create_nosubscribe=True,
            npd_ai_it_bot=True,
        ).message_post(
            body=Markup(body_html),
            author_id=bot.id,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    # ------------------------------------------------------------------
    # เปิดหัวข้อจากแท็บ "ตัวช่วย AI-IT" (เรียกผ่าน RPC จาก JS)
    # ------------------------------------------------------------------
    @api.model
    def action_start_topic(self, topic_id):
        topic = self.env['npd.ai.it.topic'].sudo().browse(int(topic_id))
        if not topic.exists() or not topic.active:
            return {'error': 'ไม่พบหัวข้อนี้'}
        if not topic._is_available_for_user(self.env.user):
            return {'error': 'คุณไม่มีสิทธิ์ใช้หัวข้อนี้'}

        bot = self._bot_partner()
        if not bot:
            return {'error': 'ยังไม่ได้ติดตั้งผู้ช่วย AI-IT กรุณาแจ้งฝ่าย IT'}

        # o18 channel_get คืน record (ฝั่ง RPC จะแปลงเป็น store data ให้เอง)
        channel = self.env['discuss.channel'].with_context(
            mail_create_nosubscribe=True,
        ).channel_get([bot.id])
        channel = channel.sudo()

        # ปิดบทสนทนาค้างของหัวข้อก่อนหน้า เพื่อไม่ให้สองเรื่องชนกันในห้องเดียว
        self.sudo().search([
            ('user_id', '=', self.env.user.id),
            ('channel_id', '=', channel.id),
            ('state', 'not in', ('done', 'cancelled')),
        ]).write({'state': 'cancelled'})

        session = self.sudo().create({
            'user_id': self.env.user.id,
            'channel_id': channel.id,
            'topic_id': topic.id,
            'state': TOPIC_START_STATE.get(topic.code, 'menu'),
        })
        session._post_intro()
        return {
            'bot_partner_id': bot.id,
            'channel_id': channel.id,
            'session_id': session.id,
            # ส่งข้อมูลห้องกลับไปให้ฝั่ง JS เปิดหน้าต่างแชทได้ตรง ๆ
            # (เปิดผ่าน partner ไม่ได้ เพราะ Odoo ห้ามแชทกับ partner ที่ไม่มี res.users
            #  ดู store.getPartner() "You can only chat with partners that have a dedicated user."
            #  — บอทของเราจงใจไม่มี user)
            'store_data': Store(channel.with_user(self.env.user)).get_result(),
        }

    def _post_intro(self):
        self.ensure_one()
        topic = self.topic_id
        if topic.intro_message:
            self._post_bot(topic.intro_message.replace('\n', '<br/>'))
            return
        # ไม่ต้องขึ้นชื่อ "ตัวช่วย AI-IT" ซ้ำ — กล่องแชทแสดงชื่อผู้ส่งอยู่แล้ว
        # ใช้ชื่อหัวข้อเป็นหัวเรื่องแทน จะได้รู้ทันทีว่ากำลังทำเรื่องอะไร
        heading = _title(html_escape(topic.name or ''),
                         TOPIC_ICONS.get(topic.code or '', '📌'))
        # ไม่ต้องต่อคำสั่งเอง — _post_bot() ต่อท้ายให้ทุกข้อความที่รอคำตอบอยู่แล้ว

        if topic.code == 'stock_not_enough':
            self._post_bot(_block(
                heading,
                'พิมพ์ <b>เลขที่เอกสาร</b> ที่ตัดสต๊อกไม่ผ่าน<br/>'
                + _hint('ใช้ได้ทั้งเลขใบสั่งขาย และเลขใบจัดส่ง'),
            ))
            return
        if topic.code == 'invoice_date_fix':
            self._post_bot(_block(
                heading,
                '<b>คัดลอก URL ของหน้าใบแจ้งหนี้</b>ที่ต้องการแก้ มาวางที่นี่<br/>'
                + _hint('ใช้ URL แทนเลขที่เอกสาร เพราะฉบับร่างยังไม่มีเลขที่ '
                        'แต่ใน URL มี id ของเอกสารอยู่เสมอ'),
                # ไม่ใช้ <code> เพราะ Bootstrap ย่อเหลือ 87.5% แล้วอ่านยากในแชท
                _rows(_hint('ตัวอย่าง'),
                      '<span class="text-muted">http://119.59.124.50:8070/odoo/'
                      'action-account.action_move_out_invoice_type/66121</span>'),
            ))
            return
        if topic.code == 'return_date_fix':
            self._post_bot(_block(
                heading,
                'พิมพ์ <b>เลขที่ใบคืน</b> ที่ต้องการแก้วันที่<br/>'
                + _hint('รับเฉพาะใบคืน (ใบรับเข้า) เท่านั้น เช่น W3/IN/08511'),
            ))
            return
        if topic.code == 'rental_status_fix':
            self._post_bot(_block(
                heading,
                'พิมพ์ <b>เลขที่ใบสั่งขาย</b> ที่ต้องการถอยสถานะ<br/>'
                + _hint('รับเฉพาะใบที่สถานะการเช่าเป็น "ปิดบิล" แล้วเท่านั้น '
                        'เช่น SO-25100600028')
                + '<br/>'
                + _hint('ระบบจะคำนวณสถานะที่ถูกต้องให้เอง จากวันที่สิ้นสุดการเช่า'),
            ))
            return
        if topic.code == 'vat_round_fix':
            self._post_bot(_block(
                heading,
                _rows(
                    'ใช้ตอนลูกค้าทักว่า <b>ยอดก่อน VAT ต่างไป 1 สตางค์</b>',
                    _hint('ยอดรวมทั้งใบไม่เปลี่ยน ย้ายแค่เศษสตางค์'
                          'ระหว่างช่องก่อน VAT กับช่อง VAT'),
                ),
                'พิมพ์ <b>เลขที่ใบแจ้งหนี้</b> หรือวาง <b>URL</b> ของหน้านั้นมาก็ได้<br/>'
                + _hint('เช่น INV-2608070024'),
            ))
            return
        self._post_bot(_block(
            heading,
            'หัวข้อนี้ยังไม่เปิดให้บริการ กรุณาแจ้งฝ่าย IT โดยตรงไปก่อน',
        ))

    # ------------------------------------------------------------------
    # รับข้อความจากห้องแชท
    # ------------------------------------------------------------------
    @api.model
    def _on_channel_message(self, channel, message, msg_vals):
        """ถูกเรียกจาก discuss.channel._message_post_after_hook

        ห้าม raise ออกจากเมธอดนี้ (ดูหมายเหตุหัวไฟล์)
        """
        if self.env.context.get('npd_ai_it_bot'):
            return
        bot = self._bot_partner()
        if not bot:
            return

        author_id = msg_vals.get('author_id') or (message.author_id.id if message else False)
        if not author_id or author_id == bot.id:
            return
        # ตอบเฉพาะข้อความที่ "ผู้ใช้ปัจจุบัน" พิมพ์เอง (ไม่ตอบ mail gateway / ระบบอื่น)
        if author_id != self.env.user.partner_id.id:
            return
        # ห้องของตัวช่วย AI-IT เป็นแชทตัวต่อตัวเสมอ — เช็คก่อนเพื่อไม่ต้องอ่าน m2m
        # ของทุกห้องที่มีคนคุยกันในระบบ
        if channel.channel_type != 'chat':
            return
        if bot not in channel.sudo().channel_partner_ids:
            return

        body = html2plaintext(msg_vals.get('body') or (message.body if message else '') or '')
        body = (body or '').strip()
        if not body:
            return

        session = self.sudo().search([
            ('user_id', '=', self.env.user.id),
            ('channel_id', '=', channel.id),
            ('state', 'not in', ('done', 'cancelled')),
        ], limit=1)

        try:
            with self.env.cr.savepoint():
                if not session:
                    session = self.sudo().create({
                        'user_id': self.env.user.id,
                        'channel_id': channel.id,
                        'state': 'menu',
                    })
                    session._post_menu()
                    return
                session._handle_user_message(body)
        except Exception:  # noqa: BLE001 - ห้ามให้ข้อความพนักงานหายไป
            _logger.exception('ตัวช่วย AI-IT: จัดการข้อความในห้อง %s ไม่สำเร็จ', channel.id)
            try:
                with self.env.cr.savepoint():
                    self._post_bot_in_channel(
                        channel,
                        '⚠️ ระบบขัดข้องระหว่างประมวลผลคำตอบของคุณ '
                        'กรุณาลองใหม่อีกครั้ง หรือแจ้งฝ่าย IT พร้อมเวลาที่เกิดปัญหา',
                    )
            except Exception:  # noqa: BLE001
                _logger.exception('ตัวช่วย AI-IT: แจ้งข้อผิดพลาดกลับห้องแชทไม่สำเร็จ')

    def _log_history(self, action_type, detail):
        """บันทึกลงตารางประวัติการแก้ (เก็บเฉพาะงานที่สำเร็จจริง)

        ห้ามให้การบันทึกประวัติทำให้ขั้นตอนหลักล้ม — งานจริงบางอย่าง (แก้วันที่/
        ยกเลิกเอกสาร) commit ในทรานแซกชันแยกไปเรียบร้อยแล้ว ถ้าปล่อยให้ error
        ตรงนี้หลุดออกไป savepoint จะย้อนแค่ข้อความในแชท ทั้งที่เอกสารเปลี่ยนไปแล้ว
        พนักงานจะเห็น "ระบบขัดข้อง" ทั้งที่งานสำเร็จ
        """
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                return self.env['npd.ai.it.history'].log(
                    action_type, detail, session=self, note=self.change_note)
        except Exception:  # noqa: BLE001
            _logger.exception(
                'ตัวช่วย AI-IT: บันทึกประวัติ (%s) ของ %s ไม่สำเร็จ',
                action_type, self.document_ref,
            )
            return self.env['npd.ai.it.history']

    def _post_menu(self):
        self.ensure_one()
        topics = self.env['npd.ai.it.topic'].get_available_topics()
        if not topics:
            self._post_bot('ยังไม่มีหัวข้อให้บริการในขณะนี้')
            return
        items = []
        for topic in topics:
            label = '<b>%d.</b> %s' % (topic['index'], html_escape(topic['name']))
            if not topic['is_ready']:
                label += ' %s' % _hint('(ยังไม่เปิดให้บริการ)')
            elif topic['description']:
                label += _indent(_hint(html_escape(topic['description'])))
            items.append(label)
        self.sudo().write({'state': 'menu'})
        self._post_bot(_block(
            _title('เลือกหัวข้อที่ต้องการให้ช่วย', '👋'),
            _rows(*items),
            _hint('พิมพ์เลขหัวข้อที่ต้องการ'),
        ))

    def _handle_user_message(self, text):
        self.ensure_one()

        # คำสั่งที่ใช้ได้ทุกขั้นตอน — เช็คก่อนตรรกะของหัวข้อเสมอ
        if _is_command(text, CANCEL_WORDS):
            if self.state == 'ask_cut':
                # เติมสต๊อกไปแล้ว แค่ไม่ให้ตัดต่อ ไม่ใช่ "ยกเลิกทั้งรายการ"
                self.sudo().write({'state': 'done'})
                self._post_bot(
                    'รับทราบครับ 👍 สต๊อกเติมให้เรียบร้อยแล้ว<br/>'
                    'กดปุ่ม "ตัดสต็อก Auto 🚚" ที่เอกสาร <b>%s</b> เองได้เลย<br/>'
                    '<i>ถ้ามีเอกสารอื่นอีก พิมพ์ "เริ่มใหม่" ได้</i>'
                    % html_escape(self.document_ref or '')
                )
                return
            self.sudo().write({'state': 'cancelled'})
            self._post_bot(
                'ยกเลิกรายการนี้แล้ว ✋<br/>'
                'พิมพ์ <b>"เริ่มใหม่"</b> เพื่อเลือกหัวข้ออีกครั้งได้เลย '
                'หรือจะเลือกจากแท็บ "ตัวช่วย AI-IT" ก็ได้เหมือนกัน'
            )
            return
        if _is_command(text, RESTART_WORDS):
            self._post_menu()
            return

        if self.state == 'menu':
            self._handle_menu_choice(text)
            return

        code = self.topic_id.code or ''
        if code == 'stock_not_enough':
            self._handle_stock_not_enough(text)
            return
        if code == 'invoice_date_fix':
            self._handle_invoice_date_fix(text)
            return
        if code == 'return_date_fix':
            self._handle_return_date_fix(text)
            return
        if code == 'rental_status_fix':
            self._handle_rental_status_fix(text)
            return
        if code == 'vat_round_fix':
            self._handle_vat_round_fix(text)
            return

        self._post_bot('หัวข้อนี้ยังไม่เปิดให้บริการ กรุณาแจ้งฝ่าย IT โดยตรงไปก่อน')

    def _handle_menu_choice(self, text):
        self.ensure_one()
        topics = self.env['npd.ai.it.topic'].get_available_topics()
        match = re.search(r'\d+', text)
        chosen = None
        if match:
            index = int(match.group())
            chosen = next((t for t in topics if t['index'] == index), None)
        if not chosen:
            self._post_menu()
            return
        if not chosen['is_ready']:
            self._post_bot('หัวข้อ <b>%s</b> ยังไม่เปิดให้บริการ' % html_escape(chosen['name']))
            return
        # ต้องใช้ตารางเดียวกับตอนกดหัวข้อจากแท็บ ไม่งั้นหัวข้อที่เริ่มด้วยขั้นตอนอื่น
        # (เช่น invoice_date_fix เริ่มที่ ask_url) จะติดค้างในสถานะที่ไม่มีตัวจัดการ
        # แล้วบอทจะ "เงียบ" ไปเลย
        self.sudo().write({
            'topic_id': chosen['id'],
            'state': TOPIC_START_STATE.get(chosen['code'], 'menu'),
        })
        self._post_intro()

    # ==================================================================
    # หัวข้อที่ 1 : แก้ปัญหาตัดสต็อกไม่ได้เนื่องจากสต็อกไม่พอ
    # ==================================================================
    def _handle_stock_not_enough(self, text):
        self.ensure_one()
        if self.state == 'ask_doc':
            self._step_ask_doc(text)
        elif self.state == 'ask_qty':
            self._step_ask_qty(text)
        elif self.state == 'confirm':
            self._step_confirm(text)
        elif self.state == 'ask_cut':
            self._step_ask_cut(text)
        else:
            self._recover_unknown_state()

    # ---- ขั้นที่ 1: รับเลขเอกสาร -------------------------------------
    def _step_ask_doc(self, text):
        Fix = self.env['npd.ai.it.stock.fix']
        doc_ref, document = self._parse_doc_number(text)
        if not document:
            self._post_bot(
                'ไม่พบเอกสาร%s ในระบบ 🙏<br/>'
                'กรุณาพิมพ์เฉพาะ <b>เลขที่เอกสาร</b> อีกครั้ง '
                '(เลขใบสั่งขาย หรือเลขใบจัดส่ง)'
                % (' "%s"' % html_escape(doc_ref) if doc_ref else '')
            )
            return

        branch, error = Fix.resolve_branch(document, self.env.user)
        if error:
            self._post_bot('⛔ %s' % html_escape(error))
            self.sudo().write({'state': 'cancelled'})
            return

        product_ids = [p.id for p, _qty in Fix._required_lines(document)]
        # หาคลังของสาขา — ถ้ายังไม่มี ตัวช่วยจะสร้าง/ผูกให้เองแล้วทำต่อเลย
        # เดิมเคสนี้จะตัดจบแล้วให้ไปตามฝ่าย IT มาสร้าง location ให้ ซึ่งพนักงานต้องรอข้ามวัน
        location, location_info = Fix.ensure_branch_internal_location(
            branch, product_ids)
        if not location:
            self._post_bot(_block(
                _rows(
                    _title('ไม่พบคลังสินค้า (internal) ของสาขา "%s"'
                           % html_escape(branch.name or ''), '⛔'),
                    'และระบบสร้างให้เองไม่ได้',
                    _hint(self._location_fail_reason(location_info)),
                ),
                'กรุณาแจ้งฝ่าย IT ให้ตั้งค่าคลังของสาขาให้ก่อน',
            ))
            self.sudo().write({'state': 'cancelled'})
            return

        all_items, shortage = Fix.analyze(document, location)
        self.sudo().write({
            'document_ref': document.name,
            'document_model': document._name,
            'document_id': document.id,
            'branch_id': branch.id,
            'location_id': location.id,
        })

        if location_info:
            self._announce_branch_location(location, location_info)

        header = _rows(
            _title(html_escape(document.name or ''), '📄'),
            _kv('สาขา', html_escape(branch.name or '—')),
            _kv('คลัง', html_escape(location.complete_name or '—')),
        )

        if not all_items:
            self._post_bot(_block(header, 'เอกสารนี้ไม่มีรายการสินค้าที่ต้องตัดสต๊อก'))
            self.sudo().write({'state': 'done'})
            return

        if not shortage:
            self._post_bot(_block(
                header,
                _rows(
                    _title('สต๊อกพอตัดครบทุกรายการ', '✅'),
                    'กลับไปที่เอกสารแล้วกดปุ่ม "ตัดสต็อก Auto 🚚" ได้เลย',
                ),
                _hint('ถ้ายังตัดไม่ผ่าน แสดงว่าติดสาเหตุอื่น กรุณาแจ้งฝ่าย IT '
                      'พร้อมข้อความ error ที่ขึ้นบนหน้าจอ'),
            ))
            self.sudo().write({'state': 'done'})
            return

        self._set_data({'items': shortage})
        self.sudo().write({'state': 'ask_qty'})

        item_rows = []
        for index, item in enumerate(shortage, start=1):
            item_rows.append(_rows(
                '<b>%d.</b> %s' % (index, html_escape(self._item_label(item))),
                _indent(
                    '<span class="text-muted">ต้องตัด</span> %s'
                    ' <span class="text-muted">· มีอยู่</span> %s'
                    ' <span class="text-muted">· ขาด</span> <b class="text-danger">%s</b>'
                    % (_fmt(item['need']), _fmt(item['current']), _fmt(item['missing']))
                ),
            ))

        if len(shortage) == 1:
            example = _hint('ตอบเป็นตัวเลขได้เลย เช่น %s' % _fmt(shortage[0]['need']))
        else:
            example = _hint('ตอบเช่น %s' % ', '.join(
                '%d=%s' % (i + 1, _fmt(it['need'])) for i, it in enumerate(shortage)))

        self._post_bot(_block(
            header,
            _title('สต๊อกไม่พอตัด %d รายการ' % len(shortage), '⚠️'),
            _rows(*item_rows),
            _rows('กรุณานับของจริงในคลัง แล้วแจ้ง <b>จำนวนสต็อกจริง</b> ของแต่ละรายการ',
                  example),
        ))

    # ---- คลังของสาขาที่ตัวช่วยสร้าง/ผูกให้เอง ------------------------
    def _location_fail_reason(self, info):
        """บอกเหตุที่สร้างคลังให้เองไม่ได้ พนักงานจะได้บอก IT ถูกจุด"""
        mode = (info or {}).get('mode')
        if mode == 'disabled':
            return ('ปิดการสร้างคลังอัตโนมัติไว้ที่ System Parameter '
                    '<b>npd_ai_it_assistant.auto_create_branch_location</b>')
        if mode == 'no_parent':
            return ('บริษัทของสาขานี้ยังไม่มีคลังสินค้า (warehouse) '
                    'ให้อ้างอิงว่าควรสร้างคลังของสาขาไว้ใต้อะไร')
        if mode == 'failed':
            return 'สร้างคลังไม่สำเร็จ: %s' % html_escape((info or {}).get('error') or '')
        return 'ระบบหาคลังของสาขานี้ไม่เจอ'

    def _announce_branch_location(self, location, info):
        """เล่าให้พนักงานฟังว่าคลังของสาขาเพิ่งถูกสร้าง/ผูกให้เมื่อกี้

        ต้องบอกให้ชัด เพราะคลังที่เพิ่งสร้างจะมีสต๊อกเป็น 0 ทุกตัว
        พนักงานจะได้ไม่ตกใจว่า "ของหายไปไหน" และรู้ว่าต้องนับของจริงมาแจ้ง
        """
        self.ensure_one()
        mode = (info or {}).get('mode')
        branch_name = html_escape(self.branch_id.name or '')
        if mode == 'created':
            head = _title('ไม่พบคลังของสาขา "%s" — สร้างให้แล้ว' % branch_name, '🏗️')
            note = _hint('คลังที่เพิ่งสร้างยังไม่มีสต๊อกในระบบ (ทุกรายการเป็น 0) '
                         'เดี๋ยวผมถามจำนวนสต็อกจริง แล้วเติมให้ในขั้นตอนถัดไป')
            detail = 'สร้างคลังใหม่ให้สาขา'
        elif mode == 'adopted':
            head = _title('คลังนี้มีอยู่แล้ว แต่ยังไม่ได้ผูกกับสาขา "%s" — ผูกให้แล้ว' % branch_name, '🔗')
            note = _hint('ต่อจากนี้ระบบจะมองเห็นคลังนี้เป็นคลังของสาขาคุณ สต๊อกเดิมที่มีอยู่ยังอยู่ครบ')
            detail = 'ผูกคลังเดิมเข้ากับสาขา'
        else:
            return

        self._post_bot(_block(_rows(
            head,
            _kv('คลัง', html_escape(location.complete_name or '—')),
            note,
        )), commands=False)
        self._log_history('stock_location', html2plaintext(
            '%s : %s (สาขา %s)'
            % (detail, location.complete_name or '-', self.branch_id.name or '-')))

    # ---- ขั้นที่ 2: รับจำนวนสต๊อกจริงของแต่ละรายการ ------------------
    def _step_ask_qty(self, text):
        data = self._get_data()
        items = data.get('items') or []
        if not items:
            self._post_bot('ข้อมูลรายการหายไป กรุณาเริ่มใหม่จากแท็บ "ตัวช่วย AI-IT"')
            self.sudo().write({'state': 'cancelled'})
            return

        quantities = self._parse_quantities(text, items)
        missing_index = [i + 1 for i in range(len(items)) if (i + 1) not in quantities]
        if missing_index:
            self._post_bot(_block(
                'ยังไม่ได้รับจำนวนสต็อกจริงของรายการนี้ 🙏',
                _rows(*['<b>%d.</b> %s %s'
                        % (i, html_escape(self._item_label(items[i - 1])),
                           _hint('(ต้องตัด %s)' % _fmt(items[i - 1]['need'])))
                        for i in missing_index]),
                _hint('ตอบเช่น %s' % ', '.join('%d=จำนวน' % i for i in missing_index)),
            ))
            return

        for index, item in enumerate(items, start=1):
            item['target'] = quantities[index]
        self._set_data({'items': items})
        self.sudo().write({'state': 'confirm'})

        item_rows, warnings = [], []
        for index, item in enumerate(items, start=1):
            add = max(item['target'] - item['current'], 0.0)
            item_rows.append(_rows(
                '<b>%d.</b> %s' % (index, html_escape(self._item_label(item))),
                _indent('%s → <b>%s</b> <span class="text-success">(เติม +%s)</span>'
                        % (_fmt(item['current']), _fmt(item['target']), _fmt(add))),
            ))
            if item['target'] < item['need']:
                warnings.append(
                    '%s <span class="text-muted">·</span> แจ้ง %s แต่ต้องตัด %s'
                    % (html_escape(self._item_label(item)),
                       _fmt(item['target']), _fmt(item['need']))
                )

        warning_block = None
        if warnings:
            warning_block = _rows(
                '<b class="text-danger">⚠️ รายการที่แจ้งมาน้อยกว่าที่ต้องตัด</b>',
                _bullets(warnings),
                _hint('ระบบจะเติมให้เท่าที่แจ้ง แต่จะยังตัดไม่ครบ'),
            )

        self._post_bot(_block(
            _rows(
                _title('ตรวจทานก่อนเติมสต๊อก', '📋'),
                _kv('คลัง', html_escape(self.location_id.complete_name or '—')),
            ),
            _rows(*item_rows),
            warning_block,
            'พิมพ์ <b>"ยืนยัน"</b> เพื่อให้ระบบเติมสต๊อก '
            'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้',
        ))

    # ---- ขั้นที่ 3: ยืนยันแล้วเติมสต๊อกจริง ---------------------------
    def _step_confirm(self, text):
        if not _is_command(text, CONFIRM_WORDS):
            self._post_bot('กรุณาพิมพ์ <b>"ยืนยัน"</b> เพื่อดำเนินการ, '
                           '<b>"ยกเลิก"</b> เพื่อยกเลิกรายการนี้ '
                           'หรือ <b>"เริ่มใหม่"</b> เพื่อกลับไปเลือกหัวข้อ')
            return

        data = self._get_data()
        items = data.get('items') or []
        location = self.location_id
        if not items or not location:
            self._post_bot('ข้อมูลรายการหายไป กรุณาเริ่มใหม่จากแท็บ "ตัวช่วย AI-IT"')
            self.sudo().write({'state': 'cancelled'})
            return

        applied = self.env['npd.ai.it.stock.fix'].apply_topup(location, items)

        need_by_product = {i['product_id']: i['need'] for i in items}
        self.env['npd.ai.it.session.line'].sudo().create([{
            'session_id': self.id,
            'product_id': row['product_id'],
            'qty_needed': need_by_product.get(row['product_id'], 0.0),
            'qty_before': row['before'],
            'qty_added': row['added'],
            'qty_after': row['after'],
        } for row in applied])

        item_rows = []
        for index, row in enumerate(applied, start=1):
            if row['added'] > 0:
                detail = ('%s → <b>%s</b> <span class="text-success">(+%s)</span>'
                          % (_fmt(row['before']), _fmt(row['after']), _fmt(row['added'])))
            else:
                detail = '%s %s' % (_fmt(row['after']), _hint('(พออยู่แล้ว ไม่ต้องเติม)'))
            item_rows.append(_rows(
                '<b>%d.</b> %s' % (index, html_escape(row['name'])),
                _indent(detail),
            ))

        if self._can_auto_cut():
            action_block = _rows(
                'พิมพ์ <b>"ทำต่อ"</b> ให้ผมกดตัดสต๊อกเอกสาร <b>%s</b> ให้เลย 🚚'
                % html_escape(self.document_ref or ''),
                _hint('หรือ "ไม่ต้อง" ถ้าจะไปกดปุ่มที่เอกสารเอง · '
                      '"เริ่มใหม่" ถ้ามีเอกสารอื่นอีก'),
            )
            next_state = 'ask_cut'
        else:
            action_block = _rows(
                'กลับไปที่เอกสาร <b>%s</b> แล้วกดปุ่ม "ตัดสต็อก Auto 🚚" อีกครั้งได้เลย'
                % html_escape(self.document_ref or ''),
                _hint('มีเอกสารอื่นอีกไหม? พิมพ์ "เริ่มใหม่" ได้เลย'),
            )
            next_state = 'done'

        lines = [_block(
            _rows(
                _title('เติมสต๊อกเรียบร้อยแล้ว', '✅'),
                _kv('คลัง', html_escape(location.complete_name or '—')),
            ),
            _rows(*item_rows),
            action_block,
        )]
        summary = html2plaintext('<br/>'.join(lines))
        self.sudo().write({'state': next_state, 'summary': summary})
        self._log_history('stock_topup', html2plaintext(
            'คลัง: %s<br/>%s'
            % (location.complete_name or '-',
               '<br/>'.join('%s : %s → %s (+%s)'
                            % (row['name'], _fmt(row['before']),
                               _fmt(row['after']), _fmt(row['added']))
                            for row in applied))
        ))
        self._post_bot('<br/>'.join(lines))
        _logger.info('ตัวช่วย AI-IT: %s เติมสต๊อกให้ %s (%d รายการ)',
                     self.user_id.display_name, self.document_ref, len(applied))

    # ---- ขั้นที่ 4 (เสริม): ตัดสต๊อกต่อให้เลย ---------------------------
    def _can_auto_cut(self):
        """ตัดสต๊อกต่อให้ได้ไหม — ต้องเป็นใบสั่งขาย และต้องมีโมดูลปุ่มตัดสต๊อกอยู่"""
        self.ensure_one()
        return bool(
            self.document_model == 'sale.order'
            and self.document_id
            and 'stock.cut.confirm.wizard' in self.env
        )

    def _step_ask_cut(self, text):
        if not _is_command(text, CONTINUE_WORDS):
            self._post_bot('พิมพ์ <b>"ทำต่อ"</b> ให้ผมตัดสต๊อกให้เลย, '
                           '<b>"ไม่ต้อง"</b> ถ้าจะไปกดปุ่มที่เอกสารเอง '
                           'หรือ <b>"เริ่มใหม่"</b> เพื่อทำเอกสารอื่นต่อ')
            return

        order = self.env['sale.order'].browse(self.document_id)
        if not order.exists():
            self._post_bot('⛔ ไม่พบเอกสาร <b>%s</b> แล้ว (อาจถูกลบไป) '
                           'กรุณาตรวจสอบที่หน้าเอกสารอีกครั้ง'
                           % html_escape(self.document_ref or ''))
            self.sudo().write({'state': 'done'})
            return

        # ข้อความบอกความคืบหน้า มีผลลัพธ์ตามมาทันที ไม่ต้องต่อคำสั่ง
        self._post_bot('⏳ กำลังตัดสต๊อกเอกสาร <b>%s</b> ให้ครับ...'
                       % html_escape(order.name or ''), commands=False)

        try:
            # savepoint แยก: ถ้าตัดไม่ผ่าน ให้ย้อนเฉพาะการตัด แล้วยังตอบกลับในแชทได้
            # (ถ้าไม่กัน error จะทะลุไป rollback ทั้งข้อความของพนักงานด้วย)
            with self.env.cr.savepoint():
                result = self._run_stock_cut(order)
        except UserError as error:
            self._post_bot(_block(
                _rows('<b class="text-danger">⛔ ตัดสต๊อกไม่สำเร็จ</b>',
                      html_escape(str(error))),
                _hint('สต๊อกที่เติมไปแล้วยังอยู่ครบ ลองกดปุ่ม "ตัดสต็อก Auto 🚚" '
                      'ที่เอกสารดูอีกที ถ้ายังไม่ได้ให้แจ้งฝ่าย IT พร้อมข้อความนี้'),
            ))
            self.sudo().write({'state': 'done'})
            return
        except Exception as error:  # noqa: BLE001 - ต้องตอบกลับในแชทเสมอ
            _logger.exception('ตัวช่วย AI-IT: ตัดสต๊อก %s ไม่สำเร็จ', self.document_ref)
            self._post_bot(_block(
                _rows('<b class="text-danger">⚠️ ระบบขัดข้องระหว่างตัดสต๊อก</b>',
                      html_escape(str(error) or error.__class__.__name__)),
                _hint('สต๊อกที่เติมไปแล้วยังอยู่ครบ กรุณาแจ้งฝ่าย IT พร้อมข้อความนี้'),
            ))
            self.sudo().write({'state': 'done'})
            return

        # confirm_stock_cut() คืน action แบบ display_notification กลับมา
        # เอาข้อความในนั้นมาเล่าต่อในแชท จะได้เห็นคำเตือนเดียวกับตอนกดปุ่มเอง
        params = (result or {}).get('params') or {}
        title = params.get('title') or '✅ ตัดสต๊อกสำเร็จ'
        message = params.get('message') or ''
        body = [_block(
            _rows('<b>%s</b>' % html_escape(title),
                  html_escape(message).replace('\n', BR) if message else None),
            _hint('มีเอกสารอื่นอีกไหม? พิมพ์ "เริ่มใหม่" ได้เลย'),
        )]

        self.sudo().write({
            'state': 'done',
            'summary': (self.summary or '') + '\n\n' + html2plaintext('<br/>'.join(body)),
        })
        self._log_history('stock_cut', html2plaintext(
            '%s<br/>%s' % (title, message) if message else title))
        self._post_bot('<br/>'.join(body))
        _logger.info('ตัวช่วย AI-IT: %s สั่งตัดสต๊อก %s ผ่านแชทสำเร็จ',
                     self.user_id.display_name, self.document_ref)

    def _run_stock_cut(self, order):
        """เรียกตรรกะเดียวกับปุ่ม "ตัดสต็อก Auto 🚚" ที่ใบสั่งขาย

        ปุ่มนั้นเปิด wizard ขึ้นมาให้กดยืนยันอีกที (so_auto_stock_cut:
        action_auto_validate_delivery -> stock.cut.confirm.wizard) ที่นี่จึงสร้าง
        wizard ด้วยค่าชุดเดียวกันแล้วเรียก confirm_stock_cut() ต่อให้เลย

        ไม่ใช้ sudo() โดยตั้งใจ — ให้สิทธิ์ของพนักงานคนที่สั่งเป็นตัวตัดสินเหมือน
        ตอนกดปุ่มเอง (wizard เปิดสิทธิ์ให้ผู้ใช้ทั่วไปอยู่แล้ว)
        """
        lines = []
        for picking in order.picking_ids.filtered(
                lambda p: p.state in ('draft', 'waiting', 'confirmed')):
            for move in picking.move_ids_without_package:
                sol = order.order_line.filtered(
                    lambda l: l.product_id.id == move.product_id.id)[:1]
                if not sol:
                    continue
                qty = 0.0
                if 'pfb_quantity' in sol._fields:
                    qty = float(sol.pfb_quantity or 0.0)
                if qty <= 0:
                    continue
                lines.append((0, 0, {
                    'product_id': move.product_id.id,
                    'quantity': qty,
                    'location_name': picking.location_id.display_name,
                }))

        wizard = self.env['stock.cut.confirm.wizard'].create({
            'order_id': order.id,
            'mode': 'cut',
            'confirm_line_ids': lines,
        })
        return wizard.confirm_stock_cut()

    # ==================================================================
    # หัวข้อที่ 2 : แก้ไขวันที่ใบแจ้งหนี้
    # ==================================================================
    def _handle_invoice_date_fix(self, text):
        self.ensure_one()
        if self.state == 'ask_url':
            self._step_ask_url(text)
        elif self.state == 'ask_date':
            self._step_ask_date(text)
        elif self.state == 'ask_reason':
            self._step_ask_reason(text)
        elif self.state == 'confirm_date':
            self._step_confirm_date(text)
        elif self.state == 'confirm_cancel':
            self._step_confirm_cancel(text)
        else:
            self._recover_unknown_state()

    # ------------------------------------------------------------------
    def _recover_unknown_state(self):
        """กันบอทเงียบ: สถานะไม่ตรงกับขั้นตอนไหนของหัวข้อเลย

        เกิดได้ถ้าสถานะกับหัวข้อไม่เข้าคู่กัน (เคยเกิดจริงตอนเลือกหัวข้อจากเมนู
        ในแชทแล้วโค้ดตั้งสถานะเริ่มต้นผิด) แทนที่จะไม่ตอบอะไรเลยจนพนักงานงง
        ให้ดึงกลับไปตั้งต้นของหัวข้อนั้นแล้วทักใหม่
        """
        self.ensure_one()
        start_state = TOPIC_START_STATE.get(self.topic_id.code or '')
        _logger.warning(
            'ตัวช่วย AI-IT: session %s สถานะ "%s" ไม่เข้าคู่กับหัวข้อ "%s" — ตั้งต้นใหม่',
            self.id, self.state, self.topic_id.code or '-',
        )
        if not start_state:
            self._post_menu()
            return
        self.sudo().write({'state': start_state})
        self._post_intro()

    # ---- ขั้นที่ 1: รับ URL แล้ววิเคราะห์เอกสาร -----------------------
    def _step_ask_url(self, text):
        Fix = self.env['npd.ai.it.invoice.fix']
        move, error = Fix.find_move(text)
        if error:
            self._post_bot('⛔ %s' % error)
            return

        branch, branch_error = self.env['npd.ai.it.stock.fix'].resolve_branch(
            move, self.env.user)
        if branch_error:
            self._post_bot('⛔ %s' % html_escape(branch_error))
            self.sudo().write({'state': 'cancelled'})
            return

        info = Fix.analyze(move)
        self.sudo().write({
            'document_ref': move.name if move.name and move.name != '/' else ('id=%s' % move.id),
            'document_model': move._name,
            'document_id': move.id,
            'branch_id': branch.id if branch else False,
        })

        header = self._invoice_header(move, info)
        if info['error']:
            self._post_bot(header + '<br/>⛔ %s' % info['error'])
            self.sudo().write({'state': 'cancelled'})
            return

        if info['plan'] == 'cancel':
            self._offer_cancel(move, info, header)
        elif info['plan'] == 'ask_date':
            self._offer_manual_date(move, info, header)
        else:
            self._offer_date_from_order(move, info, header)

    def _invoice_header(self, move, info):
        title = (move.name if move.name and move.name != '/'
                 else 'ฉบับร่าง (ยังไม่มีเลขที่)')
        branch = (move.branch_id.name
                  if 'branch_id' in move._fields and move.branch_id else '—')
        status = ' · '.join([
            STATE_LABELS.get(move.state, move.state),
            PAYMENT_LABELS.get(info['payment_state'], info['payment_state']),
        ])
        return _rows(
            _title(html_escape(title), '📄'),
            _kv('สาขา', html_escape(branch)),
            _kv('ประเภทสินค้า', html_escape(info['reason'] or '—')),
            _kv('สมุดรายวัน', html_escape(move.journal_id.name or '—')),
            _kv('วันที่เอกสาร', '%s <span class="text-muted">· ลงบัญชี</span> %s'
                % (_dt(move.invoice_date), _dt(move.date))),
            _kv('สถานะ', html_escape(status)),
        )

    # ---- ทางที่ 1: ลงบันทึก/ชำระแล้ว -> ยกเลิก ------------------------
    def _cancel_plan_lines(self, move):
        """รายการขั้นตอนที่ระบบจะทำตอนยกเลิก (อ่านสดจากเอกสารทุกครั้ง)"""
        payments = move._get_reconciled_payments()
        lines = []
        step = 0
        if payments:
            step += 1
            lines.append('<b>%d.</b> ยกเลิกการชำระเงิน %d รายการ'
                         % (step, len(payments)))
            lines.append(_bullets([
                '%s <span class="text-muted">·</span> %s บาท'
                % (html_escape(payment.name or payment.move_id.name or '—'),
                   _fmt(payment.amount))
                for payment in payments
            ]))
        step += 1
        lines.append('<b>%d.</b> ยกเลิกใบแจ้งหนี้ใบนี้' % step)
        return lines

    def _offer_cancel(self, move, info, header):
        # ถามเหตุผลก่อนเสมอ แล้วค่อยให้ยืนยัน — การยกเลิกใบที่ลงบันทึกแล้ว
        # ย้อนกลับไม่ได้ ประวัติจึงต้องมีเหตุผลกำกับเหมือนกับการแก้วันที่
        self._set_data({'plan': 'cancel'})
        self.sudo().write({'state': 'ask_reason'})
        self._post_bot(_block(
            header,
            _rows(
                _title('เอกสารนี้แก้วันที่ไม่ได้', '⚠️'),
                'ลงบันทึก/ชำระเงินไปแล้ว ถ้าจะเปลี่ยนวันที่ '
                'ต้องยกเลิกใบนี้แล้วออกใบใหม่',
            ),
            _rows(_title('สิ่งที่ระบบจะทำให้'),
                  _rows(*self._cancel_plan_lines(move))),
        ), commands=False)  # มีข้อความถามเหตุผลตามมาทันที ไม่ต้องต่อคำสั่งซ้ำ
        self._ask_change_reason('ยกเลิกเอกสารนี้')

    def _step_confirm_cancel(self, text):
        if not _is_command(text, CONFIRM_WORDS):
            self._post_bot('กรุณาพิมพ์ <b>"ยืนยัน"</b> เพื่อยกเลิกเอกสาร '
                           'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้')
            return

        Fix = self.env['npd.ai.it.invoice.fix']
        move = self.env['account.move'].sudo().browse(self.document_id)
        if not move.exists():
            self._post_bot('⛔ ไม่พบเอกสารนี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        # สรุปที่แสดงไปก่อนหน้าอาจเก่าแล้ว (เคยเจอเคสที่ถูกปลดชำระไประหว่างคุยกันอยู่)
        # ต้องอ่านสถานะสดอีกรอบก่อนลงมือเสมอ
        move.invalidate_recordset()
        if move.state == 'cancel':
            self._post_bot('เอกสาร <b>%s</b> ถูกยกเลิกไปแล้ว ไม่ต้องทำอะไรเพิ่ม'
                           % html_escape(self.document_ref or ''))
            self.sudo().write({'state': 'done'})
            return

        actor = self.env.user.display_name
        try:
            result = Fix.cancel_move_isolated(
                move.id, actor_name=actor, note=self.change_note)
        except Exception as error:  # noqa: BLE001 - ต้องตอบกลับในแชทเสมอ
            _logger.exception('ตัวช่วย AI-IT: ยกเลิกเอกสาร %s ไม่สำเร็จ', self.document_ref)
            self._post_bot(
                '⛔ <b>ยกเลิกเอกสารไม่สำเร็จ</b><br/>%s<br/><br/>'
                '<i>ระบบย้อนทุกอย่างกลับให้แล้ว เอกสารยังอยู่สถานะเดิม '
                'กรุณาแจ้งฝ่าย IT พร้อมข้อความนี้</i>'
                % html_escape(str(error) or error.__class__.__name__)
            )
            self.sudo().write({'state': 'done'})
            return

        blocks = [_rows(
            _title('ยกเลิกเอกสารเรียบร้อยแล้ว', '✅'),
            _kv('เอกสาร', '<b>%s</b>' % html_escape(self.document_ref or '')),
            _kv('เหตุผล', html_escape(self.change_note or '—')),
        )]
        if result['payments']:
            blocks.append(_rows(
                _title('ยกเลิกการชำระ %d รายการ' % len(result['payments'])),
                _bullets([
                    '%s <span class="text-muted">·</span> %s บาท '
                    '<span class="text-muted">·</span> %s'
                    % (html_escape(payment['name']), _fmt(payment['amount']),
                       STATE_LABELS.get(payment['state_after'], payment['state_after']))
                    for payment in result['payments']
                ]),
            ))
        blocks.append(_rows(
            '<b class="text-danger">❗ กรุณาไปสร้างเอกสารใหม่</b> ด้วยวันที่ที่ถูกต้อง',
            _hint('ใบเดิมถูกยกเลิกแล้ว แก้ไขไม่ได้อีก'),
        ))
        blocks.append(_hint('มีเอกสารอื่นอีกไหม? พิมพ์ "เริ่มใหม่" ได้เลย'))
        lines = [_block(*blocks)]

        self.sudo().write({
            'state': 'done',
            'summary': html2plaintext('<br/>'.join(lines)),
        })
        self._log_history('invoice_cancel', html2plaintext(
            'สถานะ: %s → %s<br/>ยกเลิกการชำระ %d รายการ%s'
            % (result['state_before'], result['state_after'],
               len(result['payments']),
               ''.join('<br/>• %s (%s)' % (p['name'], _fmt(p['amount']))
                       for p in result['payments']))
        ))
        self._post_bot('<br/>'.join(lines))

    # ---- ทางที่ 2: ฉบับร่าง -> ให้ระบุวันที่เอง ------------------------
    def _offer_manual_date(self, move, info, header):
        Fix = self.env['npd.ai.it.invoice.fix']
        first, last = Fix.month_window(move)
        self._set_data({'plan': 'ask_date', 'first': str(first), 'last': str(last)})
        self.sudo().write({'state': 'ask_date'})
        self._post_bot(_block(
            header,
            _rows(
                _title('เอกสารนี้เป็นฉบับร่าง แก้วันที่ได้เลย', '✏️'),
                'พิมพ์<b>วันที่ใหม่</b>ที่ต้องการ',
            ),
            _rows(
                _kv('ต้องอยู่ในช่วง', '<b>%s – %s</b>' % (_dt(first), _dt(last))),
                _hint('ห้ามข้ามเดือน เพราะจะทำให้ตกงวดบัญชีคนละงวด'),
            ),
            _hint('พิมพ์ได้หลายแบบ เช่น %d (ใส่แค่วันที่) · %s · %s'
                  % (last.day, _dt(last), last.strftime('%Y-%m-%d'))),
        ))

    def _step_ask_date(self, text):
        move = self.env['account.move'].sudo().browse(self.document_id)
        if not move.exists():
            self._post_bot('⛔ ไม่พบเอกสารนี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        Fix = self.env['npd.ai.it.invoice.fix']
        first, last = Fix.month_window(move)
        new_date = self._parse_date_in_month(text, first)
        if not new_date:
            self._post_bot(_rows(
                'อ่านวันที่ไม่ออกครับ 🙏 <b>พิมพ์วันที่ใหม่มาได้เลย</b>',
                _hint('เช่น %d (ใส่แค่วันที่) · %s · %s'
                      % (last.day, _dt(last), last.strftime('%Y-%m-%d'))),
            ))
            return
        if not (first <= new_date <= last):
            # ยังอยู่สถานะ ask_date อยู่ พิมพ์วันที่ใหม่มาได้เลย ระบบตรวจให้ใหม่ทันที
            self._post_bot(_block(
                _rows(
                    '<b class="text-danger">⛔ วันที่ %s อยู่นอกเดือนของเอกสาร</b>'
                    % _dt(new_date),
                    'ต้องอยู่ระหว่าง <b>%s</b> ถึง <b>%s</b> เท่านั้น'
                    % (_dt(first), _dt(last)),
                ),
                _rows(
                    '<b>พิมพ์วันที่ใหม่มาได้เลยครับ</b> เดี๋ยวผมตรวจให้ใหม่',
                    _hint('เช่น %d (ใส่แค่วันที่) · %s'
                          % (last.day, _dt(last))),
                ),
            ))
            return

        data = self._get_data()
        data.update({'pending_date': str(new_date), 'source': 'manual'})
        self._set_data(data)
        self.sudo().write({'state': 'ask_reason'})
        self._ask_change_reason('แก้วันที่')

    # ---- ทางที่ 3: ใบแจ้งหนี้ค่าเช่า -> ดึงวันที่จากใบสั่งขาย ----------
    def _offer_date_from_order(self, move, info, header):
        Fix = self.env['npd.ai.it.invoice.fix']
        order_date, order, error = Fix.order_date_from_origin(move)
        if error:
            self._post_bot(
                header + '<br/>⛔ %s<br/><br/>'
                '<i>กรุณาตรวจช่อง Source Document ที่หน้าเอกสาร '
                'หรือแจ้งฝ่าย IT</i>' % html_escape(error)
            )
            self.sudo().write({'state': 'cancelled'})
            return

        if order_date == move.invoice_date:
            self._post_bot(
                header + '<br/>'
                '✅ วันที่ใบแจ้งหนี้ตรงกับวันที่สั่งซื้อของ <b>%s</b> อยู่แล้ว '
                '(%s) ไม่ต้องแก้อะไร'
                % (html_escape(order.name), order_date)
            )
            self.sudo().write({'state': 'done'})
            return

        first, last = Fix.month_window(move)
        warning = None
        if not (first <= order_date <= last):
            warning = _rows(
                '<b class="text-danger">⚠️ วันที่สั่งซื้อข้ามเดือนของเอกสารเดิม</b>',
                _hint('เอกสารเดิมอยู่ช่วง %s – %s · ตรวจให้แน่ใจก่อนยืนยัน'
                      % (_dt(first), _dt(last))),
            )

        data = self._get_data()
        data.update({
            'plan': 'from_order',
            'pending_date': str(order_date),
            'source': 'order',
            'order_name': order.name,
        })
        self._set_data(data)
        self.sudo().write({'state': 'ask_reason'})
        self._post_bot(_block(
            header,
            _rows(
                _title('ใบแจ้งหนี้ค่าเช่าฉบับร่าง — ดึงวันที่ให้เอง', '🔗'),
                _kv('ใบสั่งขาย', '<b>%s</b>' % html_escape(order.name)),
                _kv('วันที่สั่งซื้อ', '<b>%s</b>' % _dt(order_date)),
            ),
            _kv('วันที่เอกสาร', '%s → <b>%s</b>'
                % (_dt(move.invoice_date), _dt(order_date))),
            warning,
        ), commands=False)  # มีข้อความถามเหตุผลตามมาทันที ไม่ต้องต่อคำสั่งซ้ำ
        self._ask_change_reason('แก้วันที่')

    # ---- ขั้นสุดท้าย: หมายเหตุว่าแก้เพราะอะไร -------------------------
    def _ask_change_reason(self, what='แก้วันที่'):
        """ถามเหตุผล ใช้ร่วมกันทั้งทางแก้วันที่และทางยกเลิกเอกสาร"""
        self._post_bot(_block(
            _rows(
                _title('ขอเหตุผลก่อนครับ', '📝'),
                'พิมพ์สั้น ๆ ว่า<b>%s เพราะอะไร</b>' % html_escape(what),
            ),
            _hint('ตัวอย่าง: ระบบออกเอกสารวันที่ผิด / ต้องตรงกับวันที่ส่งของจริง'),
        ))

    def _step_ask_reason(self, text):
        note = (text or '').strip()
        if len(note) < 3:
            self._post_bot('หมายเหตุสั้นไปครับ 🙏 กรุณาพิมพ์เหตุผล '
                           'อย่างน้อย 3 ตัวอักษร (จะบันทึกไว้ในประวัติของเอกสาร)')
            return

        data = self._get_data()

        # ทางแก้วันที่คืนสินค้า (หัวข้อ 3) — เอกสารเป็น stock.picking คนละโมเดล
        if data.get('plan') == 'return_date':
            self.sudo().write({'change_note': note, 'state': 'confirm_date'})
            self._step_confirm_return_date()
            return

        # ทางแก้สถานะการเช่า (หัวข้อ 4) — เอกสารเป็น sale.order
        if data.get('plan') == 'rental_status':
            self.sudo().write({'change_note': note, 'state': 'confirm_status'})
            self._step_confirm_rental_status()
            return

        # ทางแก้การปัดเศษ VAT (หัวข้อ 5)
        if data.get('plan') == 'vat_round':
            self.sudo().write({'change_note': note, 'state': 'confirm_vat'})
            self._step_confirm_vat_round()
            return

        move = self.env['account.move'].sudo().browse(self.document_id)
        if not move.exists():
            self._post_bot('⛔ ไม่พบเอกสารนี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        # ทางยกเลิกเอกสาร: เก็บเหตุผลแล้วขอให้ยืนยันอีกชั้น
        if data.get('plan') == 'cancel':
            self.sudo().write({'change_note': note, 'state': 'confirm_cancel'})
            self._post_bot(_block(
                _rows(
                    _title('ตรวจทานก่อนยกเลิก', '📋'),
                    _kv('เอกสาร', '<b>%s</b>' % html_escape(self.document_ref or '')),
                    _kv('เหตุผล', '<b>%s</b>' % html_escape(note)),
                ),
                _rows(_title('สิ่งที่ระบบจะทำให้'),
                      _rows(*self._cancel_plan_lines(move))),
                _rows(
                    '<b class="text-danger">⛔ ย้อนกลับไม่ได้</b>',
                    'พิมพ์ <b>"ยืนยัน"</b> เพื่อดำเนินการ '
                    'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้',
                ),
            ))
            return

        pending = data.get('pending_date')
        if not pending:
            self._post_bot('ข้อมูลวันที่หายไป กรุณาเริ่มใหม่จากแท็บ "ตัวช่วย AI-IT"')
            self.sudo().write({'state': 'cancelled'})
            return

        # เอกสารอาจถูกลงบันทึกไประหว่างที่คุยกันอยู่ ต้องเช็คซ้ำก่อนเขียน
        if move.state != 'draft':
            self._post_bot('⛔ เอกสารนี้ไม่ได้เป็นฉบับร่างแล้ว (สถานะ: %s) '
                           'จึงแก้วันที่ไม่ได้ กรุณาเริ่มใหม่'
                           % html_escape(move.state))
            self.sudo().write({'state': 'cancelled'})
            return

        # เก็บหมายเหตุไว้ก่อน แล้วขอให้ยืนยันอีกชั้น — การแก้วันที่กระทบงวดบัญชี
        # จึงต้องให้พนักงานเห็นสรุป "ก่อน → หลัง" พร้อมเหตุผลของตัวเองอีกรอบ
        new_date = fields.Date.to_date(pending)
        self.sudo().write({'change_note': note, 'state': 'confirm_date'})

        detail = _rows(
            _title('ตรวจทานก่อนแก้วันที่', '📋'),
            _kv('เอกสาร', '<b>%s</b>' % html_escape(self.document_ref or '')),
            _kv('วันที่เอกสาร', '%s → <b>%s</b>' % (_dt(move.invoice_date), _dt(new_date))),
            _kv('วันที่ลงบัญชี', '%s → <b>%s</b>' % (_dt(move.date), _dt(new_date))),
            _kv('เหตุผล', '<b>%s</b>' % html_escape(note)),
            _kv('ที่มา', 'ดึงวันที่สั่งซื้อจากใบสั่งขาย <b>%s</b>'
                % html_escape(data.get('order_name') or ''))
            if data.get('source') == 'order' else None,
        )
        self._post_bot(_block(
            detail,
            'พิมพ์ <b>"ยืนยัน"</b> เพื่อแก้วันที่ '
            'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้',
        ))

    def _step_confirm_date(self, text):
        if not _is_command(text, CONFIRM_WORDS):
            self._post_bot('กรุณาพิมพ์ <b>"ยืนยัน"</b> เพื่อแก้วันที่ '
                           'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้')
            return

        if self._get_data().get('plan') == 'return_date':
            self._apply_return_date()
            return

        move = self.env['account.move'].sudo().browse(self.document_id)
        if not move.exists():
            self._post_bot('⛔ ไม่พบเอกสารนี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        data = self._get_data()
        pending = data.get('pending_date')
        note = self.change_note or ''
        if not pending:
            self._post_bot('ข้อมูลวันที่หายไป กรุณาเริ่มใหม่จากแท็บ "ตัวช่วย AI-IT"')
            self.sudo().write({'state': 'cancelled'})
            return

        # เอกสารอาจถูกลงบันทึกไประหว่างที่คุยกันอยู่ ต้องเช็คซ้ำก่อนเขียนเสมอ
        move.invalidate_recordset()
        if move.state != 'draft':
            self._post_bot('⛔ เอกสารนี้ไม่ได้เป็นฉบับร่างแล้ว (สถานะ: %s) '
                           'จึงแก้วันที่ไม่ได้ กรุณาเริ่มใหม่'
                           % html_escape(move.state))
            self.sudo().write({'state': 'cancelled'})
            return

        new_date = fields.Date.to_date(pending)
        source_note = ''
        if data.get('source') == 'order':
            source_note = 'ดึงวันที่สั่งซื้อจากใบสั่งขาย %s' % (data.get('order_name') or '')
        full_note = Markup('เหตุผล: %s') % note
        if source_note:
            full_note = Markup('%s<br/>ที่มา: %s') % (full_note, source_note)

        try:
            result = self.env['npd.ai.it.invoice.fix'].apply_date_isolated(
                move.id, new_date, note=full_note,
                actor_name=self.env.user.display_name)
        except Exception as error:  # noqa: BLE001 - ต้องตอบกลับในแชทเสมอ
            _logger.exception('ตัวช่วย AI-IT: แก้วันที่ %s ไม่สำเร็จ', self.document_ref)
            self._post_bot(
                '⛔ <b>แก้วันที่ไม่สำเร็จ</b><br/>%s<br/><br/>'
                '<i>ระบบย้อนกลับให้แล้ว เอกสารยังเป็นวันที่เดิม '
                'กรุณาแจ้งฝ่าย IT พร้อมข้อความนี้</i>'
                % html_escape(str(error) or error.__class__.__name__)
            )
            self.sudo().write({'state': 'done'})
            return

        lines = [_block(
            _rows(
                _title('แก้วันที่เรียบร้อยแล้ว', '✅'),
                _kv('เอกสาร', '<b>%s</b>' % html_escape(self.document_ref or '')),
                _kv('วันที่เอกสาร', '%s → <b>%s</b>'
                    % (_dt(result['old_invoice_date']), _dt(result['new_date']))),
                _kv('วันที่ลงบัญชี', '%s → <b>%s</b>'
                    % (_dt(result['old_date']), _dt(result['new_date']))),
                _kv('เหตุผล', html_escape(note)),
                _kv('ที่มา', html_escape(source_note)) if source_note else None,
            ),
            _rows(
                _hint('บันทึกเหตุผลไว้ในประวัติของเอกสารแล้ว'),
                _hint('ถ้าวันครบกำหนดชำระต้องเลื่อนตาม กรุณาแก้ที่หน้าเอกสารเอง'),
                _hint('มีเอกสารอื่นอีกไหม? พิมพ์ "เริ่มใหม่" ได้เลย'),
            ),
        )]

        self.sudo().write({
            'state': 'done',
            'change_note': note,
            'summary': html2plaintext('<br/>'.join(lines)),
        })
        self._log_history('invoice_date', html2plaintext(
            'วันที่ใบแจ้งหนี้: %s → %s<br/>วันที่ลงบัญชี: %s → %s%s'
            % (result['old_invoice_date'] or '-', result['new_date'],
               result['old_date'] or '-', result['new_date'],
               '<br/>%s' % source_note if source_note else '')
        ))
        self._post_bot('<br/>'.join(lines))

    # ==================================================================
    # หัวข้อที่ 3 : แก้ไขวันที่คืนสินค้า
    # ==================================================================
    def _handle_return_date_fix(self, text):
        self.ensure_one()
        if self.state == 'ask_return_doc':
            self._step_ask_return_doc(text)
        elif self.state == 'ask_return_date':
            self._step_ask_return_date(text)
        elif self.state == 'ask_reason':
            self._step_ask_reason(text)
        elif self.state == 'confirm_date':
            self._step_confirm_date(text)
        else:
            self._recover_unknown_state()

    # ---- ขั้นที่ 1: รับเลขที่ใบคืน ------------------------------------
    def _step_ask_return_doc(self, text):
        Fix = self.env['npd.ai.it.picking.fix']
        picking, error = Fix.find_return_picking(text)
        if error:
            self._post_bot('⛔ %s' % error)
            return
        if not picking:
            self._post_bot('กรุณาพิมพ์ <b>เลขที่ใบคืน</b> ครับ เช่น <b>W3/IN/08511</b>')
            return

        branch, branch_error = self.env['npd.ai.it.stock.fix'].resolve_branch(
            picking, self.env.user)
        if branch_error:
            self._post_bot('⛔ %s' % html_escape(branch_error))
            self.sudo().write({'state': 'cancelled'})
            return

        current_local = Fix.to_local(picking.return_date)
        self.sudo().write({
            'document_ref': picking.name,
            'document_model': picking._name,
            'document_id': picking.id,
            'branch_id': branch.id if branch else False,
        })
        self._set_data({'plan': 'return_date'})
        self.sudo().write({'state': 'ask_return_date'})

        returned_from = Fix.returned_from(picking)
        state_label = dict(picking._fields['state'].selection).get(
            picking.state, picking.state)
        self._post_bot(_block(
            _rows(
                _title(html_escape(picking.name or ''), '↩️'),
                _kv('สาขา', html_escape(branch.name if branch else '—')),
                _kv('การส่งคืนของ', html_escape(returned_from or '—')),
                _kv('วันที่คืนปัจจุบัน',
                    '<b>%s</b>' % (_dt(current_local) if current_local else '—')),
                _kv('สถานะ', html_escape(state_label)),
            ),
            _rows(
                '<b>พิมพ์วันที่คืนใหม่</b>ที่ต้องการ',
                _hint('เช่น %s' % _dt(current_local or datetime.now())),
            ),
        ))

    # ---- ขั้นที่ 2: รับวันที่คืนใหม่ -----------------------------------
    def _step_ask_return_date(self, text):
        Fix = self.env['npd.ai.it.picking.fix']
        picking = self.env['stock.picking'].sudo().browse(self.document_id)
        if not picking.exists():
            self._post_bot('⛔ ไม่พบใบคืนนี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        current_local = Fix.to_local(picking.return_date)
        reference = current_local or datetime.now()
        new_local = self._parse_datetime(text, reference)
        if not new_local:
            self._post_bot(_rows(
                'อ่านวันที่ไม่ออกครับ 🙏 <b>พิมพ์วันที่ใหม่มาได้เลย</b>',
                _hint('เช่น %s · %s'
                      % (_dt(reference), reference.strftime('%Y-%m-%d'))),
            ))
            return

        data = self._get_data()
        data.update({
            'plan': 'return_date',
            'pending_return_dt': new_local.strftime('%Y-%m-%d %H:%M:%S'),
        })
        self._set_data(data)
        self.sudo().write({'state': 'ask_reason'})
        self._ask_change_reason('แก้วันที่คืน')

    def _step_confirm_return_date(self):
        """แสดงสรุปก่อนยืนยัน (เรียกจาก _step_ask_reason เมื่อ plan = return_date)"""
        Fix = self.env['npd.ai.it.picking.fix']
        picking = self.env['stock.picking'].sudo().browse(self.document_id)
        data = self._get_data()
        current_local = Fix.to_local(picking.return_date)
        new_local = fields.Datetime.to_datetime(data.get('pending_return_dt'))
        self._post_bot(_block(
            _rows(
                _title('ตรวจทานก่อนแก้วันที่คืน', '📋'),
                _kv('ใบคืน', '<b>%s</b>' % html_escape(self.document_ref or '')),
                _kv('วันที่คืน', '%s → <b>%s</b>'
                    % (_dt(current_local) if current_local else '—', _dt(new_local))),
                _kv('เหตุผล', '<b>%s</b>' % html_escape(self.change_note or '')),
            ),
            'พิมพ์ <b>"ยืนยัน"</b> เพื่อแก้วันที่คืน '
            'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้',
        ))

    def _apply_return_date(self):
        """ลงมือแก้จริง (เรียกจาก _step_confirm_date เมื่อ plan = return_date)"""
        Fix = self.env['npd.ai.it.picking.fix']
        picking = self.env['stock.picking'].sudo().browse(self.document_id)
        if not picking.exists():
            self._post_bot('⛔ ไม่พบใบคืนนี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        # สถานะอาจเปลี่ยนไประหว่างที่คุยกันอยู่ ต้องเช็คซ้ำก่อนเขียนเสมอ
        picking.invalidate_recordset()
        blocked = Fix.deposit_block_reason(picking)
        if blocked:
            self._post_bot('⛔ %s' % blocked)
            self.sudo().write({'state': 'cancelled'})
            return

        data = self._get_data()
        pending = data.get('pending_return_dt')
        if not pending:
            self._post_bot('ข้อมูลวันที่หายไป กรุณาเริ่มใหม่จากแท็บ "ตัวช่วย AI-IT"')
            self.sudo().write({'state': 'cancelled'})
            return

        new_local = fields.Datetime.to_datetime(pending)
        new_utc = Fix.to_utc(new_local)
        note = self.change_note or ''
        try:
            result = Fix.apply_return_date_isolated(
                picking.id, new_utc, note=note,
                actor_name=self.env.user.display_name)
        except Exception as error:  # noqa: BLE001 - ต้องตอบกลับในแชทเสมอ
            _logger.exception('ตัวช่วย AI-IT: แก้วันที่คืน %s ไม่สำเร็จ', self.document_ref)
            self._post_bot(_block(
                _rows('<b class="text-danger">⛔ แก้วันที่คืนไม่สำเร็จ</b>',
                      html_escape(str(error) or error.__class__.__name__)),
                _hint('ระบบย้อนกลับให้แล้ว ใบคืนยังเป็นวันที่เดิม '
                      'กรุณาแจ้งฝ่าย IT พร้อมข้อความนี้'),
            ))
            self.sudo().write({'state': 'done'})
            return

        old_text = _dt(result['old_local']) if result['old_local'] else '—'
        new_text = _dt(result['new_local'])
        lines = [_block(
            _rows(
                _title('แก้วันที่คืนเรียบร้อยแล้ว', '✅'),
                _kv('ใบคืน', '<b>%s</b>' % html_escape(self.document_ref or '')),
                _kv('วันที่คืน', '%s → <b>%s</b>' % (old_text, new_text)),
                _kv('เหตุผล', html_escape(note)),
            ),
            _hint('มีเอกสารอื่นอีกไหม? พิมพ์ "เริ่มใหม่" ได้เลย'),
        )]

        self.sudo().write({
            'state': 'done',
            'summary': html2plaintext('<br/>'.join(lines)),
        })
        self._log_history('return_date',
                          'วันที่คืน: %s → %s' % (old_text, new_text))
        self._post_bot('<br/>'.join(lines))

    # ==================================================================
    # หัวข้อที่ 4 : แก้ไขสถานะการเช่า
    # ==================================================================
    def _handle_rental_status_fix(self, text):
        self.ensure_one()
        if self.state == 'ask_rental_doc':
            self._step_ask_rental_doc(text)
        elif self.state == 'ask_reason':
            self._step_ask_reason(text)
        elif self.state == 'confirm_status':
            self._step_confirm_status(text)
        else:
            self._recover_unknown_state()

    # ---- ขั้นที่ 1: รับเลขที่ใบสั่งขาย แล้วคำนวณสถานะใหม่ให้เลย ---------
    def _step_ask_rental_doc(self, text):
        Fix = self.env['npd.ai.it.rental.fix']
        order, error = Fix.find_order(text)
        if error:
            self._post_bot('⛔ %s' % error)
            return
        if not order:
            self._post_bot('กรุณาพิมพ์ <b>เลขที่ใบสั่งขาย</b> ครับ '
                           'เช่น <b>SO-25100600028</b>')
            return

        branch, branch_error = self.env['npd.ai.it.stock.fix'].resolve_branch(
            order, self.env.user)
        if branch_error:
            self._post_bot('⛔ %s' % html_escape(branch_error))
            self.sudo().write({'state': 'cancelled'})
            return

        header = _rows(
            _title(html_escape(order.name or ''), '🔄'),
            _kv('สาขา', html_escape(branch.name if branch else '—')),
            _kv('สถานะการเช่าปัจจุบัน',
                '<b>%s</b>' % html_escape(Fix.label(order.rental_status))),
        )

        blocked = Fix.status_block_reason(order) or Fix.deposit_block_reason(order)
        if blocked:
            self._post_bot(_block(header, '⛔ %s' % blocked))
            self.sudo().write({'state': 'cancelled'})
            return

        new_status, end_date, status_error = Fix.target_status(order)
        if status_error:
            self._post_bot(_block(header, '⛔ %s' % status_error))
            self.sudo().write({'state': 'cancelled'})
            return

        if new_status == order.rental_status:
            self._post_bot(_block(
                header,
                _rows(
                    _title('สถานะถูกต้องอยู่แล้ว', '✅'),
                    _kv('วันที่สิ้นสุดการเช่า', _dt(end_date)),
                    'ไม่ต้องแก้อะไรครับ',
                ),
            ))
            self.sudo().write({'state': 'done'})
            return

        self.sudo().write({
            'document_ref': order.name,
            'document_model': order._name,
            'document_id': order.id,
            'branch_id': branch.id if branch else False,
        })
        self._set_data({'plan': 'rental_status', 'new_status': new_status})
        self.sudo().write({'state': 'ask_reason'})

        today = fields.Date.context_today(self)
        self._post_bot(_block(
            header,
            _rows(
                _kv('วันที่สิ้นสุดการเช่า', '<b>%s</b>' % _dt(end_date)),
                _kv('วันนี้', _dt(today)),
                _kv('สถานะที่ควรเป็น',
                    '<b>%s</b>' % html_escape(Fix.label(new_status))),
                _hint('วันนี้เกินวันสิ้นสุดการเช่าแล้ว' if new_status == 'overdue'
                      else 'วันนี้ยังไม่ถึงวันสิ้นสุดการเช่า'),
            ),
        ), commands=False)
        self._ask_change_reason('ถอยสถานะการเช่า')

    def _step_confirm_rental_status(self):
        """แสดงสรุปก่อนยืนยัน (เรียกจาก _step_ask_reason เมื่อ plan = rental_status)"""
        Fix = self.env['npd.ai.it.rental.fix']
        order = self.env['sale.order'].sudo().browse(self.document_id)
        data = self._get_data()
        self._post_bot(_block(
            _rows(
                _title('ตรวจทานก่อนแก้สถานะ', '📋'),
                _kv('ใบสั่งขาย', '<b>%s</b>' % html_escape(self.document_ref or '')),
                _kv('สถานะการเช่า', '%s → <b>%s</b>'
                    % (html_escape(Fix.label(order.rental_status)),
                       html_escape(Fix.label(data.get('new_status'))))),
                _kv('เหตุผล', '<b>%s</b>' % html_escape(self.change_note or '')),
            ),
            'พิมพ์ <b>"ยืนยัน"</b> เพื่อแก้สถานะ '
            'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้',
        ))

    def _step_confirm_status(self, text):
        if not _is_command(text, CONFIRM_WORDS):
            self._post_bot('กรุณาพิมพ์ <b>"ยืนยัน"</b> เพื่อแก้สถานะ '
                           'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้')
            return

        Fix = self.env['npd.ai.it.rental.fix']
        order = self.env['sale.order'].sudo().browse(self.document_id)
        if not order.exists():
            self._post_bot('⛔ ไม่พบใบสั่งขายนี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        # สถานะและด่านคืนเงินประกันอาจเปลี่ยนไประหว่างที่คุยกันอยู่ เช็คซ้ำก่อนเขียน
        order.invalidate_recordset()
        blocked = Fix.status_block_reason(order) or Fix.deposit_block_reason(order)
        if blocked:
            self._post_bot('⛔ %s' % blocked)
            self.sudo().write({'state': 'cancelled'})
            return

        data = self._get_data()
        new_status = data.get('new_status')
        if not new_status:
            self._post_bot('ข้อมูลสถานะหายไป กรุณาเริ่มใหม่จากแท็บ "ตัวช่วย AI-IT"')
            self.sudo().write({'state': 'cancelled'})
            return

        note = self.change_note or ''
        try:
            result = Fix.apply_status_isolated(
                order.id, new_status, note=note,
                actor_name=self.env.user.display_name)
        except Exception as error:  # noqa: BLE001 - ต้องตอบกลับในแชทเสมอ
            _logger.exception('ตัวช่วย AI-IT: แก้สถานะการเช่า %s ไม่สำเร็จ',
                              self.document_ref)
            self._post_bot(_block(
                _rows('<b class="text-danger">⛔ แก้สถานะไม่สำเร็จ</b>',
                      html_escape(str(error) or error.__class__.__name__)),
                _hint('ระบบย้อนกลับให้แล้ว สถานะยังเป็นค่าเดิม '
                      'กรุณาแจ้งฝ่าย IT พร้อมข้อความนี้'),
            ))
            self.sudo().write({'state': 'done'})
            return

        old_label = Fix.label(result['old_status'])
        new_label = Fix.label(result['new_status'])
        lines = [_block(
            _rows(
                _title('แก้สถานะการเช่าเรียบร้อยแล้ว', '✅'),
                _kv('ใบสั่งขาย', '<b>%s</b>' % html_escape(self.document_ref or '')),
                _kv('สถานะการเช่า', '%s → <b>%s</b>'
                    % (html_escape(old_label), html_escape(new_label))),
                _kv('เหตุผล', html_escape(note)),
            ),
            _rows(
                _hint('สถานะนี้เป็นฟิลด์ที่ระบบคำนวณเอง ถ้ามีการแก้วันที่เช่า '
                      'หรือใบแจ้งหนี้ทีหลัง ระบบอาจคำนวณทับได้'),
                _hint('มีเอกสารอื่นอีกไหม? พิมพ์ "เริ่มใหม่" ได้เลย'),
            ),
        )]

        self.sudo().write({
            'state': 'done',
            'summary': html2plaintext('<br/>'.join(lines)),
        })
        self._log_history('rental_status',
                          'สถานะการเช่า: %s → %s' % (old_label, new_label))
        self._post_bot('<br/>'.join(lines))

    # ==================================================================
    # หัวข้อที่ 5 : แก้การปัดเศษ VAT ในใบแจ้งหนี้ (สลับได้ทั้งไปและกลับ)
    # ==================================================================
    def _handle_vat_round_fix(self, text):
        self.ensure_one()
        if self.state == 'ask_vat_doc':
            self._step_ask_vat_doc(text)
        elif self.state == 'ask_vat_mode':
            self._step_ask_vat_mode(text)
        elif self.state == 'ask_reason':
            self._step_ask_reason(text)
        elif self.state == 'confirm_vat':
            self._step_confirm_vat(text)
        else:
            self._recover_unknown_state()

    # ---- ขั้นที่ 1: รับเอกสาร แล้วเทียบสองแบบให้ดู ----------------------
    def _step_ask_vat_doc(self, text):
        Fix = self.env['npd.ai.it.vat.fix']
        move, error = Fix.find_move(text)
        if error:
            self._post_bot('⛔ %s' % error)
            return
        if not move:
            self._post_bot('กรุณาพิมพ์ <b>เลขที่ใบแจ้งหนี้</b> '
                           'หรือวาง <b>URL</b> ของหน้านั้นครับ')
            return

        branch, branch_error = self.env['npd.ai.it.stock.fix'].resolve_branch(
            move, self.env.user)
        if branch_error:
            self._post_bot('⛔ %s' % html_escape(branch_error))
            self.sudo().write({'state': 'cancelled'})
            return

        plan, error = Fix.analyze(move)
        if error:
            self._post_bot('⛔ %s' % error)
            self.sudo().write({'state': 'cancelled'})
            return

        # ปัดแล้วลงตัวพอดีทั้งสองแบบ = ไม่มีอะไรให้เลือก จบตรงนี้
        if plan['same']:
            self._post_bot(_block(
                _rows(
                    _title('ใบนี้ไม่มีเศษให้แก้', '✅'),
                    _kv('ใบแจ้งหนี้', '<b>%s</b>' % html_escape(plan['move_name'])),
                    _kv('ยอดก่อน VAT', '<b>%s</b>' % _baht(plan['old_untaxed'])),
                    _kv('ภาษีมูลค่าเพิ่ม 7%', '<b>%s</b>' % _baht(plan['old_tax'])),
                ),
                _hint('คิดแบบยอดรวมหรือแบบรายบรรทัดก็ได้เลขเท่ากัน '
                      'ไม่ว่าลูกค้าจะคิดวิธีไหนก็ตรงกับใบนี้อยู่แล้วครับ'),
            ))
            self.sudo().write({'state': 'done'})
            return

        self.sudo().write({
            'document_ref': move.name or '',
            'document_model': move._name,
            'document_id': move.id,
            'branch_id': branch.id if branch else False,
        })
        self._set_data({'plan': 'vat_round', 'analysis': plan})
        self.sudo().write({'state': 'ask_vat_mode'})
        self._post_vat_choices(plan)

    def _post_vat_choices(self, plan):
        """กล่องเทียบสองแบบ — ให้เห็นทันทีว่าตอนนี้เป็นแบบไหนและอีกแบบได้เท่าไร"""
        current = plan.get('current_mode')
        blocks = [_rows(
            _title(html_escape(plan['move_name']), '🧮'),
            _kv('ยอดรวมทั้งสิ้น', '<b>%s บาท</b>' % _baht(plan['gross'])),
            _hint('ยอดรวมนี้ไม่เปลี่ยน ไม่ว่าจะเลือกแบบไหน '
                  'ย้ายแค่เศษสตางค์ระหว่างช่องก่อน VAT กับช่อง VAT'),
        )]

        for number, mode in ((1, 'total'), (2, 'line')):
            detail = plan['modes'][mode]
            heading = '<b>%d) %s</b>' % (number, VAT_MODE_NAME[mode])
            if mode == current:
                heading += ' <span class="text-muted">— ใบนี้ใช้อยู่ตอนนี้</span>'
            blocks.append(_rows(
                heading,
                _indent(_rows(
                    _kv('ก่อน VAT', '<b>%s</b>' % _baht(detail['untaxed'])),
                    _kv('VAT 7%', '<b>%s</b>' % _baht(detail['tax'])),
                    _hint(VAT_MODE_HOW[mode]),
                    _hint(VAT_MODE_WHO[mode]),
                )),
            ))

        if current is None:
            # ใบที่ยอดไม่ตรงกับสูตรไหนเลย เคยเจอในใบเก่าที่เคยแก้มือมาก่อน
            blocks.append(_rows(
                '<b class="text-danger">⚠️ ตอนนี้ใบนี้ไม่ตรงกับทั้งสองแบบ</b>',
                _kv('ยอดปัจจุบัน', 'ก่อน VAT <b>%s</b> · VAT <b>%s</b>'
                    % (_baht(plan['old_untaxed']), _baht(plan['old_tax']))),
                _hint('เลือกแบบที่ต้องการได้เลย ระบบจะจัดให้ตรงสูตรนั้น'),
            ))

        blocks.append(_rows(
            'พิมพ์ <b>1</b> หรือ <b>2</b> เพื่อเลือกแบบที่ต้องการ',
            _hint('ถ้าเคยให้แก้เป็นแบบยอดรวมไปแล้วอยากได้ของเดิมคืน '
                  'พิมพ์ <b>"ถอยกลับ"</b> ก็ได้ครับ'),
        ))
        self._post_bot(_block(*blocks))

    # ---- ขั้นที่ 2: เลือกแบบ ------------------------------------------
    def _step_ask_vat_mode(self, text):
        data = self._get_data()
        plan = data.get('analysis') or {}
        mode = self._parse_vat_mode(text)
        if not mode:
            self._post_bot('ยังไม่แน่ใจว่าเลือกแบบไหนครับ 🙏<br/>'
                           'พิมพ์ <b>1</b> = แบบยอดรวม หรือ <b>2</b> = แบบรายบรรทัด '
                           '(หรือพิมพ์ <b>"ถอยกลับ"</b> เพื่อเอาแบบเดิมคืน)')
            return

        if mode == plan.get('current_mode'):
            self._post_bot(_block(
                _rows(
                    _title('ใบนี้เป็น%sอยู่แล้ว' % VAT_MODE_NAME[mode], 'ℹ️'),
                    _kv('ก่อน VAT', '<b>%s</b>' % _baht(plan['old_untaxed'])),
                    _kv('VAT 7%', '<b>%s</b>' % _baht(plan['old_tax'])),
                ),
                'ถ้าต้องการอีกแบบให้พิมพ์เลขอีกข้อ '
                'หรือพิมพ์ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้',
            ))
            return

        data['mode'] = mode
        self._set_data(data)
        self.sudo().write({'state': 'ask_reason'})
        self._ask_change_reason('เปลี่ยนเป็น%s' % VAT_MODE_NAME[mode])

    def _parse_vat_mode(self, text):
        """อ่านคำตอบของพนักงานเป็น 'total' / 'line' (None = อ่านไม่ออก)"""
        if _is_command(text, VAT_TOTAL_WORDS):
            return 'total'
        if _is_command(text, VAT_LINE_WORDS):
            return 'line'
        match = re.search(r'\d+', text or '')
        if match:
            return {'1': 'total', '2': 'line'}.get(match.group())
        return None

    # ---- ขั้นที่ 3: ตรวจทานก่อนยืนยัน ---------------------------------
    def _step_confirm_vat_round(self):
        """เรียกจาก _step_ask_reason เมื่อ plan = vat_round"""
        data = self._get_data()
        plan = data.get('analysis') or {}
        mode = data.get('mode')
        detail = (plan.get('modes') or {}).get(mode) or {}

        changed_lines = [item for item in detail.get('lines', [])
                         if abs(item['new'] - item['old']) >= 0.005]
        line_rows = [
            _kv(html_escape(item['name'][:40]),
                '%s → <b>%s</b>' % (_baht(item['old']), _baht(item['new'])))
            for item in changed_lines
        ]

        blocks = [_rows(
            _title('ตรวจทานก่อนแก้', '📋'),
            _kv('ใบแจ้งหนี้', '<b>%s</b>' % html_escape(self.document_ref or '')),
            _kv('เปลี่ยนเป็น', '<b>%s</b>' % VAT_MODE_NAME.get(mode, '—')),
        ), _rows(
            _kv('ก่อน VAT', '%s → <b>%s</b>'
                % (_baht(plan.get('old_untaxed')), _baht(detail.get('untaxed')))),
            _kv('VAT 7%', '%s → <b>%s</b>'
                % (_baht(plan.get('old_tax')), _baht(detail.get('tax')))),
            _kv('ยอดรวมทั้งสิ้น', '<b>%s</b> <span class="text-muted">'
                '(เท่าเดิม)</span>' % _baht(plan.get('gross'))),
        )]

        if line_rows:
            blocks.append(_rows(_title('บรรทัดที่ยอดก่อน VAT เปลี่ยน'),
                                _indent(_rows(*line_rows))))

        blocks.append(_rows(
            _kv('เหตุผล', '<b>%s</b>' % html_escape(self.change_note or '')),
            _hint('ระบบจะแก้ยอดภาษีขายในรายงานภาษี (ภ.พ.30) ให้ตรงกันด้วย'),
        ))
        blocks.append('พิมพ์ <b>"ยืนยัน"</b> เพื่อแก้ '
                      'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้')
        self._post_bot(_block(*blocks))

    # ---- ขั้นที่ 4: ลงมือแก้ -------------------------------------------
    def _step_confirm_vat(self, text):
        if not _is_command(text, CONFIRM_WORDS):
            self._post_bot('กรุณาพิมพ์ <b>"ยืนยัน"</b> เพื่อแก้ '
                           'หรือ <b>"ยกเลิก"</b> เพื่อออกจากรายการนี้')
            return

        Fix = self.env['npd.ai.it.vat.fix']
        move = self.env['account.move'].sudo().browse(self.document_id)
        if not move.exists():
            self._post_bot('⛔ ไม่พบใบแจ้งหนี้นี้แล้ว (อาจถูกลบไป)')
            self.sudo().write({'state': 'cancelled'})
            return

        data = self._get_data()
        mode = data.get('mode')
        if mode not in ('total', 'line'):
            self._post_bot('ข้อมูลที่เลือกไว้หายไป กรุณาเริ่มใหม่จากแท็บ '
                           '"ตัวช่วย AI-IT"')
            self.sudo().write({'state': 'cancelled'})
            return

        note = self.change_note or ''
        try:
            result = Fix.apply_fix_isolated(
                move.id, mode, note=note,
                actor_name=self.env.user.display_name)
        except Exception as error:  # noqa: BLE001 - ต้องตอบกลับในแชทเสมอ
            _logger.exception('ตัวช่วย AI-IT: แก้การปัดเศษ VAT ของ %s ไม่สำเร็จ',
                              self.document_ref)
            self._post_bot(_block(
                _rows('<b class="text-danger">⛔ แก้ไม่สำเร็จ</b>',
                      html_escape(str(error) or error.__class__.__name__)),
                _hint('ระบบย้อนกลับให้แล้ว ยอดในใบยังเป็นค่าเดิมทุกอย่าง '
                      'กรุณาแจ้งฝ่าย IT พร้อมข้อความนี้'),
            ))
            self.sudo().write({'state': 'done'})
            return

        if not result.get('applied'):
            self._post_bot(_block(
                _rows(_title('ใบนี้เป็นแบบที่เลือกอยู่แล้ว', 'ℹ️'),
                      _hint('ไม่ได้แก้อะไร ยอดคงเดิมทุกช่อง')),
                _hint('มีใบอื่นอีกไหม? พิมพ์ "เริ่มใหม่" ได้เลย'),
            ))
            self.sudo().write({'state': 'done'})
            return

        summary = _block(
            _rows(
                _title('แก้เรียบร้อยแล้ว', '✅'),
                _kv('ใบแจ้งหนี้', '<b>%s</b>' % html_escape(self.document_ref or '')),
                _kv('ตอนนี้เป็น', '<b>%s</b>' % VAT_MODE_NAME.get(mode, '—')),
            ),
            _rows(
                _kv('ก่อน VAT', '%s → <b>%s</b>'
                    % (_baht(result['old_untaxed']), _baht(result['new_untaxed']))),
                _kv('VAT 7%', '%s → <b>%s</b>'
                    % (_baht(result['old_tax']), _baht(result['new_tax']))),
                _kv('ยอดรวมทั้งสิ้น', '<b>%s</b> <span class="text-muted">'
                    '(เท่าเดิม)</span>' % _baht(result['gross'])),
                _kv('เหตุผล', html_escape(note)),
            ),
            _rows(
                _hint('พิมพ์ใบเสร็จ/ใบกำกับภาษีใหม่ได้เลย ยอดจะตรงตามนี้'),
                _hint('ยอดภาษีขายในรายงานภาษีเปลี่ยนตามไปด้วย %s บาท '
                      'ถ้ายื่นแบบของเดือนนี้ไปแล้ว ควรแจ้งฝ่ายบัญชีทราบ'
                      % _baht(result['new_tax'] - result['old_tax'])),
                _hint('ถ้าต้องการกลับเป็นแบบเดิม พิมพ์ "เริ่มใหม่" '
                      'แล้วเลือกหัวข้อนี้อีกครั้งได้ตลอด'),
            ),
        )

        self.sudo().write({
            'state': 'done',
            'summary': html2plaintext(summary),
        })
        self._log_history(
            'invoice_vat_round',
            'เปลี่ยนเป็น%s · ก่อน VAT %s → %s · VAT %s → %s (ยอดรวม %s เท่าเดิม)'
            % (VAT_MODE_NAME.get(mode, mode),
               _baht(result['old_untaxed']), _baht(result['new_untaxed']),
               _baht(result['old_tax']), _baht(result['new_tax']),
               _baht(result['gross'])))
        self._post_bot(summary)

    # ------------------------------------------------------------------
    # การอ่านข้อความของพนักงาน (regex ก่อน แล้วค่อยให้ AI ช่วยถ้าอ่านไม่ออก)
    # ------------------------------------------------------------------
    def _item_label(self, item):
        # item['name'] มาจาก product.display_name ซึ่งมี [รหัสสินค้า] นำหน้าให้อยู่แล้ว
        return item['name']

    def _parse_doc_number(self, text):
        """คืน (เลขที่อ่านได้, record ของเอกสาร)"""
        Fix = self.env['npd.ai.it.stock.fix']
        candidates = []
        stripped = text.strip()
        if stripped:
            candidates.append(stripped)
        candidates += re.findall(r'[A-Za-z][A-Za-z0-9]*\d[A-Za-z0-9/_.\-]*', text)
        candidates += re.findall(r'\b\d{4,}\b', text)

        seen = set()
        for candidate in candidates:
            candidate = candidate.strip().strip('.,;:!?"\'()[]')
            key = candidate.lower()
            if not candidate or key in seen:
                continue
            seen.add(key)
            document, _error = Fix.find_document(candidate)
            if document:
                return candidate, document

        # อ่านเองไม่ออก -> ให้ AI ช่วยสกัดเลขเอกสารจากประโยค
        answer = self.env['npd.ai.it.gemini'].extract_json(
            'พนักงานพิมพ์ข้อความนี้เข้ามาในระบบ ERP ของบริษัทให้เช่าอุปกรณ์:\n'
            '"""%s"""\n\n'
            'งานของคุณคือดึง "เลขที่เอกสาร" (เลขใบสั่งขาย หรือเลขใบจัดส่ง) '
            'ออกมาจากข้อความ โดยคัดลอกมาตามที่พิมพ์เป๊ะ ๆ ห้ามเดาหรือเติมเอง\n'
            'ถ้าไม่มีเลขเอกสารในข้อความ ให้ตอบค่าว่าง\n\n'
            'ตอบเป็น JSON เท่านั้น: {"doc_number": "S00123"}' % text[:500],
            max_output_tokens=128,
        )
        number = (answer.get('doc_number') or '').strip()
        if number:
            document, _error = Fix.find_document(number)
            if document:
                return number, document
            return number, None
        return (stripped[:64] or None), None

    def _parse_quantities(self, text, items):
        """คืน {ลำดับที่(1-based): จำนวนสต๊อกจริง}"""
        count = len(items)
        result = {}

        # (1) คู่ "ลำดับ=จำนวน" เช่น "1=10, 2=5" (บรรทัดเดียวหรือหลายบรรทัดก็ได้)
        # ต้องมาก่อนการอ่านทีละบรรทัด — เดิม (o14) อ่านทีละบรรทัดก่อน แล้ว "1=1, 2=30"
        # ถูกตีเป็นรายการที่ 1 = 30 (เลขตัวท้ายของบรรทัด) และรายการที่ 2 หายไป
        # ทั้งที่เป็นรูปแบบเดียวกับตัวอย่างที่บอทบอกให้ตอบ
        for index, qty in re.findall(r'(?<![\d.,])(\d{1,2})\s*[=:]\s*(\d+(?:\.\d+)?)', text):
            index = int(index)
            if 1 <= index <= count:
                result[index] = float(qty)
        if len(result) == count:
            return result

        # (2) ทีละบรรทัด เช่น "1) 10", "2 - 5" (ไม่ทับค่าที่อ่านจากคู่ด้านบนแล้ว)
        for line in text.splitlines():
            match = re.match(r'^\s*(\d{1,2})\s*[)\].:\-=]\s*(.+)$', line)
            if not match:
                continue
            index = int(match.group(1))
            numbers = re.findall(r'\d+(?:[.,]\d+)?', match.group(2))
            if 1 <= index <= count and numbers and index not in result:
                result[index] = float(numbers[-1].replace(',', ''))
        if len(result) == count:
            return result

        # (3) ตัวเลขล้วน จำนวนเท่ากับรายการพอดี -> ไล่ตามลำดับที่แสดงไป
        if not result:
            numbers = re.findall(r'\d+(?:[.,]\d+)?', text)
            if len(numbers) == count:
                return {i + 1: float(numbers[i].replace(',', '')) for i in range(count)}

        # (4) อ่านเองไม่ออก -> ให้ AI จับคู่ชื่อสินค้ากับจำนวนให้
        for index, qty in self._ai_parse_quantities(text, items).items():
            result.setdefault(index, qty)
        return result

    def _parse_date_in_month(self, text, ref_date):
        """อ่านวันที่จากข้อความ โดยมี ref_date (วันแรกของเดือนเอกสาร) เป็นตัวตั้ง

        รองรับ: "25", "25/8", "25/08/2026", "25/8/69" (พ.ศ.), "2026-08-25",
        "25 ส.ค. 69", "25 สิงหาคม 2569" และให้ AI ช่วยอ่านถ้าอ่านเองไม่ออก
        คืน datetime.date หรือ None
        """
        raw = (text or '').strip()
        if not raw:
            return None

        # (1) รูปแบบ ISO: 2026-08-25
        match = re.search(r'(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})', raw)
        if match:
            return self._build_date(int(match.group(3)), int(match.group(2)),
                                    int(match.group(1)), ref_date)

        # (2) เดือนเป็นตัวหนังสือไทย: "25 ส.ค. 69"
        #     ไล่จากคำยาวไปสั้น กันตัวย่อไปแมตช์ชนกับชื่อเต็มของเดือนอื่น
        for label, month in sorted(THAI_MONTHS.items(), key=lambda kv: -len(kv[0])):
            if label in raw:
                nums = re.findall(r'\d+', raw.replace(label, ' '))
                if nums:
                    day = int(nums[0])
                    year = int(nums[1]) if len(nums) > 1 else None
                    return self._build_date(day, month, year, ref_date)

        # (3) d/m/y, d-m-y, d.m.y (เดือนและปีใส่หรือไม่ใส่ก็ได้)
        match = re.search(r'(?<!\d)(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?:\s*[/\-.]\s*(\d{2,4}))?', raw)
        if match:
            year = int(match.group(3)) if match.group(3) else None
            return self._build_date(int(match.group(1)), int(match.group(2)), year, ref_date)

        # (4) วันที่อย่างเดียว: "25" หรือ "วันที่ 25"
        nums = re.findall(r'(?<!\d)(\d{1,2})(?!\d)', raw)
        if len(nums) == 1:
            return self._build_date(int(nums[0]), None, None, ref_date)

        # (5) อ่านเองไม่ออก -> ให้ AI ช่วย
        answer = self.env['npd.ai.it.gemini'].extract_json(
            'พนักงานกำลังตอบ "วันที่" ที่ต้องการเปลี่ยนในเอกสารบัญชี\n'
            'เดือนของเอกสารคือ %s (ปี ค.ศ. %d เดือน %d)\n'
            'พนักงานพิมพ์มาว่า:\n"""%s"""\n\n'
            'แปลงเป็นวันที่แบบ ค.ศ. ให้หน่อย โดย:\n'
            '1. ถ้าพนักงานระบุปีเป็น พ.ศ. (เช่น 2569 หรือ 69) ให้แปลงเป็น ค.ศ.\n'
            '2. ถ้าไม่ได้ระบุเดือน/ปี ให้ใช้เดือนและปีของเอกสาร\n'
            '3. ห้ามเดา ถ้าอ่านไม่ออกให้ตอบค่าว่าง\n\n'
            'ตอบเป็น JSON เท่านั้น: {"date": "YYYY-MM-DD"}'
            % (ref_date.strftime('%B %Y'), ref_date.year, ref_date.month, raw[:200]),
            max_output_tokens=128,
        )
        value = (answer.get('date') or '').strip()
        if value:
            try:
                return fields.Date.to_date(value)
            except (ValueError, TypeError):
                return None
        return None

    def _parse_datetime(self, text, ref_dt):
        """อ่าน "วันที่ (+เวลา)" จากข้อความ โดยมี ref_dt เป็นตัวตั้ง

        ไม่บังคับให้อยู่ในเดือนเดิมเหมือนหัวข้อแก้วันที่ใบแจ้งหนี้ เพราะวันที่คืน
        ของจริงข้ามเดือนได้ปกติ  ถ้าพนักงานไม่ใส่เวลามา จะคงเวลาเดิมของเอกสารไว้
        คืน naive datetime ตามเวลาผู้ใช้ หรือ None ถ้าอ่านไม่ออก
        """
        raw = (text or '').strip()
        if not raw:
            return None

        # ตัดส่วนเวลาออกก่อน แล้วค่อยส่งที่เหลือให้ตัวอ่านวันที่
        hour, minute = ref_dt.hour, ref_dt.minute
        time_match = re.search(r'(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?::[0-5]\d)?(?!\d)', raw)
        if time_match:
            hour, minute = int(time_match.group(1)), int(time_match.group(2))
            raw = (raw[:time_match.start()] + ' ' + raw[time_match.end():]).strip()

        new_date = self._parse_date_in_month(raw, ref_dt.date()) if raw else ref_dt.date()
        if not new_date:
            return None
        return datetime(new_date.year, new_date.month, new_date.day, hour, minute)

    def _build_date(self, day, month, year, ref_date):
        """ประกอบวันที่ พร้อมแปลง พ.ศ. -> ค.ศ. และเติมเดือน/ปีที่ขาดจากเอกสาร"""
        month = month or ref_date.month
        if year is None:
            year = ref_date.year
        elif year >= 2400:            # พ.ศ. เต็ม เช่น 2569
            year -= 543
        elif year < 100:              # ปีสองหลัก: ลองทั้ง พ.ศ. และ ค.ศ.
            candidates = [1957 + year, 2000 + year]   # 69 -> 2026 / 26 -> 2026
            year = next((c for c in candidates if c == ref_date.year), candidates[0])
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _ai_parse_quantities(self, text, items):
        listing = '\n'.join(
            '%d. %s (ต้องตัด %s %s)'
            % (i + 1, self._item_label(item), _fmt(item['need']), item.get('uom') or '')
            for i, item in enumerate(items)
        )
        answer = self.env['npd.ai.it.gemini'].extract_json(
            'ระบบกำลังถามพนักงานคลังว่า "จำนวนสต็อกจริง" ที่นับได้ของสินค้าแต่ละรายการ'
            'มีเท่าไหร่ รายการสินค้าที่ถามมีดังนี้:\n%s\n\n'
            'พนักงานตอบกลับมาว่า:\n"""%s"""\n\n'
            'งานของคุณคือจับคู่ว่าเลขไหนคือจำนวนสต็อกจริงของรายการไหน\n'
            'กติกา:\n'
            '1. ใช้เฉพาะตัวเลขที่พนักงานพิมพ์มาจริง ห้ามเดา ห้ามคำนวณ ห้ามเติมเอง\n'
            '2. รายการไหนที่พนักงานไม่ได้ระบุ ให้ข้ามไป อย่าใส่ลงในคำตอบ\n'
            '3. index คือลำดับตามรายการด้านบน (เริ่มที่ 1)\n\n'
            'ตอบเป็น JSON เท่านั้น: {"quantities": [{"index": 1, "qty": 10}]}'
            % (listing, text[:800]),
            max_output_tokens=512,
        )
        result = {}
        for row in (answer.get('quantities') or []):
            try:
                index = int(row.get('index'))
                qty = float(row.get('qty'))
            except (TypeError, ValueError):
                continue
            if 1 <= index <= len(items) and qty >= 0:
                result[index] = qty
        return result
