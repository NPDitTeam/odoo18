import base64
import logging
import re

from odoo import models, fields, api, tools

_logger = logging.getLogger(__name__)


def _join_address(*parts):
    return ' '.join(p for p in parts if p)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ===== Header: company (โลโก้/ชื่อ/ที่อยู่สาขา ดึงแบบเดียวกับ jasper ใบลดหนี้) =====
    jasper_rd_company_name_display = fields.Char(
        compute='_compute_jasper_rd_company_name_display',
    )
    jasper_rd_branch_address = fields.Char(
        compute='_compute_jasper_rd_branch_address',
    )

    # ===== Customer / shipping =====
    jasper_rd_partner_full_address = fields.Char(
        compute='_compute_jasper_rd_partner_full_address',
    )
    jasper_rd_partner_vat_branch = fields.Char(
        compute='_compute_jasper_rd_partner_vat_branch',
    )
    jasper_rd_shipping_name = fields.Char(
        compute='_compute_jasper_rd_shipping',
    )
    jasper_rd_shipping_address = fields.Char(
        compute='_compute_jasper_rd_shipping',
    )

    # ===== Date =====
    jasper_rd_invoice_date_str = fields.Char(
        compute='_compute_jasper_rd_invoice_date_str',
    )

    # ===== Amounts =====
    jasper_rd_amount_untaxed = fields.Float(
        compute='_compute_jasper_rd_amounts',
    )
    jasper_rd_amount_tax = fields.Float(
        compute='_compute_jasper_rd_amounts',
    )
    jasper_rd_amount_wht = fields.Float(
        compute='_compute_jasper_rd_amounts',
    )
    jasper_rd_amount_total = fields.Float(
        compute='_compute_jasper_rd_amounts',
    )
    jasper_rd_total_discount = fields.Float(
        compute='_compute_jasper_rd_amounts',
    )
    jasper_rd_baht_text = fields.Char(
        compute='_compute_jasper_rd_baht_text',
    )

    # ===== บริษัทสำหรับสั่งจ่ายเช็ค + QR (เลือกตาม company_registry / "ID บริษัท") =====
    # odoo18 เป็น single-DB หลายบริษัท จึงเช็คจาก company_registry แทนชื่อ DB แบบ odoo14
    # 1=นภดล กรุงเทพ, 2=นภดล อินเตอร์เทรดดิ้ง, 3=นภดล เอส กรุ๊ป,
    # 4=เอ็นพีดี สตีลเทค, 5=เอ็นพีดี โลจิสติกส์
    jasper_rd_cheque_name = fields.Char(
        compute='_compute_jasper_rd_company_by_registry',
    )
    jasper_rd_qr_image = fields.Binary(
        compute='_compute_jasper_rd_company_by_registry',
    )

    _CHEQUE_NAME_BY_REGISTRY = {
        '1': 'บริษัท นภดล กรุงเทพ จำกัด',
        '2': 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด',
        '3': 'บริษัท นภดล เอส กรุ๊ป จำกัด',
        '4': 'บริษัท เอ็นพีดี สตีลเทค จำกัด',
        '5': 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด',
    }
    _QR_IMAGE_BY_REGISTRY = {
        '1': 'pfb_npd_rental_difference_jasper/static/img/qr_1.png',
        '2': 'pfb_npd_rental_difference_jasper/static/img/qr_2.png',
        '3': 'pfb_npd_rental_difference_jasper/static/img/qr_3.png',
        '4': 'pfb_npd_rental_difference_jasper/static/img/qr_4.png',
        '5': 'pfb_npd_rental_difference_jasper/static/img/qr_5.png',
    }

    # =================================================================
    # Compute methods
    # =================================================================

    @api.depends('company_id.name')
    def _compute_jasper_rd_company_name_display(self):
        for rec in self:
            name = rec.company_id.name or ''
            rec.jasper_rd_company_name_display = (
                '{} (สำนักงานใหญ่)'.format(name) if name else ''
            )

    @api.depends(
        'branch_id', 'branch_id.street', 'branch_id.street2',
        'branch_id.city', 'branch_id.state_id', 'branch_id.zip',
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_rd_branch_address(self):
        for rec in self:
            branch = rec.branch_id
            if branch:
                state_name = branch.state_id.name if branch.state_id else ''
                addr = _join_address(
                    branch.street, branch.street2, branch.city,
                    state_name, branch.zip,
                )
                if addr:
                    rec.jasper_rd_branch_address = addr
                    continue
            c = rec.company_id
            state_name = c.state_id.name if c.state_id else ''
            rec.jasper_rd_branch_address = _join_address(
                c.street, c.street2, c.city, state_name, c.zip,
            )

    @api.depends(
        'partner_id.street', 'partner_id.street2',
        'partner_id.city', 'partner_id.state_id', 'partner_id.zip',
    )
    def _compute_jasper_rd_partner_full_address(self):
        for rec in self:
            p = rec.partner_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_rd_partner_full_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('partner_id.vat', 'partner_id.branch')
    def _compute_jasper_rd_partner_vat_branch(self):
        for rec in self:
            p = rec.partner_id
            vat = p.vat or ''
            branch = p.branch or ''
            if branch == '00000':
                suffix = '(สำนักงานใหญ่)'
            elif branch:
                suffix = 'สาขาที่ {}'.format(branch)
            else:
                suffix = ''
            rec.jasper_rd_partner_vat_branch = '{}  {}'.format(vat, suffix).strip()

    @api.depends(
        'partner_shipping_id.name', 'partner_shipping_id.street',
        'partner_shipping_id.street2', 'partner_shipping_id.city',
        'partner_shipping_id.state_id', 'partner_shipping_id.zip',
    )
    def _compute_jasper_rd_shipping(self):
        for rec in self:
            p = rec.partner_shipping_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_rd_shipping_name = p.name or ''
            rec.jasper_rd_shipping_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('invoice_date')
    def _compute_jasper_rd_invoice_date_str(self):
        for rec in self:
            rec.jasper_rd_invoice_date_str = (
                rec.invoice_date.strftime('%Y-%m-%d') if rec.invoice_date else ''
            )

    @api.depends(
        'amount_untaxed', 'amount_tax', 'amount_total',
        'invoice_line_ids.discount',
    )
    def _compute_jasper_rd_amounts(self):
        for rec in self:
            untaxed = rec.amount_untaxed or 0.0
            rec.jasper_rd_amount_untaxed = untaxed
            rec.jasper_rd_amount_tax = rec.amount_tax or 0.0
            rec.jasper_rd_amount_total = rec.amount_total or 0.0
            # ภาษีหัก ณ ที่จ่าย 5% ของมูลค่าก่อนภาษี (ตามสูตร odoo14)
            rec.jasper_rd_amount_wht = untaxed * 0.05
            # ส่วนลด/Disc.% = ผลรวมเปอร์เซ็นต์ส่วนลดของบรรทัด (ตาม odoo14)
            rec.jasper_rd_total_discount = sum(
                (line.discount or 0.0) for line in rec.invoice_line_ids
            )

    @api.depends('amount_total')
    def _compute_jasper_rd_baht_text(self):
        try:
            from bahttext import bahttext
        except ImportError:
            bahttext = None
        for rec in self:
            amount = rec.amount_total or 0.0
            if bahttext:
                rec.jasper_rd_baht_text = bahttext(amount)
            else:
                rec.jasper_rd_baht_text = '{:,.2f}'.format(amount)

    @api.depends('company_id.company_registry')
    def _compute_jasper_rd_company_by_registry(self):
        for rec in self:
            registry = (rec.company_id.company_registry or '').strip()
            rec.jasper_rd_cheque_name = self._CHEQUE_NAME_BY_REGISTRY.get(
                registry, rec.company_id.name or ''
            )
            qr_b64 = False
            path = self._QR_IMAGE_BY_REGISTRY.get(registry)
            if path:
                try:
                    with tools.file_open(path, 'rb') as f:
                        qr_b64 = base64.b64encode(f.read())
                except Exception as e:
                    _logger.warning('Could not load QR image %s: %s', path, e)
            rec.jasper_rd_qr_image = qr_b64


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    jasper_rd_product_code = fields.Char(
        compute='_compute_jasper_rd_line_fields',
    )
    jasper_rd_uom_name = fields.Char(
        compute='_compute_jasper_rd_line_fields',
    )
    # ชื่อสินค้าโดยตัด "[รหัส]" นำหน้าออก (เอาแค่ชื่อ)
    jasper_rd_line_desc = fields.Char(
        compute='_compute_jasper_rd_line_fields',
    )

    @api.depends('product_id.default_code', 'product_uom_id.name', 'name')
    def _compute_jasper_rd_line_fields(self):
        for line in self:
            line.jasper_rd_product_code = line.product_id.default_code or ''
            line.jasper_rd_uom_name = line.product_uom_id.name or ''
            # ตัด prefix "[...]" หน้าชื่อ (เช่น "[PR/02755] Basic Socket" -> "Basic Socket")
            name = line.name or ''
            line.jasper_rd_line_desc = re.sub(r'^\s*\[[^\]]*\]\s*', '', name)
