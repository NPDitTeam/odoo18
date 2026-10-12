# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

UNTIL_PARAM = 'npd_rental_import_o14.auto_sync_until'


class RentalAutoSync(models.Model):
    _inherit = 'npd.rental.import.config'

    # อินเตอร์เป็นตัวหลักของรหัสสินค้า: สินค้า "(สำเนา)" ของ S Group ใช้รหัสคนละแบบ
    # ถ้ายกสินค้าทุกฐานจะสลับรหัสกันไปมาทุกสัปดาห์ จึงเปิดยกสินค้าเฉพาะฐานที่ติ๊ก
    auto_sync_products = fields.Boolean(
        string='ซิงก์สินค้าอัตโนมัติ', default=False,
        help='ยกสินค้าเช่าทุกสัปดาห์ — เปิดเฉพาะฐานที่เป็นตัวหลักของรหัสสินค้า (อินเตอร์)')
    auto_sync_pricelists = fields.Boolean(
        string='ซิงก์รายการราคาอัตโนมัติ', default=True)

    @api.model
    def _init_auto_sync_flags(self):
        """ครั้งแรกที่ติดตั้ง: เปิดซิงก์สินค้าให้อินเตอร์ (ทำครั้งเดียว ไม่ทับที่ผู้ใช้แก้ภายหลัง)"""
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('npd_rental_import_o14.auto_sync_flags_init'):
            return
        self.sudo().with_context(active_test=False).search(
            [('db_name', '=', 'NPD_Intertrading_New')]).write({'auto_sync_products': True})
        ICP.set_param('npd_rental_import_o14.auto_sync_flags_init', '1')

    @api.model
    def _cron_auto_sync(self):
        """ซิงก์สินค้า/รายการราคาจาก o14 รายสัปดาห์ จนถึงวันที่ในพารามิเตอร์ (เวลาไทย)"""
        ICP = self.env['ir.config_parameter'].sudo()
        until = fields.Date.to_date(ICP.get_param(UNTIL_PARAM) or False)
        today = fields.Date.context_today(self.with_context(tz='Asia/Bangkok'))
        if until and today > until:
            cron = self.env.ref('npd_rental_import_o14.ir_cron_rental_auto_sync',
                                raise_if_not_found=False)
            if cron:
                cron.sudo().active = False
            _logger.info('[RENTAL AUTO SYNC] เลยกำหนด %s แล้ว ปิดงานตั้งเวลา', until)
            return

        for cfg in self.sudo().search([], order='sequence, id'):
            steps = []
            if cfg.auto_sync_products:
                steps.append(('action_sync_products', _('สินค้า')))
            if cfg.auto_sync_pricelists:
                steps.append(('action_sync_pricelists', _('รายการราคา')))
            if not steps:
                continue
            texts = []
            for method, label in steps:
                try:
                    with self.env.cr.savepoint():
                        texts.append(getattr(cfg, method)() or '')
                except Exception as error:  # noqa: BLE001 — ฐานหนึ่งล้มไม่ให้ฐานอื่นหยุด
                    _logger.exception('[RENTAL AUTO SYNC %s] %s ล้ม', cfg.db_name, label)
                    texts.append(_('%s ล้ม: %s') % (label, error))
            cfg._note(_('ซิงก์อัตโนมัติรายสัปดาห์') + '\n' + '\n\n'.join(texts))
            self.env.cr.commit()
