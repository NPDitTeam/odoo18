# -*- coding: utf-8 -*-
"""บรรทัดหนี้ในแต่ละแท็บของ "รวมหนี้ลูกค้า"

ยกมาจาก o14 (อยู่ในไฟล์ debt_summary.py เดียวกัน) แยกไฟล์เพื่อให้อ่านง่ายขึ้น
ทุกแท็บผสม npd.debt.collection.status.mixin เพื่อให้มีคอลัมน์ "สถานะติดตามหนี้"
"""
from odoo import _, api, fields, models


class NpdDebtSummaryInvoiceLine(models.Model):
    _name = 'npd.debt.summary.invoice.line'
    _inherit = ['npd.debt.collection.status.mixin']
    _description = 'รายการใบแจ้งหนี้ค้างชำระ (สรุปหนี้)'
    _order = 'invoice_date_due asc'

    summary_id = fields.Many2one('npd.debt.summary', string='สรุปหนี้', ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='ใบแจ้งหนี้')
    invoice_name = fields.Char(string='เลขที่ใบแจ้งหนี้', related='invoice_id.name', store=True, readonly=True)
    invoice_origin = fields.Char(string='อ้างอิง SO')
    invoice_date = fields.Date(string='วันที่ออกใบแจ้งหนี้')
    invoice_date_due = fields.Date(string='วันกำหนดจ่าย')
    amount_total = fields.Float(string='รวม', digits=(16, 2))
    amount_residual = fields.Float(string='ยอดเงินค้างชำระ', digits=(16, 2))
    payment_state = fields.Char(string='สถานะ (code)')
    payment_state_label = fields.Char(string='สถานะการชำระเงิน')
    days_overdue = fields.Integer(string='จำนวนวันที่เกิน')
    product_info_html = fields.Html(string='รายการสินค้า', sanitize=False)
    payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'จ่ายแล้ว')],
                                      string='สถานะ', compute='_compute_payment_status', store=True)

    @api.depends('amount_residual')
    def _compute_payment_status(self):
        for line in self:
            line.payment_status = 'paid' if (line.amount_residual or 0.0) <= 0.005 else 'unpaid'

    def action_view_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('ใบแจ้งหนี้ค้างชำระ'),
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
                'target': 'current',
            }


class NpdDebtSummaryDepositLine(models.Model):
    """บรรทัดแท็บ 'ใบแจ้งหนี้ค่าประกัน' (โครงเดียวกับแท็บใบแจ้งหนี้ค่าเช่า)"""
    _name = 'npd.debt.summary.deposit.line'
    _inherit = ['npd.debt.collection.status.mixin']
    _description = 'รายการใบแจ้งหนี้ค่าประกัน (สรุปหนี้)'
    _order = 'invoice_date_due asc'

    summary_id = fields.Many2one('npd.debt.summary', string='สรุปหนี้', ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='ใบแจ้งหนี้')
    invoice_name = fields.Char(string='เลขที่ใบแจ้งหนี้', related='invoice_id.name', store=True, readonly=True)
    invoice_origin = fields.Char(string='อ้างอิง SO')
    invoice_date = fields.Date(string='วันที่ออกใบแจ้งหนี้')
    invoice_date_due = fields.Date(string='วันกำหนดจ่าย')
    amount_total = fields.Float(string='รวม', digits=(16, 2))
    amount_residual = fields.Float(string='ยอดเงินค้างชำระ', digits=(16, 2))
    payment_state = fields.Char(string='สถานะ (code)')
    payment_state_label = fields.Char(string='สถานะการชำระเงิน')
    days_overdue = fields.Integer(string='จำนวนวันที่เกิน')
    product_info_html = fields.Html(string='รายการสินค้า', sanitize=False)
    payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'จ่ายแล้ว')],
                                      string='สถานะ', compute='_compute_payment_status', store=True)

    @api.depends('amount_residual')
    def _compute_payment_status(self):
        for line in self:
            line.payment_status = 'paid' if (line.amount_residual or 0.0) <= 0.005 else 'unpaid'

    def action_view_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('ใบแจ้งหนี้ค่าประกัน'),
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
                'target': 'current',
            }


class NpdDebtSummaryRentDiffLine(models.Model):
    """บรรทัดแท็บ 'ค่าเช่าส่วนต่าง'

    โครงเหมือนแท็บใบแจ้งหนี้ค่าเช่าทุกช่อง ต่างกันแค่ประเภทของใบแจ้งหนี้
    ที่ดึงเข้ามา (scrap.reason.code = ค่าเช่าส่วนต่าง)
    """
    _name = 'npd.debt.summary.rentdiff.line'
    _inherit = ['npd.debt.collection.status.mixin']
    _description = 'รายการค่าเช่าส่วนต่าง (สรุปหนี้)'
    _order = 'invoice_date_due asc'

    summary_id = fields.Many2one('npd.debt.summary', string='สรุปหนี้', ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='ใบแจ้งหนี้')
    invoice_name = fields.Char(string='เลขที่ใบแจ้งหนี้', related='invoice_id.name', store=True, readonly=True)
    invoice_origin = fields.Char(string='อ้างอิง SO')
    invoice_date = fields.Date(string='วันที่ออกใบแจ้งหนี้')
    invoice_date_due = fields.Date(string='วันกำหนดจ่าย')
    amount_total = fields.Float(string='รวม', digits=(16, 2))
    amount_residual = fields.Float(string='ยอดเงินค้างชำระ', digits=(16, 2))
    payment_state = fields.Char(string='สถานะ (code)')
    payment_state_label = fields.Char(string='สถานะการชำระเงิน')
    days_overdue = fields.Integer(string='จำนวนวันที่เกิน')
    product_info_html = fields.Html(string='รายการสินค้า', sanitize=False)
    payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'จ่ายแล้ว')],
                                      string='สถานะ', compute='_compute_payment_status', store=True)

    @api.depends('amount_residual')
    def _compute_payment_status(self):
        for line in self:
            line.payment_status = 'paid' if (line.amount_residual or 0.0) <= 0.005 else 'unpaid'

    def action_view_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('ค่าเช่าส่วนต่าง'),
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
                'target': 'current',
            }


class NpdDebtSummaryPenaltyLine(models.Model):
    _name = 'npd.debt.summary.penalty.line'
    _inherit = ['npd.debt.collection.status.mixin']
    _collection_date_field = 'rental_start_date'
    _description = 'รายการค่าปรับหาย (สรุปหนี้)'
    _order = 'invoice_name asc'

    summary_id = fields.Many2one('npd.debt.summary', string='สรุปหนี้', ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='ใบแจ้งหนี้')
    invoice_name = fields.Char(string='เลขเอกสาร', related='invoice_id.name', store=True, readonly=True)
    branch_name = fields.Char(string='สาขา')
    sales_contact_name = fields.Char(string='เซลล์')
    rental_start_date = fields.Date(string='วันที่ออกใบแจ้งหนี้')
    rental_end_date = fields.Date(string='วันกำหนดจ่าย')
    penalty_amount = fields.Float(string='ค่าปรับหาย', digits=(16, 2))
    discount_amount = fields.Float(string='ส่วนลด', digits=(16, 2))
    net_penalty = fields.Float(string='ปรับหายสุทธิ', digits=(16, 2))
    amount_paid = fields.Float(string='รับชำระ', digits=(16, 2))
    amount_residual = fields.Float(string='คงเหลือ', digits=(16, 2))
    penalty_product_line_ids = fields.One2many(
        'npd.debt.summary.penalty.product.line', 'penalty_line_id', string='รายการสินค้า')
    product_info_html = fields.Html(string='รายการสินค้า', sanitize=False)
    payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'จ่ายแล้ว')],
                                      string='สถานะ', compute='_compute_payment_status', store=True)

    @api.depends('amount_residual')
    def _compute_payment_status(self):
        for line in self:
            line.payment_status = 'paid' if (line.amount_residual or 0.0) <= 0.005 else 'unpaid'

    def action_view_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('ใบแจ้งหนี้ค่าปรับหาย'),
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
                'target': 'current',
            }


class NpdDebtSummaryPenaltyProductLine(models.Model):
    _name = 'npd.debt.summary.penalty.product.line'
    _description = 'รายการสินค้าค่าปรับหาย (สรุปหนี้)'

    penalty_line_id = fields.Many2one('npd.debt.summary.penalty.line', string='รายการค่าปรับหาย',
                                      ondelete='cascade')
    product_name = fields.Char(string='สินค้า')
    description = fields.Char(string='รายละเอียด')
    quantity = fields.Float(string='จำนวน', digits=(16, 2))
    price_unit = fields.Float(string='ราคาต่อหน่วย', digits=(16, 2))
    discount = fields.Float(string='ส่วนลด (%)', digits=(16, 2))
    price_subtotal = fields.Float(string='ยอดรวม', digits=(16, 2))


class NpdDebtSummaryDamageLine(models.Model):
    _name = 'npd.debt.summary.damage.line'
    _inherit = ['npd.debt.collection.status.mixin']
    _collection_date_field = 'rental_start_date'
    _description = 'รายการค่าปรับชำรุด (สรุปหนี้)'
    _order = 'invoice_name asc'

    summary_id = fields.Many2one('npd.debt.summary', string='สรุปหนี้', ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='ใบแจ้งหนี้')
    invoice_name = fields.Char(string='เลขเอกสาร', related='invoice_id.name', store=True, readonly=True)
    branch_name = fields.Char(string='สาขา')
    sales_contact_name = fields.Char(string='เซลล์')
    rental_start_date = fields.Date(string='วันที่ออกใบแจ้งหนี้')
    rental_end_date = fields.Date(string='วันกำหนดจ่าย')
    damage_amount = fields.Float(string='ค่าปรับชำรุด', digits=(16, 2))
    discount_amount = fields.Float(string='ส่วนลด', digits=(16, 2))
    net_damage = fields.Float(string='ปรับชำรุดสุทธิ', digits=(16, 2))
    amount_paid = fields.Float(string='รับชำระ', digits=(16, 2))
    amount_residual = fields.Float(string='คงเหลือ', digits=(16, 2))
    product_info_html = fields.Html(string='รายการสินค้า', sanitize=False)
    payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'จ่ายแล้ว')],
                                      string='สถานะ', compute='_compute_payment_status', store=True)

    @api.depends('amount_residual')
    def _compute_payment_status(self):
        for line in self:
            line.payment_status = 'paid' if (line.amount_residual or 0.0) <= 0.005 else 'unpaid'

    def action_view_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('ใบแจ้งหนี้ค่าปรับชำรุด'),
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
                'target': 'current',
            }


class NpdDebtSummaryTransportLine(models.Model):
    """บรรทัดแท็บ 'ค่าขนส่ง'

    ข้อมูลมาจากใบสั่งขาย/ใบแจ้งหนี้ของบริษัทขนส่ง (คนละบริษัท ฐานเดียวกันใน o18)
    เก็บเป็นข้อความล้วนตามของเดิม จึงไม่มีปุ่มเปิดใบแจ้งหนี้
    """
    _name = 'npd.debt.summary.transport.line'
    _inherit = ['npd.debt.collection.status.mixin']
    _description = 'รายการค่าขนส่ง (สรุปหนี้)'
    _order = 'invoice_date_due asc'

    summary_id = fields.Many2one('npd.debt.summary', string='สรุปหนี้', ondelete='cascade')
    source_so = fields.Char(string='เลขเอกสาร SO')
    transport_so = fields.Char(string='ใบสั่งขายฝั่งขนส่ง')
    source_type = fields.Char(string='ที่มา',
                              help='ใบแจ้งหนี้ / ใบแจ้งหนี้ฉบับร่าง / ยังไม่ออกใบแจ้งหนี้ '
                                   '(สองแบบหลังใช้ยอดค่าขนส่งบนใบสั่งขายฝั่งขนส่ง)')
    invoice_name = fields.Char(string='เลขที่ใบแจ้งหนี้')
    invoice_date = fields.Date(string='วันที่ออกใบแจ้งหนี้')
    invoice_date_due = fields.Date(string='วันกำหนดจ่าย')
    amount_total = fields.Float(string='รวม', digits=(16, 2))
    amount_residual = fields.Float(string='ยอดเงินค้างชำระ', digits=(16, 2))
    payment_state = fields.Char(string='สถานะ (code)')
    days_overdue = fields.Integer(string='จำนวนวันที่เกิน')
    payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'จ่ายแล้ว')],
                                      string='สถานะ', compute='_compute_payment_status', store=True)

    @api.depends('amount_residual')
    def _compute_payment_status(self):
        for line in self:
            line.payment_status = 'paid' if (line.amount_residual or 0.0) <= 0.005 else 'unpaid'


class NpdDebtSummaryTaxLine(models.Model):
    _name = 'npd.debt.summary.tax.line'
    _inherit = ['npd.debt.collection.status.mixin']
    _description = 'รายการค่าหัก ณ ที่จ่าย (สรุปหนี้)'
    _order = 'invoice_name asc'

    summary_id = fields.Many2one('npd.debt.summary', string='สรุปหนี้', ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='ใบแจ้งหนี้')
    invoice_name = fields.Char(string='เลขที่ใบแจ้งหนี้', related='invoice_id.name', store=True, readonly=True)
    invoice_origin = fields.Char(string='อ้างอิง SO')
    invoice_date = fields.Date(string='วันที่ออกใบแจ้งหนี้')
    invoice_date_due = fields.Date(string='วันกำหนดจ่าย')
    amount_total = fields.Float(string='ยอดรวมใบแจ้งหนี้', digits=(16, 2))
    payment_id = fields.Many2one('account.payment', string='รับชำระ')
    payment_name = fields.Char(string='เลขที่รับชำระ')
    tax_amount = fields.Float(string='ยอด Tax', digits=(16, 2))
    product_info_html = fields.Html(string='รายการสินค้า', sanitize=False)
    payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'จ่ายแล้ว')],
                                      string='สถานะ', compute='_compute_payment_status', store=True)

    @api.depends('invoice_id.amount_residual')
    def _compute_payment_status(self):
        for line in self:
            residual = line.invoice_id.amount_residual if line.invoice_id else 0.0
            line.payment_status = 'paid' if (residual or 0.0) <= 0.005 else 'unpaid'

    def action_view_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('ใบแจ้งหนี้'),
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
