from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    npd_other_receivable_amount = fields.Monetary(
        string='ยอดลูกหนี้อื่น (รอใบหัก ณ ที่จ่าย)', compute='_compute_npd_other_receivable_amount',
        store=True, currency_field='currency_id')
    npd_wht_file_ids = fields.One2many('npd.payment.wht.file', 'payment_id', string='ไฟล์ใบหัก ณ ที่จ่าย')
    npd_wht_reclassed = fields.Boolean(
        string='โอนลูกหนี้อื่นเป็นภาษีถูกหักแล้ว', readonly=True, copy=False,
        help='ลงบัญชี Dr ภาษีเงินได้ถูกหัก ณ ที่จ่าย / Cr ลูกหนี้อื่น ในรายการบันทึกบัญชีของใบนี้แล้ว')
    npd_wht_file_state = fields.Selection([
        ('pending', 'ยังไม่บันทึกไฟล์หัก ณ ที่จ่าย'),
        ('done', 'บันทึกไฟล์หัก ณ ที่จ่ายแล้ว'),
    ], string='สถานะไฟล์หัก ณ ที่จ่าย', compute='_compute_npd_wht_file_state', store=True)

    @api.depends('is_payment_multi', 'paid_ids.amount', 'paid_ids.npd_kind', 'paid_ids.is_write_off')
    def _compute_npd_other_receivable_amount(self):
        for pay in self:
            lines = pay._npd_other_receivable_lines()
            pay.npd_other_receivable_amount = sum(lines.mapped('amount'))

    @api.depends('npd_other_receivable_amount', 'npd_wht_file_ids')
    def _compute_npd_wht_file_state(self):
        for pay in self:
            if not pay.npd_other_receivable_amount:
                pay.npd_wht_file_state = False
            else:
                pay.npd_wht_file_state = 'done' if pay.npd_wht_file_ids else 'pending'

    # ------------------------------------------------------------------
    def _npd_other_receivable_lines(self):
        self.ensure_one()
        if not self.is_payment_multi:
            return self.env['account.paid.line']
        return self.paid_ids.filtered(lambda l: l.npd_kind == 'other_receivable' and not l.is_write_off and l.amount)

    def _npd_wht_account(self):
        self.ensure_one()
        method = self.env['custom.payment.method'].sudo().search([
            ('company_id', '=', self.company_id.id), ('npd_kind', '=', 'wht')], limit=1)
        if not method:
            raise UserError(_('บริษัท %s ยังไม่ได้ตั้งวิธีชำระ "ภาษีเงินได้ถูกหัก ณ ที่จ่าย" '
                              '(ใช้เป็นบัญชีปลายทางตอนแนบใบหัก ณ ที่จ่าย)') % self.company_id.name)
        return method.account_id

    def _npd_wht_reclass_vals(self):
        """Dr ภาษีเงินได้ถูกหัก ณ ที่จ่าย / Cr ลูกหนี้อื่น (ยอดเท่าบรรทัดลูกหนี้อื่นในหน้ารับชำระ)"""
        self.ensure_one()
        lines = self._npd_other_receivable_lines()
        if not lines:
            return []
        sign = 1 if self.payment_type == 'inbound' else -1
        currency_id = self.currency_id.id
        vals = []
        for account in lines.mapped('account_id'):
            amount = sign * sum(lines.filtered(lambda l: l.account_id == account).mapped('amount'))
            vals.append({
                'name': _('โอนลูกหนี้อื่น → ภาษีถูกหัก ณ ที่จ่าย (ได้รับใบแล้ว)'),
                'account_id': account.id,
                'partner_id': self.partner_id.id,
                'amount_currency': -amount,
                'currency_id': currency_id,
                'debit': -amount if amount < 0 else 0.0,
                'credit': amount if amount > 0 else 0.0,
                'date_maturity': self.date,
            })
        total = sign * sum(lines.mapped('amount'))
        vals.insert(0, {
            'name': _('ภาษีเงินได้ถูกหัก ณ ที่จ่าย (ได้รับใบแล้ว)'),
            'account_id': self._npd_wht_account().id,
            'partner_id': self.partner_id.id,
            'amount_currency': total,
            'currency_id': currency_id,
            'debit': total if total > 0 else 0.0,
            'credit': -total if total < 0 else 0.0,
            'date_maturity': self.date,
        })
        return vals

    def _prepare_payment_move_lines(self):
        # รีเซ็ตเป็นร่างแล้วลงบันทึกใหม่ ต้องไม่ทำรายการโอนที่ลงไปแล้วหาย
        vals = super()._prepare_payment_move_lines()
        if self.npd_wht_reclassed and vals:
            vals += self._npd_wht_reclass_vals()
        return vals

    def _npd_apply_wht_reclass(self):
        """เพิ่ม 2 บรรทัดโอนลูกหนี้อื่น → ภาษีถูกหัก ณ ที่จ่าย ลงในรายการบันทึกบัญชี (RV) ที่ลงแล้ว"""
        self.ensure_one()
        if self.npd_wht_reclassed:
            return False
        move = self.move_id
        if not move or move.state != 'posted':
            raise UserError(_('ใบรับชำระนี้ยังไม่มีรายการบันทึกบัญชีที่ลงบันทึกแล้ว'))
        vals = self._npd_wht_reclass_vals()
        if not vals:
            return False
        # ใบที่ลงแล้วแก้ line_ids ผ่านหัวใบไม่ได้ และห้ามรีเซ็ตเป็นร่าง (จะตัดคู่กับใบแจ้งหนี้ทิ้ง)
        # จึงเพิ่มบรรทัดตรง ๆ 2 บรรทัดพร้อมกัน (สมดุลในตัว)
        self.env['account.move.line'].sudo().with_context(
            check_move_validity=False, skip_account_move_synchronization=True, skip_invoice_sync=True,
        ).create([dict(v, move_id=move.id) for v in vals])
        move.invalidate_recordset(['line_ids'])
        if not move.currency_id.is_zero(sum(move.line_ids.mapped('balance'))):
            raise UserError(_('รายการบันทึกบัญชี %s ไม่สมดุลหลังเพิ่มรายการโอน') % move.name)
        self.npd_wht_reclassed = True
        return True

    def action_npd_open_wht_file_wizard(self):
        self.ensure_one()
        if self.state not in ('in_process', 'paid'):
            raise UserError(_('เพิ่มใบหัก ณ ที่จ่ายได้เฉพาะใบที่ลงบันทึกแล้ว'))
        if not self.npd_other_receivable_amount:
            raise UserError(_('ใบนี้ไม่มีรายการลูกหนี้อื่นในหน้ารับชำระ'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('เพิ่มใบหัก ณ ที่จ่าย'),
            'res_model': 'npd.payment.wht.file.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payment_id': self.id},
        }
