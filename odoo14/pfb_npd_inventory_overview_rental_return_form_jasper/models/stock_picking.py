from odoo import models, fields, api
from datetime import datetime, timedelta


THAI_MONTHS = {
    1: 'มกราคม', 2: 'กุมภาพันธ์', 3: 'มีนาคม', 4: 'เมษายน',
    5: 'พฤษภาคม', 6: 'มิถุนายน', 7: 'กรกฎาคม', 8: 'สิงหาคม',
    9: 'กันยายน', 10: 'ตุลาคม', 11: 'พฤศจิกายน', 12: 'ธันวาคม',
}


def format_thai_date(d):
    if not d:
        return ''
    return f"{d.day} {THAI_MONTHS[d.month]} {d.year + 543}"


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    jasper_start_date_thai = fields.Char(
        string='Start Date (Thai)',
        compute='_compute_jasper_dates',
    )
    jasper_end_date_thai = fields.Char(
        string='End Date (Thai)',
        compute='_compute_jasper_dates',
    )
    jasper_return_date_thai = fields.Char(
        string='Return Date (Thai)',
        compute='_compute_jasper_dates',
    )
    jasper_document_time = fields.Char(
        string='Document Time',
        compute='_compute_jasper_dates',
    )
    jasper_print_date = fields.Char(
        string='Print Date',
        compute='_compute_jasper_print',
    )
    jasper_print_time = fields.Char(
        string='Print Time',
        compute='_compute_jasper_print',
    )
    jasper_days_used = fields.Integer(
        string='Days Used',
        compute='_compute_jasper_days',
    )
    jasper_rent_days = fields.Integer(
        string='Rent Days (Sale)',
        compute='_compute_jasper_days',
    )

    jasper_partner_address = fields.Char(
        string='Partner Full Address',
        compute='_compute_jasper_partner_address',
    )

    jasper_branch_address = fields.Char(
        string='Branch Address',
        compute='_compute_jasper_branch_address',
    )

    jasper_rental_start = fields.Float(
        string='Rental Start Amount',
        compute='_compute_jasper_summary',
    )
    jasper_insurance_amount = fields.Float(
        string='Insurance Amount',
        compute='_compute_jasper_summary',
    )
    jasper_rental_per_day = fields.Float(
        string='Rental Per Day',
        compute='_compute_jasper_summary',
    )
    jasper_total_rent = fields.Float(
        string='Total Rent Occurred',
        compute='_compute_jasper_summary',
    )
    jasper_rent_diff = fields.Float(
        string='Rent Diff (เก็บค่าเช่าส่วนต่าง)',
        compute='_compute_jasper_summary',
    )
    jasper_rent_discount = fields.Float(
        string='Rent Discount',
        compute='_compute_jasper_summary',
    )
    jasper_rent_diff_net = fields.Float(
        string='Rent Diff Net',
        compute='_compute_jasper_summary',
    )
    jasper_total_damaged = fields.Float(
        string='Total Damaged',
        compute='_compute_jasper_debit',
    )
    jasper_total_lost = fields.Float(
        string='Total Lost',
        compute='_compute_jasper_debit',
    )
    jasper_discount_lost = fields.Float(
        string='Discount Lost',
        compute='_compute_jasper_debit',
    )
    jasper_final_net = fields.Float(
        string='Final Net (เก็บเงินเพิ่มสุทธิ)',
        compute='_compute_jasper_final',
    )
    jasper_deposit_return = fields.Float(
        string='Deposit Return Net',
        compute='_compute_jasper_final',
    )
    jasper_deposit_return_text = fields.Char(
        string='Deposit Return Text',
        compute='_compute_jasper_final',
    )
    jasper_final_label = fields.Char(
        string='Final Label',
        compute='_compute_jasper_final',
    )
    jasper_total_weight = fields.Float(
        string='Total Weight',
        compute='_compute_jasper_total_weight',
    )
    jasper_note_clean = fields.Char(
        string='Note (clean)',
        compute='_compute_jasper_note',
    )
    jasper_company_logo = fields.Binary(
        string='Company Logo',
        compute='_compute_jasper_company_logo',
    )
    jasper_create_user_name = fields.Char(
        string='Create User Name',
        compute='_compute_jasper_create_info',
    )
    jasper_create_date_str = fields.Char(
        string='Create Date',
        compute='_compute_jasper_create_info',
    )

    @api.depends('start_x_date', 'end_x_date', 'return_date', 'create_date')
    def _compute_jasper_dates(self):
        for rec in self:
            rec.jasper_start_date_thai = format_thai_date(rec.start_x_date)
            rec.jasper_end_date_thai = format_thai_date(rec.end_x_date)
            return_d = rec.return_date.date() if rec.return_date else False
            rec.jasper_return_date_thai = format_thai_date(return_d)
            if rec.create_date:
                rec.jasper_document_time = (rec.create_date + timedelta(hours=7)).strftime('%H:%M:%S')
            else:
                rec.jasper_document_time = ''

    def _compute_jasper_print(self):
        now = datetime.now() + timedelta(hours=7)
        for rec in self:
            rec.jasper_print_date = now.strftime('%d/%m/%Y')
            rec.jasper_print_time = now.strftime('%H:%M:%S')

    @api.depends('start_x_date', 'end_x_date', 'return_date')
    def _compute_jasper_days(self):
        for rec in self:
            days_used = 0
            rent_days = 0
            if rec.start_x_date and rec.return_date:
                return_d = rec.return_date.date()
                if return_d == rec.start_x_date:
                    days_used = 1
                else:
                    days_used = (return_d - rec.start_x_date).days
            if rec.start_x_date and rec.end_x_date:
                if rec.end_x_date == rec.start_x_date:
                    rent_days = 1
                else:
                    rent_days = (rec.end_x_date - rec.start_x_date).days
            rec.jasper_days_used = days_used
            rec.jasper_rent_days = rent_days

    @api.depends('partner_id')
    def _compute_jasper_partner_address(self):
        for rec in self:
            p = rec.partner_id
            parts = []
            if p:
                for v in [p.street, p.street2, p.city, p.state_id.name if p.state_id else '', p.zip]:
                    if v:
                        parts.append(str(v))
                phone = f" [{p.phone}]" if p.phone else ''
                rec.jasper_partner_address = ' '.join(parts) + phone
            else:
                rec.jasper_partner_address = ''

    @api.depends('branch_id')
    def _compute_jasper_branch_address(self):
        for rec in self:
            if rec.branch_id and hasattr(rec.branch_id, 'address'):
                rec.jasper_branch_address = rec.branch_id.address or ''
            else:
                rec.jasper_branch_address = ''

    @api.depends('sale_id', 'jasper_days_used', 'jasper_rent_days')
    def _compute_jasper_summary(self):
        for rec in self:
            so = rec.sale_id
            amount_total = so.amount_total if so else 0.0
            pfb_amount = so.pfb_amount if so and hasattr(so, 'pfb_amount') else 0.0
            total_rental_discount = getattr(so, 'total_rental_discount', 0.0) if so else 0.0

            rent_days = rec.jasper_rent_days or 1
            days_used = rec.jasper_days_used or 0

            rental_per_day = amount_total / rent_days if rent_days else 0.0
            total_rent = rental_per_day * days_used
            rental_start = amount_total + total_rental_discount

            rec.jasper_rental_start = rental_start
            rec.jasper_insurance_amount = pfb_amount
            rec.jasper_rental_per_day = rental_per_day
            rec.jasper_total_rent = total_rent

            rent_diff = rec._calculate_rent_diff(total_rent, amount_total)
            rec.jasper_rent_diff = rent_diff

            approval_state = getattr(rec, 'approval_state', '')
            rent_discount = getattr(rec, 'rent_discount', 0.0) if approval_state == 'approved' else 0.0
            rec.jasper_rent_discount = rent_discount
            rec.jasper_rent_diff_net = rent_diff - rent_discount

    def _calculate_rent_diff(self, total_rent, amount_total):
        self.ensure_one()
        so = self.sale_id
        if not so:
            return 0.0

        base_diff = total_rent - amount_total

        deposit_ref = so.deposit_ref or '' if hasattr(so, 'deposit_ref') else ''
        deposit_count = len([x for x in deposit_ref.split(',') if x.strip()]) if deposit_ref else 0

        campaign_name = so.campaign_id.name if hasattr(so, 'campaign_id') and so.campaign_id else ''
        pricelist_name = so.pricelist_id.name if so.pricelist_id else ''
        return_d = self.return_date.date() if self.return_date else False

        free_campaigns = ['โปร 2026 ส่งฟรีไม่เกิน 25 Km.', 'โปร 2026 ส่งฟรีไม่เกิน 35 Km.']

        if deposit_count == 0:
            if campaign_name in free_campaigns:
                if return_d and self.end_x_date and return_d > self.end_x_date:
                    return base_diff
                return 0.0

            if 'เรทเดือน' in pricelist_name:
                is_referenced = self.env['sale.order'].search([
                    ('deposit_ref', '=', so.name),
                    ('state', '=', 'sale'),
                ], limit=1)

                if not is_referenced and return_d and self.end_x_date:
                    if return_d <= self.end_x_date:
                        return 0.0
                    return base_diff
                if is_referenced and return_d and self.end_x_date:
                    if return_d > self.end_x_date:
                        return base_diff
                    return 0.0

                diff_days = self.jasper_days_used or 0
                if diff_days < 30:
                    return 0.0
                return base_diff

            return base_diff

        deposit_refs = [ref.strip() for ref in deposit_ref.split(',') if ref.strip()]
        related_pickings = self.env['stock.picking'].search([
            ('group_id.name', 'in', deposit_refs),
        ])
        has_diff_end = any(rp.end_x_date != self.end_x_date for rp in related_pickings)

        if related_pickings and not has_diff_end and return_d and self.end_x_date and return_d <= self.end_x_date:
            if campaign_name in free_campaigns:
                return 0.0
            if 'เรทเดือน' in pricelist_name:
                diff_days = self.jasper_days_used or 0
                if diff_days < 30:
                    return 0.0
            return base_diff

        return base_diff

    @api.depends('sale_id')
    def _compute_jasper_debit(self):
        for rec in self:
            total_d = 0.0
            total_l = 0.0
            discount_total_d = 0.0

            so = rec.sale_id
            if so:
                for inv in so.invoice_ids:
                    for de in getattr(inv, 'debit_note_ids', []):
                        if de.state != 'posted':
                            continue
                        tag_name = 0
                        reason = de.reason_code_id.name if hasattr(de, 'reason_code_id') and de.reason_code_id else ''
                        for line in de.invoice_line_ids:
                            for tag in getattr(line, 'analytic_tag_ids', []):
                                if tag.name == 'D' and reason == 'สินค้าชำรุด':
                                    tag_name = 1
                                if tag.name == 'L' and reason == 'สินค้าหาย':
                                    tag_name = 2
                                    if getattr(line, 'discount_method', '') == 'per':
                                        discount_total_d += (line.quantity * line.price_unit) * getattr(line, 'discount_amount', 0.0) / 100.0
                                    else:
                                        discount_total_d += getattr(line, 'discount_amount', 0.0)

                        if tag_name == 1:
                            total_d += getattr(de, 'amount_price_total_full', de.amount_total)
                        elif tag_name == 2:
                            lost_lines = [ln for ln in de.invoice_line_ids if getattr(ln, 'is_lost_item', False)]
                            if lost_lines:
                                total_l += sum(getattr(ln, 'price_total_full', ln.price_total) for ln in lost_lines)
                            else:
                                total_l += getattr(de, 'amount_price_total_full', de.amount_total)

            rec.jasper_total_damaged = total_d
            rec.jasper_total_lost = total_l
            rec.jasper_discount_lost = discount_total_d

    @api.depends('jasper_rent_diff_net', 'jasper_total_lost', 'jasper_total_damaged', 'jasper_discount_lost', 'sale_id', 'no_deduction')
    def _compute_jasper_final(self):
        for rec in self:
            final_net = (rec.jasper_rent_diff_net + rec.jasper_total_lost + rec.jasper_total_damaged) - rec.jasper_discount_lost
            rec.jasper_final_net = final_net

            if final_net < 0:
                rec.jasper_final_label = 'คืนเงินสุทธิ'
            else:
                rec.jasper_final_label = 'เก็บเงินเพิ่มสุทธิ'

            so = rec.sale_id
            pfb_amount = so.pfb_amount if so and hasattr(so, 'pfb_amount') else 0.0
            if rec.no_deduction:
                rec.jasper_deposit_return = pfb_amount
            else:
                rec.jasper_deposit_return = pfb_amount - final_net

            try:
                from bahttext import bahttext
            except ImportError:
                bahttext = None
            if bahttext:
                rec.jasper_deposit_return_text = bahttext(rec.jasper_deposit_return)
            else:
                rec.jasper_deposit_return_text = ''

    @api.depends('sale_id')
    def _compute_jasper_total_weight(self):
        for rec in self:
            total = 0.0
            so = rec.sale_id
            if so:
                for line in so.order_line:
                    if line.price_subtotal >= 0:
                        total += (getattr(line, 'second_uom_qty', 0.0) or 0.0) * (getattr(line, 'pfb_quantity', 0.0) or 0.0)
            rec.jasper_total_weight = total

    @api.depends('note')
    def _compute_jasper_note(self):
        for rec in self:
            note = rec.note or ''
            if isinstance(note, str):
                note = note.replace('<p>', '').replace('</p>', '').replace('<br>', ' ').replace('<br/>', ' ')
            rec.jasper_note_clean = note

    @api.depends('company_id')
    def _compute_jasper_company_logo(self):
        for rec in self:
            rec.jasper_company_logo = rec.company_id.logo if rec.company_id else False

    # ที่อยู่บริษัทของเอกสาร (เปลี่ยนตามบริษัทที่เลือก) — ประกอบจาก res.company
    # เดิม header ใช้ branch_id.address ซึ่งมักว่าง ทำให้ที่อยู่ไม่แสดง
    jasper_company_address = fields.Char(
        string='Company Address',
        compute='_compute_jasper_company_address',
    )

    @api.depends('company_id')
    def _compute_jasper_company_address(self):
        for rec in self:
            c = rec.company_id
            parts = []
            if c:
                for v in [c.street, c.street2, c.city,
                          c.state_id.name if c.state_id else '', c.zip]:
                    if v:
                        parts.append(str(v))
            rec.jasper_company_address = ' '.join(parts)

    @api.depends('sale_id')
    def _compute_jasper_create_info(self):
        for rec in self:
            so = rec.sale_id
            rec.jasper_create_user_name = so.create_uid.name if so and so.create_uid else ''
            if so and so.create_date:
                rec.jasper_create_date_str = so.create_date.strftime('%d/%m/%Y')
            else:
                rec.jasper_create_date_str = ''
