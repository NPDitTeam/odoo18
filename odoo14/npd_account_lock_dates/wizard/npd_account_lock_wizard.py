# -*- coding: utf-8 -*-
"""หน้าจอตั้งวันล็อกงวดบัญชีทีละบริษัท

หน้าจอนี้ไม่เขียนฟิลด์ล็อกเอง: ตรวจเงื่อนไขภาษาไทยของเราก่อน แล้วส่งต่อให้
res.company.write ตามปกติ ตัวตรวจของ Odoo (_validate_locks) และการสร้างข้อยกเว้นการล็อกใหม่
จึงทำงานครบเหมือนตั้งจากที่อื่น ห้ามเปลี่ยนไปเขียน SQL หรือใช้ bypass_lock_check
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import format_date

from ..models.lock_fields import (
    LOCK_DATE_FIELDS,
    LOCK_FIELD_HELP,
    LOCK_FIELD_LABELS,
    LOCK_GROUP,
    SOFT_LOCK_DATE_FIELDS,
    WIZARD_WRITE,
    max_lock_date,
)

# ค่าเสื่อมรายเดือนของทีม (npd_asset_depreciation) ไม่ได้ใส่เป็น depends ให้โมดูลนี้ติดตั้งบนฐานเปล่าได้
# จึงเช็กว่ามีโมเดลในฐานก่อนนับทุกครั้ง
DEPRECIATION_LINE_MODEL = 'npd.asset.depreciation.line'


def _orig_field(fname):
    # ค่าตอนเปิดหน้าจอ ใช้หาว่าช่องไหนถูกแก้ และจับกรณีมีคนอื่นแก้ระหว่างที่เปิดค้างไว้
    return fields.Date(
        string='ปัจจุบัน: ' + LOCK_FIELD_LABELS[fname],
        compute='_compute_lock_values', store=True, readonly=False, precompute=True,
    )


def _new_field(fname):
    return fields.Date(
        string=LOCK_FIELD_LABELS[fname], help=LOCK_FIELD_HELP[fname],
        compute='_compute_lock_values', store=True, readonly=False, precompute=True,
    )


class NpdAccountLockWizard(models.TransientModel):
    _name = 'npd.account.lock.wizard'
    _description = 'ตั้งวันล็อกงวดบัญชี'

    # จำกัดที่บริษัทที่ติ๊กอยู่มุมขวาบน เพราะกฎ res.company ของพนักงานอ่านได้แค่นั้น
    # (ฝั่งเซิร์ฟเวอร์ตรวจซ้ำใน action_apply)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company,
        domain="[('id', 'in', allowed_company_ids)]",
    )

    orig_fiscalyear_lock_date = _orig_field('fiscalyear_lock_date')
    orig_tax_lock_date = _orig_field('tax_lock_date')
    orig_sale_lock_date = _orig_field('sale_lock_date')
    orig_purchase_lock_date = _orig_field('purchase_lock_date')
    orig_hard_lock_date = _orig_field('hard_lock_date')

    new_fiscalyear_lock_date = _new_field('fiscalyear_lock_date')
    new_tax_lock_date = _new_field('tax_lock_date')
    new_sale_lock_date = _new_field('sale_lock_date')
    new_purchase_lock_date = _new_field('purchase_lock_date')
    new_hard_lock_date = _new_field('hard_lock_date')

    hard_lock_changed = fields.Boolean(compute='_compute_flags')
    has_unlock = fields.Boolean(compute='_compute_flags')
    new_effective_date = fields.Date(string='ล็อกทุกสมุดใหม่มีผลถึง', compute='_compute_flags')

    hard_lock_confirm = fields.Boolean(string='เข้าใจแล้วว่าล็อกถาวรย้อนกลับไม่ได้')
    note = fields.Text(
        string='เหตุผล / หมายเหตุ',
        help='ต้องกรอกเมื่อปลดล็อก/ถอยวันล็อก หรือเปลี่ยนล็อกถาวร จะถูกบันทึกในประวัติการล็อกงวด',
    )

    draft_move_count = fields.Integer(compute='_compute_checks')
    unreconciled_line_count = fields.Integer(compute='_compute_checks')
    no_posted_moves = fields.Boolean(compute='_compute_checks')
    pending_depreciation_count = fields.Integer(compute='_compute_checks')

    # ------------------------------------------------------------------
    # compute
    # ------------------------------------------------------------------
    # ขึ้นกับ company_id อย่างเดียวโดยตั้งใจ: ถ้าผูกกับค่าบนบริษัทด้วย orig_* จะเปลี่ยนตามเมื่อมีคนอื่นแก้
    # แล้วการตรวจ "มีคนแก้ระหว่างเปิดหน้าจอ" จะจับไม่ได้
    @api.depends('company_id')
    def _compute_lock_values(self):
        for wiz in self:
            company = wiz.company_id.sudo()
            for fname in LOCK_DATE_FIELDS:
                wiz['orig_' + fname] = company[fname]
                wiz['new_' + fname] = company[fname]

    @api.depends(*('new_' + f for f in LOCK_DATE_FIELDS), *('orig_' + f for f in LOCK_DATE_FIELDS))
    def _compute_flags(self):
        for wiz in self:
            wiz.hard_lock_changed = wiz.new_hard_lock_date != wiz.orig_hard_lock_date
            wiz.has_unlock = any(
                wiz['orig_' + f] and (not wiz['new_' + f] or wiz['new_' + f] < wiz['orig_' + f])
                for f in SOFT_LOCK_DATE_FIELDS
            )
            wiz.new_effective_date = max(
                (d for d in (wiz.new_fiscalyear_lock_date, wiz.new_hard_lock_date) if d), default=False,
            )

    def _effective_moves_forward(self):
        """ล็อกทุกสมุด (ปิดงวด/ถาวร) ขยับไปข้างหน้าหรือไม่ เตือนเฉพาะกรณีนี้ ถอยหลังไม่มีอะไรต้องเตือน"""
        self.ensure_one()
        old = max((d for d in (self.orig_fiscalyear_lock_date, self.orig_hard_lock_date) if d), default=False)
        new = self.new_effective_date
        return bool(self.company_id and new and (not old or new > old))

    def _draft_moves_domain(self):
        self.ensure_one()
        # วันที่เป็นข้อความ เพราะโดเมนนี้ถูกส่งกลับไปให้หน้าเว็บด้วย (ปุ่ม ดูเอกสารร่าง)
        return [
            ('company_id', 'child_of', self.company_id.id),
            ('state', '=', 'draft'),
            ('date', '<=', fields.Date.to_string(self.new_effective_date)),
        ]

    def _pending_depreciation_domain(self):
        # เดือนที่งานตั้งเวลาค่าเสื่อมยังไม่ได้ลงบัญชี (สร้างสมุดรายวันตอนลงบัญชี จึงไม่มีเอกสารร่างให้นับ)
        # เงื่อนไขเดียวกับ _npd_post_due_lines + สินทรัพย์ที่เริ่มคิดค่าเสื่อมแล้ว ซึ่งงานตั้งเวลาจะลงให้ทีหลัง
        # ถ้าล็อกก่อน สมุดรายวันค่าเสื่อมเดือนนั้นจะถูกย้ายวันที่ไปงวดถัดไป
        self.ensure_one()
        return [
            ('company_id', 'child_of', self.company_id.id),
            ('state', '=', 'draft'),
            ('depreciation', '>', 0),
            ('date_end', '<=', fields.Date.to_string(self.new_effective_date)),
            ('asset_id.state', '=', 'open'),
        ]

    @api.depends('company_id', 'new_fiscalyear_lock_date', 'new_hard_lock_date',
                 'orig_fiscalyear_lock_date', 'orig_hard_lock_date')
    def _compute_checks(self):
        Move = self.env['account.move'].sudo()
        StatementLine = self.env['account.bank.statement.line'].sudo()
        DeprLine = (
            self.env[DEPRECIATION_LINE_MODEL].sudo() if DEPRECIATION_LINE_MODEL in self.env else None
        )
        for wiz in self:
            if not wiz._effective_moves_forward():
                wiz.draft_move_count = 0
                wiz.unreconciled_line_count = 0
                wiz.no_posted_moves = False
                wiz.pending_depreciation_count = 0
                continue
            company = wiz.company_id.sudo()
            wiz.draft_move_count = Move.search_count(wiz._draft_moves_domain())
            # ใช้โดเมนเดียวกับตัวตรวจของ Odoo ตัวเลขที่เตือนจะตรงกับที่ระบบจะปฏิเสธจริง
            wiz.unreconciled_line_count = StatementLine.search_count(
                company._get_unreconciled_statement_lines_domain(wiz.new_effective_date)
            )
            wiz.no_posted_moves = not Move.search_count(
                [('company_id', 'child_of', company.id), ('state', '=', 'posted')], limit=1,
            )
            wiz.pending_depreciation_count = (
                DeprLine.search_count(wiz._pending_depreciation_domain()) if DeprLine is not None else 0
            )

    # ------------------------------------------------------------------
    # ปุ่ม
    # ------------------------------------------------------------------
    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'name': 'ล็อกงวดบัญชี',
        }

    def action_fill_last_month(self):
        """เติมช่องอย่างเดียว ยังไม่บันทึกจนกว่าจะกด บันทึกวันล็อก"""
        self.ensure_one()
        last_day = max_lock_date(self.env)
        self.write({'new_fiscalyear_lock_date': last_day, 'new_tax_lock_date': last_day})
        return self._reopen()

    def action_view_draft_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'เอกสารร่างในช่วงที่จะล็อก',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': self._draft_moves_domain(),
            'context': {'create': False},
            'target': 'current',
        }

    def action_view_pending_depreciation(self):
        self.ensure_one()
        if DEPRECIATION_LINE_MODEL not in self.env:
            raise UserError('ฐานนี้ไม่ได้ติดตั้งโมดูลค่าเสื่อมรายเดือน')
        return {
            'type': 'ir.actions.act_window',
            'name': 'ค่าเสื่อมที่ยังไม่ลงบัญชีในช่วงที่จะล็อก',
            'res_model': DEPRECIATION_LINE_MODEL,
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': self._pending_depreciation_domain(),
            'context': {'create': False},
            'target': 'current',
        }

    def action_apply(self):
        self.ensure_one()
        # 1) สิทธิ์: กันกรณีเรียกผ่าน RPC ตรง ๆ โดยไม่ผ่านเมนู
        if not self.env.user.has_group(LOCK_GROUP):
            raise AccessError('เฉพาะผู้ใช้กลุ่ม ผู้ปิดงวดบัญชี เท่านั้น')
        # 2) บริษัทต้องติ๊กอยู่มุมขวาบน ให้ตรงกับกฎ res.company (company_ids = env.companies)
        company = self.company_id
        if company not in self.env.companies:
            raise UserError('เลือกบริษัทนี้ที่ตัวเลือกบริษัทมุมขวาบนก่อน')

        # 3) ส่งเฉพาะช่องที่เปลี่ยนจริง ส่ง hard_lock_date ค่าเดิมไปด้วยจะโดนตรวจเอกสารร่าง/ธนาคารซ้ำโดยไม่จำเป็น
        #    และช่องล็อกอื่นที่ไม่เปลี่ยนจะไปสร้างข้อยกเว้นการล็อกใหม่ทั้งที่ไม่ต้อง
        vals = {
            f: self['new_' + f]
            for f in LOCK_DATE_FIELDS
            if self['new_' + f] != self['orig_' + f]
        }
        if not vals:
            raise UserError('ยังไม่ได้เปลี่ยนวันล็อกช่องใด')

        # 4) มีคนอื่นแก้ระหว่างเปิดหน้าจอค้าง: ห้ามทับ ไม่งั้นอาจถอยล็อกของคนอื่นโดยไม่รู้ตัว
        company_sudo = company.sudo()
        company_sudo.invalidate_recordset(list(vals))
        for fname in vals:
            if company_sudo[fname] != self['orig_' + fname]:
                raise UserError(
                    'มีผู้ใช้อื่นเปลี่ยน %s ของบริษัทนี้ระหว่างที่เปิดหน้าจอ กรุณาปิดแล้วเปิดใหม่'
                    % LOCK_FIELD_LABELS[fname]
                )

        # 5) งวดที่ยังไม่จบห้ามล็อก (กันพิมพ์ปีผิด เช่น 2027 แทน 2026 แล้วเอกสารใหม่ทั้งหมดถูกย้ายไปอนาคต)
        limit = max_lock_date(self.env)
        for fname, new_date in vals.items():
            if new_date and new_date > limit:
                raise UserError(
                    'ล็อกได้ไม่เกินวันที่ %s (สิ้นเดือนที่แล้ว) งวดที่ยังไม่จบล็อกไม่ได้'
                    % format_date(self.env, limit)
                )

        # 6) ล็อกถาวร: ต้องยืนยัน และห้ามลบ/ถอย (Odoo ตรวจซ้ำอีกชั้น แต่ข้อความของเราอ่านง่ายกว่า)
        if 'hard_lock_date' in vals:
            if not self.hard_lock_confirm:
                raise UserError('ต้องติ๊ก เข้าใจแล้วว่าล็อกถาวรย้อนกลับไม่ได้ ก่อน')
            orig_hard = self.orig_hard_lock_date
            new_hard = vals['hard_lock_date']
            if orig_hard and (not new_hard or new_hard < orig_hard):
                raise UserError('ล็อกถาวรลบออกหรือเลื่อนถอยหลังไม่ได้')

        # 7) ปลดล็อก/ถอยวัน หรือแตะล็อกถาวร ต้องมีเหตุผลไว้ในประวัติ
        note = (self.note or '').strip()
        if (self.has_unlock or 'hard_lock_date' in vals) and not note:
            raise UserError('ต้องกรอกเหตุผล')

        # 8) เขียนผ่าน write ปกติ: _validate_locks ของ Odoo ยังทำงาน (UserError/RedirectWarning ส่งต่อตามเดิม)
        #    sudo เพราะสิทธิ์เขียน res.company อยู่ที่ผู้ดูแลระบบ ไม่ใช่ผู้ดูแลบัญชี
        #    ป้ายว่ามาจากหน้าจอตั้งใน contextvar แทน context ให้ประวัติแยกได้ว่าผ่านการตรวจข้างบนจริง
        old_values = {f: self['orig_' + f] for f in vals}
        token = WIZARD_WRITE.set({'note': note or False})
        try:
            company_sudo.write(vals)
        finally:
            WIZARD_WRITE.reset(token)

        def _fmt(value):
            return format_date(self.env, value) if value else 'ไม่ล็อก'

        changes = '; '.join(
            '%s %s → %s' % (LOCK_FIELD_LABELS[f], _fmt(old_values[f]), _fmt(vals[f]))
            for f in LOCK_DATE_FIELDS if f in vals
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'บันทึกวันล็อกแล้ว',
                'message': '%s: %s' % (company_sudo.name, changes),
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
