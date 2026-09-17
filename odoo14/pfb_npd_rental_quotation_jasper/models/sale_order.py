import pytz

from odoo import models, fields, api

THAI_MONTHS = {
    1: 'มกราคม', 2: 'กุมภาพันธ์', 3: 'มีนาคม', 4: 'เมษายน',
    5: 'พฤษภาคม', 6: 'มิถุนายน', 7: 'กรกฎาคม', 8: 'สิงหาคม',
    9: 'กันยายน', 10: 'ตุลาคม', 11: 'พฤศจิกายน', 12: 'ธันวาคม',
}


def _thai_long_date(value):
    """'17 กันยายน 2569' แบบหัวเอกสาร o14 (datetime แปลงเป็นเวลาไทยก่อน)"""
    if not value:
        return ''
    if hasattr(value, 'hour'):
        value = pytz.utc.localize(value).astimezone(pytz.timezone('Asia/Bangkok'))
    return '%s %s %s' % (value.strftime('%d'), THAI_MONTHS[value.month], value.year + 543)


# --- แปลงจำนวนเงินเป็นตัวอักษรภาษาไทย (pure-Python ไม่พึ่ง lib bahttext) ---
# server ไม่มี bahttext ทำให้เดิม fallback ไปแสดงตัวเลข -> เขียนเองให้ทำงานทุกเครื่อง
_THAI_DIGITS = ['ศูนย์', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
_THAI_UNITS = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน']


def _read6_thai(chunk):
    res = ''
    length = len(chunk)
    for i, ch in enumerate(chunk):
        d = int(ch)
        pos = length - i - 1
        if d == 0:
            continue
        if pos == 0 and d == 1 and length > 1:
            res += 'เอ็ด'
        elif pos == 1 and d == 2:
            res += 'ยี่สิบ'
        elif pos == 1 and d == 1:
            res += 'สิบ'
        else:
            res += _THAI_DIGITS[d] + _THAI_UNITS[pos]
    return res


def _num_to_thai(number):
    number = int(number)
    if number == 0:
        return 'ศูนย์'
    s = str(number)
    groups = []
    while s:
        groups.insert(0, s[-6:])
        s = s[:-6]
    n = len(groups)
    text = ''
    for idx, g in enumerate(groups):
        part = _read6_thai(g)
        if part:
            text += part + ('ล้าน' * (n - idx - 1))
    return text


def _baht_text(amount):
    amount = round(float(amount or 0.0), 2)
    baht = int(amount)
    satang = int(round((amount - baht) * 100))
    if satang == 0:
        return _num_to_thai(baht) + 'บาทถ้วน'
    return _num_to_thai(baht) + 'บาท' + _num_to_thai(satang) + 'สตางค์'


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
        for rec in self:
            total_amount = (rec.amount_total or 0.0) + (rec.pfb_amount or 0.0)
            rec.jasper_baht_text_rental = _baht_text(total_amount)

    @api.depends('order_line.second_uom_qty', 'order_line.pfb_quantity')
    def _compute_jasper_total_weight(self):
        for rec in self:
            rec.jasper_total_weight = sum(
                (line.second_uom_qty or 0.0) * (line.pfb_quantity or 0.0)
                for line in rec.order_line
            )

    # ค่าเช่าต่อวัน = amount_total / pfb_date_of_rent (o14 ทั้งใบเสนอราคาและใบกำกับการเช่า)
    # ฟิลด์นี้ประกาศซ้ำในใบกำกับการเช่า Jasper -> สูตรต้องเหมือนกันทั้งสองโมดูล
    @api.depends('amount_total', 'pfb_date_of_rent')
    def _compute_jasper_rental_per_day(self):
        for rec in self:
            rec.jasper_rental_per_day = (rec.amount_total or 0.0) / (rec.pfb_date_of_rent or 1)

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
    # ข้อความคัดลอกจากใบเสนอราคาเช่าสินค้า o14 (server) ตรงตัว
    _JASPER_BANK_TRANSPORT = ('ค่าขนส่ง.สินค้า โอนเงินเข้าบัญชี : บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด '
                              'ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6')
    _JASPER_BANK_BY_REGISTRY = {
        '1': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล กรุงเทพ จำกัด กสิกรไทย เลขที่บัญชี 025-290298-8\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท นภดล กรุงเทพ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-224773-9\n'
            + _JASPER_BANK_TRANSPORT
        ),
        '2': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด กสิกรไทย เลขที่บัญชี 033-885651-2\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-546107-1\n'
            + _JASPER_BANK_TRANSPORT
        ),
        '3': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล เอส กรุ๊ป จํากัด กสิกรไทย เลขที่บัญชี 020-893777-4\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท นภดล เอส กรุ๊ป จํากัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-222160-2\n'
            + _JASPER_BANK_TRANSPORT
        ),
        '4': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี สตีลเทค จำกัด กสิกรไทย เลขที่บัญชี 035-1-39757-8\n'
            'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท เอ็นพีดี สตีลเทค จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-582058-4\n'
            + _JASPER_BANK_TRANSPORT
        ),
        '5': (
            'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด กสิกรไทย เลขที่บัญชี 117-1-78329-8\n'
            + _JASPER_BANK_TRANSPORT
        ),
    }

    # --- ส่วนที่ปรับตามใบเสนอราคาเช่าสินค้า o14 (server) ---
    jasper_rq_date_order_thai = fields.Char(
        string='Quotation Date (Thai)',
        compute='_compute_jasper_rq_values',
    )
    jasper_rq_company_address = fields.Char(
        string='Quotation Company Address',
        compute='_compute_jasper_rq_values',
    )
    jasper_rq_vat_line = fields.Char(
        string='Quotation VAT Line',
        compute='_compute_jasper_rq_values',
    )
    jasper_rq_shipping_cost = fields.Float(
        string='Quotation Shipping Cost',
        compute='_compute_jasper_rq_values',
    )
    jasper_rq_line_count = fields.Integer(
        string='Quotation Line Count',
        compute='_compute_jasper_rq_values',
    )

    @staticmethod
    def _jasper_rq_join_address(parts):
        """ต่อที่อยู่โดยข้ามส่วนที่มีอยู่ในข้อความแล้ว (เหมือนใบแจ้งหนี้/ใบวางบิล Jasper)"""
        text = ''
        for part in parts:
            part = (part or '').strip()
            if not part:
                continue
            core = part[2:] if part.startswith('จ.') else part
            if core in text:
                continue
            text = ('%s %s' % (text, part)).strip()
        return text

    @api.depends_context('allowed_company_ids')
    @api.depends('date_order', 'order_line', 'shipping_cost', 'shipping_cost_m', 'use_special_delivery_zero')
    def _compute_jasper_rq_values(self):
        company = self.env.company
        address = self._jasper_rq_join_address([
            company.street, company.street2, company.city,
            company.state_id.name if company.state_id else '', company.zip])
        head_office = '' if company.parent_id else '(สำนักงานใหญ่)'
        # o14 ฐาน NPD_S_Group_New_V2 / NPD_Bangkok_New ไม่แสดงเลขผู้เสียภาษี (แสดงแค่สำนักงานใหญ่)
        if any(token in (company.name or '') for token in ('กรุ๊ป', 'กรุงเทพ')):
            vat_line = head_office
        else:
            vat_line = ('เลขที่ผู้เสียภาษี : %s %s' % (company.vat or '', head_office)).strip()
        for rec in self:
            rec.jasper_rq_date_order_thai = _thai_long_date(rec.date_order)
            rec.jasper_rq_company_address = address
            rec.jasper_rq_vat_line = vat_line
            rec.jasper_rq_line_count = len(rec.order_line)
            # ค่าขนส่ง: ค่าขนส่งพิเศษ (shipping_cost_m) ถ้ามี ไม่งั้นค่าขนส่งปกติ ตามเงื่อนไข o14
            special = rec.shipping_cost_m or 0.0
            if rec.use_special_delivery_zero:
                rec.jasper_rq_shipping_cost = 0.0 if special == 0 else (rec.shipping_cost or 0.0)
            else:
                rec.jasper_rq_shipping_cost = special if special > 0 else (rec.shipping_cost or 0.0)

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
    # ชื่อสินค้าแบบ o14 (product_template_id.name) — ประกาศเหมือนกันในใบกำกับการเช่า Jasper
    jasper_product_name = fields.Char(
        string='Product Name',
        compute='_compute_jasper_product_name',
    )

    @api.depends('product_template_id', 'product_id', 'name')
    def _compute_jasper_product_name(self):
        for line in self:
            line.jasper_product_name = (line.product_template_id.name
                                        or line.product_id.name or line.name or '')

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
