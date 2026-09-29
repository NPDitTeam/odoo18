# -*- coding: utf-8 -*-
"""เที่ยว "ส่งรถไปช่วยขนส่งอีกสาขา" ใช้หมายเหตุแทนการตรวจนับสินค้า

เที่ยวประเภทนี้ไม่ได้ขนของของตัวเอง แต่เอารถไปช่วยสาขาอื่น จึงไม่มีรายการ
สินค้าให้ตรวจนับ บังคับให้ตรวจนับเหมือนเที่ยวอื่นก็ได้แต่เป็นพิธีกรรมเปล่า ๆ
คนขับจะกด "ถูกต้องทั้งหมด" ผ่าน ๆ แล้วการตรวจนับทั้งระบบก็เสียความหมาย

เปลี่ยนเป็นให้คนขับเขียนว่าไปทำอะไรมาแทน แล้วให้ AI อ่านเทียบกับประเภทการ
จัดส่งที่ระบุไว้ ว่าสิ่งที่เขียนเข้ากันไหม เช่นอ้างว่าไปช่วยสาขาแต่เขียนว่า
ไปส่งของให้ลูกค้า ซึ่งคนละอัตราค่าเที่ยวกัน

AI เป็นตัวช่วยชี้เป้าให้คนตรวจ ไม่ได้ปิดกั้นการทำงาน ถ้า AI ไม่พร้อมหรือ
ตอบว่าไม่ตรง คนขับยังถ่ายรูปและออกรถได้ตามปกติ แค่ใบนั้นจะถูกตั้งธงไว้ให้
ฝ่ายตรวจสอบดูย้อนหลัง การให้ AI บล็อกงานหน้างานเสี่ยงกว่าปล่อยผ่านแล้วตรวจ
"""
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

PURPOSE_LABELS = {
    'to_customer': 'จัดส่งสินค้าไปยังลูกค้า',
    'from_customer': 'รับสินค้าจากลูกค้ามายังสาขา',
    'branch_transfer': 'โยกสินค้าจากสาขา ไปสาขา',
    'help_branch': 'ส่งรถไปช่วยขนส่งอีกสาขา',
}

AI_STATES = [
    ('pending', 'รอ AI ตรวจ'),
    ('match', 'หมายเหตุตรงกับประเภทงาน'),
    ('mismatch', 'หมายเหตุไม่ตรงกับประเภทงาน'),
    ('unclear', 'หมายเหตุกำกวม ตัดสินไม่ได้'),
    ('error', 'เรียก AI ไม่สำเร็จ'),
]


class VehicleBookingHelpBranchNote(models.Model):
    _inherit = 'vehicle.booking'

    needs_product_check = fields.Boolean(
        string='ต้องตรวจนับสินค้า', compute='_compute_needs_product_check',
        help='เที่ยวช่วยสาขาไม่มีสินค้าให้ตรวจ ใช้หมายเหตุแทน')

    help_branch_note = fields.Text(
        string='หมายเหตุการไปช่วยสาขา', copy=False,
        help='คนขับระบุว่าไปทำอะไรมา ใช้แทนการตรวจนับสินค้า')
    help_branch_ai_state = fields.Selection(
        AI_STATES, string='ผล AI ตรวจหมายเหตุ', readonly=True, copy=False)
    help_branch_ai_summary = fields.Html(
        string='ความเห็น AI', readonly=True, copy=False)
    help_branch_ai_date = fields.Datetime(
        string='เวลาที่ AI ตรวจ', readonly=True, copy=False)
    help_branch_ai_message = fields.Text(
        string='ความเห็น AI (ข้อความล้วน)', readonly=True, copy=False,
        help='ใช้ส่งให้แอปแสดง เพราะแอปเรนเดอร์ HTML ไม่ได้')
    help_branch_ai_example = fields.Text(
        string='ตัวอย่างข้อความที่ AI แนะนำ', readonly=True, copy=False,
        help='ร่างให้คนขับกดใช้แล้วแก้รายละเอียดเอง เมื่อหมายเหตุเดิมยังไม่ผ่าน')

    @api.depends('shipment_purpose')
    def _compute_needs_product_check(self):
        for record in self:
            record.needs_product_check = record.shipment_purpose != 'help_branch'

    # ------------------------------------------------------------------
    def _save_help_branch_note(self, note):
        """บันทึกหมายเหตุแล้วส่งให้ AI ตรวจ ใช้ร่วมกันทั้งแอปและหน้าจอ Odoo"""
        self.ensure_one()
        note = (note or '').strip()
        if not note:
            raise UserError(_('กรุณาระบุหมายเหตุว่าไปช่วยสาขาทำอะไรมา'))
        self.write({
            'help_branch_note': note,
            'help_branch_ai_state': 'pending',
            'help_branch_ai_summary': False,
            'help_branch_ai_message': False,
            'help_branch_ai_example': False,
            'help_branch_ai_date': False,
        })
        # AI ล้มไม่ควรทำให้คนขับเริ่มงานไม่ได้ เก็บสถานะ error ไว้ให้ตรวจทีหลัง
        try:
            self._run_help_branch_ai()
        except Exception:
            _logger.exception('[HelpBranch] %s: เรียก AI ไม่สำเร็จ', self.name)
            self.write({'help_branch_ai_state': 'error',
                        'help_branch_ai_date': fields.Datetime.now()})
        return True

    def _run_help_branch_ai(self):
        self.ensure_one()
        Gemini = self.env['npd.ai.it.gemini']
        if not Gemini.is_available():
            _logger.info('[HelpBranch] ยังไม่ได้ตั้งค่า AI Key ข้ามการตรวจ')
            self.write({'help_branch_ai_state': 'error',
                        'help_branch_ai_summary':
                            '<div>ยังไม่ได้ตั้งค่า AI Key จึงยังไม่ได้ตรวจ</div>',
                        'help_branch_ai_message':
                            'ยังไม่ได้ตั้งค่า AI Key จึงยังไม่ได้ตรวจหมายเหตุ',
                        'help_branch_ai_date': fields.Datetime.now()})
            return False

        facts = {
            'เลขที่การจอง': self.name or '',
            'ประเภทการจัดส่งที่ระบุไว้': PURPOSE_LABELS.get(
                self.shipment_purpose, self.shipment_purpose or ''),
            'หมายเหตุที่คนขับเขียน': self.help_branch_note or '',
            'หมายเหตุจาก Odoo 14': self.shipment_note or '',
            'สาขาต้นทาง': self.branch_id.name or '',
            'ลูกค้าในใบจอง': self.partner_id.name if self.partner_id else '',
            'สถานที่รับสินค้า': self.pickup_location or '',
            'ปลายทาง': self.destination or '',
            'คนขับ': self.driver_id.name if self.driver_id else '',
            'ค่าเที่ยว': self.travel_expenses,
            'เบี้ยเลี้ยง': self.daily_allowance,
        }
        prompt = (
            'คุณเป็นผู้ตรวจสอบภายในของบริษัทให้เช่าอุปกรณ์ก่อสร้างที่มีรถส่งของเอง\n\n'
            'นิยามของประเภท "ส่งรถไปช่วยขนส่งอีกสาขา" ที่ต้องเข้าใจให้ตรงกัน:\n'
            '- คือการเอารถกับคนขับของสาขาตัวเอง ไปช่วยทำงานขนส่งให้สาขาอื่น\n'
            '- การขนสินค้ายังเป็นเรื่องปกติของเที่ยวประเภทนี้ อย่าตัดสินว่าไม่ตรง '
            'เพียงเพราะหมายเหตุพูดถึงการขนของ เพราะไปช่วยสาขาก็คือไปช่วยขนของ\n'
            '- สิ่งที่ทำให้ "ไม่ตรง" คืองานนั้นไม่ใช่งานของสาขาอื่น เช่นไปส่งของ '
            'ให้ลูกค้าของสาขาตัวเอง ไปรับของจากลูกค้าเข้าสาขาตัวเอง '
            'หรือไปทำธุระอื่นที่ไม่เกี่ยวกับการช่วยสาขา\n\n'
            'ข้อมูลเที่ยว:\n%s\n\n'
            'สิ่งที่ต้องตัดสิน: หมายเหตุที่คนขับเขียน สอดคล้องกับประเภทการจัดส่ง '
            'ที่ระบุไว้หรือไม่\n'
            'บริบทที่ต้องรู้: แต่ละประเภทจ่ายค่าเที่ยวไม่เท่ากัน จึงมีแรงจูงใจให้เลือก '
            'ประเภทที่ได้เงินมากกว่าแล้วเขียนหมายเหตุให้ดูสมเหตุสมผล ถ้าหมายเหตุ '
            'บอกว่าไปส่งของให้ลูกค้าหรือไปรับของจากลูกค้า แต่ประเภทระบุว่าไปช่วยสาขา '
            'ถือว่าไม่ตรง\n\n'
            'ข้อควรระวัง: ช่องลูกค้า ปลายทาง และสถานที่รับสินค้าในใบจอง ถูกดึงมาจาก '
            'ระบบเก่าและมักไม่ตรงกับงานจริงของเที่ยวช่วยสาขา ถ้าข้อมูลพวกนั้นขัดกับ '
            'หมายเหตุ แต่ตัวหมายเหตุเองยังเข้าข่ายการไปช่วยสาขา ให้ตอบ unclear '
            'แล้วบอกให้ไปตรวจข้อมูลใบจอง อย่าตอบ mismatch เพราะข้อมูลส่วนนั้นอย่างเดียว\n\n'
            'ตอบเป็น JSON เท่านั้น:\n'
            '{"verdict": "match|mismatch|unclear", '
            '"summary": "เหตุผลสั้น ๆ 1-2 ประโยคภาษาไทย บอกคนขับว่าข้อความขาดอะไร", '
            '"suggest": "สิ่งที่ฝ่ายตรวจสอบควรตรวจต่อ หรือค่าว่างถ้าไม่มี", '
            '"example": "ตัวอย่างหมายเหตุที่เขียนถูกต้อง สำหรับให้คนขับกดใช้แล้ว'
            'แก้รายละเอียดเอง"}\n'
            'กติกาของ example: ใส่เมื่อ verdict เป็น mismatch หรือ unclear เท่านั้น '
            '(ถ้าเป็น match ให้ส่งค่าว่าง) เขียนเป็นภาษาไทยประโยคเดียว ความยาวประมาณ '
            '1-2 บรรทัด ให้ครบว่าไปช่วยสาขาไหน ขนอะไร กี่เที่ยวหรือช่วงเวลาไหน '
            'อิงข้อมูลเที่ยวนี้เท่าที่มี ส่วนที่ไม่รู้ให้ใส่เป็นวงเล็บให้คนขับเติม '
            'เช่น (ระบุชื่อสาขา) อย่าแต่งข้อมูลที่ไม่มีขึ้นมาเอง'
            % json.dumps(facts, ensure_ascii=False, default=str)
        )
        answer = Gemini.extract_json(prompt, max_output_tokens=512)
        if not answer:
            self.write({'help_branch_ai_state': 'error',
                        'help_branch_ai_date': fields.Datetime.now()})
            return False

        verdict = answer.get('verdict')
        state = verdict if verdict in ('match', 'mismatch', 'unclear') else 'unclear'
        body = '<div>%s</div>' % html_escape(str(answer.get('summary') or ''))
        suggest = str(answer.get('suggest') or '').strip()
        if suggest:
            body += '<div class="mt-2"><b>ควรตรวจต่อ</b>: %s</div>' % html_escape(suggest)
        example_html = str(answer.get('example') or '').strip()
        if example_html and verdict != 'match':
            body += ('<div class="mt-2"><b>ตัวอย่างที่เสนอให้คนขับ</b>: %s</div>'
                     % html_escape(example_html))
        message = str(answer.get('summary') or '').strip()
        if suggest:
            message += '\n\nควรระบุเพิ่ม: ' + suggest
        example = str(answer.get('example') or '').strip()
        # ตัวอย่างมีไว้ให้คนขับแก้ตาม ถ้าผ่านแล้วก็ไม่ต้องเสนออะไร
        if state == 'match':
            example = ''
        self.write({
            'help_branch_ai_state': state,
            'help_branch_ai_summary': body,
            'help_branch_ai_message': message,
            'help_branch_ai_example': example,
            'help_branch_ai_date': fields.Datetime.now(),
        })
        if state == 'mismatch':
            _logger.warning('[HelpBranch] %s: AI ว่าหมายเหตุไม่ตรงประเภทงาน',
                            self.name)
        return True

    def action_recheck_help_branch_note(self):
        """ปุ่มให้ฝ่ายตรวจสอบสั่ง AI ตรวจซ้ำ เช่นตอนตั้งค่า AI Key ทีหลัง"""
        for record in self:
            if record.help_branch_note:
                record._run_help_branch_ai()
        return True
