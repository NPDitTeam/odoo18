# -*- coding: utf-8 -*-
"""ตัวช่วย AI-IT : ใบโยกสินค้า (stock.api.transfer) ตัดสต๊อกไม่ผ่านเพราะของไม่พอ

ต่างจากฝั่ง Odoo 14 ตรงที่ใบโยกของ Odoo 18 เป็นแบบ "ฐานเดียว" แล้ว
ต้นทาง/ปลายทางเป็นคลังจริงใน DB นี้ ไม่ได้ยิงข้ามฐานผ่าน API อีก
การเติมสต๊อกจึงทำในเครื่องตรง ๆ ไม่ต้องตั้งค่าบัญชีเชื่อมฐานใด ๆ
"""
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

TRANSFER_MODEL = 'stock.api.transfer'

# ใบที่ยังตัดสต๊อกไม่สำเร็จ = ยังไม่ถึงขั้น confirmed
OPEN_STATES = ('draft', 'waiting_approval', 'approved')


class NpdAiItStockTransferFix(models.AbstractModel):
    _name = 'npd.ai.it.stock.transfer.fix'
    _description = 'ตัวช่วย AI-IT : เติมสต๊อกให้ใบโยกสินค้า'

    # ------------------------------------------------------------------
    # หาเอกสาร
    # ------------------------------------------------------------------
    @api.model
    def available(self):
        """โมดูลใบโยกสินค้าติดตั้งอยู่ในฐานนี้ไหม"""
        return TRANSFER_MODEL in self.env

    @api.model
    def find_transfer(self, ref):
        """หาใบโยกจากสิ่งที่พนักงานพิมพ์มา

        รับได้ทั้งเลขที่เอกสาร และเลขที่ระบบ (#206 หรือ 206) เพราะใบที่ตัด
        ไม่ผ่านมักยังไม่มีเลขที่ — เลขรันออกตอนกดยืนยันสำเร็จเท่านั้น
        """
        if not self.available():
            return None
        ref = (ref or '').strip()
        if not ref:
            return None
        Transfer = self.env[TRANSFER_MODEL].sudo()

        rec = Transfer.search([('name', '=', ref)], limit=1)
        if rec:
            return rec

        transfer_id, model_in_url = self._parse_transfer_ref(ref)
        # URL ของหน้าอื่น อย่าเดาว่าเป็นใบโยก ไม่งั้นเลขใน URL จะพาไปผิดใบ
        if model_in_url and model_in_url != TRANSFER_MODEL:
            return None
        if transfer_id:
            rec = Transfer.browse(transfer_id)
            if rec.exists():
                return rec
        return None

    @api.model
    def _parse_transfer_ref(self, text):
        """ดึงเลขที่ระบบของใบโยกจากสิ่งที่พนักงานวางมา

        รองรับทั้ง
            206 หรือ #206
            .../web#id=206&model=stock.api.transfer&view_type=form   (Odoo 14)
            .../odoo/stock.api.transfer/206                          (Odoo 18)
            .../odoo/action-123/206

        คืน (transfer_id, model_in_url) — ค่าไหนอ่านไม่ออกเป็น None
        """
        text = (text or '').strip()

        model_match = re.search(r'model=([a-zA-Z0-9_.]+)', text)
        model_in_url = model_match.group(1) if model_match else None

        # URL แบบใหม่ของ Odoo 18 ใส่ชื่อโมเดลไว้ใน path
        if not model_in_url:
            path_model = re.search(
                r'/odoo/(?:[a-z0-9-]+/)*?([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)/(\d+)', text)
            if path_model:
                return int(path_model.group(2)), path_model.group(1)

        id_match = re.search(r'(?:^|[#&?])id=(\d+)', text)
        if id_match:
            return int(id_match.group(1)), model_in_url

        bare = text.lstrip('#').strip()
        if bare.isdigit():
            return int(bare), model_in_url

        # ท้าย URL เป็นตัวเลข เช่น /odoo/action-123/206
        if '/' in text:
            tail = re.search(r'/(\d+)(?:[/?#]|$)', text)
            if tail:
                return int(tail.group(1)), model_in_url

        return None, model_in_url

    @api.model
    def pending_transfers(self, limit=15):
        """ใบโยกที่ยังตัดสต๊อกไม่สำเร็จ เรียงใบล่าสุดก่อน"""
        if not self.available():
            return None
        return self.env[TRANSFER_MODEL].sudo().search(
            [('state', 'in', OPEN_STATES)], order='id desc', limit=limit)

    # ------------------------------------------------------------------
    # อ่านสต๊อก
    # ------------------------------------------------------------------
    @api.model
    def _location_qty(self, product, location):
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ])
        return sum(quants.mapped('quantity'))

    # ------------------------------------------------------------------
    # วิเคราะห์
    # ------------------------------------------------------------------
    @api.model
    def analyze(self, transfer):
        """เทียบ "จำนวนขอตัด" กับของจริงในคลังต้นทาง

        คืน (all_items, shortage_items, error) — item เก็บลง session เป็น JSON ได้
        """
        transfer = transfer.sudo()
        all_items = []
        for line in transfer.line_ids:
            product = line.product_id
            location = line.source_location_id
            need = float(line.request_qty or 0.0)
            if not product or not location or need <= 0:
                continue
            current = self._location_qty(product, location)
            all_items.append({
                'line_id': line.id,
                'product_id': product.id,
                'code': product.default_code or '',
                'name': product.display_name,
                'location_id': location.id,
                'location_name': location.complete_name or '',
                'need': need,
                'current': current,
                'missing': max(need - current, 0.0),
                'target': None,
            })

        all_items.sort(key=lambda i: i['name'])
        shortage = [i for i in all_items if i['missing'] > 0]
        return all_items, shortage, None

    # ------------------------------------------------------------------
    # เติมสต๊อก
    # ------------------------------------------------------------------
    @api.model
    def apply_topup(self, transfer, items):
        """เติมสต๊อกที่คลังต้นทางให้ถึงจำนวนที่พนักงานนับได้จริง

        คืน (applied, error) — applied เป็น list ของ
        {code, name, location_id, location_name, before, added, after}

        เติมอย่างเดียว ถ้าจำนวนที่แจ้งน้อยกว่าหรือเท่าของในระบบ จะไม่แตะเลย
        """
        Product = self.env['product.product'].sudo()
        Location = self.env['stock.location'].sudo()
        Quant = self.env['stock.quant'].sudo()
        applied = []

        for item in items:
            target = float(item.get('target') or 0.0)
            if target <= 0:
                continue
            product = Product.browse(item['product_id'])
            location = Location.browse(item['location_id'])
            if not product.exists() or not location.exists():
                return [], 'ไม่พบสินค้าหรือคลังของรายการที่จะเติม'
            if location.usage != 'internal':
                return [], ('คลัง %s ไม่ใช่คลังภายใน จึงปรับสต๊อกให้ไม่ได้'
                            % (location.complete_name or location.id))

            before = self._location_qty(product, location)
            if target <= before:
                applied.append({
                    'code': item.get('code') or '',
                    'name': item.get('name') or product.display_name,
                    'location_id': location.id,
                    'location_name': item.get('location_name')
                    or location.complete_name or '',
                    'before': before, 'added': 0.0, 'after': before,
                })
                continue

            quant = Quant.search([
                ('product_id', '=', product.id),
                ('location_id', '=', location.id),
                ('lot_id', '=', False),
                ('package_id', '=', False),
                ('owner_id', '=', False),
            ], limit=1)
            if quant:
                quant = quant.with_context(inventory_mode=True)
                quant.write({'inventory_quantity': quant.quantity + (target - before)})
            else:
                quant = Quant.with_context(inventory_mode=True).create({
                    'product_id': product.id,
                    'location_id': location.id,
                    'inventory_quantity': target - before,
                })
            quant.action_apply_inventory()

            after = self._location_qty(product, location)
            _logger.info(
                'ตัวช่วย AI-IT: เติมสต๊อกใบโยก %s @ %s | %.2f -> %.2f (+%.2f)',
                product.display_name, location.complete_name,
                before, after, after - before)
            applied.append({
                'code': item.get('code') or (product.default_code or ''),
                'name': item.get('name') or product.display_name,
                'location_id': location.id,
                'location_name': item.get('location_name')
                or location.complete_name or '',
                'before': before, 'added': after - before, 'after': after,
            })

        return applied, None
