# -*- coding: utf-8 -*-
"""ล็อกค่าเที่ยว / ค่าเบี้ยเลี้ยง ให้ดึงจากคำสั่งขนส่งอย่างเดียว

ปัญหาเดิม (ผู้ใช้ระบุ 16 ก.ย. 2569): สองฟิลด์นี้เป็นตัวเลขกรอกมือได้ ค่าจะถูกเติมจาก
คำสั่งขนส่งผ่าน onchange เท่านั้น ซึ่งทำงานเฉพาะตอนกรอกในฟอร์ม พอเขียนผ่าน API
หรือแก้มือทีหลังก็เปลี่ยนได้เลย (มี endpoint /api/v1/vehicle_booking/update_expenses
ที่เป็น public เขียนค่าเที่ยวได้ตรง ๆ ด้วย) จึงเป็นช่องให้แก้ยอดเอง

วิธีล็อก: ไม่ว่าจะเขียนมาจากทางไหน ระบบจะบังคับให้เท่ากับค่าของคำสั่งขนส่งเสมอ
    create() / write()  -> เขียนทับค่าที่ส่งเข้ามาด้วยค่าจากคำสั่งขนส่ง
    ฟอร์ม              -> ทำเป็น readonly (ดู views/booking_pay_lock_views.xml)
    คำสั่งขนส่งเปลี่ยน  -> ใบจองที่ยังไม่ปิดงานอัพเดทตาม (ใบที่ปิดแล้วไม่แตะ เพราะ payroll ใช้ยอดนั้นแล้ว)

ถ้ามีเคสจำเป็นต้องแก้จริง ๆ ให้ใส่ผู้ใช้เข้ากลุ่ม "แก้ค่าเที่ยว/เบี้ยเลี้ยงเองได้ (ยกเว้น)"
ระบบจะยอมให้แก้ แต่บันทึกไว้ใน chatter ว่าใครแก้จากเท่าไรเป็นเท่าไร
"""
import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools.misc import html_escape

_logger = logging.getLogger(__name__)

PAY_FIELDS = ('travel_expenses', 'daily_allowance')
OVERRIDE_GROUP = 'npd_transport_fraud_check.group_transport_pay_override'
# context นี้ใช้ตอนที่ระบบเป็นคนเขียนเอง (เช่นซิงก์จากคำสั่งขนส่ง) จะได้ไม่วนซ้ำ
SKIP_CONTEXT = 'npd_pay_lock_skip'


def _fmt(value):
    return '{:,.2f}'.format(value or 0.0)


class VehicleBookingPayLock(models.Model):
    _inherit = 'vehicle.booking'

    def _pay_from_order(self, order):
        """ยอดที่ควรเป็นตามคำสั่งขนส่ง"""
        if not order:
            return {}
        return {
            'travel_expenses': order.trip_allowance or 0.0,
            'daily_allowance': order.daily_allowance or 0.0,
        }

    def _pay_lock_enabled(self):
        """ล็อกอยู่ไหม — ไม่ล็อกเมื่อระบบเขียนเอง (context) หรือผู้ใช้อยู่กลุ่มยกเว้น"""
        if self.env.context.get(SKIP_CONTEXT):
            return False
        return not self.env.user.has_group(OVERRIDE_GROUP)

    @api.model_create_multi
    def create(self, vals_list):
        if self._pay_lock_enabled():
            Order = self.env['transport.order'].sudo()
            for vals in vals_list:
                order = Order.browse(vals.get('transport_order_id')) if vals.get('transport_order_id') else None
                expected = self._pay_from_order(order) if order and order.exists() else {}
                for field in PAY_FIELDS:
                    if not expected:
                        continue
                    sent = vals.get(field)
                    if sent is not None and abs((sent or 0.0) - expected[field]) >= 0.01:
                        _logger.info('ล็อกค่าจ้างเที่ยว: สร้างใบจองด้วย %s=%s แต่คำสั่งขนส่งกำหนด %s',
                                     field, sent, expected[field])
                    vals[field] = expected[field]
        return super().create(vals_list)

    def write(self, vals):
        touched = [field for field in PAY_FIELDS if field in vals]
        if not touched:
            return super().write(vals)

        if not self._pay_lock_enabled():
            # กลุ่มยกเว้น (หรือระบบเขียนเอง): ให้แก้ได้ แต่ต้องมีร่องรอยในแชท
            if not self.env.context.get(SKIP_CONTEXT):
                for booking in self:
                    before = {field: booking[field] for field in touched}
                    after = {field: vals[field] for field in touched}
                    if any(abs((before[f] or 0.0) - (after[f] or 0.0)) >= 0.01 for f in touched):
                        booking._log_pay_override(before, after)
            return super().write(vals)

        # ล็อกอยู่: ตัดสองฟิลด์นี้ออกจากคำสั่งเขียน แล้วบังคับให้เท่ากับคำสั่งขนส่งของแต่ละใบ
        attempted = {field: vals.pop(field) for field in touched}
        result = super().write(vals) if vals else True
        for booking in self:
            expected = booking._pay_from_order(booking.transport_order_id)
            if not expected:
                continue
            fix = {field: expected[field] for field in touched
                   if abs((booking[field] or 0.0) - expected[field]) >= 0.01}
            if fix:
                super(VehicleBookingPayLock,
                      booking.with_context(**{SKIP_CONTEXT: True})).write(fix)
            off_spec = {field: attempted[field] for field in touched
                        if abs((attempted[field] or 0.0) - expected[field]) >= 0.01}
            if off_spec:
                booking._log_pay_lock(off_spec, {field: expected[field] for field in off_spec})
        return result

    def _log_pay_lock(self, sent, expected):
        """บอกในแชทของใบจองว่ามีคนพยายามแก้ยอด แล้วระบบดึงกลับ"""
        self.ensure_one()
        labels = {'travel_expenses': 'ค่าเที่ยว', 'daily_allowance': 'ค่าเบี้ยเลี้ยง'}
        rows = ''.join(
            '<li>%s: พยายามตั้งเป็น <b>%s</b> ระบบใช้ค่าจากคำสั่งขนส่ง <b>%s</b></li>'
            % (labels.get(field, field), _fmt(sent.get(field)), _fmt(value))
            for field, value in expected.items())
        body = ('<p>🔒 <b>ค่าเที่ยว/ค่าเบี้ยเลี้ยงถูกล็อกไว้</b> '
                'ให้ใช้ค่าจากคำสั่งขนส่ง %s เท่านั้น</p><ul>%s</ul>'
                % (html_escape(self.transport_order_id.name or '-'), rows))
        try:
            # Odoo 18 escape body ที่เป็น str ทั้งก้อน ค่าที่ประกอบมาผ่าน html_escape แล้ว จึงห่อ Markup ได้
            self.sudo().message_post(body=Markup(body), message_type='comment', subtype_xmlid='mail.mt_note')
        except Exception:  # noqa: BLE001 - แจ้งเตือนต้องไม่ทำให้การบันทึกล้ม
            _logger.exception('ล็อกค่าจ้างเที่ยว: บันทึกข้อความในใบจอง %s ไม่สำเร็จ', self.id)

    def _log_pay_override(self, before, after):
        self.ensure_one()
        labels = {'travel_expenses': 'ค่าเที่ยว', 'daily_allowance': 'ค่าเบี้ยเลี้ยง'}
        rows = ''.join('<li>%s: %s → <b>%s</b></li>' % (labels.get(field, field),
                                                        _fmt(before.get(field)), _fmt(value))
                       for field, value in after.items())
        body = ('<p>⚠️ <b>แก้ยอดโดยผู้มีสิทธิ์ยกเว้น</b> (%s)</p><ul>%s</ul>'
                % (html_escape(self.env.user.name or ''), rows))
        try:
            # Odoo 18 escape body ที่เป็น str ทั้งก้อน ค่าที่ประกอบมาผ่าน html_escape แล้ว จึงห่อ Markup ได้
            self.sudo().message_post(body=Markup(body), message_type='comment', subtype_xmlid='mail.mt_note')
        except Exception:  # noqa: BLE001
            _logger.exception('ล็อกค่าจ้างเที่ยว: บันทึกข้อความในใบจอง %s ไม่สำเร็จ', self.id)

    def action_resync_pay_from_order(self):
        """ปุ่ม: ดึงค่าเที่ยว/เบี้ยเลี้ยงจากคำสั่งขนส่งใหม่"""
        updated = self.browse()
        for booking in self:
            expected = booking._pay_from_order(booking.transport_order_id)
            if not expected:
                continue
            if any(abs((booking[field] or 0.0) - value) >= 0.01 for field, value in expected.items()):
                super(VehicleBookingPayLock, booking.with_context(**{SKIP_CONTEXT: True})).write(expected)
                updated |= booking
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ดึงยอดจากคำสั่งขนส่งแล้ว'),
                'message': _('อัพเดท %s ใบ') % len(updated),
                'type': 'success',
                'sticky': False,
            },
        }


class TransportOrderPaySync(models.Model):
    _inherit = 'transport.order'

    def write(self, vals):
        """คำสั่งขนส่งเปลี่ยนยอด -> ใบจองที่ยังไม่ปิดงานต้องตามให้ตรง

        ใบที่ปิดงานแล้วไม่แตะ เพราะเงินเดือนคิดจากยอดนั้นไปแล้ว
        (ถ้าต้องแก้จริง ให้คนมีสิทธิ์กดปุ่มดึงยอดใหม่เอง)
        """
        result = super().write(vals)
        if not any(field in vals for field in ('trip_allowance', 'daily_allowance')):
            return result
        bookings = self.env['vehicle.booking'].sudo().search([
            ('transport_order_id', 'in', self.ids),
            ('state', 'not in', ('done', 'cancelled')),
        ])
        for booking in bookings:
            expected = booking._pay_from_order(booking.transport_order_id)
            if expected and any(abs((booking[field] or 0.0) - value) >= 0.01
                                for field, value in expected.items()):
                booking.with_context(**{SKIP_CONTEXT: True}).write(expected)
                _logger.info('ล็อกค่าจ้างเที่ยว: อัพเดทใบจอง %s ตามคำสั่งขนส่ง %s',
                             booking.name, booking.transport_order_id.name)
        return result
