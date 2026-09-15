# -*- coding: utf-8 -*-
u"""ผลตรวจสอบราย "สลิป" ของใบรับชำระ

ลูกค้ามักโอนไม่ครบในครั้งเดียว พนักงานจึงแนบสลิปหลายไฟล์ในใบรับชำระใบเดียว
(เช่น โอน 6,920.00 วันหนึ่ง แล้วโอนอีก 0.50 อีกวัน รวมเป็น 6,920.50)

โมเดลนี้เก็บผลตรวจของแต่ละไฟล์แยกกัน — AI อ่านทีละไฟล์ และจับคู่กับรายการ
เดินบัญชีทีละรายการ ใบรับชำระจะขึ้น "โอนสำเร็จ" ก็ต่อเมื่อ **ทุกสลิป** จับคู่ได้
"""
from odoo import models, fields


class ScbPaymentSlip(models.Model):
    _name = 'npd.scb.payment.slip'
    _description = u'ผลตรวจสอบสลิปโอนเงิน (รายไฟล์)'
    _order = 'slip_date, id'
    _rec_name = 'attachment_name'

    payment_id = fields.Many2one(
        'account.payment', string=u'ใบรับชำระ', required=True,
        ondelete='cascade', index=True)
    attachment_id = fields.Many2one(
        'ir.attachment', string=u'ไฟล์แนบ', required=True, ondelete='cascade')
    attachment_name = fields.Char(
        string=u'ชื่อไฟล์', related='attachment_id.name', store=True, readonly=True)

    # ---- ค่าที่ AI อ่านได้จากสลิปใบนี้ ----
    slip_date = fields.Date(string=u'วันที่จากสลิป', readonly=True)
    slip_time = fields.Char(
        string=u'เวลาจากสลิป', readonly=True,
        help=u'ใช้เทียบกับเวลาที่ธนาคารบันทึก — ช่วยยืนยันกรณีที่ชื่อผู้โอน '
             u'ถอดเป็นภาษาอังกฤษแบบไม่เป็นมาตรฐานจนเทียบไม่ได้')
    slip_amount = fields.Float(string=u'จำนวนเงิน', digits=(16, 2), readonly=True)
    slip_sender = fields.Char(string=u'ชื่อผู้โอน', readonly=True)
    slip_sender_acc = fields.Char(string=u'บัญชีผู้โอน', readonly=True)
    slip_ref = fields.Char(string=u'เลขอ้างอิง', readonly=True)
    raw = fields.Text(string=u'ข้อมูลดิบจาก AI', readonly=True)

    # ---- ผลการจับคู่ ----
    state = fields.Selection([
        ('to_check', u'รอตรวจสอบ'),
        ('unreadable', u'อ่านสลิปไม่ได้'),
        ('waiting', u'รอข้อมูลจากธนาคาร'),
        ('matched', u'จับคู่ได้'),
        ('not_found', u'ไม่พบรายการ'),
        # สลิปใบเดียวกันถูกแนบซ้ำ (ถ่ายสองรอบ / ส่งมาทั้งจากไลน์และอีเมล)
        ('duplicate', u'สลิปซ้ำ'),
        # ไฟล์ที่พนักงานแนบปนมา แต่ไม่ใช่หลักฐานการโอน (50 ทวิ / ใบกำกับภาษี ฯลฯ)
        ('not_slip', u'ไม่ใช่สลิปการโอน'),
        ('skipped', u'ไม่ต้องตรวจ'),
    ], string=u'ผล', default='to_check', readonly=True, index=True)
    # รายละเอียดบอกเกณฑ์การตรวจทั้งหมด (เทียบอะไร ได้คะแนนเท่าไร)
    # จำกัดให้เฉพาะผู้จัดการบัญชี กันพนักงานรู้ว่าต้องทำสลิปอย่างไรให้ผ่าน
    reason = fields.Text(string=u'รายละเอียด (ภายใน)', readonly=True,
                         groups="account.group_account_manager")
    statement_id = fields.Many2one(
        'npd.scb.bank.statement', string=u'รายการเดินบัญชีที่ตรงกัน',
        readonly=True, ondelete='set null', index=True)
    statement_amount = fields.Monetary(
        string=u'เงินเข้าจริง', related='statement_id.deposit',
        readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', related='payment_id.currency_id', readonly=True)
