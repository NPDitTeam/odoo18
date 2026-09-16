# -*- coding: utf-8 -*-
"""รวมหนี้ลูกค้า -- พอร์ตจาก Odoo 14 (npd_debt_summary 14.0.1.13.0)

ต่างจากฝั่ง o14 ตรงที่ o18 เป็น "ฐานข้อมูลเดียว 5 บริษัท" จึงปรับ 3 จุดหลัก
  1. เลขที่เอกสาร/บัญชีรับโอน แยกตาม "บริษัท" แทน "ชื่อฐานข้อมูล"
  2. 1 ลูกค้ามีได้ 1 รายการต่อบริษัท (o14 มีได้ใบเดียวเพราะแต่ละบริษัทคนละฐาน)
  3. ค่าขนส่งอ่านในฐานเดียวกัน ผ่าน sale.order.source_company_id + so_number
     (โมดูล sale_api_rent) แทนการเปิด cursor ข้ามฐานข้อมูลแบบ o14
"""
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models

try:
    from bahttext import bahttext
except ImportError:  # pragma: no cover - เครื่องที่ยังไม่ได้ติดตั้ง
    bahttext = None

_logger = logging.getLogger(__name__)

# เริ่มดึงข้อมูลหนี้ตั้งแต่ปี 2026 เป็นต้นไป (ข้อมูลปีต่ำกว่า 2026 จะไม่ถูกดึง/ถูกล้างออก)
DEBT_START_DATE = date(2026, 1, 1)
DEBT_START_STR = '2026-01-01'

# ----------------------------------------------------------------------------
# ประเภทเอกสาร (scrap.reason.code -> account.move.reason_code_id ของ
# npd_commission_fields) ใช้แยกว่าใบแจ้งหนี้ใบไหนไปอยู่แท็บอะไร
# ใบที่ไม่ได้ระบุประเภทถือเป็นค่าเช่า
# ----------------------------------------------------------------------------
REASON_RENT = 'ใบแจ้งหนี้ค่าเช่า'
REASON_RENT_DIFF = 'ค่าเช่าส่วนต่าง'
REASON_LOST = 'สินค้าหาย'
REASON_DAMAGE = 'สินค้าชำรุด'

# ----------------------------------------------------------------------------
# เลขที่เอกสาร -- คำนำหน้าแยกตามบริษัท
# รูปแบบ: <คำนำหน้า> <เลขรัน 4 หลัก>/<ปี พ.ศ.>  เช่น NPS.N 0001/2569
# จับคู่ด้วย "คำในชื่อบริษัท" ไม่ผูกกับ id เผื่อฐานทดสอบที่ id ไม่ตรงกัน
# ----------------------------------------------------------------------------
COMPANY_DOC_PREFIX = (
    ('เอส กรุ๊ป', 'NPD.N'),
    ('อินเตอร์เทรดดิ้ง', 'NPI.N'),
    ('สตีลเทค', 'NPS.N'),
    ('กรุงเทพ', 'NBK.N'),
    ('โลจิสติกส์', 'NPL.N'),
)
DEFAULT_DOC_PREFIX = 'NPD.N'
# ตั้ง System Parameter ตัวนี้เพื่อบังคับคำนำหน้าเอง (สำคัญกว่าตารางข้างบน)
# ใส่ต่อบริษัทได้ด้วย npd_debt_summary.doc_prefix.<company_id>
DOC_PREFIX_PARAM = 'npd_debt_summary.doc_prefix'


class NpdDebtSummary(models.Model):
    _name = 'npd.debt.summary'
    _description = 'รวมหนี้ลูกค้า'
    _order = 'partner_name asc'

    name = fields.Char(string='เลขที่เอกสาร', default='New', readonly=True, copy=False, index=True,
                       help='เลขที่เอกสารสรุปหนี้รวมของลูกค้า')

    @api.depends('name', 'partner_name')
    def _compute_display_name(self):
        for rec in self:
            if rec.partner_name and rec.name and rec.name != 'New':
                rec.display_name = '%s - %s' % (rec.name, rec.partner_name)
            else:
                rec.display_name = rec.name or rec.partner_name or 'New'

    # เก็บไว้เพื่อความเข้ากันได้กับรายงาน (ไม่แสดงในฟอร์ม)
    note = fields.Text(string='หมายเหตุ')

    customer_id = fields.Many2one('res.partner', string='ลูกค้า', required=True, ondelete='cascade',
                                  index=True, help='ลูกค้า (Commercial Partner)')
    partner_name = fields.Char(string='ชื่อลูกค้า', store=True)
    partner_phone = fields.Char(string='เบอร์โทรศัพท์')
    partner_mobile = fields.Char(string='มือถือ')
    partner_email = fields.Char(string='อีเมล')
    partner_vat = fields.Char(string='เลขที่ผู้เสียภาษี')
    partner_street = fields.Char(string='ที่อยู่')
    partner_street2 = fields.Char(string='ที่อยู่ 2')
    partner_city = fields.Char(string='เมือง')
    partner_state_id = fields.Many2one('res.country.state', string='จังหวัด')
    partner_zip = fields.Char(string='รหัสไปรษณีย์')

    company_id = fields.Many2one('res.company', string='บริษัท', required=True, index=True,
                                 default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one('res.currency', string='สกุลเงิน',
                                  related='company_id.currency_id', readonly=True)

    last_update = fields.Datetime(string='อัพเดทล่าสุด', readonly=True)

    # o18 ฐานเดียวหลายบริษัท ลูกค้ารายเดียวกันเป็นหนี้ได้หลายบริษัท
    # จึงคุมให้ไม่ซ้ำ "ต่อบริษัท" (ของ o14 คุมแค่ลูกค้าเพราะแยกฐานอยู่แล้ว)
    _sql_constraints = [
        ('customer_company_uniq', 'unique(customer_id, company_id)',
         'ลูกค้าแต่ละรายต้องมีได้เพียงรายการเดียวต่อบริษัท'),
    ]

    # ===== ใบแจ้งหนี้ค้างชำระ =====
    customer_invoice_line_ids = fields.One2many('npd.debt.summary.invoice.line',
                                                'summary_id', string='ใบแจ้งหนี้ค้างชำระทั้งหมด')
    customer_amount_residual = fields.Monetary(string='ยอดค้างชำระใบแจ้งหนี้',
                                               currency_field='currency_id', compute='_compute_residuals', store=True)

    # ===== ใบแจ้งหนี้ค่าประกัน =====
    customer_deposit_line_ids = fields.One2many('npd.debt.summary.deposit.line',
                                                'summary_id', string='ใบแจ้งหนี้ค่าประกันทั้งหมด')
    customer_deposit_residual = fields.Monetary(string='ค้างชำระค่าประกัน',
                                                currency_field='currency_id', compute='_compute_residuals', store=True)

    # ===== ค่าเช่าส่วนต่าง =====
    customer_rentdiff_line_ids = fields.One2many('npd.debt.summary.rentdiff.line',
                                                 'summary_id', string='ค่าเช่าส่วนต่างทั้งหมด')
    customer_rentdiff_residual = fields.Monetary(string='ค้างชำระค่าเช่าส่วนต่าง',
                                                 currency_field='currency_id', compute='_compute_residuals', store=True)

    # ===== ค่าปรับหาย =====
    customer_penalty_line_ids = fields.One2many('npd.debt.summary.penalty.line',
                                                'summary_id', string='ค่าปรับหายทั้งหมด')
    customer_penalty_residual = fields.Monetary(string='ค้างชำระค่าปรับหาย',
                                                currency_field='currency_id', compute='_compute_residuals', store=True)

    # ===== ค่าปรับชำรุด =====
    customer_damage_line_ids = fields.One2many('npd.debt.summary.damage.line',
                                               'summary_id', string='ค่าปรับชำรุดทั้งหมด')
    customer_damage_residual = fields.Monetary(string='ค้างชำระค่าปรับชำรุด',
                                               currency_field='currency_id', compute='_compute_residuals', store=True)

    # ===== ค่าขนส่ง (บริษัทขนส่งอยู่ในฐานเดียวกัน คนละบริษัท) =====
    customer_transport_line_ids = fields.One2many('npd.debt.summary.transport.line',
                                                  'summary_id', string='ค่าขนส่งทั้งหมด')
    customer_transport_residual = fields.Monetary(string='ค้างชำระค่าขนส่ง',
                                                  currency_field='currency_id', compute='_compute_residuals', store=True)

    # ===== ค่าหัก ณ ที่จ่าย =====
    customer_tax_line_ids = fields.One2many('npd.debt.summary.tax.line',
                                            'summary_id', string='ค่าหัก ณ ที่จ่ายทั้งหมด')
    customer_tax_residual = fields.Monetary(string='ค้างชำระค่าหัก ณ ที่จ่าย',
                                            currency_field='currency_id', compute='_compute_residuals', store=True)

    @api.depends('customer_invoice_line_ids.amount_residual', 'customer_invoice_line_ids.payment_status',
                 'customer_deposit_line_ids.amount_residual', 'customer_deposit_line_ids.payment_status',
                 'customer_rentdiff_line_ids.amount_residual', 'customer_rentdiff_line_ids.payment_status',
                 'customer_penalty_line_ids.amount_residual', 'customer_penalty_line_ids.payment_status',
                 'customer_damage_line_ids.amount_residual', 'customer_damage_line_ids.payment_status',
                 'customer_transport_line_ids.amount_residual', 'customer_transport_line_ids.payment_status',
                 'customer_tax_line_ids.tax_amount', 'customer_tax_line_ids.payment_status')
    def _compute_residuals(self):
        for rec in self:
            rec.customer_amount_residual = sum(
                l.amount_residual for l in rec.customer_invoice_line_ids if l.payment_status == 'unpaid')
            rec.customer_deposit_residual = sum(
                l.amount_residual for l in rec.customer_deposit_line_ids if l.payment_status == 'unpaid')
            rec.customer_rentdiff_residual = sum(
                l.amount_residual for l in rec.customer_rentdiff_line_ids if l.payment_status == 'unpaid')
            rec.customer_penalty_residual = sum(
                l.amount_residual for l in rec.customer_penalty_line_ids if l.payment_status == 'unpaid')
            rec.customer_damage_residual = sum(
                l.amount_residual for l in rec.customer_damage_line_ids if l.payment_status == 'unpaid')
            rec.customer_transport_residual = sum(
                l.amount_residual for l in rec.customer_transport_line_ids if l.payment_status == 'unpaid')
            rec.customer_tax_residual = sum(
                l.tax_amount for l in rec.customer_tax_line_ids if l.payment_status == 'unpaid')

    grand_total = fields.Monetary(string='รวมหนี้ทั้งสิ้น', currency_field='currency_id',
                                  compute='_compute_grand_total', store=True)

    payment_status = fields.Selection([
        ('unpaid', 'ค้างชำระ'),
        ('paid', 'ชำระแล้ว'),
    ], string='สถานะรวม', compute='_compute_payment_status', store=True, default='unpaid')

    # สถานะแยกตามแต่ละแท็บ
    invoice_payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'ชำระแล้ว')],
                                              string='สถานะใบแจ้งหนี้', compute='_compute_payment_status', store=True)
    deposit_payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'ชำระแล้ว')],
                                              string='สถานะค่าประกัน', compute='_compute_payment_status', store=True)
    rentdiff_payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'ชำระแล้ว')],
                                               string='สถานะค่าเช่าส่วนต่าง', compute='_compute_payment_status', store=True)
    lost_payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'ชำระแล้ว')],
                                           string='สถานะค่าปรับหาย', compute='_compute_payment_status', store=True)
    damage_payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'ชำระแล้ว')],
                                             string='สถานะค่าปรับชำรุด', compute='_compute_payment_status', store=True)
    transport_payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'ชำระแล้ว')],
                                                string='สถานะค่าขนส่ง', compute='_compute_payment_status', store=True)
    tax_payment_status = fields.Selection([('unpaid', 'ค้างชำระ'), ('paid', 'ชำระแล้ว')],
                                          string='สถานะค่าหัก ณ ที่จ่าย', compute='_compute_payment_status', store=True)

    @api.depends('customer_invoice_line_ids.payment_status',
                 'customer_deposit_line_ids.payment_status',
                 'customer_rentdiff_line_ids.payment_status',
                 'customer_penalty_line_ids.payment_status',
                 'customer_damage_line_ids.payment_status',
                 'customer_transport_line_ids.payment_status',
                 'customer_tax_line_ids.payment_status')
    def _compute_payment_status(self):
        for rec in self:
            inv_unpaid = any(l.payment_status == 'unpaid' for l in rec.customer_invoice_line_ids)
            dep_unpaid = any(l.payment_status == 'unpaid' for l in rec.customer_deposit_line_ids)
            diff_unpaid = any(l.payment_status == 'unpaid' for l in rec.customer_rentdiff_line_ids)
            pen_unpaid = any(l.payment_status == 'unpaid' for l in rec.customer_penalty_line_ids)
            dmg_unpaid = any(l.payment_status == 'unpaid' for l in rec.customer_damage_line_ids)
            trn_unpaid = any(l.payment_status == 'unpaid' for l in rec.customer_transport_line_ids)
            tax_unpaid = any(l.payment_status == 'unpaid' for l in rec.customer_tax_line_ids)
            rec.invoice_payment_status = 'unpaid' if inv_unpaid else 'paid'
            rec.deposit_payment_status = 'unpaid' if dep_unpaid else 'paid'
            rec.rentdiff_payment_status = 'unpaid' if diff_unpaid else 'paid'
            rec.lost_payment_status = 'unpaid' if pen_unpaid else 'paid'
            rec.damage_payment_status = 'unpaid' if dmg_unpaid else 'paid'
            rec.transport_payment_status = 'unpaid' if trn_unpaid else 'paid'
            rec.tax_payment_status = 'unpaid' if tax_unpaid else 'paid'
            rec.payment_status = 'unpaid' if (inv_unpaid or dep_unpaid or diff_unpaid
                                              or pen_unpaid or dmg_unpaid or trn_unpaid
                                              or tax_unpaid) else 'paid'

    # ===== วันที่/วันครบกำหนดชำระ ของแต่ละประเภท (คำนวณจากรายการล่าสุด + 14 วัน) =====
    invoice_report_date = fields.Date(string='วันที่ (ใบแจ้งหนี้)', compute='_compute_report_dates', store=True)
    invoice_due_date = fields.Date(string='วันที่กำหนดชำระ (ใบแจ้งหนี้)', compute='_compute_report_dates', store=True)
    deposit_report_date = fields.Date(string='วันที่ (ค่าประกัน)', compute='_compute_report_dates', store=True)
    deposit_due_date = fields.Date(string='วันที่กำหนดชำระ (ค่าประกัน)', compute='_compute_report_dates', store=True)
    rentdiff_report_date = fields.Date(string='วันที่ (ค่าเช่าส่วนต่าง)', compute='_compute_report_dates', store=True)
    rentdiff_due_date = fields.Date(string='วันที่กำหนดชำระ (ค่าเช่าส่วนต่าง)', compute='_compute_report_dates', store=True)
    lost_report_date = fields.Date(string='วันที่ (ค่าปรับหาย)', compute='_compute_report_dates', store=True)
    lost_due_date = fields.Date(string='วันที่กำหนดชำระ (ค่าปรับหาย)', compute='_compute_report_dates', store=True)
    damage_report_date = fields.Date(string='วันที่ (ค่าปรับชำรุด)', compute='_compute_report_dates', store=True)
    damage_due_date = fields.Date(string='วันที่กำหนดชำระ (ค่าปรับชำรุด)', compute='_compute_report_dates', store=True)
    transport_report_date = fields.Date(string='วันที่ (ค่าขนส่ง)', compute='_compute_report_dates', store=True)
    transport_due_date = fields.Date(string='วันที่กำหนดชำระ (ค่าขนส่ง)', compute='_compute_report_dates', store=True)
    tax_report_date = fields.Date(string='วันที่ (ค่าหัก ณ ที่จ่าย)', compute='_compute_report_dates', store=True)
    tax_due_date = fields.Date(string='วันที่กำหนดชำระ (ค่าหัก ณ ที่จ่าย)', compute='_compute_report_dates', store=True)

    @api.depends('customer_transport_line_ids.invoice_date',
                 'customer_deposit_line_ids.invoice_date',
                 'customer_rentdiff_line_ids.invoice_date',
                 'customer_invoice_line_ids.invoice_date',
                 'customer_penalty_line_ids.rental_start_date',
                 'customer_damage_line_ids.rental_start_date',
                 'customer_tax_line_ids.invoice_date')
    def _compute_report_dates(self):
        for rec in self:
            inv_dates = [l.invoice_date for l in rec.customer_invoice_line_ids if l.invoice_date]
            rec.invoice_report_date = max(inv_dates) if inv_dates else False
            rec.invoice_due_date = (rec.invoice_report_date + timedelta(days=14)) if rec.invoice_report_date else False

            dep_dates = [l.invoice_date for l in rec.customer_deposit_line_ids if l.invoice_date]
            rec.deposit_report_date = max(dep_dates) if dep_dates else False
            rec.deposit_due_date = ((rec.deposit_report_date + timedelta(days=14))
                                    if rec.deposit_report_date else False)

            diff_dates = [l.invoice_date for l in rec.customer_rentdiff_line_ids if l.invoice_date]
            rec.rentdiff_report_date = max(diff_dates) if diff_dates else False
            rec.rentdiff_due_date = ((rec.rentdiff_report_date + timedelta(days=14))
                                     if rec.rentdiff_report_date else False)

            pen_dates = [l.rental_start_date for l in rec.customer_penalty_line_ids if l.rental_start_date]
            rec.lost_report_date = max(pen_dates) if pen_dates else False
            rec.lost_due_date = (rec.lost_report_date + timedelta(days=14)) if rec.lost_report_date else False

            dmg_dates = [l.rental_start_date for l in rec.customer_damage_line_ids if l.rental_start_date]
            rec.damage_report_date = max(dmg_dates) if dmg_dates else False
            rec.damage_due_date = (rec.damage_report_date + timedelta(days=14)) if rec.damage_report_date else False

            trn_dates = [l.invoice_date for l in rec.customer_transport_line_ids if l.invoice_date]
            rec.transport_report_date = max(trn_dates) if trn_dates else False
            rec.transport_due_date = ((rec.transport_report_date + timedelta(days=14))
                                      if rec.transport_report_date else False)

            tax_dates = [l.invoice_date for l in rec.customer_tax_line_ids if l.invoice_date]
            rec.tax_report_date = max(tax_dates) if tax_dates else False
            rec.tax_due_date = (rec.tax_report_date + timedelta(days=14)) if rec.tax_report_date else False

    @api.depends('customer_amount_residual', 'customer_deposit_residual',
                 'customer_rentdiff_residual', 'customer_penalty_residual',
                 'customer_damage_residual', 'customer_transport_residual',
                 'customer_tax_residual')
    def _compute_grand_total(self):
        for rec in self:
            rec.grand_total = (rec.customer_amount_residual + rec.customer_deposit_residual
                               + rec.customer_rentdiff_residual + rec.customer_penalty_residual
                               + rec.customer_damage_residual + rec.customer_transport_residual
                               + rec.customer_tax_residual)

    # ===== เลขที่เอกสาร =====
    def _debt_doc_prefix(self, company=None):
        """คำนำหน้าเลขที่เอกสารของบริษัทที่ออกเอกสาร

        ลำดับการหา: System Parameter ต่อบริษัท -> System Parameter รวม ->
        คำในชื่อบริษัท -> ค่าเริ่มต้น
        """
        company = company or (self and self[:1].company_id) or self.env.company
        param = self.env['ir.config_parameter'].sudo()
        value = param.get_param('%s.%s' % (DOC_PREFIX_PARAM, company.id)) or param.get_param(DOC_PREFIX_PARAM)
        if value:
            return value.strip()
        name = company.name or ''
        for keyword, prefix in COMPANY_DOC_PREFIX:
            if keyword in name:
                return prefix
        _logger.warning('npd_debt_summary: ไม่รู้จักบริษัท %s ใช้คำนำหน้า %s ไปก่อน '
                        '(ตั้ง System Parameter %s.%s เพื่อกำหนดเอง)',
                        name, DEFAULT_DOC_PREFIX, DOC_PREFIX_PARAM, company.id)
        return DEFAULT_DOC_PREFIX

    def _debt_sequence(self, company):
        """ir.sequence ของบริษัทนั้น (สร้างให้ถ้ายังไม่มี)

        o14 ใช้ sequence ตัวเดียวได้เพราะแต่ละบริษัทอยู่คนละฐานข้อมูล
        o18 ฐานเดียว ถ้าใช้ตัวเดียวกันเลขจะเดินสลับกันข้ามบริษัท
        """
        Sequence = self.env['ir.sequence'].sudo()
        seq = Sequence.search([('code', '=', 'npd.debt.summary'),
                               ('company_id', '=', company.id)], limit=1)
        if seq:
            return seq
        return Sequence.create({
            'name': 'รวมหนี้ลูกค้า - %s' % (company.name or ''),
            'code': 'npd.debt.summary',
            'padding': 4,
            'number_next': 1,
            'number_increment': 1,
            'use_date_range': True,
            'company_id': company.id,
        })

    def _next_debt_doc_name(self, company=None):
        """เลขที่เอกสารใบถัดไป เช่น NPS.N 0001/2569

        เลขรันมาจาก ir.sequence (padding 4, ไม่มี prefix) ที่เปิด use_date_range
        ไว้ Odoo จึงตัดรอบให้เองทุกปี ขึ้นปีใหม่เลขจะกลับไปเริ่ม 0001
        ส่วนปีที่ต่อท้ายเป็น พ.ศ. = ค.ศ. + 543
        """
        company = company or self.env.company
        number = self._debt_sequence(company).next_by_id()
        if not number:
            return 'New'
        return '%s %s/%s' % (self._debt_doc_prefix(company), number,
                             fields.Date.context_today(self).year + 543)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self._next_debt_doc_name(company)
        return super().create(vals_list)

    # ===== baht text (สำหรับรายงาน) =====
    def _baht(self, amount):
        if bahttext:
            return bahttext(amount or 0.0)
        return '{:,.2f} บาท'.format(amount or 0.0)

    def get_total_baht_text_sheet(self):
        return self._baht(self.customer_amount_residual)

    def get_lost_baht_text_sheet(self):
        return self._baht(self.customer_penalty_residual)

    def get_damage_baht_text_sheet(self):
        return self._baht(self.customer_damage_residual)

    def get_total_baht_text_sheet_tax(self):
        return self._baht(self.customer_tax_residual)

    def get_amount_residual_formatted(self):
        return '{:,.2f}'.format(self.customer_amount_residual)

    def get_amount_lost_formatted(self):
        return '{:,.2f}'.format(self.customer_penalty_residual)

    def get_amount_damage_formatted(self):
        return '{:,.2f}'.format(self.customer_damage_residual)

    def get_amount_tax_formatted(self):
        return '{:,.2f}'.format(self.customer_tax_residual)

    # =========================================================================
    #  ค้นหาลูกค้าที่เข้าเงื่อนไข + สร้าง/อัพเดท record  (เรียกจากเมนู/ปุ่มอัพเดท)
    # =========================================================================
    @api.model
    def _target_companies(self):
        """บริษัทที่จะสแกนหนี้ให้ = บริษัทที่ผู้ใช้เปิดใช้งานอยู่"""
        return self.env.companies or self.env.company

    @api.model
    def _get_overdue_partner_ids(self, company):
        """commercial partner ids ที่มีใบแจ้งหนี้ลูกค้าค้างชำระของบริษัทนี้"""
        invoices = self.env['account.move'].sudo().search([
            ('company_id', '=', company.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('amount_residual', '>', 0),
            ('invoice_date', '>=', DEBT_START_STR),
        ])
        partner_ids = set()
        for inv in invoices:
            partner = inv.partner_id.commercial_partner_id or inv.partner_id
            if partner:
                partner_ids.add(partner.id)
        return list(partner_ids)

    @api.model
    def _fix_stale_invoice_residuals(self, company):
        """ล้างยอดค้างที่ล้าสมัยของใบแจ้งหนี้ก่อนดึงข้อมูล

        amount_residual กับ payment_state เป็นฟิลด์ compute แบบ store
        ถ้าไปแก้วันที่บนใบที่ลงบัญชี (posted) แล้ว Odoo ไม่ได้สั่งคำนวณใหม่
        ค่าที่เก็บไว้จึงค้างของเดิม อาการที่ตรวจจับได้คือใบที่ payment_state = paid
        แต่ amount_residual ยังมากกว่า 0
        """
        moves = self.env['account.move'].sudo().search([
            ('company_id', '=', company.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('payment_state', '=', 'paid'),
            ('amount_residual', '>', 0.005),
        ])
        if moves:
            moves._compute_amount()
            _logger.info('npd_debt_summary: ล้างยอดค้างล้าสมัย %s ใบ (%s)', len(moves), company.name)
        return len(moves)

    @api.model
    def cron_refresh_all(self):
        """อัพเดทข้อมูลทุกลูกค้า (เรียกจาก Scheduled Action ทุกวันตี 3)

        cron ไม่มีบริษัทที่ "เปิดใช้งาน" แบบหน้าจอ จึงไล่ทุกบริษัทในระบบ
        """
        companies = self.env['res.company'].sudo().search([])
        for company in companies:
            self.with_company(company)._refresh_all_records(company)

    @api.model
    def action_refresh_all(self):
        """อัพเดททั้งหมดแล้วเปิดรายการ (สำหรับเรียกเองเมื่อต้องการ)"""
        for company in self._target_companies():
            self.with_company(company)._refresh_all_records(company)
        return {
            'type': 'ir.actions.act_window',
            'name': _('รวมหนี้ลูกค้า'),
            'res_model': 'npd.debt.summary',
            'view_mode': 'list,form',
            'search_view_id': self.env.ref('npd_debt_summary.npd_debt_summary_view_search').id,
            'context': {},
            'target': 'current',
        }

    @api.model
    def _refresh_all_records(self, company=None):
        """สแกน + อัพเดทข้อมูลทุกแท็บของทุกลูกค้าในบริษัทนั้น"""
        company = company or self.env.company
        self._fix_stale_invoice_residuals(company)
        partner_ids = set(self._get_overdue_partner_ids(company))
        existing = self.search([('company_id', '=', company.id)])
        by_customer = {r.customer_id.id: r for r in existing}
        all_ids = partner_ids | set(by_customer.keys())

        for pid in all_ids:
            rec = by_customer.get(pid)
            if not rec:
                rec = self.create({'customer_id': pid, 'company_id': company.id})
            rec._populate_customer_data()
        self._remove_empty_records(company)

    def _is_debt_cleared(self):
        """ลูกค้ารายนี้ไม่ต้องติดตามแล้วหรือยัง"""
        self.ensure_one()
        if not (self.customer_invoice_line_ids or self.customer_deposit_line_ids
                or self.customer_rentdiff_line_ids or self.customer_penalty_line_ids
                or self.customer_damage_line_ids or self.customer_transport_line_ids
                or self.customer_tax_line_ids):
            return True
        all_paid = all(status == 'paid' for status in (
            self.invoice_payment_status, self.deposit_payment_status,
            self.rentdiff_payment_status, self.lost_payment_status,
            self.damage_payment_status, self.transport_payment_status,
            self.tax_payment_status))
        return all_paid and abs(self.grand_total or 0.0) < 0.01

    @api.model
    def _remove_empty_records(self, company=None):
        """ล้างลูกค้าที่ไม่มีหนี้ค้างแล้วออกจากรายการ

        ถ้าวันหลังลูกค้ามีหนี้ค้างอีก ระบบจะสร้างรายการใหม่ให้เองตอนกดอัพเดท
        (ได้เลขที่เอกสารใบใหม่)
        """
        domain = [('company_id', '=', company.id)] if company else []
        cleared = self.search(domain).filtered(lambda r: r._is_debt_cleared())
        if cleared:
            _logger.info('npd_debt_summary: เคลียร์ลูกค้าที่ชำระครบแล้ว %s ราย', len(cleared))
            cleared.unlink()

    def action_refresh_one(self):
        """ปุ่มอัพเดทข้อมูลลูกค้ารายนี้"""
        cleared = self.browse()
        for rec in self:
            rec._populate_customer_data()
            if rec._is_debt_cleared():
                cleared |= rec
        if cleared:
            cleared.unlink()
            return {
                'type': 'ir.actions.act_window',
                'name': _('รวมหนี้ลูกค้า'),
                'res_model': 'npd.debt.summary',
                'view_mode': 'list,form',
                'context': {},
                'target': 'current',
            }
        return True

    @staticmethod
    def _move_reason_name(move):
        """ชื่อประเภทเอกสารของใบแจ้งหนี้ ('' ถ้าไม่ได้ระบุ/ไม่มีฟิลด์)"""
        reason = getattr(move, 'reason_code_id', False)
        return reason.name if reason else ''

    def _deposit_invoice_ids(self, invoices):
        """id ของ 'ใบแจ้งหนี้ค่าประกัน' ในกลุ่มที่ส่งเข้ามา

        ใบค่าประกัน (INS-) ระบุประเภทเป็น 'ใบแจ้งหนี้ค่าเช่า' เหมือนใบค่าเช่าปกติ
        ดูจากประเภทอย่างเดียวจึงแยกไม่ออก ต้องดูที่การผูกกับใบสั่งขายผ่านฟิลด์
        sale.order.rent_check (โมดูล pfb_npd_all_customs ตาราง sale_order_rent_check_rel)
        -- ของ o14 ใช้ตาราง account_move_sale_order_rel ซึ่ง o18 ไม่มีแล้ว
        """
        if not invoices:
            return set()
        self.env.cr.execute("""
            SELECT 1 FROM information_schema.tables
             WHERE table_name = 'sale_order_rent_check_rel' LIMIT 1
        """)
        if not self.env.cr.fetchone():
            return set()   # ฐานที่ไม่ได้ติดตั้งโมดูลใบแจ้งหนี้ค่าประกัน
        self.env.cr.execute("""
            SELECT DISTINCT move_id
              FROM sale_order_rent_check_rel
             WHERE move_id IN %s
        """, (tuple(invoices.ids),))
        return set(row[0] for row in self.env.cr.fetchall())

    @staticmethod
    def _product_lines(inv):
        """บรรทัดสินค้าจริงบนใบแจ้งหนี้

        o14 ใช้ exclude_from_invoice_tab ซึ่ง o18 ถอดออกแล้ว
        ใช้ display_type == 'product' แทน (บรรทัดหัวข้อ/ภาษี/ยอดรวมไม่นับ)
        """
        return inv.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

    def _build_invoice_line_vals(self, inv, today):
        """ค่าของ 1 บรรทัดในแท็บใบแจ้งหนี้ค่าเช่า / ค่าเช่าส่วนต่าง (โครงเดียวกัน)"""
        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        payment_label = dict(
            self.env['account.move']._fields['payment_state'].selection
        ).get(inv.payment_state, inv.payment_state)
        return {
            'invoice_id': inv.id,
            'invoice_name': inv.name,
            'invoice_origin': inv.invoice_origin or '',
            'invoice_date': inv.invoice_date,
            'invoice_date_due': inv.invoice_date_due,
            'amount_total': inv.amount_total,
            'amount_residual': inv.amount_residual,
            'payment_state': inv.payment_state,
            'payment_state_label': payment_label,
            'days_overdue': ((today - inv.invoice_date_due).days
                             if inv.invoice_date_due else 0),
            'product_info_html': self._build_product_html(inv),
        }

    # ------------------------------------------------------------------
    # ค่าขนส่ง -- บริษัทขนส่งอยู่ในฐานเดียวกัน (o14 ต้องเปิด cursor ข้ามฐาน)
    # ------------------------------------------------------------------
    def _transport_debt_rows(self, so_names):
        """ใบแจ้งหนี้ค่าขนส่งที่ยังค้างชำระ ของเลข SO ที่ส่งเข้ามา

        ฝั่งขนส่ง (โมดูล sale_api_rent) ใบสั่งขายจะบันทึกไว้ว่า
            source_company_id = บริษัทต้นทางที่รับงานเช่ามา
            so_number         = เลขเอกสาร SO ของบริษัทต้นทางนั้น
        จับคู่ 2 ฟิลด์นี้กับบริษัทของเอกสารนี้ + เลข SO ของลูกค้า
        แล้วดูใบแจ้งหนี้ของใบสั่งขายฝั่งขนส่ง (ผูกผ่าน invoice_origin
        หรือ shipping_invoice_id ของโมดูล custom_shipping_invoice) ว่ายังค้างไหม
        """
        self.ensure_one()
        company = self.company_id
        SaleOrder = self.env['sale.order'].sudo()
        if not so_names or 'so_number' not in SaleOrder._fields:
            return []
        transport_orders = SaleOrder.search([
            ('source_company_id', '=', company.id),
            ('so_number', 'in', list(so_names)),
            ('state', 'in', ('sale', 'done')),
            ('date_order', '>=', DEBT_START_STR),
        ])
        if not transport_orders:
            return []

        rows = []
        Move = self.env['account.move'].sudo()
        for order in transport_orders:
            shipping_invoice = getattr(order, 'shipping_invoice_id', False)
            domain = ['|', ('invoice_origin', '=', order.name),
                      ('id', '=', shipping_invoice.id if shipping_invoice else 0)]
            posted = Move.search(domain + [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('amount_residual', '>', 0),
                ('invoice_date', '>=', DEBT_START_STR),
            ], order='invoice_date')
            if posted:
                for move in posted:
                    rows.append({
                        'source_so': order.so_number or '',
                        'transport_so': order.name or '',
                        'invoice_name': move.name or '',
                        'invoice_date': move.invoice_date,
                        'invoice_date_due': move.invoice_date_due,
                        'amount_total': move.amount_total,
                        'amount_residual': move.amount_residual,
                        'payment_state': move.payment_state or '',
                        'source_type': 'ใบแจ้งหนี้',
                    })
                continue

            # ยังไม่ออกใบแจ้งหนี้ หรือใบแจ้งหนี้ยังเป็นฉบับร่าง
            # -> ใช้ยอดค่าขนส่งบนใบสั่งขายฝั่งขนส่งแทน (สูตรเดียวกับ custom_shipping_invoice)
            #    ค่าขนส่งเป็น 0 = ถือว่าไม่มีหนี้ ไม่ต้องขึ้นรายการ
            if Move.search_count(domain + [('move_type', '=', 'out_invoice'),
                                           ('state', '=', 'posted')]):
                continue      # ออกใบแล้วและชำระครบ
            if getattr(order, 'use_special_delivery_zero', False) and not (order.shipping_cost_m or 0.0):
                amount = 0.0
            elif (getattr(order, 'shipping_cost_m', 0.0) or 0.0) > 0:
                amount = order.shipping_cost_m
            else:
                amount = getattr(order, 'shipping_cost', 0.0) or 0.0
            if amount <= 0:
                continue
            draft = Move.search(domain + [('move_type', '=', 'out_invoice'),
                                          ('state', '=', 'draft')], order='id desc', limit=1)
            rows.append({
                'source_so': order.so_number or '',
                'transport_so': order.name or '',
                'invoice_name': draft.name or '' if draft else '',
                'invoice_date': order.date_order.date() if order.date_order else False,
                'invoice_date_due': False,
                'amount_total': amount,
                'amount_residual': amount,
                'payment_state': 'not_paid',
                'source_type': 'ใบแจ้งหนี้ฉบับร่าง' if draft else 'ยังไม่ออกใบแจ้งหนี้',
            })
        return rows

    def _transport_source_so_names(self, commercial):
        """เลขเอกสาร SO ของลูกค้ารายนี้ ที่จะเอาไปจับคู่กับฝั่งขนส่ง

        ใช้ใบสั่งขายของลูกค้าตั้งแต่ปีที่กำหนด (DEBT_START_DATE) ทั้งหมด
        ไม่ได้จำกัดเฉพาะใบที่ยังค้างชำระฝั่งเรา เพราะค่าเช่ากับค่าขนส่ง
        เก็บเงินคนละใบ ลูกค้าจ่ายค่าเช่าครบแล้วแต่ยังค้างค่าขนส่งได้
        """
        self.ensure_one()
        orders = self.env['sale.order'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('partner_id', 'child_of', commercial.id),
            ('date_order', '>=', DEBT_START_STR),
        ])
        return set(name for name in orders.mapped('name') if name)

    def _populate_customer_data(self):
        """ดึงข้อมูลหนี้ทุกประเภทของลูกค้ารายนี้มาเก็บเป็น record จริง"""
        self.ensure_one()
        customer = self.customer_id
        if not customer:
            return
        today = fields.Date.context_today(self)
        commercial = customer.commercial_partner_id or customer
        company = self.company_id
        Move = self.env['account.move'].sudo()
        company_domain = [('company_id', '=', company.id)]

        # ====== 1) ใบแจ้งหนี้ แยกตามประเภท: ค่าเช่า / ค่าประกัน / ค่าเช่าส่วนต่าง ======
        # เก็บเฉพาะใบที่ยังค้างชำระ (ผู้ใช้ระบุ 21 ส.ค. 2026 ฝั่ง o14)
        unpaid_invoices = Move.search(company_domain + [
            ('partner_id', 'child_of', commercial.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('amount_residual', '>', 0),
            ('invoice_date', '>=', DEBT_START_STR),
        ])
        invoices = unpaid_invoices.exists().filtered(
            lambda m: m.invoice_date and m.invoice_date >= DEBT_START_DATE)
        inv_lines = [(5, 0, 0)]
        deposit_lines = [(5, 0, 0)]
        rentdiff_lines = [(5, 0, 0)]
        deposit_ids = self._deposit_invoice_ids(invoices)
        for inv in invoices:
            reason = self._move_reason_name(inv)
            if reason in (REASON_LOST, REASON_DAMAGE):
                continue       # มีแท็บของตัวเองอยู่แล้ว
            line_vals = self._build_invoice_line_vals(inv, today)
            if inv.id in deposit_ids:
                # เช็คค่าประกันก่อนประเภท เพราะใบค่าประกันระบุประเภทเป็นค่าเช่า
                deposit_lines.append((0, 0, line_vals))
            elif reason == REASON_RENT_DIFF:
                rentdiff_lines.append((0, 0, line_vals))
            else:
                inv_lines.append((0, 0, line_vals))

        # ============ 2) ค่าปรับหาย / 3) ค่าปรับชำรุด ============
        penalty_lines = self._penalty_like_lines(commercial, REASON_LOST, company_domain)
        damage_lines = self._penalty_like_lines(commercial, REASON_DAMAGE, company_domain)

        # ============ 4) ค่าหัก ณ ที่จ่าย ============
        tax_lines = self._wht_lines(commercial, company_domain)

        # ============ 5) ค่าขนส่ง ============
        transport_lines = [(5, 0, 0)]
        so_names = self._transport_source_so_names(commercial)
        for row in self._transport_debt_rows(sorted(so_names)):
            due = row['invoice_date_due']
            transport_lines.append((0, 0, {
                'source_type': row.get('source_type') or '',
                'source_so': row['source_so'] or '',
                'transport_so': row['transport_so'] or '',
                'invoice_name': row['invoice_name'] or '',
                'invoice_date': row['invoice_date'],
                'invoice_date_due': due,
                'amount_total': row['amount_total'] or 0.0,
                'amount_residual': row['amount_residual'] or 0.0,
                'payment_state': row['payment_state'] or '',
                'days_overdue': (today - due).days if due else 0,
            }))

        # ============ เขียนข้อมูลทั้งหมดลง record ============
        self.write({
            'partner_name': customer.name or '',
            'partner_phone': customer.phone or '',
            'partner_mobile': customer.mobile or '',
            'partner_email': customer.email or '',
            'partner_vat': customer.vat or '',
            'partner_street': customer.street or '',
            'partner_street2': customer.street2 or '',
            'partner_city': customer.city or '',
            'partner_state_id': customer.state_id.id if customer.state_id else False,
            'partner_zip': customer.zip or '',
            'customer_invoice_line_ids': inv_lines,
            'customer_deposit_line_ids': deposit_lines,
            'customer_rentdiff_line_ids': rentdiff_lines,
            'customer_penalty_line_ids': penalty_lines,
            'customer_damage_line_ids': damage_lines,
            'customer_transport_line_ids': transport_lines,
            'customer_tax_line_ids': tax_lines,
            'last_update': fields.Datetime.now(),
        })

    def _penalty_like_lines(self, commercial, reason_name, company_domain):
        """บรรทัดแท็บค่าปรับหาย/ค่าปรับชำรุด (โครงเดียวกัน ต่างแค่ประเภทเอกสาร)

        คืนคำสั่งเขียน one2many (เคลียร์ของเดิมแล้วใส่ใหม่)
        ฟิลด์ยอดของแท็บสองตัวนี้ชื่อไม่เหมือนกัน (penalty_amount/damage_amount)
        จึงส่งชื่อฟิลด์เข้ามาตอนประกอบ vals
        """
        self.ensure_one()
        is_lost = reason_name == REASON_LOST
        amount_field = 'penalty_amount' if is_lost else 'damage_amount'
        net_field = 'net_penalty' if is_lost else 'net_damage'
        lines = [(5, 0, 0)]
        reason = self.env['scrap.reason.code'].sudo().search([('name', '=', reason_name)], limit=1)
        if not reason:
            # ฐานที่ยังไม่ได้ตั้งประเภทเอกสาร -> ไม่มีใบไหนเข้าแท็บนี้
            return lines
        invoices = self.env['account.move'].sudo().search(company_domain + [
            ('partner_id', 'child_of', commercial.id),
            ('state', '=', 'posted'),
            ('amount_residual', '>', 0),
            ('reason_code_id', '=', reason.id),
            ('invoice_date', '>=', DEBT_START_STR),
        ]).exists().filtered(lambda m: m.invoice_date and m.invoice_date >= DEBT_START_DATE)
        for inv in invoices:
            inv.invalidate_recordset(['amount_residual'])
            residual = inv.amount_residual
            gross = getattr(inv, 'amount_price_subtotal_without_discount', 0.0) or 0.0
            if not gross:
                gross = sum(l.quantity * l.price_unit for l in self._product_lines(inv))
            discount = (getattr(inv, 'discount_amt_line', 0.0) or 0.0)
            discount += (getattr(inv, 'discount_amt', 0.0) or 0.0)
            product_html, product_line_vals = self._build_product_html_and_lines(inv)
            vals = {
                'invoice_id': inv.id,
                'invoice_name': inv.name,
                'branch_name': inv.branch_id.name or '' if getattr(inv, 'branch_id', False) else '',
                'sales_contact_name': (inv.sales_contact_id.name or ''
                                       if getattr(inv, 'sales_contact_id', False) else ''),
                'rental_start_date': inv.invoice_date,
                'rental_end_date': inv.invoice_date_due,
                amount_field: gross,
                'discount_amount': discount,
                net_field: inv.amount_total,
                'amount_paid': inv.amount_total - residual,
                'amount_residual': residual,
                'product_info_html': product_html,
            }
            if is_lost:
                vals['penalty_product_line_ids'] = product_line_vals
            lines.append((0, 0, vals))
        return lines

    def _wht_lines(self, commercial, company_domain):
        """บรรทัดแท็บค่าหัก ณ ที่จ่าย

        o14 หาจาก 2 ทาง: ชื่อวิธีชำระเงินที่มีคำว่า "ภาษี...หัก..." และ wt_cert_ids
        o18 บรรทัดวิธีชำระ (account.paid.line) ไม่มีวิธีชำระแบบมีชื่อแล้ว (มีแต่
        payment_method_type) แต่บรรทัดใบแจ้งหนี้ของใบรับชำระ (account.payment.invoice)
        เก็บยอดหัก ณ ที่จ่ายรายใบไว้ที่ wt_amount อยู่แล้ว จึงใช้ค่านั้นตรง ๆ
        ถ้าใบไหนไม่ได้ลงยอดไว้ ค่อยถอยไปใช้หนังสือรับรองหัก ณ ที่จ่าย (wt_cert_ids)
        ของใบรับชำระที่มีใบแจ้งหนี้ใบเดียว
        """
        self.ensure_one()
        lines = [(5, 0, 0)]
        PaymentInvoice = self.env['account.payment.invoice'].sudo()
        invoices = self.env['account.move'].sudo().search(company_domain + [
            ('partner_id', 'child_of', commercial.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', DEBT_START_STR),
        ])
        if not invoices:
            return lines
        payment_links = PaymentInvoice.search([
            ('move_id', 'in', invoices.ids),
            ('payment_id.state', 'not in', ('draft', 'canceled', 'cancel')),
        ])
        seen = set()
        for link in payment_links:
            payment = link.payment_id
            invoice = link.move_id
            if not payment or not invoice or (invoice.id, payment.id) in seen:
                continue
            amount = link.wt_amount or 0.0
            if amount <= 0 and getattr(payment, 'wht_has_slip', False):
                # ใบรับชำระที่มีใบแจ้งหนี้ใบเดียว ยอดทั้งก้อนเป็นของใบนี้
                if len(payment.custom_invoice_ids) <= 1:
                    amount = (sum(payment.wt_cert_ids.mapped('tax_amount'))
                              or getattr(payment, 'wht_amount', 0.0) or 0.0)
            if amount <= 0:
                continue
            seen.add((invoice.id, payment.id))
            lines.append((0, 0, self._prepare_tax_line_vals(invoice, payment, amount)))
        return lines

    # ------------------------------------------------------------------ helpers
    def _build_product_html(self, inv):
        """สร้าง HTML table แสดงรายการสินค้าของใบแจ้งหนี้"""
        html, _lines = self._build_product_html_and_lines(inv)
        return html

    def _build_product_html_and_lines(self, inv):
        """สร้าง HTML table + product line vals (ใช้กับแท็บค่าปรับหาย)"""
        html = '<table class="table table-sm table-bordered" style="width:100%">'
        html += '<thead><tr style="background:#f5f5f5">'
        html += '<th>สินค้า</th><th>รายละเอียด</th>'
        html += '<th style="text-align:right">จำนวน</th>'
        html += '<th style="text-align:right">ราคาต่อหน่วย</th>'
        html += '<th style="text-align:right">ส่วนลด (%)</th>'
        html += '<th style="text-align:right">ยอดรวม</th>'
        html += '</tr></thead><tbody>'
        has_lines = False
        product_line_vals = []
        for line in self._product_lines(inv):
            has_lines = True
            pname = line.product_id.name if line.product_id else ''
            html += '<tr>'
            html += '<td>%s</td>' % pname
            html += '<td>%s</td>' % (line.name or '')
            html += '<td style="text-align:right">%.2f</td>' % line.quantity
            html += '<td style="text-align:right">{:,.2f}</td>'.format(line.price_unit)
            html += '<td style="text-align:right">%.2f</td>' % line.discount
            html += '<td style="text-align:right">{:,.2f}</td>'.format(line.price_subtotal)
            html += '</tr>'
            product_line_vals.append((0, 0, {
                'product_name': pname,
                'description': line.name or '',
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'price_subtotal': line.price_subtotal,
            }))
        if not has_lines:
            html += '<tr><td colspan="6" style="text-align:center;color:#999">ไม่มีรายการสินค้า</td></tr>'
        html += '</tbody></table>'
        return html, product_line_vals

    def _prepare_tax_line_vals(self, invoice, payment, tax_amt):
        """สร้าง dict สำหรับ tax line record"""
        return {
            'invoice_id': invoice.id,
            'invoice_name': invoice.name,
            'invoice_origin': invoice.invoice_origin or '',
            'invoice_date': invoice.invoice_date,
            'invoice_date_due': invoice.invoice_date_due,
            'amount_total': invoice.amount_total,
            'payment_id': payment.id,
            'payment_name': payment.name or '',
            'tax_amount': tax_amt,
            'product_info_html': self._build_product_html(invoice),
        }
