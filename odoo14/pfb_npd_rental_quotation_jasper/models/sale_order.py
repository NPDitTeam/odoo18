from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    jasper_baht_text_rental = fields.Char(
        string='Baht Text Rental',
        compute='_compute_jasper_baht_text_rental',
    )
    jasper_total_weight = fields.Float(
        string='Total Weight',
        compute='_compute_jasper_total_weight',
    )
    jasper_rental_per_day = fields.Float(
        string='Rental Per Day',
        compute='_compute_jasper_rental_per_day',
    )
    jasper_grand_total = fields.Float(
        string='Grand Total (Rental + Insurance)',
        compute='_compute_jasper_grand_total',
    )

    @api.depends('amount_total', 'pfb_amount')
    def _compute_jasper_baht_text_rental(self):
        try:
            from bahttext import bahttext
        except ImportError:
            bahttext = None
        for rec in self:
            total_amount = (rec.amount_total or 0.0) + (rec.pfb_amount or 0.0)
            if bahttext:
                rec.jasper_baht_text_rental = bahttext(total_amount)
            else:
                rec.jasper_baht_text_rental = str(total_amount)

    @api.depends('order_line.second_uom_qty', 'order_line.pfb_quantity')
    def _compute_jasper_total_weight(self):
        for rec in self:
            rec.jasper_total_weight = sum(
                (line.second_uom_qty or 0.0) * (line.pfb_quantity or 0.0)
                for line in rec.order_line
            )

    @api.depends('amount_total', 'pfb_date_of_rent')
    def _compute_jasper_rental_per_day(self):
        for rec in self:
            if rec.pfb_date_of_rent:
                rec.jasper_rental_per_day = rec.amount_total / rec.pfb_date_of_rent
            else:
                rec.jasper_rental_per_day = 0.0

    @api.depends('amount_total', 'pfb_amount')
    def _compute_jasper_grand_total(self):
        for rec in self:
            rec.jasper_grand_total = (rec.amount_total or 0.0) + (rec.pfb_amount or 0.0)

    # --- หัวกระดาษ: ใช้บริษัทที่กำลังเลือกอยู่ (active company / env.company) ---
    jasper_active_company_name = fields.Char(
        string='Active Company Name',
        compute='_compute_jasper_active_company',
    )
    jasper_active_company_vat = fields.Char(
        string='Active Company VAT',
        compute='_compute_jasper_active_company',
    )
    jasper_active_company_address = fields.Char(
        string='Active Company Address',
        compute='_compute_jasper_active_company',
    )
    jasper_active_company_id = fields.Many2one(
        'res.company',
        string='Active Company',
        compute='_compute_jasper_active_company',
    )
    jasper_active_company_head_office = fields.Char(
        string='Active Company Head Office Suffix',
        compute='_compute_jasper_active_company',
    )

    @api.depends_context('allowed_company_ids')
    def _compute_jasper_active_company(self):
        company = self.env.company
        parts = []
        if company.street:
            parts.append(company.street)
        if company.street2:
            parts.append(company.street2)
        if company.city:
            parts.append(company.city)
        if company.state_id:
            parts.append(company.state_id.name)
        if company.zip:
            parts.append(company.zip)
        address = ' '.join(parts)
        head_office = '' if company.parent_id else ' (สำนักงานใหญ่)'
        name = company.name or ''
        vat = company.vat or ''
        for rec in self:
            rec.jasper_active_company_id = company
            rec.jasper_active_company_name = name
            rec.jasper_active_company_vat = vat
            rec.jasper_active_company_address = address
            rec.jasper_active_company_head_office = head_office

    jasper_bank_info = fields.Char(
        string='Bank Info',
        compute='_compute_jasper_bank_info',
    )

    # เลือกบัญชีรับเงินตาม company_registry (ID บริษัท) ของบริษัทที่กำลังเลือกอยู่
    # (odoo18 เป็น single-DB หลายบริษัท จึงเช็คจาก company_registry แทนชื่อ DB แบบ odoo14)
    # 1=นภดล กรุงเทพ, 2=นภดล อินเตอร์เทรดดิ้ง, 3=นภดล เอส กรุ๊ป, 4=เอ็นพีดี สตีลเทค, 5=เอ็นพีดี โลจิสติกส์
    _JASPER_BANK_BY_REGISTRY = {
        '1': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล กรุงเทพ จำกัด กสิกรไทย เลขที่บัญชี 025-290298-8\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล กรุงเทพ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-224773-9\n'
            'ค่าขนส่งสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6'
        ),
        '2': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด กสิกรไทย เลขที่บัญชี 033-885651-2\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-546107-1\n'
            'ค่าขนส่งสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6'
        ),
        '3': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล เอส กรุ๊ป จำกัด กสิกรไทย เลขที่บัญชี 020-893777-4\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล เอส กรุ๊ป จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-222160-2\n'
            'ค่าขนส่งสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6'
        ),
        '4': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี สตีลเทค จำกัด กสิกรไทย เลขที่บัญชี 035-1-39757-8\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี สตีลเทค จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-582058-4\n'
            'ค่าขนส่งสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6'
        ),
        '5': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด กสิกรไทย เลขที่บัญชี 117-1-78329-8\n'
            'ค่าขนส่งสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6'
        ),
    }

    @api.depends_context('allowed_company_ids')
    def _compute_jasper_bank_info(self):
        registry = self.env.company.company_registry or ''
        text = self._JASPER_BANK_BY_REGISTRY.get(registry.strip(), '')
        for rec in self:
            rec.jasper_bank_info = text


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    jasper_product_code = fields.Char(
        string='Product Code',
        compute='_compute_jasper_product_fields',
    )
    jasper_product_desc = fields.Char(
        string='Product Description',
        compute='_compute_jasper_product_fields',
    )
    jasper_line_weight = fields.Float(
        string='Line Weight',
        compute='_compute_jasper_line_weight',
    )
    jasper_insurance_total = fields.Float(
        string='Insurance Total',
        compute='_compute_jasper_insurance_total',
    )

    @api.depends('name')
    def _compute_jasper_product_fields(self):
        for line in self:
            if line.name:
                parts = line.name.split(' ', 1)
                line.jasper_product_code = parts[0] if parts else ''
                line.jasper_product_desc = parts[1] if len(parts) > 1 else ''
            else:
                line.jasper_product_code = ''
                line.jasper_product_desc = ''

    @api.depends('second_uom_qty', 'pfb_quantity')
    def _compute_jasper_line_weight(self):
        for line in self:
            line.jasper_line_weight = (line.second_uom_qty or 0.0) * (line.pfb_quantity or 0.0)

    @api.depends('pfb_quantity', 'pfb_insurance_price')
    def _compute_jasper_insurance_total(self):
        for line in self:
            line.jasper_insurance_total = (line.pfb_quantity or 0.0) * (line.pfb_insurance_price or 0.0)

    # ค่าเช่าต่อหน่วย (ถอด VAT 7% แบบ price-included) เทียบเท่า price_unit_no_vat ฝั่ง odoo14
    jasper_price_unit_no_vat = fields.Float(
        string='Unit Price (ex VAT)',
        compute='_compute_jasper_price_unit_no_vat',
    )

    @api.depends('price_unit', 'tax_id')
    def _compute_jasper_price_unit_no_vat(self):
        for line in self:
            has_vat_7_incl = any(
                t.price_include and abs(t.amount - 7.0) < 0.01
                for t in line.tax_id
            )
            if has_vat_7_incl:
                line.jasper_price_unit_no_vat = round((line.price_unit or 0.0) / 1.07, 2)
            else:
                line.jasper_price_unit_no_vat = line.price_unit or 0.0
