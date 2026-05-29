from odoo import models, fields, api

THAI_MONTHS = {
    1: 'มกราคม', 2: 'กุมภาพันธ์', 3: 'มีนาคม', 4: 'เมษายน',
    5: 'พฤษภาคม', 6: 'มิถุนายน', 7: 'กรกฎาคม', 8: 'สิงหาคม',
    9: 'กันยายน', 10: 'ตุลาคม', 11: 'พฤศจิกายน', 12: 'ธันวาคม',
}


def _format_thai_date(dt):
    if not dt:
        return ''
    day = dt.strftime('%d')
    month = THAI_MONTHS.get(dt.month, '')
    year = dt.year + 543
    return '{} {} {}'.format(day, month, year)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # --- Thai Buddhist era dates ---
    jasper_start_rent_thai = fields.Char(
        string='Start Rent Date (Thai)',
        compute='_compute_jasper_rent_dates_thai',
    )
    jasper_end_rent_thai = fields.Char(
        string='End Rent Date (Thai)',
        compute='_compute_jasper_rent_dates_thai',
    )

    @api.depends('start_rent_date', 'end_rent_date')
    def _compute_jasper_rent_dates_thai(self):
        for rec in self:
            rec.jasper_start_rent_thai = _format_thai_date(rec.start_rent_date)
            rec.jasper_end_rent_thai = _format_thai_date(rec.end_rent_date)

    jasper_date_order_thai = fields.Char(
        string='Order Date (Thai)',
        compute='_compute_jasper_date_order_thai',
    )

    @api.depends('date_order')
    def _compute_jasper_date_order_thai(self):
        for rec in self:
            if rec.date_order:
                dt = rec.date_order
                rec.jasper_date_order_thai = '{}/{}/{}'.format(
                    dt.strftime('%d'), dt.strftime('%m'), dt.year + 543
                )
            else:
                rec.jasper_date_order_thai = ''

    # --- Sales contact ---
    jasper_sales_contact_name = fields.Char(
        string='Sales Contact Name',
        compute='_compute_jasper_sales_contact_name',
    )

    @api.depends('sales_contact')
    def _compute_jasper_sales_contact_name(self):
        for rec in self:
            if rec.contact_type == 'sale' and rec.sales_contact:
                rec.jasper_sales_contact_name = rec.sales_contact.name or ''
            else:
                rec.jasper_sales_contact_name = ''

    # --- Partner full address ---
    jasper_partner_full_address = fields.Char(
        string='Partner Full Address',
        compute='_compute_jasper_partner_full_address',
    )

    @api.depends(
        'partner_id.street', 'partner_id.street2',
        'partner_id.city', 'partner_id.state_id',
        'partner_id.zip', 'partner_id.phone',
    )
    def _compute_jasper_partner_full_address(self):
        for rec in self:
            parts = []
            p = rec.partner_id
            if p.street:
                parts.append(p.street)
            if p.street2:
                parts.append(p.street2)
            if p.city:
                parts.append(p.city)
            if p.state_id:
                parts.append(p.state_id.name)
            if p.zip:
                parts.append(p.zip)
            addr = ' '.join(parts)
            if p.phone:
                addr += ' [{}]'.format(p.phone)
            rec.jasper_partner_full_address = addr

    # --- Baht text ---
    jasper_baht_text_rental = fields.Char(
        string='Baht Text Rental',
        compute='_compute_jasper_baht_text_rental',
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

    # --- Total weight ---
    jasper_total_weight = fields.Float(
        string='Total Weight',
        compute='_compute_jasper_total_weight',
    )

    @api.depends('order_line.second_uom_qty', 'order_line.pfb_quantity')
    def _compute_jasper_total_weight(self):
        for rec in self:
            rec.jasper_total_weight = sum(
                (line.second_uom_qty or 0.0) * (line.pfb_quantity or 0.0)
                for line in rec.order_line
            )

    # --- Rental per day ---
    jasper_rental_per_day = fields.Float(
        string='Rental Per Day',
        compute='_compute_jasper_rental_per_day',
    )

    @api.depends('amount_total', 'pfb_date_of_rent')
    def _compute_jasper_rental_per_day(self):
        for rec in self:
            if rec.pfb_date_of_rent:
                rec.jasper_rental_per_day = rec.amount_total / rec.pfb_date_of_rent
            else:
                rec.jasper_rental_per_day = 0.0

    # --- Grand total (rental + insurance) ---
    jasper_grand_total = fields.Float(
        string='Grand Total (Rental + Insurance)',
        compute='_compute_jasper_grand_total',
    )

    @api.depends('amount_total', 'pfb_amount')
    def _compute_jasper_grand_total(self):
        for rec in self:
            rec.jasper_grand_total = (rec.amount_total or 0.0) + (rec.pfb_amount or 0.0)

    # --- Print datetime ---
    jasper_print_datetime = fields.Char(
        string='Print DateTime',
        compute='_compute_jasper_print_datetime',
    )

    def _compute_jasper_print_datetime(self):
        from datetime import datetime
        import pytz
        tz = pytz.timezone('Asia/Bangkok')
        now = datetime.now(tz)
        formatted = now.strftime('%d-%m-%Y %H:%M:%S')
        for rec in self:
            rec.jasper_print_datetime = formatted


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

    jasper_line_weight = fields.Float(
        string='Line Weight',
        compute='_compute_jasper_line_weight',
    )

    @api.depends('second_uom_qty', 'pfb_quantity')
    def _compute_jasper_line_weight(self):
        for line in self:
            line.jasper_line_weight = (line.second_uom_qty or 0.0) * (line.pfb_quantity or 0.0)

    jasper_daily_rental_total = fields.Float(
        string='Daily Rental Total',
        compute='_compute_jasper_daily_rental_total',
    )

    @api.depends('price_subtotal')
    def _compute_jasper_daily_rental_total(self):
        for line in self:
            line.jasper_daily_rental_total = line.price_subtotal or 0.0
