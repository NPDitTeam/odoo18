# -*- coding: utf-8 -*-
"""บรรทัดค่าเสื่อมราคารายเดือน -- 1 สินทรัพย์ = 1 บรรทัดต่อ 1 เดือน

เก็บครบทั้งยอดยกมา ค่าเสื่อม และยอดยกไป เพื่อให้ตรวจย้อนได้ว่าเดือนไหน
คิดจากอะไร และให้รายงาน 12 เดือนหยิบไปวางเป็นคอลัมน์ได้ตรง ๆ

นำเข้าข้อมูลได้ด้วยเมนูนำเข้ามาตรฐานของ Odoo (สินทรัพย์ / ปี / เดือน /
ยอดยกมา / ค่าเสื่อม) สำหรับใครที่อยากยกประวัติเดือนเก่ามาทั้งชุด
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

MONTHS = [
    ('1', 'ม.ค.'), ('2', 'ก.พ.'), ('3', 'มี.ค.'), ('4', 'เม.ย.'),
    ('5', 'พ.ค.'), ('6', 'มิ.ย.'), ('7', 'ก.ค.'), ('8', 'ส.ค.'),
    ('9', 'ก.ย.'), ('10', 'ต.ค.'), ('11', 'พ.ย.'), ('12', 'ธ.ค.'),
]


class NpdAssetDepreciationLine(models.Model):
    _name = 'npd.asset.depreciation.line'
    _description = 'ค่าเสื่อมราคาสินทรัพย์รายเดือน'
    _order = 'year desc, month_no, asset_id'
    # o14 เก็บชื่อไว้ในฟิลด์ display_name (store) แต่ o18 display_name เป็นฟิลด์ระบบ
    # ที่ห้ามเก็บลงฐานข้อมูล จึงย้ายมาเก็บที่ name แทน
    _rec_name = 'name'
    _check_company_auto = True

    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='สินทรัพย์',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    # เก็บเป็นคอลัมน์จริง (store) เพื่อให้จัดกลุ่ม/กรอง/ออกรายงานได้เร็ว
    profile_id = fields.Many2one(
        related='asset_id.profile_id',
        string='หมวดสินทรัพย์',
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related='asset_id.company_id',
        string='บริษัท',
        store=True,
        index=True,
    )
    asset_code = fields.Char(related='asset_id.code', string='รหัสทรัพย์สิน', store=True)
    # OCA 18 เก็บราคาเป็น Monetary ฟิลด์ related ต้องเป็นชนิดเดียวกัน
    currency_id = fields.Many2one(related='asset_id.currency_id', string='สกุลเงิน')
    purchase_value = fields.Monetary(related='asset_id.purchase_value',
                                     string='ราคาทรัพย์สิน', store=True,
                                     currency_field='currency_id')
    depre_rate = fields.Float(related='asset_id.npd_depre_rate',
                              string='ร้อยละต่อปี', store=True)
    date_purchase = fields.Date(related='asset_id.date_start',
                                string='วันที่ซื้อ', store=True)

    year = fields.Integer(string='ปี (ค.ศ.)', required=True, index=True)
    month = fields.Selection(MONTHS, string='เดือน', required=True, index=True)
    year_label = fields.Char(
        string='ปี (ค.ศ.)',
        compute='_compute_year_label',
        store=True,
        help='ปีแบบข้อความ ใช้แสดงบนตารางไม่ให้ขึ้นลูกน้ำคั่นหลักพัน',
    )
    year_be_label = fields.Char(
        string='ปี (พ.ศ.)',
        compute='_compute_year_label',
        store=True,
    )
    month_no = fields.Integer(
        string='ลำดับเดือน',
        compute='_compute_month_no',
        store=True,
        index=True,
        help='เก็บเลขเดือนเป็นตัวเลขไว้เรียงลำดับ เพราะช่องเดือนเก็บเป็นข้อความ',
    )
    date_start = fields.Date(string='ต้นเดือน', required=True)
    date_end = fields.Date(string='สิ้นเดือน', required=True, index=True)
    days = fields.Integer(string='จำนวนวันที่คิด')

    opening_value = fields.Float(string='ยอดยกมา', digits='Account')
    depreciation = fields.Float(string='ค่าเสื่อม', digits='Account')
    closing_value = fields.Float(string='ยอดยกไป', digits='Account')

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='สมุดรายวัน',
        readonly=True,
        ondelete='set null',
        copy=False,
    )
    state = fields.Selection(
        selection=[('draft', 'ยังไม่ลงบัญชี'), ('posted', 'ลงบัญชีแล้ว')],
        string='สถานะ',
        default='draft',
        required=True,
        index=True,
    )

    name = fields.Char(string='งวดค่าเสื่อม', compute='_compute_name', store=True)

    _sql_constraints = [
        ('asset_period_uniq',
         'unique(asset_id, year, month)',
         'สินทรัพย์ 1 ตัวมีค่าเสื่อมได้เดือนละ 1 บรรทัดเท่านั้น'),
    ]

    @api.depends('year')
    def _compute_year_label(self):
        for line in self:
            line.year_label = str(line.year) if line.year else ''
            line.year_be_label = str(line.year + 543) if line.year else ''

    @api.depends('month')
    def _compute_month_no(self):
        for line in self:
            line.month_no = int(line.month) if line.month else 0

    @api.depends('asset_id', 'asset_id.code', 'asset_id.name', 'year', 'month')
    def _compute_name(self):
        labels = dict(MONTHS)
        for line in self:
            line.name = '%s %s/%s' % (
                line.asset_id.code or line.asset_id.name or '',
                labels.get(line.month, ''),
                (line.year or 0) + 543,
            )

    # ------------------------------------------------------------------
    # ซิงก์ตาราง 12 เดือน (npd.asset.depreciation.year) ให้ตรงเสมอ
    # ตารางนั้นเป็นแค่มุมมองที่กางเดือนออกเป็นคอลัมน์ ต้นฉบับคือบรรทัดนี้
    # ------------------------------------------------------------------
    def _sync_year_table(self):
        if not self:
            return
        self.env['npd.asset.depreciation.year']._sync_assets(
            self.mapped('asset_id').ids, self.mapped('year'))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_year_table()
        return lines

    def write(self, vals):
        res = super().write(vals)
        self._sync_year_table()
        return res

    # ------------------------------------------------------------------
    # ลงบัญชี
    # ------------------------------------------------------------------
    def _prepare_depreciation_move(self):
        """เดบิต ค่าเสื่อมราคา / เครดิต ค่าเสื่อมราคาสะสม ตามผังบัญชีของหมวด"""
        self.ensure_one()
        profile = self.asset_id.profile_id
        if not profile:
            raise UserError(_('สินทรัพย์ %s ยังไม่ได้เลือกหมวดสินทรัพย์ '
                              'จึงไม่รู้ว่าต้องลงบัญชีตัวไหน')
                            % (self.asset_id.name or ''))
        if not profile.journal_id or not profile.account_depreciation_id \
                or not profile.account_expense_depreciation_id:
            raise UserError(_('หมวดสินทรัพย์ %s ยังตั้งสมุดรายวันหรือผังบัญชี'
                              'ค่าเสื่อมไม่ครบ') % (profile.name or ''))

        label = '%s %s' % (_('ค่าเสื่อมราคา'), self.name)
        return {
            'journal_id': profile.journal_id.id,
            'company_id': self.company_id.id,
            'date': self.date_end,
            'ref': label,
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {
                    'name': label,
                    'account_id': profile.account_expense_depreciation_id.id,
                    'debit': self.depreciation,
                    'credit': 0.0,
                    'partner_id': False,
                }),
                (0, 0, {
                    'name': label,
                    'account_id': profile.account_depreciation_id.id,
                    'debit': 0.0,
                    'credit': self.depreciation,
                    'partner_id': False,
                }),
            ],
        }

    def action_post(self):
        """สร้างสมุดรายวันให้บรรทัดที่ยังไม่ลงบัญชี (ข้ามบรรทัดค่าเสื่อม 0)"""
        posted = 0
        for line in self:
            if line.state == 'posted':
                continue
            if not line.depreciation:
                continue          # เดือนที่ไม่มีค่าเสื่อม ไม่ต้องมีสมุดรายวัน
            # ฐานเดียวหลายบริษัท: สร้าง/ลงบัญชีในบริษัทของสินทรัพย์ตัวนั้นเสมอ
            Move = self.env['account.move'].with_company(line.company_id)
            move = line.move_id
            if move and move.state == 'draft':
                # เคยถอนการลงบัญชีไว้ ใบเดิมยังเป็นฉบับร่างอยู่ เอามาใช้ต่อ
                # ปรับยอด/วันที่ให้ตรงกับที่คำนวณรอบล่าสุดก่อนค่อยลงบัญชีซ้ำ
                line._npd_refresh_move(move.with_company(line.company_id))
            elif not move:
                move = Move.create(line._prepare_depreciation_move())
            move.with_company(line.company_id).action_post()
            line.write({'move_id': move.id, 'state': 'posted'})
            posted += 1
        return posted

    def _npd_refresh_move(self, move):
        """ปรับใบสมุดรายวันฉบับร่างให้ตรงกับยอดที่คำนวณล่าสุด

        ไม่แตะสมุดรายวัน (journal_id) เพราะเลขที่เอกสารออกมาจากสมุดนั้นแล้ว
        ถ้าย้ายสมุด เลขที่จะไม่ตรงกับเล่ม
        """
        self.ensure_one()
        vals = self._prepare_depreciation_move()
        move.write({
            'date': vals['date'],
            'ref': vals['ref'],
            'line_ids': [(5, 0, 0)] + vals['line_ids'],
        })

    def _npd_move_to_draft(self, move):
        """พาสมุดรายวันกลับเป็นฉบับร่าง

        บางฐานติดโมดูล user_cancel_control ที่ห้ามผู้ใช้ที่ไม่มีสิทธิ์กดยกเลิก
        เอกสารใด ๆ ทำให้ถอนการลงบัญชีค่าเสื่อมไม่ผ่านทั้งที่เป็นเอกสารที่
        ระบบออกเองและกำลังจะถูกลบอยู่แล้ว จึงข้ามด่านนั้นเฉพาะเอกสารชุดนี้
        การตรวจวันที่ปิดงวดยังทำงานตามปกติ (อยู่ใน write ของ account.move)
        """
        if move.state != 'posted':
            return
        Users = self.env['res.users']
        blocked = 'allow_cancel' in Users._fields and not self.env.user.allow_cancel
        if blocked:
            move.write({'state': 'draft'})
        else:
            move.button_draft()

    def action_unpost(self):
        """ถอนการลงบัญชี -- ดึงสมุดรายวันกลับเป็นฉบับร่าง ไม่ลบทิ้ง

        เดิมลบใบทิ้ง แต่ Odoo ห้ามลบเอกสารที่เคยลงบัญชีไปแล้ว
        (You cannot delete an entry which has been posted once)
        กด "กลับเป็นฉบับร่าง" ที่สินทรัพย์จึงพังทั้งชุด

        เก็บใบไว้เป็นฉบับร่างดีกว่าอยู่แล้ว -- เลขที่เอกสารไม่หาย ไม่มีรูโหว่
        ในเล่ม และถ้ากดเริ่มคิดค่าเสื่อมใหม่ ระบบเอาใบเดิมมาลงบัญชีซ้ำได้เลย
        """
        for line in self:
            if line.move_id:
                self._npd_move_to_draft(line.move_id.with_company(line.company_id))
            line.state = 'draft'
        return True

    def unlink(self):
        if any(line.state == 'posted' for line in self):
            raise UserError(_('ลบบรรทัดที่ลงบัญชีแล้วไม่ได้ '
                              'ต้องกดถอนการลงบัญชีก่อน'))
        assets = self.mapped('asset_id').ids
        years = self.mapped('year')
        res = super().unlink()
        self.env['npd.asset.depreciation.year']._sync_assets(assets, years)
        return res
