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


# --- แปลงจำนวนเงินเป็นตัวอักษรภาษาไทย (pure-Python ไม่พึ่ง lib bahttext) ---
# server ไม่มี bahttext ทำให้เดิม fallback ไปแสดงตัวเลข ("10.7") -> เขียนเองให้ทำงานทุกเครื่อง
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
        # รูปแบบไทยแบบยาว "08 กรกฎาคม 2568" ให้ตรงกับ O14 (หัวเอกสาร บรรทัด "วันที่")
        for rec in self:
            rec.jasper_date_order_thai = _format_thai_date(rec.date_order)

    # --- เลขที่สัญญาเช่าเต็ม (อ่านจากโมดูล rental contract ถ้ามี) ---
    jasper_contract_full = fields.Char(
        string='Rental Contract Full',
        compute='_compute_jasper_contract_full',
    )

    def _compute_jasper_contract_full(self):
        # rental_contract_full เป็นฟิลด์ที่โมดูล pfb_npd_rental_equipment_contract_jasper
        # เพิ่มบน sale.order — อ่านแบบปลอดภัยเผื่อโมดูลนั้นไม่ได้ติดตั้ง
        for rec in self:
            rec.jasper_contract_full = getattr(rec, 'rental_contract_full', '') or ''

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
    # Many2one ชี้บริษัทที่กำลังเลือกอยู่ เพื่อให้ jasper_reports ดึง logo ผ่าน relation
    # (export เป็นไฟล์รูปเอง เหมือน Company-company_id/Logo-logo เดิม)
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

    # --- Baht text ---
    jasper_baht_text_rental = fields.Char(
        string='Baht Text Rental',
        compute='_compute_jasper_baht_text_rental',
    )

    @api.depends('amount_total', 'pfb_amount')
    def _compute_jasper_baht_text_rental(self):
        for rec in self:
            total_amount = (rec.amount_total or 0.0) + (rec.pfb_amount or 0.0)
            rec.jasper_baht_text_rental = _baht_text(total_amount)

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

    # ค่าเช่าต่อวันรวม(vat) = ยอดรวมสุทธิ / จำนวนวันเช่า (end_rent_date - start_rent_date)
    @api.depends('amount_total', 'start_rent_date', 'end_rent_date')
    def _compute_jasper_rental_per_day(self):
        for rec in self:
            days = 0
            if rec.start_rent_date and rec.end_rent_date:
                days = (rec.end_rent_date - rec.start_rent_date).days
            if not days:
                days = 1
            rec.jasper_rental_per_day = (rec.amount_total or 0.0) / days

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

    # --- เบอร์โทรผู้เซ็นฝั่งผู้เช่า (เทียบ user.partner_id.phone ฝั่ง O14) ---
    jasper_user_phone = fields.Char(
        string='Signer Phone',
        compute='_compute_jasper_user_phone',
    )

    def _compute_jasper_user_phone(self):
        user = self.env.user
        partner = user.partner_id
        phone = (partner.phone or partner.mobile or '') if partner else ''
        for rec in self:
            rec.jasper_user_phone = phone

    # --- เงื่อนไขข้อ 5-7 (เลขบัญชี) ต่อบริษัท ---
    # O14 เลือกด้วย request.db (แยก DB ต่อบริษัท) -> O18 single-DB เลือกด้วย
    # บริษัทที่กำลังใช้งาน (env.company) โดย match จาก token ในชื่อบริษัท
    # ข้อ 7 (ค่าขนส่ง) ใช้บัญชี เอ็นพีดี โลจิสติกส์ เหมือนกันทุกบริษัท
    # บริษัทโลจิสติกส์เองไม่มีข้อ 6 (ค่าเช่า) -> ค่าขนส่งเลื่อนเป็นข้อ 6
    jasper_rent_conditions = fields.Char(
        string='Rent Conditions 5-7',
        compute='_compute_jasper_rent_conditions',
    )

    def _compute_jasper_rent_conditions(self):
        transport = (u'ค่าขนส่ง.สินค้า โอนเงินเข้าบัญชี : บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด '
                     u'ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6')
        # token ในชื่อบริษัท -> (ข้อ5 ค่าประกัน, ข้อ6 ค่าเช่า | None ถ้าไม่มี)
        table = [
            (u'อินเตอร์เทรดดิ้ง',
             u'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด กสิกรไทย เลขที่บัญชี 033-885651-2',
             u'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-546107-1'),
            (u'กรุงเทพ',
             u'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล กรุงเทพ จำกัด กสิกรไทย เลขที่บัญชี 025-290298-8',
             u'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท นภดล กรุงเทพ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-224773-9'),
            (u'กรุ๊ป',
             u'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท นภดล เอส กรุ๊ป จำกัด กสิกรไทย เลขที่บัญชี 020-893777-4',
             u'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท นภดล เอส กรุ๊ป จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-222160-2'),
            (u'สตีลเทค',
             u'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี สตีลเทค จำกัด กสิกรไทย เลขที่บัญชี 035-1-39757-8',
             u'ค่าเช่าสินค้า โอนเงินเข้าบัญชี : บช.บริษัท เอ็นพีดี สตีลเทค จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-582058-4'),
            (u'โลจิสติกส์',
             u'ค่าประกันสินค้า โอนเงินเข้าบัญชี บช.บริษัท เอ็นพีดี โลจิสติกส์ จำกัด กสิกรไทย เลขที่บัญชี 117-1-78329-8',
             None),
        ]
        company_name = self.env.company.name or ''
        insurance = rent = None
        for token, ins, rnt in table:
            if token in company_name:
                insurance, rent = ins, rnt
                break

        if insurance is None:
            text = ''
        else:
            num = 5
            lines = [u'%d.  %s' % (num, insurance)]
            num += 1
            if rent:
                lines.append(u'%d.  %s' % (num, rent))
                num += 1
            lines.append(u'%d.  %s' % (num, transport))
            text = u'\n'.join(lines)

        for rec in self:
            rec.jasper_rent_conditions = text


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

    # ค่าเช่าต่อหน่วย (ถอด VAT 7% แบบ price-included) เทียบเท่า price_unit_no_vat ฝั่ง Odoo 14
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

    jasper_daily_rental_total = fields.Float(
        string='Daily Rental Total',
        compute='_compute_jasper_daily_rental_total',
    )

    @api.depends('price_subtotal')
    def _compute_jasper_daily_rental_total(self):
        for line in self:
            line.jasper_daily_rental_total = line.price_subtotal or 0.0
