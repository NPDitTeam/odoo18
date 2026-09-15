# -*- coding: utf-8 -*-
u"""หัวข้อที่ 4 : แก้ไขสถานะการเช่า (ถอยสถานะใบกำกับการเช่า)

แก้ฟิลด์ sale.order.rental_status ซึ่งเป็น computed + store และหน้าจอตั้ง
readonly ไว้ (โมดูล pfb_npd_add_date_quatation_order)

กติกาที่ตกลงไว้
    ห้ามแก้   ถ้ามีเอกสาร "คืนเงินประกันค่าเช่า" (account.voucher ชนิด purchase
              เลขขึ้นต้น CP-) ที่อ้างถึงใบสั่งขายนี้ และสถานะเป็น posted แล้ว
    สถานะใหม่ คำนวณจาก "วันที่สิ้นสุดการเช่า" เทียบกับวันนี้
              วันนี้ > วันสิ้นสุด  -> เกินกำหนด (overdue)
              วันนี้ <= วันสิ้นสุด -> ครบกำหนด (due_date)
"""
import logging

from markupsafe import Markup

import odoo
from odoo import SUPERUSER_ID, api, fields, models
from odoo.tools.misc import html_escape

_logger = logging.getLogger(__name__)

# ป้ายสถานะการเช่า (ยึดตามที่โมดูลเดิมประกาศไว้)
RENTAL_STATUS_LABELS = {
    'due_date': u'ครบกำหนด',
    'nearly_due': u'ใกล้ครบกำหนด',
    'overdue': u'เกินกำหนด',
    'in_rent': u'อยู่ระหว่างการเช่า',
    'ready': u'ทำราคา',
    'done': u'ปิดบิล',
}


class NpdAiItRentalFix(models.AbstractModel):
    _name = 'npd.ai.it.rental.fix'
    _description = u'ตัวช่วย AI-IT : แก้ไขสถานะการเช่า'

    # ------------------------------------------------------------------
    # หาเอกสาร
    # ------------------------------------------------------------------
    @api.model
    def find_order(self, text):
        """คืน (order, error_message) — รับเลขที่ใบสั่งขาย หรือ URL ของหน้านั้น"""
        name = (text or '').strip()
        if not name:
            return None, None

        Order = self.env['sale.order'].sudo()
        order = Order.search([('name', '=', name)], limit=1)
        if not order:
            order_id, model_in_url = self.env['npd.ai.it.invoice.fix'].parse_move_reference(text)
            if order_id and (not model_in_url or model_in_url == 'sale.order'):
                candidate = Order.browse(order_id)
                if candidate.exists():
                    order = candidate
        if not order:
            return None, (u'ไม่พบใบสั่งขายเลขที่ "%s" ในระบบ<br/>'
                          u'กรุณาพิมพ์เลขที่ใบสั่งขาย เช่น SO-25100600028' % html_escape(name))

        if 'rental_status' not in order._fields:
            return None, (u'ระบบนี้ยังไม่มีฟิลด์ "สถานะการเช่า" กรุณาแจ้งฝ่าย IT')

        return order, None

    # ------------------------------------------------------------------
    # ด่าน: คืนเงินประกันแล้วห้ามแก้
    # ------------------------------------------------------------------
    @api.model
    def deposit_vouchers(self, order):
        u"""เอกสาร "คืนเงินประกันค่าเช่า" ที่ลงบันทึกแล้วของใบสั่งขายนี้"""
        if 'account.voucher' not in self.env:
            return self.env['sale.order'].browse()  # ไม่มีโมดูลนี้ = ไม่มีด่าน
        return self.env['account.voucher'].sudo().search([
            ('reference', '=', order.name),
            ('voucher_type', '=', 'purchase'),
            ('state', '=', 'posted'),
        ])

    @api.model
    def deposit_block_reason(self, order):
        u"""คืนข้อความห้ามแก้ ถ้าคืนเงินประกันไปแล้ว — คืน None เมื่อแก้ได้"""
        vouchers = self.deposit_vouchers(order)
        if not vouchers:
            return None
        numbers = ', '.join(v.number or str(v.id) for v in vouchers)
        return (u'ใบสั่งขาย <b>%s</b> มีเอกสารคืนเงินประกันค่าเช่าที่ลงบันทึกแล้ว '
                u'(<b>%s</b>) จึงถอยสถานะการเช่าไม่ได้<br/>'
                u'ถ้าจำเป็นต้องแก้จริง ๆ กรุณาติดต่อฝ่ายบัญชี/การเงิน'
                % (order.name, numbers))

    # ------------------------------------------------------------------
    # ด่าน: ถอยได้เฉพาะใบที่ปิดบิลแล้ว
    # ------------------------------------------------------------------
    @api.model
    def status_block_reason(self, order):
        u"""เมนูนี้มีไว้ "ถอย" สถานะ จึงต้องเริ่มจากใบที่ปิดบิลแล้วเท่านั้น

        ใบที่ยังไม่ปิดบิลถือว่ายังอยู่ในกระบวนการปกติ ระบบคำนวณสถานะให้เองอยู่แล้ว
        ไม่ควรมาแทรกด้วยมือ  คืน None เมื่อแก้ได้
        """
        if order.rental_status == 'done':
            return None
        return (u'สถานะการเช่าปัจจุบันของ <b>%s</b> คือ <b>"%s"</b><br/>'
                u'เมนูนี้ถอยสถานะได้เฉพาะใบที่ <b>"ปิดบิล"</b> แล้วเท่านั้น'
                % (order.name, self.label(order.rental_status)))

    # ------------------------------------------------------------------
    # สถานะใหม่ตามวันที่สิ้นสุดการเช่า
    # ------------------------------------------------------------------
    @api.model
    def target_status(self, order):
        u"""คืน (สถานะใหม่, วันสิ้นสุดการเช่า, error_message)"""
        end_date = order.end_rent_date if 'end_rent_date' in order._fields else False
        if not end_date:
            return None, None, (u'ใบสั่งขาย <b>%s</b> ไม่มี "วันที่สิ้นสุดการเช่า" '
                                u'จึงคำนวณสถานะให้ไม่ได้' % order.name)
        today = fields.Date.context_today(self)
        status = 'overdue' if today > end_date else 'due_date'
        return status, end_date, None

    @api.model
    def label(self, status):
        return RENTAL_STATUS_LABELS.get(status, status or u'—')

    # ------------------------------------------------------------------
    # ลงมือแก้
    # ------------------------------------------------------------------
    @api.model
    def apply_status_isolated(self, order_id, new_status, note=u'', actor_name=None):
        u"""แก้ในทรานแซกชันแยก (เหตุผลเดียวกับหัวข้ออื่น — ดู ai_it_invoice_fix)"""
        self.env['sale.order'].flush_model()

        registry = odoo.registry(self.env.cr.dbname)
        with registry.cursor() as new_cr:
            new_env = api.Environment(new_cr, SUPERUSER_ID, dict(self.env.context))
            order = new_env['sale.order'].browse(order_id)
            if not order.exists():
                raise ValueError(u'ไม่พบใบสั่งขาย id=%s' % order_id)
            result = new_env['npd.ai.it.rental.fix'].apply_status(
                order, new_status, note=note, actor_name=actor_name)

        self.env['sale.order'].invalidate_model()
        return result

    @api.model
    def apply_status(self, order, new_status, note=u'', actor_name=None):
        actor_name = actor_name or self.env.user.display_name
        order = order.sudo()
        old_status = order.rental_status

        # เขียนตรง ๆ แบบเดียวกับ wizard เดิมของระบบ (npd_rental_status_update)
        order.write({'rental_status': new_status})

        body = Markup(u'<b>ตัวช่วย AI-IT</b> แก้สถานะการเช่าโดย %s<br/>'
                      u'สถานะการเช่า: %s → %s') % (
            actor_name, self.label(old_status), self.label(new_status))
        if note:
            body += Markup(u'<br/>เหตุผล: %s') % note
        order.message_post(body=body, message_type='notification')

        _logger.info(
            u'ตัวช่วย AI-IT: %s แก้ rental_status ของ sale.order id=%s (%s) %s -> %s',
            actor_name, order.id, order.name, old_status, new_status,
        )
        return {
            'old_status': old_status,
            'new_status': new_status,
        }
