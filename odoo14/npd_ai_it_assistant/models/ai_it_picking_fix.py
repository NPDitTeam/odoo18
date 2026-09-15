# -*- coding: utf-8 -*-
u"""หัวข้อที่ 3 : แก้ไขวันที่คืนสินค้า

รับ "เลขที่ใบคืน" (ใบรับเข้า เช่น W3/IN/08511) แล้วแก้ฟิลด์ return_date
ของ stock.picking ซึ่งเป็น Datetime และหน้าจอล็อกไว้ให้แก้ไม่ได้ ถ้าผู้ใช้
ไม่มีสิทธิ์ can_edit_force_date (ดู rental_stock_picking)

รับเฉพาะ "ใบคืน" เท่านั้นตามที่ตกลงไว้ — ใบส่งออกไม่ให้แตะ เพราะ return_date
มีความหมายเฉพาะกับใบที่รับของกลับเข้าคลัง
"""
import logging

import pytz
from markupsafe import Markup

import odoo
from odoo import SUPERUSER_ID, api, fields, models
from odoo.tools.misc import html_escape

_logger = logging.getLogger(__name__)


class NpdAiItPickingFix(models.AbstractModel):
    _name = 'npd.ai.it.picking.fix'
    _description = u'ตัวช่วย AI-IT : แก้ไขวันที่คืนสินค้า'

    # ------------------------------------------------------------------
    # หาเอกสาร
    # ------------------------------------------------------------------
    @api.model
    def find_return_picking(self, text):
        """คืน (picking, error_message) — รับเฉพาะใบคืนเท่านั้น"""
        name = (text or '').strip()
        if not name:
            return None, None

        Picking = self.env['stock.picking'].sudo()
        picking = Picking.search([('name', '=', name)], limit=1)
        if not picking:
            # เผื่อพนักงานวาง URL มาแทนเลขเอกสาร
            move_id, model_in_url = self.env['npd.ai.it.invoice.fix'].parse_move_reference(text)
            if move_id and (not model_in_url or model_in_url == 'stock.picking'):
                picking = Picking.browse(move_id)
                if not picking.exists():
                    picking = Picking
        if not picking:
            return None, (u'ไม่พบใบคืนเลขที่ "%s" ในระบบ<br/>'
                          u'กรุณาพิมพ์เลขที่ใบคืนให้ตรงกับที่หน้าเอกสาร '
                          u'เช่น W3/IN/08511' % html_escape(name))

        if 'return_date' not in picking._fields:
            return None, (u'ระบบนี้ยังไม่มีฟิลด์ "วันที่และเวลาคืน" '
                          u'กรุณาแจ้งฝ่าย IT')

        if picking.picking_type_id.code != 'incoming':
            return None, (u'เอกสาร <b>%s</b> ไม่ใช่ใบคืน (เป็น%s)<br/>'
                          u'เมนูนี้แก้ได้เฉพาะ <b>ใบคืน</b> เท่านั้น'
                          % (picking.name,
                             picking.picking_type_id.name or u'เอกสารประเภทอื่น'))

        if picking.state == 'cancel':
            return None, u'ใบคืน <b>%s</b> ถูกยกเลิกไปแล้ว' % picking.name

        blocked = self.deposit_block_reason(picking)
        if blocked:
            return None, blocked

        return picking, None

    @api.model
    def deposit_block_reason(self, picking):
        u"""คืนข้อความห้ามแก้ ถ้าคืนเงินประกันไปแล้ว

        คืนเงินประกันแล้ว = ปิดงานเช่ารอบนั้นไปเรียบร้อย การย้อนไปแก้วันที่คืน
        จะทำให้ยอดค่าเช่า/ค่าปรับที่คำนวณไปแล้วไม่ตรงกับเงินที่คืนไปจริง
        จึงต้องให้ฝ่ายที่รับผิดชอบตัดสินใจเอง ไม่ให้แก้ผ่านตัวช่วยนี้

        คืน None เมื่อแก้ได้
        """
        if 'deposit_return_state' not in picking._fields:
            return None
        if picking.deposit_return_state != 'returned':
            return None
        return (u'ใบคืน <b>%s</b> มีสถานะการคืนเงินประกันเป็น '
                u'<b>"คืนเงินแล้ว"</b> จึงแก้วันที่คืนไม่ได้<br/>'
                u'ถ้าจำเป็นต้องแก้จริง ๆ กรุณาติดต่อฝ่ายบัญชี/การเงิน'
                % picking.name)

    @api.model
    def returned_from(self, picking):
        """ใบนี้เป็นการคืนของใบไหน (ใช้แสดงให้พนักงานตรวจว่าถูกใบ)"""
        origin_moves = picking.sudo().move_ids.mapped('origin_returned_move_id')
        if origin_moves:
            names = origin_moves.mapped('picking_id.name')
            return ', '.join(n for n in dict.fromkeys(names) if n)
        return picking.origin or ''

    # ------------------------------------------------------------------
    # แปลงเวลา (ฟิลด์เก็บ UTC แต่พนักงานคิดเป็นเวลาไทย)
    # ------------------------------------------------------------------
    @api.model
    def _user_tz(self):
        return pytz.timezone(self.env.user.tz or 'Asia/Bangkok')

    @api.model
    def to_local(self, utc_dt):
        """Datetime (UTC) -> naive datetime ตามเวลาผู้ใช้"""
        if not utc_dt:
            return None
        return fields.Datetime.context_timestamp(self, utc_dt).replace(tzinfo=None)

    @api.model
    def to_utc(self, local_dt):
        """naive datetime ตามเวลาผู้ใช้ -> Datetime (UTC) สำหรับเก็บลงฐาน"""
        return self._user_tz().localize(local_dt).astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # ลงมือแก้
    # ------------------------------------------------------------------
    @api.model
    def apply_return_date_isolated(self, picking_id, new_utc_dt, note=u'', actor_name=None):
        u"""แก้ในทรานแซกชันแยก (เหตุผลเดียวกับหัวข้อ 2 — ดู ai_it_invoice_fix)"""
        self.env['stock.picking'].flush_model()

        registry = odoo.registry(self.env.cr.dbname)
        with registry.cursor() as new_cr:
            new_env = api.Environment(new_cr, SUPERUSER_ID, dict(self.env.context))
            picking = new_env['stock.picking'].browse(picking_id)
            if not picking.exists():
                raise ValueError(u'ไม่พบใบคืน id=%s' % picking_id)
            result = new_env['npd.ai.it.picking.fix'].apply_return_date(
                picking, new_utc_dt, note=note, actor_name=actor_name)

        self.env['stock.picking'].invalidate_model()
        return result

    @api.model
    def apply_return_date(self, picking, new_utc_dt, note=u'', actor_name=None):
        actor_name = actor_name or self.env.user.display_name
        picking = picking.sudo()
        old_utc = picking.return_date

        picking.write({'return_date': new_utc_dt})

        old_local = self.to_local(old_utc)
        new_local = self.to_local(new_utc_dt)
        # แสดงเฉพาะวันที่ — เวลาถูกคงไว้ตามของเดิม ไม่ได้เป็นสิ่งที่ผู้ใช้สนใจ
        # (ถ้าอยากดูค่าเป๊ะ ๆ ดูได้ที่ tracking ของฟิลด์ซึ่ง Odoo บันทึกให้อยู่แล้ว)
        body = Markup(u'<b>ตัวช่วย AI-IT</b> แก้วันที่คืนสินค้าโดย %s<br/>'
                      u'วันที่คืน: %s → %s') % (
            actor_name,
            old_local.strftime('%d/%m/%Y') if old_local else u'—',
            new_local.strftime('%d/%m/%Y'))
        if note:
            body += Markup(u'<br/>เหตุผล: %s') % note
        picking.message_post(body=body)

        _logger.info(
            u'ตัวช่วย AI-IT: %s แก้ return_date ของ stock.picking id=%s (%s) %s -> %s',
            actor_name, picking.id, picking.name, old_utc, new_utc_dt,
        )
        return {
            'old_local': old_local,
            'new_local': new_local,
        }
