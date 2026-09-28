# -*- coding: utf-8 -*-
"""วันตัดโอนการซิงค์ข้อมูลขนส่งจาก Odoo 14

หลังวันที่ตั้งไว้ ฝั่งบริษัท เอ็นพีดี โลจิสติกส์ จะมีปุ่มส่งข้อมูลเข้ามาที่
หน้าข้อมูลขนส่งเอง การดึงจากฝั่ง 14 จึงต้องหยุด ไม่งั้นข้อมูลเก่าจะไหลมาทับ
สิ่งที่ฝั่งโลจิสติกส์เพิ่งส่งเข้ามา แล้วไม่มีใครรู้ว่าทับตอนไหน

หยุดสามชั้นพร้อมกัน
  1. งานตั้งเวลาปิดตัวเองถาวร
  2. เมนูซิงค์สองอันถูกซ่อน (เปิดคืนได้ถ้าจำเป็น)
  3. ต่อให้มีคนเรียกเมธอดตรง ๆ ก็ถูกปฏิเสธพร้อมบอกเหตุผล

เลื่อนวันได้ที่ การตั้งค่า > เทคนิค > พารามิเตอร์ระบบ
``transport_sync.stop_after_date`` (รูปแบบ YYYY-MM-DD) ว่าง = ไม่หยุด
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STOP_PARAM = 'transport_sync.stop_after_date'
# วันสุดท้ายที่ "ยังใช้งานได้เต็มวัน" ไม่ใช่วันแรกที่หยุด
# 2026-12-30 = วันที่ 30 ยังซิงค์ได้ปกติ หยุดตั้งแต่วันที่ 31 เป็นต้นไป
DEFAULT_STOP_DATE = '2026-12-30'
SYNC_MENU_XMLIDS = (
    'transport_sync.menu_transport_sync_today',
    'transport_sync.menu_transport_sync_all',
)


class TransportOrderCutover(models.Model):
    _inherit = 'transport.order'

    # ------------------------------------------------------------------
    @api.model
    def _sync_stop_date(self):
        """วันสุดท้ายที่ยังดึงจากฝั่ง 14 ได้ — None = ไม่กำหนด"""
        raw = (self.env['ir.config_parameter'].sudo()
               .get_param(STOP_PARAM, default=DEFAULT_STOP_DATE) or '').strip()
        if not raw:
            return None
        try:
            return fields.Date.to_date(raw)
        except (ValueError, TypeError):
            _logger.warning('[TRANSPORT SYNC] ค่า %s = %r ผิดรูปแบบ '
                            'ต้องเป็น YYYY-MM-DD', STOP_PARAM, raw)
            return None

    @api.model
    def _sync_is_stopped(self):
        """เลยวันตัดโอนแล้วหรือยัง (นับตามเวลาไทย)"""
        stop_date = self._sync_stop_date()
        if not stop_date:
            return False
        today = fields.Date.context_today(
            self.with_context(tz='Asia/Bangkok'))
        return today > stop_date

    @api.model
    def _sync_disable_everything(self):
        """ปิดงานตั้งเวลาและซ่อนเมนูซิงค์ — เรียกซ้ำได้ ไม่พังถ้าปิดไปแล้ว"""
        stop_date = self._sync_stop_date()
        cron = self.env.ref('transport_sync.ir_cron_transport_sync',
                            raise_if_not_found=False)
        if cron and cron.active:
            cron.sudo().write({'active': False})
            _logger.warning(
                '[TRANSPORT SYNC] เลยวันตัดโอน (%s) แล้ว ปิดงานตั้งเวลาถาวร',
                stop_date)
        for xmlid in SYNC_MENU_XMLIDS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.active:
                menu.sudo().write({'active': False})
                _logger.warning('[TRANSPORT SYNC] ซ่อนเมนู %s', xmlid)

    @api.model
    def _sync_check_allowed(self):
        """ปฏิเสธพร้อมบอกเหตุผล ถ้าเลยวันตัดโอนแล้ว"""
        if not self._sync_is_stopped():
            return
        self._sync_disable_everything()
        raise UserError(_(
            'เลยวันตัดโอนข้อมูลขนส่ง (%s) แล้ว จึงดึงจากฝั่ง Odoo 14 ไม่ได้อีก\n\n'
            'หลังวันนี้ ฝั่งบริษัท เอ็นพีดี โลจิสติกส์ เป็นผู้ส่งข้อมูลเข้ามาเอง '
            'ถ้าดึงซ้ำ ข้อมูลเก่าจะทับของใหม่ที่เพิ่งส่งเข้ามา\n\n'
            'ถ้าจำเป็นต้องดึงจริง ๆ ให้เลื่อนวันที่ในพารามิเตอร์ระบบ %s ก่อน'
        ) % (self._sync_stop_date(), STOP_PARAM))

    # ------------------------------------------------------------------
    def action_sync_from_odoo14(self):
        self._sync_check_allowed()
        return super().action_sync_from_odoo14()

    def action_sync_recent_from_odoo14(self):
        # งานตั้งเวลาเรียกตัวนี้ ต้องไม่โยน error ใส่ cron ให้ขึ้นแดงทุกห้านาที
        # ปิดตัวเองเงียบ ๆ แล้วจบไป ส่วนคนกดเองจะเห็นข้อความจากชั้น UserError
        if self.env.context.get('transport_sync_from_cron'):
            if self._sync_is_stopped():
                self._sync_disable_everything()
                return False
            return super().action_sync_recent_from_odoo14()
        self._sync_check_allowed()
        return super().action_sync_recent_from_odoo14()
