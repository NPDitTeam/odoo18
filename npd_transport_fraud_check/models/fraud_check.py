# -*- coding: utf-8 -*-
"""ผลการตรวจทุจริตของเที่ยวจัดส่ง 1 เที่ยว (1 booking = 1 แถว)

เก็บทั้งค่าที่ใช้ตรวจ (สแนปช็อตตอนปิดงาน) ผลของกฎแต่ละข้อ และคำอธิบายจาก AI
ไม่แก้ไขข้อมูลการจองใด ๆ — เป็นบันทึกสำหรับให้คนไปตรวจต่อเท่านั้น
"""
from odoo import _, api, fields, models

RISK_LEVELS = [
    ('ok', 'ปกติ'),
    ('watch', 'ควรดู'),
    ('high', 'น่าสงสัยมาก'),
]

REVIEW_STATES = [
    ('new', 'ยังไม่ตรวจ'),
    ('checking', 'กำลังตรวจ'),
    ('ok', 'ตรวจแล้ว ไม่มีปัญหา'),
    ('issue', 'ตรวจแล้ว มีปัญหาจริง'),
]

AI_STATES = [
    ('skipped', 'ไม่ต้องใช้ AI'),
    ('pending', 'รอ AI วิเคราะห์'),
    ('done', 'AI วิเคราะห์แล้ว'),
    ('error', 'AI วิเคราะห์ไม่สำเร็จ'),
]


class NpdTransportFraudCheck(models.Model):
    _name = 'npd.transport.fraud.check'
    _description = 'ผลตรวจทุจริตการจัดส่ง'
    _order = 'risk_score desc, delivery_date desc, id desc'
    _rec_name = 'booking_name'

    booking_id = fields.Many2one('vehicle.booking', string='เที่ยวจัดส่ง',
                                 required=True, ondelete='cascade', index=True)
    booking_name = fields.Char(string='เลขที่การจอง', index=True)
    transport_order_id = fields.Many2one('transport.order', string='คำสั่งขนส่ง')
    order_name = fields.Char(string='เลขที่เอกสารขนส่ง')

    branch_id = fields.Many2one('res.branch', string='สาขา', index=True)
    driver_id = fields.Many2one('vehicle.driver', string='คนขับ', index=True)
    driver_name = fields.Char(string='ชื่อคนขับ')
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ')
    partner_id = fields.Many2one('res.partner', string='ลูกค้า')

    delivery_date = fields.Date(string='วันที่จัดส่ง', index=True)
    done_datetime = fields.Datetime(string='เวลาที่ปิดงาน')
    delivery_type = fields.Char(string='ประเภทการจัดส่ง',
                                help='ค่าที่ตั้งไว้ฝั่ง Odoo 14 เช่น customer = ลูกค้าให้ไปส่ง, branch = ส่งของสาขา')
    delivery_source = fields.Char(string='แหล่งที่มา', help='app = ปิดงานจากแอปคนขับ, odoo = ปิดจากหน้าจอ')
    done_method = fields.Selection([
        ('app', 'ปิดงานผ่านแอป'),
        ('manual', 'ปิดงานเองในระบบ'),
    ], string='วิธีปิดงาน')
    no_app_done_reason = fields.Text(string='เหตุผลที่ไม่ได้ปิดผ่านแอป')

    # เวลาจริงของงาน (แอปคนขับบันทึกให้ถ้าปิดงานผ่านแอป)
    pickup_datetime = fields.Datetime(string='เวลารับงาน/ออกเดินทาง')
    delivered_datetime = fields.Datetime(string='เวลาส่งถึง')
    app_delivery_timestamp = fields.Datetime(string='เวลาส่งจากแอป (GPS)')
    duration_hours = fields.Float(string='ใช้เวลา (ชม.)', digits=(10, 2))
    booking_create_date = fields.Datetime(string='เวลาที่สร้างใบจอง')
    days_booking_to_delivery = fields.Integer(string='ห่างจากวันจองถึงวันส่ง (วัน)')

    distance_km = fields.Float(string='ระยะทาง (กม.)')
    travel_expenses = fields.Float(string='ค่าเที่ยว')
    daily_allowance = fields.Float(string='ค่าเบี้ยเลี้ยง')
    shipping_cost = fields.Float(string='ค่าขนส่งที่เก็บลูกค้า')
    order_trip_allowance = fields.Float(string='ค่าเที่ยวตาม Odoo 14')
    order_daily_allowance = fields.Float(string='เบี้ยเลี้ยงตาม Odoo 14')
    shipping_cost_system = fields.Float(string='ค่าขนส่งที่ระบบคิด')
    shipping_diff = fields.Float(string='ส่วนต่างค่าขนส่ง', help='เก็บจริง - ที่ระบบคิด (ติดลบ = ลดให้ลูกค้า)')
    free_shipping = fields.Boolean(string='ตั้งไม่คิดค่าขนส่ง')

    # สถิติย้อนหลังของคนขับ/สาขา ณ เวลาที่ตรวจ (เก็บไว้ให้ดูย้อนหลังได้ว่าตอนนั้นเทียบกับอะไร)
    driver_trip_count = fields.Integer(string='เที่ยวของคนขับ (120 วัน)')
    driver_customer_share = fields.Float(string='สัดส่วน "ลูกค้าให้ไปส่ง" ของคนขับ (%)', digits=(5, 1))
    branch_customer_share = fields.Float(string='สัดส่วนของทั้งสาขา (%)', digits=(5, 1))
    driver_prior_flag_count = fields.Integer(string='ใบที่เคยเข้าข่ายของคนขับ')
    driver_confirmed_issue_count = fields.Integer(string='ใบที่ตรวจแล้วพบปัญหาจริงของคนขับ')

    risk_score = fields.Integer(string='คะแนนความเสี่ยง', index=True)
    risk_level = fields.Selection(RISK_LEVELS, string='ระดับความเสี่ยง', index=True, default='ok')
    flag_ids = fields.One2many('npd.transport.fraud.flag', 'check_id', string='ข้อสังเกต')
    flag_count = fields.Integer(string='จำนวนข้อสังเกต', compute='_compute_flag_count', store=True)
    headline = fields.Char(string='สรุปสั้น ๆ',
                           help='อ่านบรรทัดเดียวให้รู้ว่าเที่ยวนี้ผิดปกติตรงไหน')
    summary = fields.Text(string='สรุปข้อสังเกต (จากกฎ)')

    ai_state = fields.Selection(AI_STATES, string='สถานะ AI', default='skipped', index=True)
    ai_summary = fields.Html(string='ผลวิเคราะห์ของ AI', sanitize=False)
    ai_severity = fields.Selection(RISK_LEVELS, string='ระดับที่ AI ให้')
    ai_date = fields.Datetime(string='เวลาที่ AI วิเคราะห์')

    review_state = fields.Selection(REVIEW_STATES, string='สถานะการตรวจ', default='new', index=True)
    review_user_id = fields.Many2one('res.users', string='ผู้ตรวจ')
    review_date = fields.Datetime(string='วันที่ตรวจ')
    review_note = fields.Text(string='บันทึกการตรวจ')

    analyzed_date = fields.Datetime(string='เวลาที่ตรวจด้วยกฎ', default=fields.Datetime.now)
    company_id = fields.Many2one('res.company', string='บริษัท', default=lambda self: self.env.company)

    _sql_constraints = [
        ('booking_uniq', 'unique(booking_id)', 'เที่ยวจัดส่งนี้มีผลตรวจอยู่แล้ว'),
    ]

    @api.depends('flag_ids')
    def _compute_flag_count(self):
        for rec in self:
            rec.flag_count = len(rec.flag_ids)

    def action_open_booking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('เที่ยวจัดส่ง'),
            'res_model': 'vehicle.booking',
            'res_id': self.booking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_mark_checking(self):
        return self._set_review('checking')

    def action_mark_ok(self):
        return self._set_review('ok')

    def action_mark_issue(self):
        return self._set_review('issue')

    def _set_review(self, state):
        self.write({
            'review_state': state,
            'review_user_id': self.env.user.id,
            'review_date': fields.Datetime.now(),
        })
        return True

    def action_ai_analyze(self):
        """ปุ่ม "ให้ AI วิเคราะห์ใบนี้" (ปกติ cron ทำให้อยู่แล้ว)"""
        self.env['npd.transport.fraud.analyzer']._ai_explain(self)
        return True

    @api.model
    def action_backfill_button(self):
        """ปุ่มบนหัวรายการ: ตรวจย้อนหลังตั้งแต่เดือน 6

        ต้องอยู่บนโมเดลนี้ เพราะปุ่มบนหัว list เรียกเมธอดของโมเดลที่แสดงอยู่
        ตัวทำงานจริงอยู่ที่ npd.transport.fraud.analyzer
        """
        return self.env['npd.transport.fraud.analyzer'].action_backfill_button()


class NpdTransportFraudFlag(models.Model):
    _name = 'npd.transport.fraud.flag'
    _description = 'ข้อสังเกตจากการตรวจทุจริตการจัดส่ง'
    _order = 'severity desc, id'

    check_id = fields.Many2one('npd.transport.fraud.check', string='ผลตรวจ',
                               required=True, ondelete='cascade', index=True)
    code = fields.Char(string='รหัสกฎ', required=True, index=True)
    name = fields.Char(string='ข้อสังเกต', required=True)
    severity = fields.Selection([
        ('low', 'ต่ำ'),
        ('medium', 'กลาง'),
        ('high', 'สูง'),
    ], string='ความรุนแรง', default='medium', index=True)
    score = fields.Integer(string='คะแนน')
    detail = fields.Text(string='รายละเอียด')
    # เก็บค่าที่เทียบไว้ด้วย เผื่อย้อนดูว่าเกณฑ์ตอนนั้นเป็นเท่าไร
    value = fields.Float(string='ค่าที่พบ')
    baseline = fields.Float(string='ค่าที่ควรเป็น/ค่าเฉลี่ยกลุ่ม')
