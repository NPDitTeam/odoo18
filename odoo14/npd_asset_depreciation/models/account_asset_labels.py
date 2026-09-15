# -*- coding: utf-8 -*-
"""เปลี่ยนชื่อฟิลด์บนหน้าจอสินทรัพย์เป็นภาษาไทย

โมดูลสินทรัพย์ต้นทาง (OCA account_asset_management) ตั้งชื่อฟิลด์ไว้เป็น
ภาษาอังกฤษ ไฟล์นี้เขียนทับเฉพาะ "ชื่อที่แสดง" (string) เท่านั้น
ไม่ได้แตะชนิดฟิลด์ การคำนวณ หรือข้อมูลใด ๆ

ทำที่ระดับฟิลด์ ไม่ใช่ไฟล์แปลภาษา เพื่อให้ชื่อไทยขึ้นเหมือนกันทุกที่
(ฟอร์ม ตาราง ตัวกรอง ตัวช่วยนำเข้า รายงาน) และไม่ต้องพึ่งว่าผู้ใช้
ตั้งภาษาอะไรไว้

ชนิดฟิลด์ต้องตรงกับต้นทาง (OCA 18 เปลี่ยนยอดเงินเป็น Monetary แล้ว)
ฟิลด์ที่ OCA 18 ไม่มี (logo, purchase_paid_value, date_purchase, analytic_tag_ids,
account_analytic_id, company_currency_id) ตัดออก ถ้าประกาศไว้จะกลายเป็นฟิลด์ใหม่ที่พัง
"""
from odoo import fields, models


class AccountAssetThaiLabels(models.Model):
    _inherit = 'account.asset'

    # ---- ข้อมูลหลัก ----
    name = fields.Char(string='ชื่อทรัพย์สิน')
    code = fields.Char(string='อ้างถึง')
    number = fields.Char(string='เลขทะเบียนทรัพย์สิน')
    state = fields.Selection(string='สถานะ')
    profile_id = fields.Many2one(string='หมวดหมู่สินทรัพย์')
    group_ids = fields.Many2many(string='กลุ่มสินทรัพย์')
    partner_id = fields.Many2one(string='พาร์ทเนอร์')
    company_id = fields.Many2one(string='บริษัท')
    note = fields.Text(string='บันทึกย่อ')

    # ---- มูลค่า ----
    purchase_value = fields.Monetary(string='ราคาทรัพย์สิน (ฐานคิดค่าเสื่อม)')
    salvage_value = fields.Monetary(string='มูลค่าซาก')
    depreciation_base = fields.Monetary(string='ฐานคิดค่าเสื่อม')
    value_depreciated = fields.Monetary(string='ค่าเสื่อมสะสม')
    value_residual = fields.Monetary(string='มูลค่าคงเหลือ')

    # ---- วันที่ ----
    date_start = fields.Date(string='วันที่เริ่มใช้สินทรัพย์')
    date_remove = fields.Date(string='วันที่ตัดจำหน่าย')

    # ---- วิธีคิดค่าเสื่อมของระบบเดิม (โมดูลใหม่ไม่ได้ใช้ แต่ยังต้องกรอกให้ผ่าน) ----
    method = fields.Selection(string='วิธีการคำนวณ')
    method_time = fields.Selection(string='วิธีนับเวลา')
    method_number = fields.Integer(string='จำนวนปี')
    method_period = fields.Selection(string='ความถี่การคิดค่าเสื่อม')
    method_end = fields.Date(string='วันที่สิ้นสุด')
    method_progress_factor = fields.Float(string='ตัวคูณแบบยอดลดลง')
    days_calc = fields.Boolean(string='คิดตามจำนวนวัน')
    use_leap_years = fields.Boolean(string='นับปีอธิกสุรทิน')
    prorata = fields.Boolean(string='เฉลี่ยตามช่วงเวลา')
    depreciation_line_ids = fields.One2many(string='ตารางค่าเสื่อม (ระบบเดิม)')

    # ---- บัญชี ----
    account_move_line_ids = fields.One2many(string='รายการสมุดรายวัน')
    move_line_check = fields.Boolean(string='มีรายการบัญชีแล้ว')

    # ---- ทะเบียนทรัพย์สิน (มาจากโมดูล pfb_std_asset_free_field) ----
    # ช่องพวกนี้ไม่เกี่ยวกับการคำนวณค่าเสื่อม ใช้ตอนตรวจนับทรัพย์สินว่า
    # ของอยู่กับใคร อยู่ที่ไหน สภาพเป็นอย่างไร
    std_barcode = fields.Char(string='เลขทะเบียนทรัพย์สิน (เดิม)')
    std_condition_type_id = fields.Many2one(string='สภาพทรัพย์สิน')
    std_condition_remark = fields.Text(string='หมายเหตุสภาพ')
    std_employee_id = fields.Many2one(string='ผู้ถือครอง')
    std_location_id = fields.Many2one(string='สถานที่เก็บ')
    std_invoice = fields.Char(string='เลขที่ใบแจ้งหนี้')
    std_asset_purchase_id = fields.Many2one(string='เลขที่ใบสั่งซื้อ')
    std_purchase_price = fields.Float(string='ราคาซื้อ')
    std_purchase_date = fields.Date(string='วันที่ซื้อ (ทะเบียน)')
    std_model = fields.Char(string='รุ่น')
    std_serial_no = fields.Char(string='หมายเลขเครื่อง')
    std_no_compute_asset = fields.Boolean(string='ไม่คิดค่าเสื่อม (ระบบเดิม)')
    sh_qr_code_img = fields.Binary(string='รูป QR Code')


class AccountConditionTypeThaiLabels(models.Model):
    _inherit = 'account.condition.type'

    name = fields.Char(string='ชื่อสภาพทรัพย์สิน')


class AccountAssetProfileThaiLabels(models.Model):
    _inherit = 'account.asset.profile'

    name = fields.Char(string='ชื่อหมวดหมู่สินทรัพย์')
    journal_id = fields.Many2one(
        string='สมุดรายวัน',
        help='สมุดที่รายการค่าเสื่อมรายเดือนไปลง '
             'ไม่เกี่ยวกับการสร้างสินทรัพย์อัตโนมัติ')
    account_asset_id = fields.Many2one(
        string='บัญชีสินทรัพย์',
        help='ตัวสั่งสร้างสินทรัพย์อัตโนมัติ — เมื่อลงใบแจ้งหนี้เข้าบัญชีนี้แล้วกดลงบันทึก '
             'ระบบจะสร้างสินทรัพย์ให้เองโดยใช้หมวดนี้ '
             '(ป้ายกำกับของบรรทัดในใบแจ้งหนี้จะกลายเป็นชื่อสินทรัพย์ ถ้าเว้นว่างจะลงบันทึกไม่ผ่าน)')
    account_depreciation_id = fields.Many2one(
        string='บัญชีค่าเสื่อมราคาสะสม',
        help='ขาเครดิต ตอนลงบัญชีค่าเสื่อมรายเดือน')
    account_expense_depreciation_id = fields.Many2one(
        string='บัญชีค่าใช้จ่ายค่าเสื่อมราคา',
        help='ขาเดบิต ตอนลงบัญชีค่าเสื่อมรายเดือน')
    method = fields.Selection(string='วิธีการคำนวณ')
    method_time = fields.Selection(string='วิธีนับเวลา')
    method_number = fields.Integer(string='จำนวนปี')
    method_period = fields.Selection(string='ความถี่การคิดค่าเสื่อม')
    days_calc = fields.Boolean(string='คิดตามจำนวนวัน')
    use_leap_years = fields.Boolean(string='นับปีอธิกสุรทิน')
    prorata = fields.Boolean(string='เฉลี่ยตามช่วงเวลา')
