# -*- coding: utf-8 -*-
"""สรุปค่าเสื่อมตามหมวดสินทรัพย์ (หน้าตาเดียวกับแท็บ "สรุปตามหมวด" ในไฟล์ Excel)

1 หมวด = 1 บรรทัด ต่อ 1 งวด (เดือน) รวมยอดจากบรรทัดค่าเสื่อมรายเดือนของหมวดนั้น
พร้อมสัดส่วนที่ไฟล์เดิมมี คือ % ของค่าเสื่อมรวม, % คงเหลือต่อทุน และจำนวนรายการ
ที่ตัดค่าเสื่อมครบแล้ว (เหลือไม่เกินมูลค่าซาก)

ตัวเลขทั้งหมดคัดมาจาก npd.asset.depreciation.line ที่เป็นต้นฉบับ ไม่ได้คิดใหม่
o18 ฐานเดียวหลายบริษัท: สร้าง/ลบบรรทัดสรุปเฉพาะของบริษัทที่สั่ง ไม่แตะบริษัทอื่น
"""
from odoo import api, fields, models

from .depreciation_line import MONTHS


class NpdAssetDepreciationSummary(models.Model):
    _name = 'npd.asset.depreciation.summary'
    _description = 'สรุปค่าเสื่อมตามหมวดสินทรัพย์'
    _order = 'year desc, month_no desc, profile_code'
    _rec_name = 'profile_name'

    year = fields.Integer(string='ปี (ค.ศ.)', required=True, index=True)
    year_label = fields.Char(string='ปี (ค.ศ.)')
    month = fields.Selection(MONTHS, string='งวดตั้งแต่', required=True, index=True)
    month_to = fields.Selection(MONTHS, string='ถึง')
    period_label = fields.Char(string='งวด')
    month_no = fields.Integer(string='ลำดับเดือน', index=True)
    date_start = fields.Date(string='ต้นงวด')
    date_end = fields.Date(string='สิ้นงวด')

    profile_id = fields.Many2one('account.asset.profile', string='หมวดสินทรัพย์',
                                 ondelete='cascade', index=True)
    profile_code = fields.Char(string='รหัสหมวด')
    profile_name = fields.Char(string='ชื่อหมวด')
    company_id = fields.Many2one('res.company', string='บริษัท', index=True)

    asset_count = fields.Integer(string='จำนวนรายการ')
    purchase_value = fields.Float(string='ราคาทรัพย์สิน', digits='Account')
    opening_value = fields.Float(string='ยอดยกมา', digits='Account')
    depreciation = fields.Float(string='ค่าสึกหรอ', digits='Account')
    closing_value = fields.Float(string='ยอดยกไป', digits='Account')

    pct_of_total = fields.Float(string='% ของค่าเสื่อมรวม', digits=(5, 2))
    pct_remaining = fields.Float(string='% คงเหลือต่อทุน', digits=(5, 2))
    done_count = fields.Integer(string='ตัดครบแล้ว (รายการ)',
                                help='จำนวนรายการที่ยอดยกไปเหลือไม่เกินมูลค่าซาก')

    _sql_constraints = [
        ('period_profile_uniq', 'unique(year, month, month_to, profile_id)',
         'หมวดหนึ่งมีได้บรรทัดเดียวต่อหนึ่งงวด'),
    ]

    # ------------------------------------------------------------------
    @api.model
    def build_from_wizard(self, wizard):
        """สร้างบรรทัดสรุปของงวดที่เลือกบนหน้าจอ (รองรับช่วงหลายเดือน)

        ยอดยกมาเอาต้นเดือนแรกของงวด ยอดยกไปเอาปลายเดือนสุดท้าย
        ค่าสึกหรอรวมทุกเดือนในงวด — ตรรกะเดียวกับรายงาน พ.ร.ฎ.
        """
        rows = wizard._period_rows()
        months = wizard._period_months()
        m_from, m_to = str(months[0]), str(months[-1])
        date_from, date_to = wizard._period_dates()
        labels = dict(MONTHS)
        period_label = labels.get(m_from, '')
        if m_from != m_to:
            period_label += ' - ' + labels.get(m_to, '')

        self.search([('year', '=', wizard.year), ('month', '=', m_from),
                     ('month_to', '=', m_to),
                     ('company_id', '=', wizard.company_id.id)]).unlink()
        if not rows:
            return self.browse()

        buckets = {}
        for row in rows:
            buckets.setdefault(row['profile'], []).append(row)
        total_dep = sum(r['depreciation'] for r in rows)

        created = self.browse()
        for profile, group in buckets.items():
            purchase = sum(r['asset'].purchase_value or 0.0 for r in group)
            closing = sum(r['closing'] for r in group)
            dep = sum(r['depreciation'] for r in group)
            done = len([r for r in group
                        if r['closing'] <= (r['asset'].npd_salvage_value or 1.0) + 0.005])
            created |= self.create({
                'year': wizard.year,
                'year_label': str(wizard.year),
                'month': m_from,
                'month_to': m_to,
                'period_label': period_label,
                'month_no': int(m_from),
                'date_start': date_from,
                'date_end': date_to,
                'profile_id': profile.id,
                'profile_code': profile.npd_category_code() if profile else '',
                'profile_name': profile.npd_category_name() if profile else '',
                'company_id': wizard.company_id.id,
                'asset_count': len(group),
                'purchase_value': purchase,
                'opening_value': sum(r['opening'] for r in group),
                'depreciation': dep,
                'closing_value': closing,
                'pct_of_total': (dep / total_dep * 100.0) if total_dep else 0.0,
                'pct_remaining': (closing / purchase * 100.0) if purchase else 0.0,
                'done_count': done,
            })
        return created

    @api.model
    def build(self, year, month, company=None):
        """สร้าง/แทนที่บรรทัดสรุปของงวดที่ระบุ แล้วคืน recordset ที่ได้"""
        company = company or self.env.company
        month = str(int(month))
        self.search([('year', '=', year), ('month', '=', month),
                     ('company_id', '=', company.id)]).unlink()

        lines = self.env['npd.asset.depreciation.line'].search([
            ('year', '=', year), ('month', '=', month),
            ('company_id', '=', company.id),
        ])
        if not lines:
            return self.browse()

        buckets = {}
        for line in lines:
            buckets.setdefault(line.profile_id, self.env['npd.asset.depreciation.line'])
            buckets[line.profile_id] |= line
        total_dep = sum(lines.mapped('depreciation'))

        created = self.browse()
        for profile, group in buckets.items():
            purchase = sum(group.mapped('purchase_value'))
            closing = sum(group.mapped('closing_value'))
            dep = sum(group.mapped('depreciation'))
            # "ตัดครบแล้ว" = ยอดยกไปเหลือไม่เกินมูลค่าซากของสินทรัพย์ตัวนั้น
            done = len(group.filtered(
                lambda l: l.closing_value <= (l.asset_id.npd_salvage_value or 1.0) + 0.005))
            first = group[0]
            created |= self.create({
                'year': year,
                'year_label': str(year),
                'month': month,
                'month_no': int(month),
                'date_start': first.date_start,
                'date_end': first.date_end,
                'profile_id': profile.id,
                'profile_code': profile.npd_category_code() if profile else '',
                'profile_name': profile.npd_category_name() if profile else '',
                'company_id': company.id,
                'asset_count': len(group),
                'purchase_value': purchase,
                'opening_value': sum(group.mapped('opening_value')),
                'depreciation': dep,
                'closing_value': closing,
                'pct_of_total': (dep / total_dep * 100.0) if total_dep else 0.0,
                'pct_remaining': (closing / purchase * 100.0) if purchase else 0.0,
                'done_count': done,
            })
        return created
