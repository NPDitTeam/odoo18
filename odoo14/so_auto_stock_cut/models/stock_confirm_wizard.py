# -*- coding: utf-8 -*-
# ======================================================================
# SO Auto Stock Cut — Odoo 18
# เวอร์ชันนี้ตัดการเชื่อมต่อ MySQL / บ้านเขียว (external sync) ออกทั้งหมด
# ทำงานเฉพาะการ "ตัดสต๊อก" และ "คืนสต๊อก" ภายใน Odoo เท่านั้น
# ======================================================================
from odoo import models, api, fields
from odoo.exceptions import UserError
from odoo.tools import float_compare
import logging

_logger = logging.getLogger(__name__)


def _dbg(msg):
    try:
        _logger.info(msg)
    except Exception:
        pass


class StockCutConfirmWizard(models.TransientModel):
    _name = 'stock.cut.confirm.wizard'
    _description = 'Confirm Stock Cut Wizard'

    order_id = fields.Many2one('sale.order', string='Sale Order')
    confirm_line_ids = fields.One2many(
        'stock.cut.confirm.line', 'wizard_id', string='Stock Moves to Confirm')

    # โหมดของ wizard: 'cut' = ตัดสต๊อก, 'return' = คืนสต๊อก
    mode = fields.Selection([
        ('cut', 'ตัดสต๊อก'),
        ('return', 'คืนสต๊อก'),
    ], string='โหมด', default='cut')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_odoo_stock_qty(self, product, location):
        """ดึงสต๊อกคงเหลือใน Odoo จากตาราง stock.quant (ฟิลด์ quantity) ที่คลังต้นทาง (location)"""
        if not product or not location:
            return 0.0
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ])
        return sum(quants.mapped('quantity'))

    def _get_branch_internal_location(self, branch, product_ids=None):
        """หา 'คลังต้นทาง' (usage=internal) ของสาขา
        กันเคส location ซ้ำ (บางสาขามีหลาย location ชื่อเดียวกัน เช่น ปลวกแดง/โคราช)
        โดยเลือกอันที่ 'มีสต๊อกจริง' ของสินค้าที่จะตัดมากที่สุด แทนการหยิบ limit=1
        มั่ว ๆ ที่อาจได้ location ว่าง -> จองไม่ได้ -> error"""
        Location = self.env['stock.location']
        locations = Location.search([
            ('branch_id', '=', branch.id),
            ('usage', '=', 'internal'),
        ])
        if len(locations) <= 1:
            return locations[:1]

        Quant = self.env['stock.quant']

        def _best(domain):
            agg = {}
            for q in Quant.search(domain):
                agg[q.location_id.id] = agg.get(q.location_id.id, 0.0) + q.quantity
            if agg:
                best_id = max(agg, key=agg.get)
                if agg[best_id] > 0:
                    return Location.browse(best_id)
            return None

        # 1) เลือกจากสต๊อกของ 'สินค้าที่จะตัด'
        if product_ids:
            loc = _best([('location_id', 'in', locations.ids),
                         ('product_id', 'in', list(product_ids))])
            if loc:
                return loc
        # 2) เลือกจากสต๊อกรวมทั้งหมด (หา location ที่ใช้งานจริง)
        loc = _best([('location_id', 'in', locations.ids)])
        if loc:
            return loc
        # 3) ไม่มีสต๊อกเลย -> อันแรก (พฤติกรรมเดิม)
        return locations[:1]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = self.env.context.get('default_order_id')
        if not order_id:
            return res

        order = self.env['sale.order'].browse(order_id)
        location = self._get_branch_internal_location(
            order.branch_id,
            order.order_line.filtered(lambda l: l.product_id).mapped('product_id').ids,
        )
        location_name = location.display_name if location else "ไม่พบคลังของสาขา"

        # ----------------- โหมดคืนสต๊อก: ดึงสินค้าที่ 'ตัดจริง' มาแสดงเพื่อคืน -----------------
        mode = self.env.context.get('default_mode', 'cut')
        if mode == 'return':
            res['mode'] = 'return'
            res['order_id'] = order.id
            res['confirm_line_ids'] = self._build_return_lines(order, location, location_name)
            return res

        # ----------------- โหมดตัดสต๊อก: เตรียมไลน์จาก SO -----------------
        base_lines = []
        for so_line in order.order_line.filtered(
                lambda l: not l.display_type
                          and l.product_id
                          and l.product_id.type == 'consu'
                          and (l.pfb_quantity or 0) > 0
        ):
            base_lines.append((0, 0, {
                'product_id': so_line.product_id.id,
                'quantity': so_line.pfb_quantity,
                'location_name': location_name,
                'odoo_stock_qty': self._get_odoo_stock_qty(so_line.product_id, location),
            }))

        res['order_id'] = order.id
        res['confirm_line_ids'] = base_lines
        return res

    def _fix_stale_reserved_qty(self, cut_items, location):
        """
        ปลด reserved เฉพาะสินค้าที่กำลังจะตัดสต็อก ที่ location นี้เท่านั้น
        เพื่อให้ action_assign() สามารถ reserve ใหม่ได้อย่างถูกต้อง

        หมายเหตุ Odoo 18: โมเดลการจองสต๊อกถูกเขียนใหม่ตั้งแต่ Odoo 17
          - stock.move.line ไม่มีคอลัมน์ qty_done / product_uom_qty อีกต่อไป
            ใช้ 'quantity' (จำนวนที่จอง/ตัด) + 'picked' (bool = ตัดจริงแล้ว) แทน
          - 'ยังจองอยู่แต่ยังไม่ตัด' = picked = false และ quantity > 0
        """
        cr = self.env.cr
        product_ids = list(cut_items.keys())
        if not product_ids:
            return

        for product_id in product_ids:
            product = cut_items[product_id]['product']

            # 1) ปลด move_line reservations ที่ยังไม่ได้ตัดจริง (picked = false)
            cr.execute("""
                UPDATE stock_move_line
                SET quantity = 0
                WHERE product_id = %s
                  AND location_id = %s
                  AND state NOT IN ('done', 'cancel')
                  AND quantity > 0
                  AND COALESCE(picked, FALSE) = FALSE
            """, (product_id, location.id))
            cleared = cr.rowcount
            if cleared > 0:
                _dbg(f"⚠️ UNRESERVE: {product.display_name} @ {location.display_name} | "
                     f"ปลด {cleared} move_lines")

            # 2) Force set reserved_quantity = 0 บน quant
            cr.execute("""
                UPDATE stock_quant
                SET reserved_quantity = 0
                WHERE product_id = %s
                  AND location_id = %s
                  AND reserved_quantity > 0
            """, (product_id, location.id))
            if cr.rowcount > 0:
                _dbg("   ✅ Reset quant reserved_quantity = 0")

            # 3) Invalidate cache (Odoo 18: invalidate_cache -> invalidate_model/invalidate_recordset)
            self.env['stock.move.line'].invalidate_model(['quantity'])
            self.env['stock.quant'].invalidate_model(['reserved_quantity'])
            product.invalidate_recordset(
                ['qty_available', 'virtual_available', 'free_qty'])

    # ==================================================================
    # คืนสต๊อก Auto (return) — ย้อนกลับการตัดสต๊อก
    # ==================================================================
    def _sync_rent_dates(self, picking):
        """คัดลอกวันที่เริ่มต้น/สิ้นสุดการเช่า จาก sale.order ไปยัง stock.picking
        (start_rent_date -> start_x_date, end_rent_date -> end_x_date)
        ใช้ทั้งตอนตัดสต๊อกและตอนคืนสต๊อก
        (ฟิลด์เหล่านี้มาจากโมดูลเช่าภายนอก — ป้องกันด้วย hasattr กันพังหากไม่มี)"""
        order = self.order_id
        vals = {}
        if hasattr(order, 'start_rent_date') and order.start_rent_date and 'start_x_date' in picking._fields:
            vals['start_x_date'] = order.start_rent_date
        if hasattr(order, 'end_rent_date') and order.end_rent_date and 'end_x_date' in picking._fields:
            vals['end_x_date'] = order.end_rent_date
        if vals:
            picking.write(vals)

    @staticmethod
    def _is_cut_picking(p):
        """เป็นใบ 'ตัดสต๊อก' จริง = ใบส่งออกเสร็จสิ้น และไม่ใช่ใบคืน
        ตรวจใบคืนด้วย origin_returned_move_id (ไม่ใช่ข้อความ origin ที่ถูกแปลภาษาได้)"""
        return (
            p.state == 'done'
            and p.picking_type_id.code == 'outgoing'
            and not any(m.origin_returned_move_id for m in p.move_ids)
        )

    def _get_last_cut_picking(self):
        """ใบจัดส่งขาออกที่ตัดสต๊อกแล้ว (done) ล่าสุดของคำสั่งขายนี้ (ไม่ใช่ใบคืน)"""
        pickings = self.order_id.picking_ids.filtered(
            self._is_cut_picking
        ).sorted('id', reverse=True)
        return pickings[:1]

    def _build_return_lines(self, order, location, location_name):
        """สร้างบรรทัดรายการคืน จากสินค้าที่ 'ตัดจริง' ในใบจัดส่งขาออกล่าสุด"""
        lines = []
        picking = order.picking_ids.filtered(
            self._is_cut_picking
        ).sorted('id', reverse=True)[:1]
        if not picking:
            return lines
        for move in picking.move_ids_without_package.filtered(
                lambda m: m.state == 'done' and m.quantity > 0):
            lines.append((0, 0, {
                'product_id': move.product_id.id,
                'quantity': move.quantity,
                'location_name': location_name,
                'odoo_stock_qty': self._get_odoo_stock_qty(move.product_id, location),
            }))
        return lines

    def _force_done_full(self, picking):
        """ใส่จำนวนที่ตัด (done) เต็มตามความต้องการให้ทุก move แล้ว validate ปิดใบเป็น 'เสร็จสิ้น'

        Odoo 18: ใช้ move._set_quantity_done(qty) (สร้าง/ปรับ move line ให้ได้ยอด done)
        แล้วตั้ง move.picked = True แทนการเขียน qty_done ตรง ๆ (ฟิลด์นั้นถูกลบไปแล้ว)"""
        picking.action_assign()
        for move in picking.move_ids:
            qty = float(move.product_uom_qty or 0.0)  # ความต้องการ (demand)
            if qty <= 0:
                continue
            move._set_quantity_done(qty)
            for ml in move.move_line_ids:
                if move.product_id.tracking in ('lot', 'serial') and not (ml.lot_id or ml.lot_name):
                    ml.lot_name = f"AUTO-{fields.Date.today()}"
            move.picked = True
        picking.invalidate_recordset()
        picking.with_context(
            skip_backorder=True, skip_sms=True
        ).button_validate()

    def confirm_stock_return(self):
        self.ensure_one()
        order = self.order_id
        picking = self._get_last_cut_picking()
        if not picking:
            raise UserError("❌ ไม่พบใบจัดส่งที่ตัดสต๊อกแล้ว (เสร็จสิ้น) สำหรับคำสั่งขายนี้")

        # กันคืนซ้ำ: มี move ในใบตัดนี้ถูกอ้างอิงเป็นต้นทางการคืน (origin_returned_move_id) แล้วหรือยัง
        # ใช้โครงสร้างจริงแทนการเทียบ origin เพราะ 'Return of..' ถูกแปลภาษาได้
        cut_move_ids = set(picking.move_ids.ids)
        already_returned = any(
            m.origin_returned_move_id.id in cut_move_ids
            for p in order.picking_ids.filtered(lambda x: x.state == 'done')
            for m in p.move_ids
            if m.origin_returned_move_id
        )
        if already_returned:
            raise UserError("↩️ ใบจัดส่งนี้ถูกคืนสต๊อกเรียบร้อยแล้ว ไม่สามารถคืนซ้ำได้")

        # จำนวนที่ 'ตัดจริง' ต่อสินค้า (ใช้ตรวจความครบถ้วนของการคืน)
        cut_qty_by_product = {}
        for move in picking.move_ids_without_package.filtered(
                lambda m: m.state == 'done' and m.quantity > 0):
            cut_qty_by_product[move.product_id.id] = \
                cut_qty_by_product.get(move.product_id.id, 0.0) + move.quantity
        if not cut_qty_by_product:
            raise UserError("❌ ไม่พบรายการสินค้าที่ถูกตัดในใบจัดส่งนี้")

        # ---- สร้างใบคืนด้วย stock.return.picking (มาตรฐาน Odoo) ----
        # Odoo 18: stock.return.picking.line ใช้ฟิลด์ product_id/quantity/move_id
        #   - uom_id เป็น related readonly (มาจาก product) จึงไม่ต้องส่ง
        #   - wizard ไม่มีฟิลด์ location_id แล้ว (ปลายทางคืนถูกคำนวณอัตโนมัติ)
        return_lines = []
        for move in picking.move_ids_without_package.filtered(
                lambda m: m.state == 'done' and m.quantity > 0):
            return_lines.append((0, 0, {
                'product_id': move.product_id.id,
                'quantity': move.quantity,
                'move_id': move.id,
            }))

        return_wiz = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_ids=picking.ids, active_model='stock.picking'
        ).create({
            'picking_id': picking.id,
            'product_return_moves': return_lines,
        })

        # Odoo 18: create_returns() ถูกแทนด้วย _create_return() ที่คืน recordset ใบคืนโดยตรง
        new_picking = return_wiz._create_return()
        _dbg(f"↩️ สร้างใบคืน {new_picking.name} จาก {picking.name}")

        # ---- ดันให้เสร็จสิ้นอัตโนมัติ (จำนวนเต็ม + validate) ----
        self._force_done_full(new_picking)

        # sync วันที่เช่าจาก SO ไปยังใบคืน (start_x_date/end_x_date)
        # ⚠️ ต้องทำ 'หลัง' _force_done_full เพราะ action_assign อาจเขียนค่าวันทับ
        self._sync_rent_dates(new_picking)

        # ---- ตรวจความครบถ้วนของการคืน เทียบกับสินค้าที่ 'ตัดจริง' ----
        new_picking.invalidate_recordset()
        returned_qty_by_product = {}
        for move in new_picking.move_ids_without_package.filtered(lambda m: m.state == 'done'):
            returned_qty_by_product[move.product_id.id] = \
                returned_qty_by_product.get(move.product_id.id, 0.0) + move.quantity

        not_returned = []
        for product_id, need in cut_qty_by_product.items():
            product = self.env['product.product'].browse(product_id)
            rounding = product.uom_id.rounding or 0.01
            done = returned_qty_by_product.get(product_id, 0.0)
            if float_compare(done, need, precision_rounding=rounding) < 0:
                not_returned.append((product, need, done))

        if not_returned:
            lines = [
                f"• {p.display_name} — ต้องคืน {need:.0f} แต่คืนได้ {done:.0f}"
                for (p, need, done) in not_returned
            ]
            raise UserError(
                "❌ คืนสต๊อกไม่ครบทุกรายการ!\n\n"
                "สินค้าต่อไปนี้ถูกตัดไปแต่คืนกลับได้ไม่ครบ:\n\n"
                + "\n".join(lines)
                + "\n\nระบบยกเลิกการคืนสต๊อกทั้งใบแล้ว (ไม่มีการคืนค้างบางส่วน)\n"
                  "กรุณาตรวจสอบและลองใหม่อีกครั้ง หรือแจ้งผู้ดูแลระบบ"
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ คืนสต๊อกสำเร็จ',
                'message': f'สร้างใบคืน {new_picking.name} และปิดสถานะเสร็จสิ้นเรียบร้อย '
                           f'(คืน {len(cut_qty_by_product)} รายการ)',
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'}
            }
        }

    def confirm_stock_cut(self):
        pickings = self.order_id.picking_ids.filtered(
            lambda p: p.state != 'cancel').sorted('id', reverse=True)
        if not pickings:
            raise UserError("❌ ไม่พบใบจัดส่งสำหรับคำสั่งขายนี้")
        picking = pickings[0]

        # sync วันที่เช่า (start_rent_date/end_rent_date -> start_x_date/end_x_date)
        self._sync_rent_dates(picking)

        if picking.state == 'done':
            raise UserError("📦 ใบจัดส่งนี้ถูกตัดสต๊อกเรียบร้อยแล้ว ไม่สามารถตัดซ้ำได้")

        # ใช้คลังสาขา (เลือก location ที่มีสต๊อกจริง กันเคส location ซ้ำของสาขา)
        location = self._get_branch_internal_location(
            self.order_id.branch_id,
            self.order_id.order_line.filtered(lambda l: l.product_id).mapped('product_id').ids,
        )
        if not location:
            raise UserError("❌ ไม่พบคลังต้นทางของสาขา (ย่อย)")

        if picking.location_id.id != location.id:
            picking.write({'location_id': location.id})

        # ✅ อ่าน product/quantity จาก SO line โดยตรง (readonly field ใน TransientModel ไม่ถูกส่งกลับจาก client)
        so_lines = self.order_id.order_line.filtered(
            lambda l: not l.display_type
                      and l.product_id
                      and l.product_id.type == 'consu'
                      and (l.pfb_quantity or 0) > 0
        )
        cut_items = {}
        for sol in so_lines:
            cut_items[sol.product_id.id] = {
                'product': sol.product_id,
                'quantity': sol.pfb_quantity,
            }
        if not cut_items:
            raise UserError("❌ ไม่พบสินค้าที่ต้องตัดสต๊อก (ตรวจจำนวน pfb_quantity ในใบสั่งขาย)")
        _dbg(f"📊 cut_items from SO: {[(v['product'].display_name, v['quantity']) for v in cut_items.values()]}")

        # 📌 บันทึกสต๊อกคงเหลือใน Odoo ก่อนตัด (ต่อสินค้า) ไว้ตรวจ/เตือนกรณีสต๊อกไม่พอ
        pre_cut_available = {
            product_id: self._get_odoo_stock_qty(item['product'], location)
            for product_id, item in cut_items.items()
        }

        # ============ จัดการ moves + validate picking ============
        _dbg(f"🔧 picking {picking.name}: state={picking.state}, "
             f"moves={len(picking.move_ids_without_package)}")

        # ✅ แก้ reserved_quantity ค้างใน stock.quant ก่อนตัดสต๊อก
        self._fix_stale_reserved_qty(cut_items, location)

        # ✅ สร้าง move ให้ครบทุกสินค้าจาก SO ที่ยังไม่มีใน picking
        existing_product_ids = set(picking.move_ids_without_package.mapped('product_id').ids)
        missing_moves = []
        for product_id, item in cut_items.items():
            if product_id in existing_product_ids:
                continue
            product = item['product']
            missing_moves.append((0, 0, {
                'name': product.name,
                'product_id': product.id,
                'product_uom_qty': float(item['quantity']),
                'product_uom': product.uom_id.id,
                'location_id': location.id,
                'location_dest_id': picking.location_dest_id.id,
                'picking_id': picking.id,
            }))
        if missing_moves:
            picking.write({'move_ids_without_package': missing_moves})
            _dbg(f"📦 สร้าง moves สำหรับสินค้าที่ยังไม่มีใน picking: {len(missing_moves)} รายการ")

        # ✅ อัพเดท location ของ moves ที่มีอยู่
        for move in picking.move_ids_without_package:
            if move.location_id.id != location.id:
                move.location_id = location.id

        # ✅ confirm moves ที่ยังเป็น draft
        draft_moves = picking.move_ids_without_package.filtered(lambda m: m.state == 'draft')
        if draft_moves:
            _dbg(f"📦 confirming {len(draft_moves)} draft moves")
            draft_moves._action_confirm()

        # ✅ unreserve ก่อน (ล้าง reservation เก่าบน picking นี้)
        if picking.move_ids_without_package.filtered(lambda m: m.state not in ('draft', 'cancel', 'done')):
            picking.do_unreserve()
            _dbg("📦 do_unreserve() done — ล้าง reservation เก่า")

        # ✅ reserve สต็อก
        picking.action_assign()
        _dbg(f"📦 action_assign() done. state={picking.state}")

        # ✅ ใส่จำนวนที่ตัด (done) บน move
        # Odoo 18: ใช้ move._set_quantity_done(qty) แล้วตั้ง move.picked = True
        #   แทนการเขียน qty_done ตรง ๆ บน move.line (ฟิลด์ qty_done/product_uom_qty ถูกลบไปแล้ว)
        cut_items_keys = list(cut_items.keys())
        any_qty_set = False
        for move in picking.move_ids_without_package:
            item = cut_items.get(move.product_id.id)
            if not item:
                continue
            qty_done = float(item['quantity'] or 0.0)
            move._set_quantity_done(qty_done)
            for ml in move.move_line_ids:
                vals = {}
                if ml.location_id.id != location.id:
                    vals['location_id'] = location.id
                if move.product_id.tracking in ('lot', 'serial') and not (ml.lot_id or ml.lot_name):
                    vals['lot_name'] = f"AUTO-{fields.Date.today()}"
                if vals:
                    ml.write(vals)
            move.picked = True
            any_qty_set = True
            _dbg(f"  ✅ set quantity(done)={qty_done} + picked=True บน move {move.id}")

        if not any_qty_set:
            raise UserError(
                "❌ ไม่สามารถจับคู่สินค้ากับ moves ในใบจัดส่งได้\n\n"
                f"cut_items product_ids: {cut_items_keys}\n"
                f"move product_ids: {[m.product_id.id for m in picking.move_ids_without_package]}"
            )

        # ✅ invalidate cache + fix reserved อีกรอบ + validate picking
        picking.invalidate_recordset()
        self._fix_stale_reserved_qty(cut_items, location)

        _dbg(f"🚀 กำลัง button_validate() picking {picking.name}")
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()

        # ============================================================
        # ✅ ตรวจสอบความครบถ้วน: สินค้าทุกตัวจาก Sale Order ต้องถูกตัดครบ
        # ============================================================
        picking.invalidate_recordset()

        done_qty_by_product = {}
        for move in picking.move_ids_without_package.filtered(lambda m: m.state == 'done'):
            done_qty_by_product[move.product_id.id] = \
                done_qty_by_product.get(move.product_id.id, 0.0) + move.quantity

        not_cut = []        # ตัดไม่ครบจำนวน / ไม่ถูกตัดเลย
        insufficient = []   # ตัดครบ แต่สต๊อกในระบบไม่พอ (ตัดจนติดลบ)
        for product_id, item in cut_items.items():
            product = item['product']
            need = float(item['quantity'] or 0.0)
            rounding = product.uom_id.rounding or 0.01
            done = done_qty_by_product.get(product_id, 0.0)
            if float_compare(done, need, precision_rounding=rounding) < 0:
                not_cut.append((product, need, done))
            avail_before = pre_cut_available.get(product_id, 0.0)
            if float_compare(avail_before, need, precision_rounding=rounding) < 0:
                insufficient.append((product, need, avail_before))

        # ❌ ตัดไม่ครบ → ยกเลิกทั้งใบ (rollback) แล้วแจ้งพนักงานให้ชัด
        if not_cut:
            lines = [
                f"• {p.display_name} — ต้องตัด {need:.0f} แต่ตัดได้ {done:.0f}"
                for (p, need, done) in not_cut
            ]
            raise UserError(
                "❌ ตัดสต๊อกไม่ครบทุกรายการ!\n\n"
                "สินค้าต่อไปนี้ถูกส่งมาจากใบสั่งขายแต่ตัดสต๊อกได้ไม่ครบ:\n\n"
                + "\n".join(lines)
                + "\n\nระบบยกเลิกการตัดสต๊อกทั้งใบแล้ว (ไม่มีการตัดค้างไว้บางส่วน)\n"
                  "กรุณาตรวจสอบและลองใหม่อีกครั้ง หรือแจ้งผู้ดูแลระบบ"
            )

        # ⚠️ ตัดครบแต่สต๊อกในระบบไม่พอ (ติดลบ) → เตรียมข้อความเตือน (ไม่ยกเลิกการตัด)
        insufficient_msg = ""
        if insufficient:
            lines = [
                f"• {p.display_name} — ตัด {need:.0f} / มีในระบบ {avail:.0f}"
                for (p, need, avail) in insufficient
            ]
            insufficient_msg = (
                "\n\n⚠️ สต๊อกในระบบไม่พอ (ตัดจนติดลบ) สำหรับ:\n"
                + "\n".join(lines)
                + "\nกรุณาตรวจนับ/เติมสต๊อกสาขาให้ตรงกับความเป็นจริง"
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '⚠️ ตัดสต๊อกสำเร็จ (มีรายการสต๊อกไม่พอ)' if insufficient else '✅ ตัดสต๊อกสำเร็จ',
                'message': (f'ใบจัดส่ง {picking.name} ถูกตัดสต๊อกใน Odoo เรียบร้อย' + insufficient_msg),
                'sticky': True if insufficient else False,
                'type': 'warning' if insufficient else 'success',
                'next': {'type': 'ir.actions.act_window_close'}
            }
        }


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_return_picking = fields.Boolean(
        string='เป็นใบคืน',
        compute='_compute_sc_picking_flags',
        help='ใบนี้เป็นใบคืน (มี move อ้างอิงใบตัดผ่าน origin_returned_move_id)')
    sc_is_rental_picking = fields.Boolean(
        string='ใบขาย/เช่า',
        compute='_compute_sc_picking_flags',
        help='ใบที่มาจากคำสั่งขาย (sale_id) หรือเป็นใบคืน — ใช้ล็อกยกเลิก/ลบเมื่อเสร็จสิ้น')

    @api.depends('move_ids.origin_returned_move_id', 'sale_id')
    def _compute_sc_picking_flags(self):
        for picking in self:
            is_ret = any(m.origin_returned_move_id for m in picking.move_ids)
            picking.is_return_picking = is_ret
            picking.sc_is_rental_picking = bool(picking.sale_id) or is_ret

    def unlink(self):
        # ห้ามลบใบขาย/เช่าที่สถานะเสร็จสิ้นแล้ว (กันพนักงานลบใบตัด/คืนที่ปิดงานแล้ว)
        for picking in self:
            if picking.state == 'done' and picking.sc_is_rental_picking:
                raise UserError(
                    "❌ ใบ '%s' สถานะ 'เสร็จสิ้น' แล้ว ไม่สามารถลบได้" % (picking.name or ''))
        return super().unlink()
