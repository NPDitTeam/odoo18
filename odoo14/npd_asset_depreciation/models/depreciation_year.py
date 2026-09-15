# -*- coding: utf-8 -*-
"""ตารางค่าเสื่อม 12 เดือน -- 1 สินทรัพย์ = 1 บรรทัดต่อ 1 ปี

หน้าจอเดียวกับไฟล์ Excel เดิม คือกางเดือนออกเป็นคอลัมน์ (ยอดยกมา/ค่าเสื่อม
สลับกันไป 12 เดือน) อ่านทั้งปีจบในบรรทัดเดียว

ตัวเลขในตารางนี้ไม่ได้คิดเอง แต่คัดลอกมาจาก npd.asset.depreciation.line
ที่เป็นต้นฉบับ ทุกครั้งที่บรรทัดรายเดือนเปลี่ยน ตารางนี้จะถูกอัพเดทตาม
จึงไม่มีทางที่สองที่จะไม่ตรงกัน
"""
from odoo import api, fields, models

MONTH_LABELS = [
    'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
    'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.',
]


def _month_fields():
    """[(ชื่อฟิลด์ยอดยกมา, ชื่อฟิลด์ค่าเสื่อม), ...] เรียงตามเดือน 1-12"""
    return [('m%02d_open' % m, 'm%02d_dep' % m) for m in range(1, 13)]


class NpdAssetDepreciationYear(models.Model):
    _name = 'npd.asset.depreciation.year'
    _description = 'ตารางค่าเสื่อมราคา 12 เดือน'
    _order = 'year desc, profile_code, asset_code'
    _rec_name = 'asset_id'

    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='ชื่อทรัพย์สิน',
        required=True,
        ondelete='cascade',
        index=True,
    )
    year = fields.Integer(string='ปี (ค.ศ.)', required=True, index=True)
    year_be = fields.Integer(string='ปี (พ.ศ.)', compute='_compute_year_be', store=True)

    profile_id = fields.Many2one(related='asset_id.profile_id', string='หมวดสินทรัพย์',
                                 store=True, index=True)
    profile_code = fields.Char(string='รหัสหมวด', compute='_compute_profile_text', store=True)
    profile_name = fields.Char(string='ชื่อหมวด', compute='_compute_profile_text', store=True)
    asset_code = fields.Char(related='asset_id.code', string='รหัสทรัพย์สิน', store=True)
    company_id = fields.Many2one(related='asset_id.company_id', string='บริษัท', store=True,
                                 index=True)

    date_purchase = fields.Date(related='asset_id.date_start', string='วันที่ซื้อ (ค.ศ.)',
                                store=True)
    date_purchase_be = fields.Char(string='วันที่ซื้อ (พ.ศ.)',
                                   compute='_compute_date_purchase_be', store=True)
    # OCA 18 เก็บราคาเป็น Monetary ฟิลด์ related ต้องเป็นชนิดเดียวกัน
    currency_id = fields.Many2one(related='asset_id.currency_id', string='สกุลเงิน')
    purchase_value = fields.Monetary(related='asset_id.purchase_value', string='ราคาทรัพย์สิน',
                                     store=True, currency_field='currency_id')
    depre_rate = fields.Float(related='asset_id.npd_depre_rate', string='ร้อยละ', store=True)

    # ---- ยอดยกมา/ค่าเสื่อม รายเดือน (กางเป็นคอลัมน์เหมือนไฟล์ Excel) ----
    m01_open = fields.Float(string='ม.ค. ยอดยกมา', digits='Account')
    m01_dep = fields.Float(string='ม.ค. ค่าเสื่อม', digits='Account')
    m02_open = fields.Float(string='ก.พ. ยอดยกมา', digits='Account')
    m02_dep = fields.Float(string='ก.พ. ค่าเสื่อม', digits='Account')
    m03_open = fields.Float(string='มี.ค. ยอดยกมา', digits='Account')
    m03_dep = fields.Float(string='มี.ค. ค่าเสื่อม', digits='Account')
    m04_open = fields.Float(string='เม.ย. ยอดยกมา', digits='Account')
    m04_dep = fields.Float(string='เม.ย. ค่าเสื่อม', digits='Account')
    m05_open = fields.Float(string='พ.ค. ยอดยกมา', digits='Account')
    m05_dep = fields.Float(string='พ.ค. ค่าเสื่อม', digits='Account')
    m06_open = fields.Float(string='มิ.ย. ยอดยกมา', digits='Account')
    m06_dep = fields.Float(string='มิ.ย. ค่าเสื่อม', digits='Account')
    m07_open = fields.Float(string='ก.ค. ยอดยกมา', digits='Account')
    m07_dep = fields.Float(string='ก.ค. ค่าเสื่อม', digits='Account')
    m08_open = fields.Float(string='ส.ค. ยอดยกมา', digits='Account')
    m08_dep = fields.Float(string='ส.ค. ค่าเสื่อม', digits='Account')
    m09_open = fields.Float(string='ก.ย. ยอดยกมา', digits='Account')
    m09_dep = fields.Float(string='ก.ย. ค่าเสื่อม', digits='Account')
    m10_open = fields.Float(string='ต.ค. ยอดยกมา', digits='Account')
    m10_dep = fields.Float(string='ต.ค. ค่าเสื่อม', digits='Account')
    m11_open = fields.Float(string='พ.ย. ยอดยกมา', digits='Account')
    m11_dep = fields.Float(string='พ.ย. ค่าเสื่อม', digits='Account')
    m12_open = fields.Float(string='ธ.ค. ยอดยกมา', digits='Account')
    m12_dep = fields.Float(string='ธ.ค. ค่าเสื่อม', digits='Account')

    total_dep = fields.Float(string='รวมค่าเสื่อมทั้งปี', digits='Account')
    closing_value = fields.Float(string='ยอดคงเหลือปลายปี', digits='Account')

    _sql_constraints = [
        ('asset_year_uniq', 'unique(asset_id, year)',
         'สินทรัพย์ 1 ตัวมีได้ปีละ 1 บรรทัดในตารางนี้'),
    ]

    @api.depends('year')
    def _compute_year_be(self):
        for rec in self:
            rec.year_be = (rec.year or 0) + 543

    @api.depends('profile_id', 'profile_id.name', 'profile_id.npd_code')
    def _compute_profile_text(self):
        for rec in self:
            profile = rec.profile_id
            rec.profile_code = profile.npd_category_code() if profile else ''
            rec.profile_name = profile.npd_category_name() if profile else ''

    @api.depends('date_purchase')
    def _compute_date_purchase_be(self):
        for rec in self:
            buy = rec.date_purchase
            rec.date_purchase_be = (
                '%02d/%02d/%s' % (buy.day, buy.month, str(buy.year + 543)[-2:])
                if buy else ''
            )

    # ------------------------------------------------------------------
    # ซิงก์จากบรรทัดรายเดือน
    # ------------------------------------------------------------------
    @api.model
    def _sync_assets(self, asset_ids, years):
        """สร้าง/อัพเดทบรรทัดของสินทรัพย์+ปีที่ระบุ ให้ตรงกับบรรทัดรายเดือน"""
        asset_ids = [a for a in set(asset_ids) if a]
        years = [y for y in set(years) if y]
        if not asset_ids or not years:
            return
        # ตารางนี้เป็นสำเนาของบรรทัดรายเดือน ซิงก์ข้ามกฎบริษัท (สิทธิ์ตรวจที่ตัวบรรทัดแล้ว)
        Line = self.env['npd.asset.depreciation.line'].sudo()
        lines = Line.search([('asset_id', 'in', asset_ids), ('year', 'in', years)])
        this = self.sudo()

        buckets = {}
        for line in lines:
            buckets.setdefault((line.asset_id.id, line.year), []).append(line)

        month_fields = _month_fields()
        for asset_id in asset_ids:
            for year in years:
                rows = buckets.get((asset_id, year), [])
                existing = this.search([('asset_id', '=', asset_id),
                                        ('year', '=', year)], limit=1)
                if not rows:
                    # ไม่มีบรรทัดรายเดือนแล้ว ก็ไม่ต้องมีบรรทัดในตารางนี้
                    if existing:
                        existing.unlink()
                    continue

                vals = {'asset_id': asset_id, 'year': year}
                for fname_open, fname_dep in month_fields:
                    vals[fname_open] = 0.0
                    vals[fname_dep] = 0.0
                total = 0.0
                closing = 0.0
                last_month = 0
                for line in rows:
                    month = int(line.month)
                    vals['m%02d_open' % month] = line.opening_value
                    vals['m%02d_dep' % month] = line.depreciation
                    total += line.depreciation
                    if month >= last_month:
                        last_month = month
                        closing = line.closing_value
                vals['total_dep'] = round(total, 2)
                vals['closing_value'] = closing
                if existing:
                    existing.write(vals)
                else:
                    this.create(vals)
