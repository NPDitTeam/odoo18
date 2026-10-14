# -*- coding: utf-8 -*-
from odoo import api, fields, models

WHT_RATE_SELECTION = [
    ('0', 'ไม่หัก'),
    ('1', '1%'),
    ('2', '2%'),
    ('3', '3%'),
    ('5', '5%'),
]


class WhtCategory(models.Model):
    """หมวดหมู่ภาษีหัก ณ ที่จ่าย — กำหนดอัตราตามประเภทค่าใช้จ่าย เช่น ค่าบริการ 3%, ค่าเช่า 5%"""
    _name = 'wht.category'
    _description = 'Withholding Tax Category'
    _order = 'sequence, name'

    name = fields.Char(string='ชื่อหมวดหมู่', required=True,
                       help='ชื่อหมวดหมู่ เช่น ค่าบริการทั่วไป, ค่าเช่า, ค่าขนส่ง')
    code = fields.Char(string='รหัส')
    sequence = fields.Integer(default=10)
    wht_rate = fields.Selection(WHT_RATE_SELECTION, string='อัตรา WHT', required=True, default='0')
    wht_rate_float = fields.Float(string='อัตรา WHT (%)', compute='_compute_wht_rate_float', store=True)
    wt_cert_income_type = fields.Selection([
        ('1', '1. เงินเดือน ค่าจ้าง ฯลฯ 40(1)'),
        ('2', '2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)'),
        ('3', '3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)'),
        ('5', '5. ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 3 เตรส'),
        ('6', '6. อื่นๆ (ระบุ)'),
    ], string='ประเภทเงินได้', required=True, default='6', help='ประเภทเงินได้ตามแบบ ภ.ง.ด.')
    income_description = fields.Char(string='รายละเอียดเงินได้',
                                     help='รายละเอียดเพิ่มเติม เช่น ค่าบริการ, ค่าเช่า, ค่าขนส่ง')
    note = fields.Text(string='หมายเหตุ')
    active = fields.Boolean(default=True)

    @api.depends('wht_rate')
    def _compute_wht_rate_float(self):
        for rec in self:
            rec.wht_rate_float = float(rec.wht_rate or 0)

    @api.depends('name', 'wht_rate')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s (%s%%)' % (rec.name or '', rec.wht_rate or '0')
