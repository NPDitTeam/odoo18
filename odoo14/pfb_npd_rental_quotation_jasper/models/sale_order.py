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

    jasper_bank_info = fields.Char(
        string='Bank Info',
        compute='_compute_jasper_bank_info',
    )

    @api.depends('company_id', 'company_id.name')
    def _compute_jasper_bank_info(self):
        company_bank_map = {
            'นภดล เอส กรุ๊ป': 'บริษัท นภดล เอส กรุ๊ป จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-222160-2',
            'นภดล กรุงเทพ': 'บริษัท นภดล กรุงเทพ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-224773-9',
            'นภดล อินเตอร์เทรดดิ้ง': 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-546107-1',
        }
        for rec in self:
            company_name = rec.company_id.name or ''
            rec.jasper_bank_info = ''
            for key, value in company_bank_map.items():
                if key in company_name:
                    rec.jasper_bank_info = value
                    break


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
