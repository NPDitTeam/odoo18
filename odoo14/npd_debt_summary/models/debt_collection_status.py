# -*- coding: utf-8 -*-
"""กำหนดสถานะติดตามหนี้ (ตั้งค่าเอง สร้างได้หลายสถานะ)

ผู้ใช้ระบุ 28 ส.ค. 2026 (ฝั่ง o14):
  - ตั้งช่วงจำนวนวันค้างชำระไว้ เช่น 1 ถึง 7 วัน แล้วตั้งชื่อสถานะให้ช่วงนั้น
  - สร้างได้หลายสถานะ (หลายช่วงวัน)
  - มีสวิตช์ "เริ่มแสดงที่รายงาน" ค่าเริ่มต้นคือไม่แสดง

o18 เป็นฐานเดียวหลายบริษัท แต่ชุดสถานะที่ใช้จริงบน o14 เหมือนกันทุกบริษัท
จึงเก็บเป็นตารางกลางชุดเดียว (ไม่แยกตามบริษัท) เหมือนเดิม
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class NpdDebtCollectionStatus(models.Model):
    _name = 'npd.debt.collection.status'
    _description = 'กำหนดสถานะติดตามหนี้'
    _order = 'day_from asc, id asc'

    name = fields.Char(string='ชื่อสถานะที่เป็นหนี้', required=True,
                       help='ชื่อที่จะใช้เรียกลูกค้าที่ค้างชำระอยู่ในช่วงวันนี้ เช่น ค้างใหม่ / ติดตามด่วน')
    day_from = fields.Integer(string='วันเริ่มต้น', required=True, default=1,
                              help='จำนวนวันค้างชำระตั้งแต่ (นับรวมวันนี้)')
    day_to = fields.Integer(string='ถึง (วัน)', required=True, default=7,
                            help='จำนวนวันค้างชำระถึง (นับรวมวันนี้)')
    day_range_label = fields.Char(string='ช่วงวัน', compute='_compute_day_range_label')
    show_in_report = fields.Boolean(string='เริ่มแสดงที่รายงาน', default=False,
                                    help='ติ๊กไว้ถ้าต้องการให้สถานะนี้ไปแสดงในรายงาน ค่าเริ่มต้นคือไม่แสดง')
    active = fields.Boolean(string='ใช้งาน', default=True)

    @api.depends('day_from', 'day_to')
    def _compute_day_range_label(self):
        for rec in self:
            rec.day_range_label = '%d - %d วัน' % (rec.day_from, rec.day_to)

    @api.constrains('day_from', 'day_to')
    def _check_day_range(self):
        for rec in self:
            if rec.day_from < 0 or rec.day_to < 0:
                raise ValidationError(_('จำนวนวันต้องไม่ติดลบ (สถานะ "%s")') % rec.name)
            if rec.day_to < rec.day_from:
                raise ValidationError(
                    _('ช่วงวันของสถานะ "%s" ไม่ถูกต้อง วันสิ้นสุด (%d) ต้องไม่น้อยกว่าวันเริ่มต้น (%d)')
                    % (rec.name, rec.day_to, rec.day_from))

    @api.constrains('day_from', 'day_to', 'active')
    def _check_no_overlap(self):
        """ช่วงวันห้ามซ้อนทับกัน ไม่งั้นวันเดียวกันจะตกได้หลายสถานะ"""
        for rec in self:
            if not rec.active:
                continue
            other = self.search([
                ('id', '!=', rec.id),
                ('day_from', '<=', rec.day_to),
                ('day_to', '>=', rec.day_from),
            ], limit=1)
            if other:
                raise ValidationError(
                    _('ช่วงวัน %d - %d ของสถานะ "%s" ซ้อนทับกับสถานะ "%s" (%d - %d วัน)')
                    % (rec.day_from, rec.day_to, rec.name,
                       other.name, other.day_from, other.day_to))

    # o18: name_get ถูกถอดออก ใช้ _compute_display_name แทน
    @api.depends('name', 'day_from', 'day_to')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s (%d - %d วัน)' % (rec.name or '', rec.day_from, rec.day_to)

    # ------------------------------------------------------------------
    # จับจำนวนวันเข้ากับช่วงสถานะ
    # ------------------------------------------------------------------
    def _match_days(self, days):
        """เลือกสถานะที่ตรงกับจำนวนวันค้างชำระ (self = สถานะทั้งหมดที่จะพิจารณา)

        ผู้ใช้ระบุ 28 ส.ค. 2026: ถ้าจำนวนวันเกินช่วงสูงสุดที่ตั้งไว้
        ให้ยึดสถานะของช่วงที่วันมากที่สุดมาแสดงแทน
        (เช่น ตั้งไว้สูงสุด 138-140 วัน ลูกค้าค้าง 200 วัน ก็ยังได้สถานะนั้น)
        น้อยกว่าช่วงแรก (เช่น เพิ่งออกใบแจ้งหนี้วันนี้) จะไม่มีสถานะ
        """
        if not self:
            return self
        for status in self:
            if status.day_from <= days <= status.day_to:
                return status
        latest = max(self, key=lambda s: s.day_to)
        if days > latest.day_to:
            return latest
        return self.browse()


class NpdDebtCollectionStatusMixin(models.AbstractModel):
    """ผสมคอลัมน์ "สถานะติดตามหนี้" ให้บรรทัดหนี้ในแต่ละแท็บของ รวมหนี้ลูกค้า

    นับจากวันที่ออกใบแจ้งหนี้ถึงวันนี้ว่ากี่วัน แล้วเอาไปเทียบกับช่วงวันที่ตั้งไว้
    ในเมนู "กำหนดสถานะติดตามหนี้"

    ค่าเปลี่ยนไปทุกวันตามวันที่ปัจจุบัน จึงคำนวณสด (store=False) ไม่เก็บลงฐานข้อมูล
    แต่ละแท็บใช้ชื่อฟิลด์วันที่ออกใบแจ้งหนี้ไม่เหมือนกัน ให้ระบุผ่าน
    _collection_date_field ในคลาสของแท็บนั้น
    """
    _name = 'npd.debt.collection.status.mixin'
    _description = 'คอลัมน์สถานะติดตามหนี้ (สรุปหนี้)'

    # ชื่อฟิลด์ "วันที่ออกใบแจ้งหนี้" ของแท็บนั้น (แท็บค่าปรับหาย/ชำรุดใช้ rental_start_date)
    _collection_date_field = 'invoice_date'

    collection_status_id = fields.Many2one(
        'npd.debt.collection.status', string='สถานะติดตามหนี้',
        compute='_compute_collection_status')
    collection_status_name = fields.Char(
        string='สถานะติดตามหนี้', compute='_compute_collection_status')
    collection_days = fields.Integer(
        string='จำนวนวันนับจากวันที่ออกใบแจ้งหนี้', compute='_compute_collection_status')

    def _collection_base_date(self):
        """วันที่ที่ใช้ตั้งต้นนับ = วันที่ออกใบแจ้งหนี้ของแท็บนั้น"""
        self.ensure_one()
        return self[self._collection_date_field]

    @api.depends('payment_status')
    def _compute_collection_status(self):
        statuses = self.env['npd.debt.collection.status'].search([])
        today = fields.Date.context_today(self)
        for rec in self:
            base_date = rec._collection_base_date()
            # จ่ายครบแล้วไม่ต้องมีสถานะติดตาม (สถานะมีไว้สำหรับเอกสารที่ยังค้างชำระ)
            if not base_date or rec.payment_status == 'paid':
                rec.collection_days = 0
                rec.collection_status_id = False
                rec.collection_status_name = ''
                continue
            days = (today - base_date).days
            status = statuses._match_days(days)
            rec.collection_days = days
            rec.collection_status_id = status
            rec.collection_status_name = status.name or ''
