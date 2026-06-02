import logging
from odoo import models, fields, api
from odoo.tools import format_date

_logger = logging.getLogger(__name__)

# ข้อความบัญชีธนาคารคงที่ (ตามรายงานเดิม odoo14)
BANK_TRANSFER_LINE = (
    'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6'
)


def _safe(obj, attr, default=''):
    """ ดึงค่า attribute แบบปลอดภัย (กัน field ไม่มี/ค่าว่าง) """
    if not obj:
        return default
    try:
        val = getattr(obj, attr, default)
    except Exception:
        return default
    if val is False or val is None:
        return default
    return val


def _join(*parts):
    return ' '.join(str(p) for p in parts if p)


def _money(val):
    try:
        return '{:,.2f}'.format(float(val or 0.0))
    except Exception:
        return '0.00'


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ---- ฟิลด์สำหรับ Jasper (header) ----
    jasper_company_logo = fields.Binary(
        string='Company Logo', compute='_compute_jasper_shipping_header')
    jasper_company_name = fields.Char(
        string='Company Name', compute='_compute_jasper_shipping_header')
    jasper_company_address = fields.Char(
        string='Company Address', compute='_compute_jasper_shipping_header')
    jasper_doc_date_return = fields.Char(
        string='Return Date', compute='_compute_jasper_shipping_header')

    # ---- ผู้ส่ง / ผู้รับ ----
    jasper_origin = fields.Char(
        string='Origin', compute='_compute_jasper_shipping_parties')
    jasper_sender_name = fields.Char(
        string='Sender Name', compute='_compute_jasper_shipping_parties')
    jasper_sender_address = fields.Char(
        string='Sender Address', compute='_compute_jasper_shipping_parties')
    jasper_destination = fields.Char(
        string='Destination', compute='_compute_jasper_shipping_parties')
    jasper_receiver_name = fields.Char(
        string='Receiver Name', compute='_compute_jasper_shipping_parties')
    jasper_receiver_address = fields.Char(
        string='Receiver Address', compute='_compute_jasper_shipping_parties')

    # ---- ตัวเลข ----
    jasper_shipping_cost = fields.Char(
        string='Shipping Cost', compute='_compute_jasper_shipping_numbers')
    jasper_distance = fields.Char(
        string='Distance (km)', compute='_compute_jasper_shipping_numbers')
    jasper_total_weight = fields.Char(
        string='Total Weight', compute='_compute_jasper_shipping_numbers')

    # ---- footer ----
    jasper_note = fields.Char(
        string='Note', compute='_compute_jasper_shipping_footer')
    jasper_bank_transfer_line = fields.Char(
        string='Bank Transfer Line', compute='_compute_jasper_shipping_footer')
    jasper_officer_name = fields.Char(
        string='Officer Name', compute='_compute_jasper_shipping_footer')
    jasper_driver_info = fields.Char(
        string='Driver Info', compute='_compute_jasper_shipping_footer')

    # ---- รายการสินค้า (สำหรับ ODOO_RELATIONS) ----
    jasper_ship_line_ids = fields.Many2many(
        'sale.order.line', compute='_compute_jasper_ship_lines',
        string='Shipping Lines')

    def _compute_jasper_shipping_header(self):
        for rec in self:
            company = rec.company_id
            rec.jasper_company_logo = _safe(company, 'logo', False) or False
            rec.jasper_company_name = _safe(company, 'name', '')
            state = _safe(_safe(company, 'state_id', False), 'name', '')
            rec.jasper_company_address = _join(
                _safe(company, 'street', ''),
                _safe(company, 'street2', ''),
                _safe(company, 'city', ''),
                state,
                _safe(company, 'zip', ''),
            )
            # วันที่ส่งคืนสินค้า = commitment_date ของ sale order (dd/MM/yyyy)
            date_return = ''
            sale = _safe(rec, 'sale_id', False)
            commit = _safe(sale, 'commitment_date', False)
            if commit:
                try:
                    date_return = format_date(
                        self.env, commit, date_format='dd/MM/yyyy')
                except Exception:
                    date_return = ''
            rec.jasper_doc_date_return = date_return

    def _compute_jasper_shipping_parties(self):
        for rec in self:
            sale = _safe(rec, 'sale_id', False)
            employee = _safe(sale, 'delivery_employee_id', False)
            partner = _safe(sale, 'partner_id', False)
            partner_ship = _safe(sale, 'partner_shipping_id', False)
            delivery_type = _safe(sale, 'delivery_type', 'customer')
            emp_loc = (
                _safe(_safe(employee, 'work_location_id', False), 'name', '')
                or _safe(employee, 'work_location', '')
            )
            rec.jasper_origin = _safe(sale, 'pickup_location', '')
            rec.jasper_destination = _safe(sale, 'destination', '')
            if delivery_type == 'customer':
                # ผู้ส่ง = พนักงานส่งของ ; ผู้รับ = ลูกค้า
                rec.jasper_sender_name = _safe(employee, 'name', '')
                rec.jasper_sender_address = emp_loc
                rec.jasper_receiver_name = _safe(partner, 'name', '')
                rec.jasper_receiver_address = _safe(partner_ship, 'street', '')
            else:
                # ผู้ส่ง = ลูกค้า ; ผู้รับ = พนักงานส่งของ
                rec.jasper_sender_name = _safe(partner, 'name', '')
                rec.jasper_sender_address = _safe(partner_ship, 'street', '')
                rec.jasper_receiver_name = _safe(employee, 'name', '')
                rec.jasper_receiver_address = emp_loc

    def _compute_jasper_shipping_numbers(self):
        for rec in self:
            sale = _safe(rec, 'sale_id', False)
            shipping_cost = _safe(sale, 'shipping_cost', 0.0) or 0.0
            shipping_cost_m = _safe(sale, 'shipping_cost_m', 0.0) or 0.0
            use_zero = _safe(sale, 'use_special_delivery_zero', False)
            # เงื่อนไขเดียวกับรายงานเดิม
            if use_zero and shipping_cost_m == 0:
                final_cost = shipping_cost_m
            elif (not use_zero) and shipping_cost_m > 0:
                final_cost = shipping_cost_m
            else:
                final_cost = shipping_cost
            rec.jasper_shipping_cost = _money(final_cost)
            rec.jasper_distance = '{:,.3f}'.format(
                float(_safe(sale, 'distance_km', 0.0) or 0.0))
            # น้ำหนักรวมสุทธิ์
            total_weight = 0.0
            for line in rec.jasper_ship_line_ids:
                total_weight += float(_safe(line, 'total_weight', 0.0) or 0.0)
            rec.jasper_total_weight = _money(total_weight)

    def _compute_jasper_shipping_footer(self):
        for rec in self:
            sale = _safe(rec, 'sale_id', False)
            note = _safe(rec, 'note', '')
            # note อาจเป็น html -> ตัด tag คร่าวๆ
            if note:
                import re
                note = re.sub(r'<[^>]+>', '', str(note)).strip()
            rec.jasper_note = note or 'ไม่มีหมายเหตุ'
            rec.jasper_bank_transfer_line = BANK_TRANSFER_LINE
            rec.jasper_officer_name = _safe(self.env.user, 'name', '')
            plate = _safe(_safe(sale, 'license_plate_id', False), 'name', '')
            driver = _safe(
                _safe(sale, 'delivery_employee_id', False), 'name', '')
            if plate and driver:
                rec.jasper_driver_info = '%s : %s' % (plate, driver)
            else:
                rec.jasper_driver_info = plate or driver or ''

    def _compute_jasper_ship_lines(self):
        for rec in self:
            sale = _safe(rec, 'sale_id', False)
            lines = sale.order_line if sale else rec.env['sale.order.line']
            rec.jasper_ship_line_ids = lines.filtered(
                lambda l: not l.display_type
                and (l.price_subtotal or 0.0) >= 0
            )
