from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ธง: มี 'การตัดสต๊อก' ที่ยังไม่ได้คืน (ใช้สลับปุ่ม ตัดสต๊อก <-> คืนสต๊อก)
    #   True  = ตัดแล้วยังไม่ได้คืน  -> แสดงปุ่มคืน / ซ่อนปุ่มตัด
    #   False = ยังไม่ตัด หรือคืนครบแล้ว -> แสดงปุ่มตัด / ซ่อนปุ่มคืน
    #           (ถ้าตัดสต๊อกใหม่อีกรอบ ธงจะกลับเป็น True และปุ่มคืนแสดงอีกครั้ง)
    sc_has_cut = fields.Boolean(
        string='มีการตัดที่ยังไม่ได้คืน', compute='_compute_sc_stock_flags')

    # Odoo 18: stock.picking.move_lines ถูกเปลี่ยนชื่อเป็น move_ids ตั้งแต่ Odoo 16
    @api.depends('state', 'picking_ids.state', 'picking_ids.picking_type_id.code',
                 'picking_ids.move_ids.origin_returned_move_id',
                 'picking_ids.move_ids.state')
    def _compute_sc_stock_flags(self):
        for order in self:
            done_pickings = order.picking_ids.filtered(lambda p: p.state == 'done')
            # id ของ move 'การตัด' ที่ถูกคืนแล้ว (มีใบคืน done อ้างอิงถึงผ่าน origin_returned_move_id)
            # ใช้ origin_returned_move_id แทนการดู origin เพราะ origin ('Return of..') ถูกแปลภาษาได้
            returned_src_ids = set()
            for p in done_pickings:
                for m in p.move_ids:
                    if m.origin_returned_move_id:
                        returned_src_ids.add(m.origin_returned_move_id.id)
            # หา 'ใบตัดสต๊อก' (ส่งออก done, ไม่ใช่ใบคืน) ที่ยังไม่ถูกคืน 'ครบ'
            # รองรับการตัดหลายรอบ: ทุกใบตัดต้องถูกคืนครบทุก move จึงจะไม่บล็อก
            unreturned_cut = False
            for p in done_pickings:
                if p.picking_type_id.code != 'outgoing':
                    continue
                if any(m.origin_returned_move_id for m in p.move_ids):
                    continue  # ใบนี้เป็นใบคืน ไม่ใช่ใบตัด
                # move ที่ตัดจริง (done) 'ทุกตัว' ต้องถูกคืน (subset) ไม่ใช่แค่บางตัว
                cut_move_ids = set(p.move_ids.filtered(lambda m: m.state == 'done').ids)
                if cut_move_ids and not cut_move_ids.issubset(returned_src_ids):
                    unreturned_cut = True
                    break
            order.sc_has_cut = unreturned_cut

    def action_auto_validate_delivery(self):
        self.ensure_one()
        lines = []
        for picking in self.picking_ids.filtered(lambda p: p.state in ['draft', 'waiting', 'confirmed']):
            for move in picking.move_ids_without_package:
                sol = self.order_line.filtered(lambda l: l.product_id.id == move.product_id.id)
                if sol and sol.pfb_quantity > 0:
                    lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'quantity': sol.pfb_quantity,
                        'location_name': picking.location_id.display_name,
                    }))
        # เปิด Wizard และส่งข้อมูลลงไปเลย
        return {
            'name': 'ยืนยันตัดสต๊อก',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.cut.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_mode': 'cut',
                'default_confirm_line_ids': lines,
            }
        }

    def action_auto_return_delivery(self):
        """เปิด Wizard คืนสต๊อก (โหมด return) — ระบบจะดึงสินค้าที่ตัดจริงมาแสดง"""
        self.ensure_one()
        return {
            'name': 'ยืนยันคืนสต๊อก',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.cut.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_mode': 'return',
            }
        }
