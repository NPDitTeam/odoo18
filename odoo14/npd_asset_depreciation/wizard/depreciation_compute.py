# -*- coding: utf-8 -*-
"""ตัวช่วยคำนวณค่าเสื่อมทั้งปี และออกไฟล์ Excel หน้าตาเดียวกับไฟล์เดิม

o18 ฐานเดียวหลายบริษัท: หน้าต่างนี้ทำงานทีละบริษัท (ช่องบริษัท ค่าเริ่มต้น = บริษัทที่เลือกอยู่)
ทั้งการคำนวณ สรุปตามหมวด รายงาน พ.ร.ฎ. และไฟล์ Excel
"""
import base64
import calendar
import io
from datetime import date
from urllib.parse import urlencode

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.depreciation_line import MONTHS

THAI_MONTHS = [
    '', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
    'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.',
]

# คอลัมน์หัวตารางฝั่งซ้าย (ก่อนถึงคอลัมน์รายเดือน) -- ลำดับตามไฟล์ Excel เดิม
BASE_COLUMNS = [
    ('ลำดับ', 6),
    ('รหัสหมวด', 10),
    ('ชื่อหมวด', 22),
    ('รหัสทรัพย์สิน', 16),
    ('ชื่อทรัพย์สิน', 34),
    ('วันที่ซื้อ (พ.ศ.)', 14),
    ('วันที่ซื้อ (ค.ศ.)', 14),
    ('ราคาทรัพย์สิน', 15),
    ('ร้อยละ', 9),
]


class NpdAssetDepreciationCompute(models.TransientModel):
    _name = 'npd.asset.depreciation.compute'
    _description = 'คำนวณค่าเสื่อมราคาสินทรัพย์ทั้งปี'
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='บริษัท',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.user.company_ids.ids)],
    )
    year = fields.Integer(
        string='ปี (ค.ศ.)',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
        help='คำนวณ 12 เดือน ม.ค. - ธ.ค. ของปีนี้',
    )
    profile_ids = fields.Many2many(
        comodel_name='account.asset.profile',
        string='เฉพาะหมวดสินทรัพย์',
        domain="[('company_id', '=', company_id)]",
        help='เว้นว่าง = ทุกหมวด',
    )
    asset_ids = fields.Many2many(
        comodel_name='account.asset',
        string='เฉพาะสินทรัพย์',
        domain="[('company_id', '=', company_id)]",
        help='เว้นว่าง = ทุกตัวที่กรอกร้อยละค่าเสื่อมไว้',
    )
    month_from = fields.Selection(
        MONTHS,
        string='งวดตั้งแต่เดือน',
        default=lambda self: str(fields.Date.context_today(self).month),
        help='ใช้กับปุ่มสรุปตามหมวดและปุ่มพิมพ์รายงาน เลือกช่วงได้หลายเดือน',
    )
    month_to = fields.Selection(
        MONTHS,
        string='ถึงเดือน',
        default=lambda self: str(fields.Date.context_today(self).month),
        help='เลือกเดือนเดียวกับช่องซ้ายถ้าต้องการงวดเดือนเดียว',
    )
    only_active = fields.Boolean(
        string='ข้ามสินทรัพย์ที่ตัดจำหน่ายแล้ว',
        default=True,
        help='ไม่คิดค่าเสื่อมให้สินทรัพย์ที่มีวันที่ตัดจำหน่ายก่อนปีที่เลือก',
    )

    file_data = fields.Binary(string='ไฟล์', readonly=True)
    file_name = fields.Char(string='ชื่อไฟล์', readonly=True)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        self.profile_ids = self.profile_ids.filtered(lambda p: p.company_id == self.company_id)
        self.asset_ids = self.asset_ids.filtered(lambda a: a.company_id == self.company_id)

    def _company_env(self):
        """สิ่งแวดล้อมของบริษัทที่เลือก (กฎบริษัทจะกรองให้ตรงกับบริษัทนี้)"""
        self.ensure_one()
        return self.with_company(self.company_id)

    # ------------------------------------------------------------------
    def _target_assets(self):
        """สินทรัพย์ที่เข้าเงื่อนไขของตัวกรองบนหน้าจอ"""
        self.ensure_one()
        if self.asset_ids:
            assets = self.asset_ids.filtered(lambda a: a.company_id == self.company_id)
        else:
            # รับทั้งฉบับร่างและที่เริ่มคิดค่าเสื่อมแล้ว -- การคำนวณไม่แตะบัญชี
            # จึงต้องดูตัวเลขให้ตรงก่อนได้ ค่อยกด "เริ่มคิดค่าเสื่อม" เพื่อลงบัญชีทีหลัง
            domain = [('npd_depre_rate', '!=', 0), ('state', 'in', ('draft', 'open')),
                      ('company_id', '=', self.company_id.id)]
            if self.profile_ids:
                domain.append(('profile_id', 'in', self.profile_ids.ids))
            assets = self._company_env().env['account.asset'].search(domain)
        if self.only_active:
            year_start = date(self.year, 1, 1)
            assets = assets.filtered(
                lambda a: not a.date_remove or a.date_remove >= year_start)
        return assets.with_company(self.company_id)

    def action_compute(self):
        """ปุ่มคำนวณ -- สร้าง/อัพเดทบรรทัด 12 เดือนของปีที่เลือก"""
        self.ensure_one()
        assets = self._target_assets()
        if not assets:
            raise UserError(_('ไม่พบสินทรัพย์ที่เข้าเงื่อนไข '
                              'ตรวจว่ากรอก "ร้อยละค่าเสื่อมต่อปี" ไว้แล้วหรือยัง'))
        assets.npd_compute_year(self.year)
        return {
            'type': 'ir.actions.act_window',
            'name': _('ค่าเสื่อมราคา ปี %s') % (self.year + 543),
            'res_model': 'account.asset',
            'view_mode': 'list,form',
            'domain': [('id', 'in', assets.ids)],
            'context': {},
        }

    def action_show_year(self):
        """ปุ่มดูย้อนหลัง -- สลับคอลัมน์รายเดือนในตารางสินทรัพย์ไปเป็นปีที่เลือก

        ไม่คำนวณใหม่ แค่ดึงยอดที่เคยคำนวณไว้ของปีนั้นมาแสดง
        ใช้ตอนขึ้นปีใหม่แล้วอยากย้อนดูปีเก่าโดยไม่แตะข้อมูล
        """
        self.ensure_one()
        assets = self._target_assets()
        if not assets:
            raise UserError(_('ไม่พบสินทรัพย์ที่เข้าเงื่อนไข'))
        assets._npd_fill_month_columns(self.year)
        return {
            'type': 'ir.actions.act_window',
            'name': _('สินทรัพย์ - ค่าเสื่อมปี %s') % (self.year + 543),
            'res_model': 'account.asset',
            'view_mode': 'list,form',
            'domain': [('id', 'in', assets.ids)],
            'context': {},
        }

    # ------------------------------------------------------------------
    # งวดแบบช่วงเดือน
    # ------------------------------------------------------------------
    def _period_months(self):
        """[เลขเดือน] ในช่วงที่เลือก (สลับให้เองถ้ากรอกกลับหัว)"""
        self.ensure_one()
        today_month = str(fields.Date.context_today(self).month)
        start = int(self.month_from or today_month)
        end = int(self.month_to or self.month_from or today_month)
        if start > end:
            start, end = end, start
        return list(range(start, end + 1))

    def _period_dates(self):
        """(วันแรกของงวด, วันสุดท้ายของงวด)"""
        months = self._period_months()
        return (date(self.year, months[0], 1),
                date(self.year, months[-1], calendar.monthrange(self.year, months[-1])[1]))

    def _period_rows(self):
        """รวมยอดของแต่ละสินทรัพย์ตลอดทั้งงวด (เฉพาะบริษัทที่เลือก)

        ยอดยกมา = ต้นเดือนแรกของงวด
        ค่าสึกหรอ = ผลรวมทุกเดือนในงวด
        ยอดยกไป = ปลายเดือนสุดท้ายของงวด
        คืน list ของ dict เรียงตามหมวด/รหัสทรัพย์สิน
        """
        self.ensure_one()
        months = [str(m) for m in self._period_months()]
        lines = self._company_env().env['npd.asset.depreciation.line'].search([
            ('year', '=', self.year), ('month', 'in', months),
            ('company_id', '=', self.company_id.id),
        ])
        if self.profile_ids:
            lines = lines.filtered(lambda l: l.profile_id in self.profile_ids)
        if self.asset_ids:
            lines = lines.filtered(lambda l: l.asset_id in self.asset_ids)

        by_asset = {}
        for line in lines:
            by_asset.setdefault(line.asset_id, []).append(line)

        rows = []
        for asset, group in by_asset.items():
            group.sort(key=lambda l: l.month_no)
            rows.append({
                'asset': asset,
                'profile': asset.profile_id,
                'opening': group[0].opening_value,
                'closing': group[-1].closing_value,
                'depreciation': sum(l.depreciation for l in group),
                'months': len(group),
            })
        rows.sort(key=lambda r: (r['profile'].npd_category_code() if r['profile'] else '',
                                 r['asset'].code or ''))
        return rows

    # ------------------------------------------------------------------
    # รายงาน พ.ร.ฎ. (PDF)
    # ------------------------------------------------------------------
    @staticmethod
    def _be(value, short=False):
        """วันที่แบบไทย 20/05/64 (สั้น) หรือ 20 พ.ค. 2569"""
        if not value:
            return ''
        if short:
            return '%02d/%02d/%s' % (value.day, value.month, str(value.year + 543)[-2:])
        return '%d %s %d' % (value.day, THAI_MONTHS[value.month], value.year + 543)

    @staticmethod
    def _num(value):
        return '{:,.2f}'.format(value or 0.0)

    def get_tax_report_data(self):
        """ข้อมูลของรายงานค่าสึกหรอ จัดกลุ่มตามหมวดสินทรัพย์ (รองรับงวดหลายเดือน)"""
        self.ensure_one()
        rows_all = self._period_rows()
        date_from, date_to = self._period_dates()

        groups, index = [], {}
        for row in rows_all:
            profile = row['profile']
            key = profile.id or 0
            if key not in index:
                index[key] = {
                    'code': profile.npd_category_code() if profile else '',
                    'name': profile.npd_category_name() if profile else 'ไม่ระบุหมวด',
                    'rows': [],
                }
                groups.append(index[key])
            index[key]['rows'].append(row)

        def totals(records):
            return (sum(r['asset'].purchase_value or 0.0 for r in records),
                    sum(r['opening'] for r in records),
                    sum(r['depreciation'] for r in records),
                    sum(r['closing'] for r in records))

        out_groups = []
        for grp in groups:
            rows = grp['rows']
            p, o, d, c = totals(rows)
            out_groups.append({
                'code': grp['code'],
                'name': grp['name'],
                'purchase': self._num(p), 'opening': self._num(o),
                'depreciation': self._num(d), 'closing': self._num(c),
                'lines': [{
                    'seq': seq,
                    'code': r['asset'].code or '',
                    'name': r['asset'].name or '',
                    'date_buy': self._be(r['asset'].date_start, short=True),
                    'purchase': self._num(r['asset'].purchase_value),
                    'opening': self._num(r['opening']),
                    'rate': '{:,.2f}'.format(r['asset'].npd_depre_rate or 0.0),
                    'depreciation': self._num(r['depreciation']),
                    'closing': self._num(r['closing']),
                    'date_sold': self._be(r['asset'].date_remove, short=True),
                } for seq, r in enumerate(rows, start=1)],
            })

        # ทรัพย์สินที่ตัดจำหน่ายภายในงวดนี้ แยกออกมาโชว์ตามแบบฟอร์ม
        sold = [r for r in rows_all
                if r['asset'].date_remove and date_from <= r['asset'].date_remove <= date_to]
        tp, to_, td, tc = totals(rows_all)
        sp, so, sd, sc = totals(sold)

        return {
            'company_name': self.company_id.name or '',
            'date_from': self._be(date_from),
            'date_to': self._be(date_to),
            'print_date': self._be(fields.Date.context_today(self), short=True),
            'groups': out_groups,
            'count': len(rows_all),
            'purchase': self._num(tp), 'opening': self._num(to_),
            'depreciation': self._num(td), 'closing': self._num(tc),
            'sold_purchase': self._num(sp), 'sold_opening': self._num(so),
            'sold_depreciation': self._num(sd), 'sold_closing': self._num(sc),
            'left_purchase': self._num(tp - sp), 'left_opening': self._num(to_ - so),
            'left_depreciation': self._num(td - sd), 'left_closing': self._num(tc - sc),
        }

    def action_print_tax_report(self):
        """ปุ่มพิมพ์รายงานค่าสึกหรอ (พ.ร.ฎ.)"""
        self.ensure_one()
        if not self._period_rows():
            raise UserError(_('งวดที่เลือกยังไม่มีบรรทัดค่าเสื่อม ให้กดคำนวณของปีนั้นก่อน'))
        # เปิดรายงานด้วย URL ตรง ๆ ส่งเงื่อนไขไปกับ URL ไม่ใช่ id ของ record นี้
        # เพราะหน้าต่างนี้เป็น TransientModel ตอนเบราว์เซอร์ไปโหลด PDF (คนละ request)
        # record อาจถูกเก็บกวาดไปแล้ว จะพังด้วย MissingError -- ดู models/tax_report.py
        # (o14 มีเหตุผลอีกข้อคือหน้าเว็บพังเมื่อคืน ir.actions.report จากป๊อปอัป)
        months = self._period_months()
        params = {
            'company': self.company_id.id,
            'year': self.year,
            'month_from': months[0],
            'month_to': months[-1],
            'profiles': ','.join(str(i) for i in self.profile_ids.ids),
            'assets': ','.join(str(i) for i in self.asset_ids.ids),
        }
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '/report/pdf/npd_asset_depreciation.report_npd_tax_depreciation?%s'
                   % urlencode(params),
        }

    def action_summary_by_profile(self):
        """ปุ่มสรุปตามหมวด -- รวมยอดของงวดที่เลือกตามหมวดสินทรัพย์"""
        self.ensure_one()
        rows = self.env['npd.asset.depreciation.summary'].build_from_wizard(self)
        if not rows:
            raise UserError(_('งวดที่เลือกยังไม่มีบรรทัดค่าเสื่อม '
                              'ให้กดคำนวณของปีนั้นก่อน'))
        months = self._period_months()
        label = dict(MONTHS).get(str(months[0]), '')
        if len(months) > 1:
            label += ' - ' + dict(MONTHS).get(str(months[-1]), '')
        return {
            'type': 'ir.actions.act_window',
            'name': _('สรุปค่าเสื่อมตามหมวด %s/%s') % (label, self.year + 543),
            'res_model': 'npd.asset.depreciation.summary',
            'view_mode': 'list',
            'domain': [('id', 'in', rows.ids)],
            'context': {},
        }

    # ------------------------------------------------------------------
    # ไฟล์ Excel 12 เดือน (หน้าตาเดียวกับไฟล์ "ค่าเสื่อม นภดล 5 บริษัท")
    # ------------------------------------------------------------------
    def _line_map(self, assets):
        """{(asset_id, month): บรรทัด} ของปีที่เลือก"""
        lines = self._company_env().env['npd.asset.depreciation.line'].search([
            ('year', '=', self.year),
            ('asset_id', 'in', assets.ids),
        ])
        return {(line.asset_id.id, int(line.month)): line for line in lines}

    def action_export_xlsx(self):
        """ปุ่มออก Excel -- คำนวณให้ก่อนถ้ายังไม่มีบรรทัดของปีนั้น"""
        self.ensure_one()
        try:
            import xlsxwriter
        except ImportError as e:
            raise UserError(_('เครื่องนี้ยังไม่ได้ติดตั้ง xlsxwriter '
                              'จึงออกไฟล์ Excel ไม่ได้')) from e

        assets = self._target_assets().sorted(
            key=lambda a: (a.profile_id.npd_category_code() if a.profile_id else '',
                           a.code or '', a.name or ''))
        if not assets:
            raise UserError(_('ไม่พบสินทรัพย์ที่เข้าเงื่อนไข'))
        line_map = self._line_map(assets)

        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        sheet = book.add_worksheet('ค่าเสื่อม %s' % (self.year + 543))

        f_title = book.add_format({'bold': True, 'font_size': 14, 'font_name': 'Tahoma'})
        f_month = book.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter',
                                   'border': 1, 'bg_color': '#DDEBF7', 'font_name': 'Tahoma'})
        f_head = book.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter',
                                  'border': 1, 'text_wrap': True, 'bg_color': '#F2F2F2',
                                  'font_name': 'Tahoma'})
        f_text = book.add_format({'border': 1, 'font_name': 'Tahoma'})
        f_center = book.add_format({'border': 1, 'align': 'center', 'font_name': 'Tahoma'})
        f_num = book.add_format({'border': 1, 'num_format': '#,##0.00', 'font_name': 'Tahoma'})
        f_pct = book.add_format({'border': 1, 'align': 'center',
                                 'num_format': '0.00"%"', 'font_name': 'Tahoma'})
        f_total = book.add_format({'border': 1, 'bold': True, 'num_format': '#,##0.00',
                                   'bg_color': '#F2F2F2', 'font_name': 'Tahoma'})

        company = self.company_id
        sheet.write(0, 0, '%s - ค่าเสื่อมราคา ปี %s' % (company.name or '', self.year + 543),
                    f_title)

        # แถวหัวเดือน (รวม 2 ช่อง: ยอดยกมา + ค่าเสื่อม)
        base_len = len(BASE_COLUMNS)
        for idx, (_month_key, month_label) in enumerate(MONTHS):
            col = base_len + idx * 2
            sheet.merge_range(1, col, 1, col + 1, month_label, f_month)
        for idx, (label, width) in enumerate(BASE_COLUMNS):
            sheet.write(2, idx, label, f_head)
            sheet.set_column(idx, idx, width)
        for idx in range(12):
            col = base_len + idx * 2
            sheet.write(2, col, 'ยอดยกมา', f_head)
            sheet.write(2, col + 1, 'ค่าเสื่อม', f_head)
            sheet.set_column(col, col + 1, 13)
        sheet.freeze_panes(3, base_len)

        row = 3
        totals = [0.0] * 24
        for seq, asset in enumerate(assets, start=1):
            profile = asset.profile_id
            buy = asset.date_start
            sheet.write(row, 0, seq, f_center)
            sheet.write(row, 1, profile.npd_category_code() if profile else '', f_center)
            sheet.write(row, 2, profile.npd_category_name() if profile else '', f_text)
            sheet.write(row, 3, asset.code or '', f_text)
            sheet.write(row, 4, asset.name or '', f_text)
            sheet.write(row, 5, buy.strftime('%d/%m/') + str(buy.year + 543)[-2:] if buy else '',
                        f_center)
            sheet.write(row, 6, buy.strftime('%d/%m/%Y') if buy else '', f_center)
            sheet.write(row, 7, asset.purchase_value or 0.0, f_num)
            sheet.write(row, 8, asset.npd_depre_rate or 0.0, f_pct)
            for idx in range(12):
                col = base_len + idx * 2
                line = line_map.get((asset.id, idx + 1))
                opening = line.opening_value if line else None
                dep = line.depreciation if line else None
                if opening is None:
                    sheet.write(row, col, '', f_text)
                else:
                    sheet.write(row, col, opening, f_num)
                    totals[idx * 2] += opening
                if dep is None:
                    sheet.write(row, col + 1, '', f_text)
                else:
                    sheet.write(row, col + 1, dep, f_num)
                    totals[idx * 2 + 1] += dep
            row += 1

        sheet.write(row, 4, 'รวมทั้งสิ้น', f_head)
        sheet.write(row, 7, sum(assets.mapped('purchase_value')), f_total)
        for idx in range(24):
            sheet.write(row, base_len + idx, totals[idx], f_total)

        book.close()
        stream.seek(0)
        self.write({
            'file_data': base64.b64encode(stream.read()),
            'file_name': 'ค่าเสื่อมราคา_%s.xlsx' % (self.year + 543),
        })
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': '/web/content/?model=%s&id=%s&field=file_data'
                   '&filename_field=file_name&download=true' % (self._name, self.id),
        }
