# -*- coding: utf-8 -*-
"""ค่าเสื่อมราคาสินทรัพย์แบบ NPD -- สูตรและข้อมูลตั้งต้นบนตัวสินทรัพย์

สูตรทั้งหมดอยู่ที่ npd_month_depreciation() ที่เดียว ทั้งตัวคำนวณและรายงาน
เรียกใช้ตัวนี้ตัวเดียวกัน ตัวเลขบนจอกับในรายงานจึงตรงกันเสมอ
"""
import calendar
import logging
import re
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

# ตัวย่อหน้าเลขทะเบียนทรัพย์สิน แยกตามบริษัท
# o14 แยกตามชื่อฐานข้อมูล (1 ฐาน = 1 บริษัท) o18 อยู่ฐานเดียวจึงดูจากชื่อบริษัทแทน
# (คำในชื่อบริษัท, ตัวย่อ, เลขถัดไปตอนสร้างครั้งแรก = เลขล่าสุดของ o14 + 1 ณ 15 ก.ย. 2569)
COMPANY_ASSET_PREFIX = [
    ('เอส กรุ๊ป', 'SG-', 1064),
    ('อินเตอร์เทรดดิ้ง', 'IN-', 46),
    ('สตีลเทค', 'ST-', 188),
    ('กรุงเทพ', 'NB-', 659),
    ('โลจิสติกส์', 'LG-', 161),
]
FALLBACK_ASSET_PREFIX = 'AST-'
ASSET_SEQUENCE_CODE = 'npd.asset.number'

# ปกติทรัพย์สินไทยเหลือมูลค่าซาก 1 บาทไว้จนกว่าจะตัดจำหน่าย
DEFAULT_SALVAGE = 1.0

# ปีฐานที่ใช้เฉลี่ยค่าเสื่อมรายวัน (ไฟล์ Excel ใช้ 365 วันคงที่ ไม่สนปีอธิกสุรทิน)
DAYS_PER_YEAR = 365.0


def month_range(year, month):
    """(วันแรก, วันสุดท้าย) ของเดือนนั้น"""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def npd_month_depreciation(cost, rate_pct, buy_date, mstart, mend,
                           opening, salvage=DEFAULT_SALVAGE):
    """ค่าเสื่อมของสินทรัพย์ 1 ตัวใน 1 เดือน -- สูตรเดียวกับไฟล์ Excel

    :param cost:     ราคาทรัพย์สิน (ใช้เป็นฐานคิดค่าเสื่อมเสมอ ไม่ใช่ยอดคงเหลือ)
    :param rate_pct: ร้อยละต่อปี เช่น 20 = 20%
    :param buy_date: วันที่ซื้อ (ค.ศ.)
    :param mstart:   วันแรกของเดือน
    :param mend:     วันสุดท้ายของเดือน
    :param opening:  ยอดยกมาต้นเดือน
    :param salvage:  มูลค่าซากที่ต้องเหลือไว้
    :return: (จำนวนวัน, ค่าเสื่อม)
    """
    if not cost or not buy_date:
        return 0, 0.0
    if buy_date > mend:
        # ยังไม่ได้ซื้อในเดือนนี้
        return 0, 0.0

    if buy_date > mstart:
        # เดือนที่ซื้อ -- คิดตั้งแต่วันที่ซื้อถึงสิ้นเดือน (นับวันที่ซื้อด้วย)
        days = (mend - buy_date).days + 1
    else:
        days = (mend - mstart).days + 1

    room = (opening or 0.0) - salvage
    if room <= 0:
        # ตัดจนเหลือมูลค่าซากแล้ว ไม่ต้องคิดต่อ
        return days, 0.0

    dep = cost * (rate_pct or 0.0) / 100.0 * days / DAYS_PER_YEAR
    if dep > room:
        dep = room          # เดือนสุดท้าย ตัดแค่ที่เหลือ ไม่ให้ต่ำกว่ามูลค่าซาก
    if dep < 0:
        dep = 0.0
    return days, round(dep, 2)


class AccountAssetProfile(models.Model):
    _inherit = 'account.asset.profile'

    npd_code = fields.Char(
        string='รหัสหมวด',
        size=8,
        help='รหัสย่อของหมวดสินทรัพย์ที่ใช้ในรายงาน เช่น RE EQ CA BD '
             'ถ้าเว้นว่างจะดึงตัวอักษรหน้าเครื่องหมาย - ของชื่อหมวดมาใช้แทน',
    )
    npd_depre_rate = fields.Float(
        string='ร้อยละค่าเสื่อมต่อปี',
        digits=(5, 2),
        help='อัตราตั้งต้นของหมวดนี้ ใส่เป็นตัวเลข เช่น 20 = 20% ต่อปี '
             'สินทรัพย์ที่สร้างใหม่จะดึงค่านี้ไปใช้ แก้รายตัวได้ภายหลัง',
    )

    def npd_category_code(self):
        """รหัสหมวดที่ใช้ในรายงาน (ไม่ได้ตั้งไว้ก็เดาจากชื่อ 'RE - ทรัพย์สินให้เช่า')"""
        self.ensure_one()
        if self.npd_code:
            return self.npd_code
        name = self.name or ''
        if '-' in name:
            return name.split('-')[0].strip()
        return ''

    def npd_category_name(self):
        """ชื่อหมวดล้วน ๆ ไม่มีรหัสนำหน้า (ชื่อเต็มเก็บรูป "BD - อาคาร")"""
        self.ensure_one()
        name = (self.name or '').strip()
        code = self.npd_code or ''
        if code and name.startswith(code):
            rest = name[len(code):].lstrip()
            if rest.startswith('-'):
                rest = rest[1:].strip()
            if rest:
                return rest
        if '-' in name:
            return name.split('-', 1)[1].strip()
        return name


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    npd_depre_rate = fields.Float(
        string='ร้อยละค่าเสื่อมต่อปี',
        digits=(5, 2),
        help='ใส่เป็นตัวเลข เช่น 20 = 20% ต่อปี เว้นว่างจะไม่คิดค่าเสื่อม',
    )
    npd_salvage_value = fields.Float(
        string='มูลค่าซากคงเหลือ',
        digits='Account',
        default=DEFAULT_SALVAGE,
        help='ยอดที่ต้องเหลือค้างไว้เสมอ ปกติคือ 1 บาท จนกว่าจะตัดจำหน่าย',
    )

    # ---- ยกยอดจากระบบเดิม ----------------------------------------------
    npd_opening_date = fields.Date(
        string='ยกยอด ณ วันที่',
        help='วันสุดท้ายที่ระบบเดิมคิดค่าเสื่อมไว้ เช่น 31/12/2025 '
             'ระบบจะเริ่มคิดต่อจากวันถัดไป ถ้าเว้นว่างจะไล่คิดตั้งแต่วันที่ซื้อ',
    )
    npd_opening_nbv = fields.Float(
        string='ยอดยกมา',
        digits='Account',
        help='มูลค่าคงเหลือ ณ วันที่ยกยอด (ราคาทรัพย์สิน - ค่าเสื่อมสะสม)',
    )

    # ---- ค่าเสื่อม 12 เดือนของปีที่แสดง (คัดลอกมาจากบรรทัดรายเดือน) ----
    npd_display_year = fields.Integer(
        string='ปีที่แสดง (ค.ศ.)',
        help='คอลัมน์รายเดือนในตารางนี้เป็นของปีนี้ '
             'เปลี่ยนได้ด้วยการสั่งคำนวณปีอื่นจากเมนูคำนวณค่าเสื่อมประจำปี',
    )
    npd_m01_open = fields.Float(string='ม.ค. ยอดยกมา', digits='Account')
    npd_m01_dep = fields.Float(string='ม.ค. ค่าเสื่อม', digits='Account')
    npd_m02_open = fields.Float(string='ก.พ. ยอดยกมา', digits='Account')
    npd_m02_dep = fields.Float(string='ก.พ. ค่าเสื่อม', digits='Account')
    npd_m03_open = fields.Float(string='มี.ค. ยอดยกมา', digits='Account')
    npd_m03_dep = fields.Float(string='มี.ค. ค่าเสื่อม', digits='Account')
    npd_m04_open = fields.Float(string='เม.ย. ยอดยกมา', digits='Account')
    npd_m04_dep = fields.Float(string='เม.ย. ค่าเสื่อม', digits='Account')
    npd_m05_open = fields.Float(string='พ.ค. ยอดยกมา', digits='Account')
    npd_m05_dep = fields.Float(string='พ.ค. ค่าเสื่อม', digits='Account')
    npd_m06_open = fields.Float(string='มิ.ย. ยอดยกมา', digits='Account')
    npd_m06_dep = fields.Float(string='มิ.ย. ค่าเสื่อม', digits='Account')
    npd_m07_open = fields.Float(string='ก.ค. ยอดยกมา', digits='Account')
    npd_m07_dep = fields.Float(string='ก.ค. ค่าเสื่อม', digits='Account')
    npd_m08_open = fields.Float(string='ส.ค. ยอดยกมา', digits='Account')
    npd_m08_dep = fields.Float(string='ส.ค. ค่าเสื่อม', digits='Account')
    npd_m09_open = fields.Float(string='ก.ย. ยอดยกมา', digits='Account')
    npd_m09_dep = fields.Float(string='ก.ย. ค่าเสื่อม', digits='Account')
    npd_m10_open = fields.Float(string='ต.ค. ยอดยกมา', digits='Account')
    npd_m10_dep = fields.Float(string='ต.ค. ค่าเสื่อม', digits='Account')
    npd_m11_open = fields.Float(string='พ.ย. ยอดยกมา', digits='Account')
    npd_m11_dep = fields.Float(string='พ.ย. ค่าเสื่อม', digits='Account')
    npd_m12_open = fields.Float(string='ธ.ค. ยอดยกมา', digits='Account')
    npd_m12_dep = fields.Float(string='ธ.ค. ค่าเสื่อม', digits='Account')

    npd_depre_line_ids = fields.One2many(
        comodel_name='npd.asset.depreciation.line',
        inverse_name='asset_id',
        string='ค่าเสื่อมรายเดือน',
    )
    npd_depre_line_count = fields.Integer(
        string='จำนวนเดือนที่คำนวณแล้ว',
        compute='_compute_npd_depre_line_count',
    )

    # ยอดคงเหลือ/ค่าเสื่อมสะสม ที่คิดจากบรรทัดค่าเสื่อมของโมดูลนี้
    # (ช่องเดิมของ OCA เป็นตัวเลขจากเครื่องคำนวณที่เราไม่ได้ใช้ จึงซ่อนไปแล้ว)
    npd_value_residual = fields.Float(
        string='มูลค่าคงเหลือ',
        digits='Account',
        compute='_compute_npd_values',
        help='ยอดยกไปของเดือนล่าสุดที่คำนวณไว้ ถ้ายังไม่เคยคำนวณจะเป็นยอดตั้งต้น',
    )
    npd_accum_dep = fields.Float(
        string='ค่าเสื่อมสะสม',
        digits='Account',
        compute='_compute_npd_values',
        help='ราคาทรัพย์สิน - มูลค่าคงเหลือ',
    )

    @api.depends('npd_depre_line_ids.closing_value', 'purchase_value',
                 'npd_opening_nbv', 'npd_opening_date')
    def _compute_npd_values(self):
        for asset in self:
            last = self.env['npd.asset.depreciation.line'].search(
                [('asset_id', '=', asset.id)], order='date_end desc', limit=1)
            if last:
                residual = last.closing_value
            else:
                _start, residual = asset._npd_start_point()
            asset.npd_value_residual = residual or 0.0
            asset.npd_accum_dep = round((asset.purchase_value or 0.0) - (residual or 0.0), 2)

    @api.depends('npd_depre_line_ids')
    def _compute_npd_depre_line_count(self):
        for asset in self:
            asset.npd_depre_line_count = len(asset.npd_depre_line_ids)

    # ------------------------------------------------------------------
    # เติมค่าที่ระบบเดิมบังคับ ให้ผู้ใช้ไม่ต้องเห็น/ไม่ต้องกรอก
    #
    # ข้อบังคับ _check_dates ของ OCA จะพังถ้า method_time = year แล้ว
    # method_number ว่าง ใส่จำนวนปีไว้กันเงื่อนไขนั้น ค่านี้ไม่มีผลกับสูตรของโมดูลนี้
    # (o14 ต้องเติม purchase_paid_value ด้วย แต่ OCA 18 ไม่มีฟิลด์นั้นแล้ว)
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        Profile = self.env['account.asset.profile']
        for vals in vals_list:
            if not vals.get('method_number'):
                vals['method_number'] = 5
            # ตอนนำเข้าข้อมูลเป็นชุด Odoo ไม่เรียก onchange อัตราจึงไม่ถูกดึงมาให้
            # ต้องดึงจากหมวดตรงนี้ ไม่งั้นไฟล์นำเข้าต้องมีคอลัมน์ร้อยละทุกแถว
            if not vals.get('npd_depre_rate') and vals.get('profile_id'):
                rate = Profile.browse(vals['profile_id']).npd_depre_rate
                if rate:
                    vals['npd_depre_rate'] = rate
        assets = super().create(vals_list)
        assets._npd_assign_asset_number()
        return assets

    @api.onchange('profile_id')
    def _onchange_profile_npd_rate(self):
        """ดึงอัตราตั้งต้นของหมวดมาให้ ถ้ายังไม่เคยกรอกอัตราไว้"""
        if self.profile_id and not self.npd_depre_rate:
            self.npd_depre_rate = self.profile_id.npd_depre_rate

    # ------------------------------------------------------------------
    # จุดตั้งต้นของการคำนวณ
    # ------------------------------------------------------------------
    def _npd_start_point(self):
        """(วันเริ่มคิด, ยอดตั้งต้น) -- ยกยอดมาก็เริ่มจากวันถัดจากวันยกยอด"""
        self.ensure_one()
        if self.npd_opening_date:
            return self.npd_opening_date + timedelta(days=1), self.npd_opening_nbv
        return self.date_start, self.purchase_value

    def _npd_opening_for(self, year, month):
        """ยอดยกมาต้นเดือนที่ขอ -- ไล่คิดจากจุดตั้งต้นมาทีละเดือน

        ถ้าเดือนก่อนหน้ามีบรรทัดที่คำนวณไว้แล้ว จะใช้ยอดยกไปของบรรทัดนั้นเลย
        ไม่ต้องไล่ใหม่ (ทำให้เดือนที่ลงบัญชีไปแล้วเป็นตัวตั้งเสมอ)
        """
        self.ensure_one()
        target_start = date(year, month, 1)
        prev = self.env['npd.asset.depreciation.line'].search([
            ('asset_id', '=', self.id),
            ('date_end', '<', target_start),
        ], order='date_end desc', limit=1)
        if prev:
            return prev.closing_value

        start_date, opening = self._npd_start_point()
        if not start_date:
            return 0.0
        if start_date >= target_start:
            return opening

        cost = self.purchase_value
        rate = self.npd_depre_rate
        salvage = self.npd_salvage_value or DEFAULT_SALVAGE
        buy = self.date_start
        cursor = date(start_date.year, start_date.month, 1)
        while cursor < target_start:
            mstart, mend = month_range(cursor.year, cursor.month)
            # เดือนแรกที่เริ่มคิดหลังยกยอด ให้ตัดเศษวันจากวันที่ยกยอดด้วย
            effective_buy = max(buy or start_date, start_date)
            _days, dep = npd_month_depreciation(
                cost, rate, effective_buy, mstart, mend, opening, salvage)
            opening = round(opening - dep, 2)
            cursor = mend + timedelta(days=1)
        return opening

    # ------------------------------------------------------------------
    # สร้างบรรทัดค่าเสื่อมของทั้งปี
    # ------------------------------------------------------------------
    def npd_compute_year(self, year):
        """สร้าง/แทนที่บรรทัดค่าเสื่อม 12 เดือนของปีที่ระบุ

        บรรทัดที่ลงบัญชีไปแล้วจะไม่ถูกแตะ (ถือว่าปิดงวดแล้ว)
        คืนจำนวนบรรทัดที่สร้างใหม่
        """
        Line = self.env['npd.asset.depreciation.line']
        created = 0
        for asset in self:
            if not asset.npd_depre_rate:
                continue
            start_date, _opening = asset._npd_start_point()
            if not start_date:
                continue

            cost = asset.purchase_value
            salvage = asset.npd_salvage_value or DEFAULT_SALVAGE
            buy = asset.date_start
            opening = asset._npd_opening_for(year, 1)

            for month in range(1, 13):
                mstart, mend = month_range(year, month)
                existing = Line.search([
                    ('asset_id', '=', asset.id),
                    ('year', '=', year),
                    ('month', '=', str(month)),
                ], limit=1)
                if existing and existing.state == 'posted':
                    # ลงบัญชีแล้ว ใช้ยอดของบรรทัดนั้นเป็นตัวตั้งของเดือนถัดไป
                    opening = existing.closing_value
                    continue

                effective_buy = max(buy or start_date, start_date)
                days, dep = npd_month_depreciation(
                    cost, asset.npd_depre_rate, effective_buy,
                    mstart, mend, opening, salvage)
                if effective_buy > mend:
                    # ยังไม่ถึงเดือนที่เริ่มคิด ไม่ต้องมีบรรทัด
                    if existing:
                        existing.unlink()
                    continue

                vals = {
                    'asset_id': asset.id,
                    'year': year,
                    'month': str(month),
                    'date_start': mstart,
                    'date_end': mend,
                    'days': days,
                    'opening_value': opening,
                    'depreciation': dep,
                    'closing_value': round(opening - dep, 2),
                }
                if existing:
                    existing.write(vals)
                else:
                    Line.create(vals)
                    created += 1
                opening = round(opening - dep, 2)

        # กางเป็นตาราง 12 เดือนให้พร้อมอ่าน (หน้าตาเดียวกับไฟล์ Excel)
        self.env['npd.asset.depreciation.year']._sync_assets(self.ids, [year])
        self._npd_fill_month_columns(year)
        return created

    # ------------------------------------------------------------------
    # เลขทะเบียนทรัพย์สิน แยกเลขรันต่อบริษัท
    # ------------------------------------------------------------------
    @api.model
    def _npd_asset_prefix(self, company):
        """(ตัวย่อ, เลขเริ่มต้น) ของบริษัท ดูจากคำในชื่อบริษัท"""
        name = re.sub(r'\s+', ' ', company.name or '')
        for keyword, prefix, start in COMPANY_ASSET_PREFIX:
            if keyword in name:
                return prefix, start
        return FALLBACK_ASSET_PREFIX, 1

    @api.model
    def _npd_asset_sequence(self, company):
        return self.env['ir.sequence'].sudo().search([
            ('code', '=', ASSET_SEQUENCE_CODE),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.model
    def _npd_setup_asset_sequences(self):
        """สร้างเลขรันทะเบียนทรัพย์สินให้บริษัทที่ยังไม่มี

        เรียกทุกครั้งที่ติดตั้ง/อัพเดทโมดูล ตัวที่มีอยู่แล้วไม่แตะ (เลขที่เดินไปแล้วไม่ถูกย้อน)
        """
        Sequence = self.env['ir.sequence'].sudo()
        created = []
        for company in self.env['res.company'].sudo().search([]):
            if self._npd_asset_sequence(company):
                continue
            prefix, start = self._npd_asset_prefix(company)
            Sequence.create({
                'name': 'เลขทะเบียนทรัพย์สิน - %s' % company.name,
                'code': ASSET_SEQUENCE_CODE,
                'prefix': prefix,
                'padding': 5,
                'number_next': start,
                'number_increment': 1,
                'implementation': 'standard',
                'company_id': company.id,
            })
            created.append('%s%05d (%s)' % (prefix, start, company.name))
        if created:
            _logger.info('npd_asset_depreciation: สร้างเลขรันทะเบียนทรัพย์สิน %s', ', '.join(created))
        return created

    def _npd_assign_asset_number(self):
        """ออกเลขทะเบียนทรัพย์สินให้เอง ไม่ต้องกดปุ่ม RUN

        ใช้เลขรันของหมวดสินทรัพย์ถ้าตั้งไว้ ไม่ได้ตั้งก็ใช้เลขรันของบริษัท
        ต่างจากปุ่ม RUN เดิมตรงที่ไม่ไปเขียนทับช่อง "อ้างถึง"
        (ปุ่มเดิมเขียนทับ ทำให้รหัสทรัพย์สินที่นำเข้ามาหาย)
        เติมช่องเลขสินทรัพย์ของ OCA (number) ด้วยเลขเดียวกัน รายงานสินทรัพย์ไทยใช้ช่องนั้น
        """
        for asset in self:
            if asset.std_barcode:
                if not asset.number:
                    asset.number = asset.std_barcode
                continue
            sequence = asset.profile_id.std_asset_sequence_id \
                or self._npd_asset_sequence(asset.company_id)
            if not sequence:
                continue
            barcode = sequence.next_by_id(sequence_date=asset.date_start)
            vals = {'std_barcode': barcode}
            if not asset.number:
                vals['number'] = barcode
            asset.write(vals)

    def _npd_post_due_lines(self):
        """ลงบัญชีเฉพาะเดือนที่ผ่านไปแล้ว (สิ้นเดือนไม่เกินวันนี้)

        ไม่ลงบัญชีเดือนที่ยังมาไม่ถึง เพราะการบันทึกค่าเสื่อมของงวดอนาคต
        ทำให้งบการเงินของเดือนนี้ผิด เดือนที่เหลือจะถูกลงให้เองเมื่อถึงเวลา
        โดยงานประจำเดือน (cron)
        """
        today = fields.Date.context_today(self)
        lines = self.env['npd.asset.depreciation.line'].search([
            ('asset_id', 'in', self.ids),
            ('state', '=', 'draft'),
            ('depreciation', '>', 0),
            ('date_end', '<=', today),
        ])
        if lines:
            lines.action_post()
        return len(lines)

    def _npd_unpost_all_lines(self):
        """ถอนการลงบัญชีทุกเดือนของสินทรัพย์นี้

        สมุดรายวันที่ออกไปแล้วจะถูกดึงกลับเป็นฉบับร่าง ไม่ถูกลบ
        """
        lines = self.env['npd.asset.depreciation.line'].search([
            ('asset_id', 'in', self.ids),
            ('state', '=', 'posted'),
        ])
        if lines:
            lines.action_unpost()
        return len(lines)

    def set_to_draft(self):
        """กลับเป็นฉบับร่าง -- ถอนการลงบัญชีค่าเสื่อมคืนให้ด้วย

        ถ้าไม่ถอนก่อน สมุดรายวันค่าเสื่อมจะค้างอยู่ทั้งที่สินทรัพย์กลับไปเป็น
        ฉบับร่างแล้ว ทำให้ยอดในบัญชีไม่ตรงกับสถานะบนเอกสาร
        """
        undone = self._npd_unpost_all_lines()
        if undone:
            _logger.info('npd_asset_depreciation: ถอนการลงบัญชีค่าเสื่อม %s เดือน', undone)
        return super().set_to_draft()

    def compute_depreciation_board(self):
        """ปิดการสร้างตารางค่าเสื่อมของระบบเดิม สำหรับสินทรัพย์ที่ใช้สูตรของโมดูลนี้

        กันที่เมธอดนี้ ไม่ใช่ที่ปุ่มยืนยัน เพราะมีหลายโมดูลเรียกมันคนละทาง
        (ปุ่มยืนยันของ OCA, การสร้างสินทรัพย์จากใบแจ้งหนี้, ตัวช่วยแก้ไขสินทรัพย์)
        ตัวที่ยังใช้เครื่องคำนวณเดิม (ไม่ได้ตั้งร้อยละค่าเสื่อม) ทำงานเหมือนเดิมทุกอย่าง

        o14 ต้องเขียนทับ validate() กันอีกชั้น o18 ปุ่มยืนยันของ OCA เรียกเมธอดนี้
        ซึ่งถูกกันไว้แล้ว จึงปล่อยให้ validate() ของทุกโมดูลในสายทำงานตามปกติ
        """
        others = self.filtered(lambda a: not a.npd_depre_rate)
        if others:
            return super(AccountAsset, others).compute_depreciation_board()
        return True

    def action_npd_start_depreciation(self):
        """ปุ่ม 'เริ่มคิดค่าเสื่อม' -- เปลี่ยนสถานะเป็นกำลังทำงานอยู่ แล้วคำนวณปีนี้ให้เลย

        ระบบจะคิดค่าเสื่อมให้เฉพาะสินทรัพย์ที่สถานะกำลังทำงานอยู่เท่านั้น
        ทั้งตอนกดคำนวณเองและตอนงานประจำเดือน ของที่ยังคีย์ไม่เสร็จจึงไม่ถูกคิดไปด้วย
        """
        year = fields.Date.context_today(self).year
        ready = self.filtered(lambda a: a.npd_depre_rate)
        skipped = self - ready
        if not ready:
            raise UserError(_('สินทรัพย์ที่เลือกยังไม่ได้ใส่ร้อยละค่าเสื่อมต่อปี '
                              'จึงยังเริ่มคิดค่าเสื่อมไม่ได้'))
        ready.filtered(lambda a: a.state == 'draft').write({'state': 'open'})
        ready.npd_compute_year(year)
        posted = ready._npd_post_due_lines()
        if posted:
            _logger.info('npd_asset_depreciation: ลงบัญชีค่าเสื่อมให้ %s เดือน', posted)
        if skipped:
            # กดทีเดียวหลายร้อยตัวหลังนำเข้าข้อมูล ตัวที่ยังไม่พร้อมให้ข้ามไป
            # ไม่ใช่ล้มทั้งชุด แล้วบอกไว้ในบันทึกของระบบว่าข้ามตัวไหน
            _logger.info('npd_asset_depreciation: ข้าม %s รายการที่ยังไม่ได้ใส่อัตรา (%s)',
                         len(skipped), ', '.join(skipped.mapped('code')[:20]))
        return True

    @api.model
    def cron_npd_compute_current_year(self):
        """งานประจำเดือน: คำนวณค่าเสื่อมของปีปัจจุบันให้ทุกสินทรัพย์ที่ตั้งอัตราไว้

        คำนวณทับได้ไม่มีปัญหา เดือนที่ลงบัญชีไปแล้วจะถูกข้าม
        และใช้ยอดของบรรทัดนั้นเป็นตัวตั้งของเดือนถัดไป
        ทำทีละบริษัท สมุดรายวันจะได้ออกในบริษัทของสินทรัพย์นั้น
        """
        year = fields.Date.context_today(self).year
        year_start = date(year, 1, 1)
        total = posted = 0
        for company in self.env['res.company'].sudo().search([]):
            Asset = self.with_company(company).with_context(allowed_company_ids=company.ids)
            assets = Asset.search([('npd_depre_rate', '!=', 0),
                                   ('state', 'in', ('draft', 'open')),
                                   ('company_id', '=', company.id)])
            assets = assets.filtered(
                lambda a: not a.date_remove or a.date_remove >= year_start)
            if not assets:
                continue
            # คำนวณให้ทุกตัวรวมฉบับร่าง แต่ลงบัญชีเฉพาะตัวที่กด "เริ่มคิดค่าเสื่อม" แล้ว
            # ฉบับร่างคือตัวที่ยังไม่ได้ตรวจ ยังไม่ควรมีอะไรวิ่งเข้าบัญชี
            assets.npd_compute_year(year)
            posted += assets.filtered(lambda a: a.state == 'open')._npd_post_due_lines()
            total += len(assets)
        _logger.info('npd_asset_depreciation: คำนวณค่าเสื่อมปี %s ให้ %s รายการ '
                     'และลงบัญชี %s เดือน', year, total, posted)
        return total

    def _npd_fill_month_columns(self, year):
        """คัดลอกยอดรายเดือนของปีที่ระบุ มาไว้บนตัวสินทรัพย์

        ทำเพื่อให้ดูจบในตารางสินทรัพย์ตารางเดียว ไม่ต้องเปิดอีกหน้า
        ต้นฉบับยังเป็นบรรทัดรายเดือนเหมือนเดิม ตรงนี้เป็นแค่สำเนาไว้แสดงผล
        """
        Line = self.env['npd.asset.depreciation.line']
        lines = Line.search([('asset_id', 'in', self.ids), ('year', '=', year)])
        by_asset = {}
        for line in lines:
            by_asset.setdefault(line.asset_id.id, []).append(line)

        # สำเนาไว้แสดงผล ไม่ต้องบันทึกประวัติลงแชทของสินทรัพย์ทุกครั้งที่คำนวณ
        for asset in self.with_context(tracking_disable=True):
            vals = {'npd_display_year': year}
            for month in range(1, 13):
                vals['npd_m%02d_open' % month] = 0.0
                vals['npd_m%02d_dep' % month] = 0.0
            for line in by_asset.get(asset.id, []):
                month = int(line.month)
                vals['npd_m%02d_open' % month] = line.opening_value
                vals['npd_m%02d_dep' % month] = line.depreciation
            asset.write(vals)

    def action_npd_view_depreciation(self):
        """ปุ่มบนฟอร์มสินทรัพย์ -- เปิดดูค่าเสื่อมรายเดือนของตัวนี้"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('ค่าเสื่อมรายเดือน - %s') % (self.name or ''),
            'res_model': 'npd.asset.depreciation.line',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id, 'search_default_group_year': 1},
        }
