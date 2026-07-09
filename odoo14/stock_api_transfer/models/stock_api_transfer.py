# -*- coding: utf-8 -*-
# ======================================================================
# Stock (Internal) Transfer — Odoo 18
# เดิม (Odoo 14): โยกสต๊อกข้ามบริษัทที่อยู่ "คนละ DB" ผ่าน HTTP API (npderp.com)
# เวอร์ชันนี้: หลายบริษัทอยู่ใน "DB เดียวกัน" → โอนภายในตรงๆ โดยปรับ stock.quant
#             (ตัดคลังต้นทาง + เติมคลังปลายทาง) ไม่ต้องเรียก API ภายนอกอีกต่อไป
# ======================================================================
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class StockAPITransfer(models.Model):
    _name = "stock.api.transfer"
    _description = "Stock Transfer (Internal, multi-company)"
    _order = "create_date desc"

    name = fields.Char(string="เลขอ้างอิง", required=True, copy=False, readonly=True, default="New")
    transfer_date = fields.Date(string="วันโยกสินค้า", default=lambda self: date.today(), required=True)
    note = fields.Text(string="หมายเหตุ")

    # ต้นทาง/ปลายทาง = บริษัท + คลังจริงใน DB เดียวกัน (แทน database_selection เดิมที่เป็น DB แยก)
    source_company_id = fields.Many2one("res.company", string="บริษัทต้นทาง", required=True)
    source_location_id = fields.Many2one("stock.location", string="คลังต้นทาง")
    dest_company_id = fields.Many2one(
        "res.company", string="บริษัทปลายทาง", required=True,
        default=lambda self: self.env.company)
    # ปลายทาง — คงชื่อฟิลด์เดิม location_id ไว้ (line.destination_location_id related มาที่ฟิลด์นี้)
    location_id = fields.Many2one("stock.location", string="คลังปลายทาง")

    product_ids = fields.Many2many("product.product", string="สินค้า")
    line_ids = fields.One2many("stock.api.transfer.line", "transfer_id", string="รายการสินค้า", copy=True)

    state = fields.Selection([
        ("draft", "ร่าง"),
        ("waiting_approval", "รออนุมัติ"),
        ("approved", "อนุมัติแล้ว"),
        ("confirmed", "ยืนยันแล้ว"),
    ], default="draft", string="สถานะ")

    # ------------------ ข้อมูลการอนุมัติ (คงเดิม) ------------------
    approval_id = fields.Many2one("stock.transfer.approval", string="การอนุมัติ", readonly=True, copy=False)
    approval_reason = fields.Text(related="approval_id.reason", string="เหตุผลการโยก", readonly=True)
    approval_reject_note = fields.Text(related="approval_id.reject_note", string="หมายเหตุตีกลับ", readonly=True)
    approver_id = fields.Many2one(related="approval_id.approver_id", string="ผู้อนุมัติ", readonly=True, store=True)
    approval_state = fields.Selection(related="approval_id.state", string="สถานะอนุมัติ", readonly=True)
    approval_attachment_ids = fields.Many2many(related="approval_id.attachment_ids", string="ไฟล์แนบ", readonly=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_source_qty(self, product, location):
        """คงเหลือจริงของสินค้าที่คลัง (อ่านจาก stock.quant)"""
        if not product or not location:
            return 0.0
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ])
        return sum(quants.mapped('quantity'))

    @api.onchange('source_company_id')
    def _onchange_source_company(self):
        # เปลี่ยนบริษัทต้นทาง → ล้างคลัง/สินค้า/รายการ กันข้อมูลค้างข้ามบริษัท
        self.source_location_id = False
        self.product_ids = [(5, 0, 0)]
        self.line_ids = [(5, 0, 0)]

    @api.onchange('source_location_id', 'product_ids', 'location_id')
    def _onchange_build_lines(self):
        """สร้างรายการจากสินค้าที่เลือก + อ่านคงเหลือจริงที่คลังต้นทาง"""
        self.line_ids = [(5, 0, 0)]
        if not self.source_location_id or not self.product_ids:
            return
        vals = []
        for product in self.product_ids:
            qty = self._get_source_qty(product, self.source_location_id)
            vals.append((0, 0, {
                'product_id': product.id,
                'source_location_id': self.source_location_id.id,
                'available_qty': qty,
                'request_qty': 0.0,
                'status': 'รอดำเนินการ',
            }))
        self.line_ids = vals

    # ------------------------------------------------------------------
    # Approval workflow (คงเดิม — ไม่เกี่ยวกับสถาปัตยกรรม DB)
    # ------------------------------------------------------------------
    def action_send_approval(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("ไม่สามารถส่งขออนุมัติได้ เนื่องจากไม่มีรายการสินค้า\n"
                            "กรุณาเลือกคลังต้นทางและสินค้าให้ถูกต้อง")
        if not any(line.request_qty > 0 for line in self.line_ids):
            raise UserError("กรุณาระบุจำนวนขอตัดอย่างน้อย 1 รายการ")
        if not self.location_id:
            raise UserError("กรุณาเลือกคลังปลายทาง")
        approver_group = self.env.ref('stock_api_transfer.group_stock_transfer_approver')
        approver_user_ids = self.env['res.users'].search([
            ('groups_id', 'in', [approver_group.id])
        ]).ids
        return {
            'name': 'ส่งขออนุมัติการโยกสินค้า',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.transfer.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transfer_id': self.id,
                'approver_user_ids': approver_user_ids,
            },
        }

    def action_approve(self):
        self.ensure_one()
        if self.approval_id:
            self.approval_id.action_approve()

    def action_open_reject_wizard(self):
        self.ensure_one()
        return {
            'name': 'ตีกลับการโยกสินค้า',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.transfer.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_transfer_id': self.id},
        }

    def unlink(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError("ไม่สามารถลบเอกสารที่ยืนยันแล้วได้")
        return super().unlink()

    # ------------------------------------------------------------------
    # Confirm / Cancel — โอนสต๊อกภายใน DB ด้วยการปรับ quant
    # ------------------------------------------------------------------
    def _move_quant(self, product, location, qty):
        """ปรับสต๊อกที่ location (qty > 0 = เติม, qty < 0 = ตัด) ผ่าน API มาตรฐานของ stock.quant
        ใช้ with_company ตามบริษัทของคลัง เพื่อให้ quant ผูกบริษัทถูกต้องเวลาโอนข้ามบริษัท"""
        if not product or not location or not qty:
            return
        company = location.company_id or self.env.company
        self.env['stock.quant'].with_company(company).sudo()._update_available_quantity(
            product, location, qty)

    def action_confirm(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError("ต้องได้รับการอนุมัติก่อนจึงจะยืนยันการโอนได้")
        if not self.source_location_id or not self.location_id:
            raise UserError("กรุณาเลือกคลังต้นทางและคลังปลายทางให้ครบ")

        lines = self.line_ids.filtered(lambda l: l.request_qty > 0)
        if not lines:
            raise UserError("ไม่มีรายการที่ระบุจำนวนขอตัด")

        # ตรวจสต๊อกต้นทางให้พอ (อ่านค่าจริง ณ ตอนยืนยัน)
        shortages = []
        for line in lines:
            avail = self._get_source_qty(line.product_id, self.source_location_id)
            if line.request_qty > avail:
                shortages.append(
                    f"• {line.product_id.display_name} — ขอ {line.request_qty:.2f} / คงเหลือ {avail:.2f}")
        if shortages:
            raise UserError("สต๊อกคลังต้นทางไม่พอสำหรับ:\n" + "\n".join(shortages))

        if self.name == 'New':
            seq_date = fields.Date.context_today(self).strftime('%Y-%m-%d')
            self.name = self.env['ir.sequence'].with_context(
                ir_sequence_date=seq_date
            ).next_by_code('stock.api.transfer') or 'New'

        # ปรับ quant: ตัดคลังต้นทาง + เติมคลังปลายทาง
        for line in lines:
            self._move_quant(line.product_id, self.source_location_id, -line.request_qty)
            self._move_quant(line.product_id, self.location_id, line.request_qty)
            line.write({
                'status': 'สำเร็จ',
                'available_qty': self._get_source_qty(line.product_id, self.source_location_id),
            })
            _logger.info("📦 โอน %s: %s -%.2f → %s +%.2f",
                         line.product_id.display_name,
                         self.source_location_id.display_name, line.request_qty,
                         self.location_id.display_name, line.request_qty)

        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.ensure_one()
        if not self.env.user.has_group('stock_api_transfer.group_stock_transfer_approver'):
            raise UserError("เฉพาะผู้อนุมัติเท่านั้นที่สามารถยกเลิกได้")
        if self.state != 'confirmed':
            return

        # ย้อนสต๊อก: เติมกลับคลังต้นทาง + ตัดคลังปลายทาง
        for line in self.line_ids.filtered(lambda l: l.request_qty > 0):
            self._move_quant(line.product_id, self.location_id, -line.request_qty)
            self._move_quant(line.product_id, self.source_location_id, line.request_qty)
            line.write({
                'status': 'รอดำเนินการ',
                'available_qty': self._get_source_qty(line.product_id, self.source_location_id),
            })
            _logger.info("🔄 ยกเลิกโอน %s: คืน %s +%.2f / ตัด %s -%.2f",
                         line.product_id.display_name,
                         self.source_location_id.display_name, line.request_qty,
                         self.location_id.display_name, line.request_qty)

        self.write({'state': 'draft'})


class StockAPITransferLine(models.Model):
    _name = "stock.api.transfer.line"
    _description = "รายการสินค้าโยกสต๊อก"

    transfer_id = fields.Many2one("stock.api.transfer", string="เอกสารอ้างอิง",
                                  required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="สินค้า", required=True)
    default_code = fields.Char(related="product_id.default_code", string="รหัสสินค้า", readonly=True)
    source_location_id = fields.Many2one("stock.location", string="คลังต้นทาง", required=True)
    destination_location_id = fields.Many2one(
        "stock.location", string="คลังปลายทาง",
        related="transfer_id.location_id", store=True, readonly=True, ondelete='set null')
    available_qty = fields.Float(string="คงเหลือ")
    request_qty = fields.Float(string="จำนวนขอตัด")
    status = fields.Char(string="สถานะ", readonly=True, default="รอดำเนินการ")
