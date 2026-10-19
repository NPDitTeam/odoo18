# -*- coding: utf-8 -*-
# models/insurance_deposit_docs.py
# แสดงค่าประกันคงเหลือของลูกค้าในหน้า "การรับชำระ" (วิธีชำระ หักเงินประกันค่าเช่า)
# และหน้า "คืนเงินประกันค่าเช่า" (account.voucher)

import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from .res_partner import INSURANCE_ACCOUNT_CODE
from .insurance_chain import NO_SO, TOLERANCE

_logger = logging.getLogger(__name__)
INSURANCE_DEDUCT_METHOD = 'หักเงินประกันค่าเช่า'
NEGATIVE_BALANCE_MSG = ("ยอดเงินประกันติดลบ ไม่สามารถบันทึกได้ โปรดติดต่อฝ่ายการเงิน\n\n"
                        "ลูกค้า: %s\nค่าประกันคงเหลือ: %s\nยอด%sใบนี้: %s\nคงเหลือหลัง%s: %s")


def _fmt(amount):
    return '{:,.2f}'.format(amount)


def _check_not_negative(records, amount_field, label):
    """ห้ามหัก/คืนเงินประกันจนยอดรวมของลูกค้าติดลบ (เฉพาะใบที่ยังไม่ลงบันทึก)

    บล็อกเฉพาะเมื่อยอดรวมของลูกค้าติดลบ (ใช้เงินประกันข้าม SO ของลูกค้าคนเดียวกันได้ตามปกติ)
    แต่ข้อความ Error อธิบายสาเหตุตามสาย SO ของเอกสาร เช่น เงินประกันไม่เคยเข้าระบบ / ใช้เกินยอดที่รับ
    ให้พนักงานรู้ว่าผิดเพราะอะไรและต้องทำอะไรต่อ"""
    engine = records.env['npd.insurance.chain.engine']
    for rec in records:
        if rec.state != 'draft' or rec[amount_field] <= TOLERANCE:
            continue
        if rec.currency_id.compare_amounts(rec.insurance_balance_after, -TOLERANCE) >= 0:
            continue
        exclude = rec._origin.move_id.ids if rec._origin else []
        chains = {}
        for so_name in rec._insurance_so_names():
            c = engine.chain_for_so(rec.partner_id, so_name, exclude)
            chains.setdefault(c['root'], c)
        chains.pop(NO_SO, None)
        if len(chains) == 1:
            msg = engine.staff_error(list(chains.values())[0], label, rec[amount_field])
            if msg:
                raise ValidationError(msg + _customer_line(rec, amount_field))
        elif len(chains) > 1:
            # หลายสายในใบเดียว: ตรวจยอดรวมของทุกสาย
            merged = {'root': ', '.join(chains), 'so_names': [], 'entries': [],
                      'received': sum(c['received'] for c in chains.values()),
                      'deducted': sum(c['deducted'] for c in chains.values()),
                      'refunded': sum(c['refunded'] for c in chains.values()),
                      'balance': sum(c['balance'] for c in chains.values()),
                      'cancelled_ins': [], 'root_so': False}
            if merged['received'] < TOLERANCE:
                msg = engine.staff_error(list(chains.values())[0], label, rec[amount_field])
            else:
                msg = engine.staff_error(merged, label, rec[amount_field])
            if msg:
                raise ValidationError(msg + _customer_line(rec, amount_field))
        raise ValidationError(NEGATIVE_BALANCE_MSG % (
            rec.partner_id.display_name, _fmt(rec.insurance_balance_before), label,
            _fmt(rec[amount_field]), label, _fmt(rec.insurance_balance_after)))


def _customer_line(rec, amount_field):
    return '\n\nยอดเงินประกันรวมของลูกค้า %s: คงเหลือ %s / รายการนี้ %s / หลังทำรายการ %s บาท (ติดลบ)' % (
        rec.partner_id.display_name, _fmt(rec.insurance_balance_before), _fmt(rec[amount_field]),
        _fmt(rec.insurance_balance_after))


class AccountPaymentInsuranceDeposit(models.Model):
    _inherit = 'account.payment'

    is_insurance_deduct = fields.Boolean(
        compute='_compute_insurance_deposit_info',
        string='หักเงินประกันค่าเช่า',
    )
    insurance_balance_before = fields.Monetary(
        string='ค่าประกันคงเหลือของลูกค้า',
        compute='_compute_insurance_deposit_info',
        currency_field='currency_id',
        help='ยอดคงเหลือบัญชี 2133-01 ของลูกค้า ไม่รวมใบรับชำระนี้ = ยอดที่ใช้หักได้สูงสุด',
    )
    insurance_deduct_amount = fields.Monetary(
        string='ยอดหักเงินประกันใบนี้',
        compute='_compute_insurance_deposit_info',
        currency_field='currency_id',
    )
    insurance_balance_after = fields.Monetary(
        string='ค่าประกันคงเหลือหลังหัก',
        compute='_compute_insurance_deposit_info',
        currency_field='currency_id',
    )

    @api.depends('partner_id', 'amount', 'is_payment_multi', 'payment_method_one_id',
                 'paid_ids.payment_method_id', 'paid_ids.amount', 'state')
    def _compute_insurance_deposit_info(self):
        for pay in self:
            if pay.is_payment_multi:
                lines = pay.paid_ids.filtered(lambda l: l.payment_method_id.name == INSURANCE_DEDUCT_METHOD)
                is_deduct = bool(lines)
                deduct = sum(lines.mapped('amount'))  # o18: account.paid.line.amount (o14 = total)
            else:
                is_deduct = pay.payment_method_one_id.name == INSURANCE_DEDUCT_METHOD
                deduct = pay.amount if is_deduct else 0.0

            before = 0.0
            if is_deduct and pay.partner_id:
                move_ids = pay._origin.move_id.ids if pay._origin else []
                before = pay.partner_id._get_insurance_deposit_balance(exclude_move_ids=move_ids)

            pay.is_insurance_deduct = is_deduct
            pay.insurance_balance_before = before
            pay.insurance_deduct_amount = deduct
            pay.insurance_balance_after = before - deduct

    def _insurance_so_names(self):
        """SO ของใบแจ้งหนี้ที่ใบรับชำระนี้หักเงินประกันไปชำระ"""
        self.ensure_one()
        names = [n.strip() for n in (self.search_invoice_name or '').split(',') if n.strip()]
        if names:
            invoices = self.env['account.move'].sudo().search([('name', 'in', names)])
        else:
            # ยังไม่ได้สร้างเลขใบแจ้งหนี้ → ใช้แถวในตาราง Invoice ที่มียอดชำระ
            invoices = self.custom_invoice_ids.filtered(lambda l: l.paid_total).mapped('invoice_id')  # o18: custom_invoice_ids (o14 = invoice_ids)
        return [so for so in dict.fromkeys(invoices.mapped('invoice_origin')) if so and so.startswith('SO')]

    @api.constrains('partner_id', 'amount', 'is_payment_multi', 'payment_method_one_id', 'paid_ids')
    def _constrains_insurance_not_negative(self):
        _check_not_negative(self.filtered('is_insurance_deduct'), 'insurance_deduct_amount', 'หักเงินประกัน')

    def action_post(self):
        # ตรวจซ้ำตอนลงบันทึก เผื่อยอดคงเหลือเปลี่ยนหลังบันทึกร่าง (มีใบอื่นหัก/คืนไปก่อน)
        _check_not_negative(self.filtered('is_insurance_deduct'), 'insurance_deduct_amount', 'หักเงินประกัน')
        return super().action_post()


class AccountVoucherInsuranceDeposit(models.Model):
    _inherit = 'account.voucher'

    insurance_balance_before = fields.Monetary(
        string='ค่าประกันคงเหลือของลูกค้า',
        compute='_compute_insurance_deposit_info',
        currency_field='currency_id',
        help='ยอดคงเหลือบัญชี 2133-01 ของลูกค้า ไม่รวมใบคืนเงินประกันนี้ = ยอดที่ต้องคืนทั้งหมด',
    )
    insurance_refund_amount = fields.Monetary(
        string='ยอดคืนเงินประกันใบนี้',
        compute='_compute_insurance_deposit_info',
        currency_field='currency_id',
    )
    insurance_balance_after = fields.Monetary(
        string='ค่าประกันคงเหลือหลังคืน',
        compute='_compute_insurance_deposit_info',
        currency_field='currency_id',
    )
    # สาเหตุที่คืนเงินประกันผิด (แสดงเป็นกล่องเตือนด้านบนฟอร์ม ให้พนักงานเห็นและแก้ได้ทันที)
    insurance_problem_reason = fields.Text(
        string='สาเหตุที่คืนเงินประกันผิด',
        compute='_compute_insurance_problem_reason',
    )
    insurance_problem_level = fields.Selection(
        [('danger', 'บันทึกไม่ได้'), ('warning', 'คำเตือน')],
        compute='_compute_insurance_problem_reason',
    )

    @api.depends('partner_id', 'line_ids.price_subtotal', 'line_ids.account_id', 'state', 'check_show')
    def _compute_insurance_deposit_info(self):
        accounts = self.env['res.partner']._insurance_accounts()
        for voucher in self:
            before = refund = 0.0
            if voucher.check_show and voucher.partner_id:
                move_ids = voucher._origin.move_id.ids if voucher._origin else []
                before = voucher.partner_id._get_insurance_deposit_balance(exclude_move_ids=move_ids)
                refund = sum(voucher.line_ids.filtered(
                    lambda l: l.account_id in accounts).mapped('price_subtotal'))
            voucher.insurance_balance_before = before
            voucher.insurance_refund_amount = refund
            voucher.insurance_balance_after = before - refund

    @api.depends('partner_id', 'reference', 'line_ids.price_subtotal', 'line_ids.account_id', 'state', 'check_show')
    def _compute_insurance_problem_reason(self):
        """เฉพาะส่วน "สาเหตุ" (ไม่รวมสิ่งที่ต้องทำ) ของสาย SO ใน Bill Reference
        - ใบร่าง: ถ้าคืนใบนี้แล้วสาย SO ไม่มีเงินประกันเข้าระบบ / ใช้เกินยอด
            danger  = ยอดรวมลูกค้าจะติดลบ → บันทึกไม่ได้
            warning = สาย SO นี้ไม่พอ แต่ลูกค้ามีเงินประกันจาก SO อื่น → บันทึกได้ แต่ควรตรวจ
        - ใบที่ลงบันทึกแล้ว: แสดงสาเหตุถ้าสาย SO นี้มีปัญหา (ใช้ไล่เคสย้อนหลัง)"""
        engine = self.env['npd.insurance.chain.engine']
        for voucher in self:
            reason, level = False, False
            so_names = voucher._insurance_so_names() if voucher.check_show and voucher.partner_id else []
            if so_names and voucher.state != 'cancel':
                if voucher.state == 'draft':
                    exclude = voucher._origin.move_id.ids if voucher._origin else []
                    c = engine.chain_for_so(voucher.partner_id, so_names[0], exclude)
                    msg = engine.staff_error(c, 'คืนเงินประกัน', voucher.insurance_refund_amount) \
                        if voucher.insurance_refund_amount > TOLERANCE else None
                    if msg:
                        reason = msg.split('\n\nสิ่งที่ต้องทำ')[0].strip()
                        level = 'danger' if voucher.insurance_balance_after < -TOLERANCE else 'warning'
                        if level == 'warning':
                            reason = reason.replace('ไม่สามารถคืนเงินประกันได้: ', 'คำเตือน: ', 1) + (
                                '\nบันทึกได้ เพราะลูกค้ายังมีเงินประกันจาก SO อื่นเหลือ %s บาท '
                                'แต่ควรตรวจว่าตั้งใจใช้เงินประกันข้าม SO จริง' % '{:,.2f}'.format(voucher.insurance_balance_before))
                else:
                    c = engine.chain_for_so(voucher.partner_id, so_names[0])
                    if c['status'] in ('wrong_partner', 'no_ins', 'over'):
                        reason, level = c['reason'], 'danger'
            voucher.insurance_problem_reason = reason
            voucher.insurance_problem_level = level

    def _insurance_so_names(self):
        """SO ใน Bill Reference ของใบคืนเงินประกัน"""
        self.ensure_one()
        ref = (self.reference or '').strip()
        return [ref] if ref.startswith('SO') else []

    # ไม่ตรวจตอนบันทึก (constrains) เพราะขั้นตอนจริงคือ เลือกใบแจ้งหนี้ → กด "รับชำระหนี้ค้างชำระ"
    # (สร้าง+ลงบันทึกใบหักเงินประกัน แล้วค่อยลดยอดคืนในใบนี้) ระหว่างนั้นยอดคืนยังไม่ลด
    # ถ้าตรวจตอนบันทึกจะบล็อกกลางทาง ทั้งที่ใบหักลงบันทึก (commit) ไปแล้ว → ตรวจตอน Validate อย่างเดียว
    # ระหว่างเป็นร่าง พนักงานเห็นสาเหตุจากกล่องเตือนบนฟอร์ม (insurance_problem_reason)

    def proforma_voucher(self):
        # ตรวจตอนกด Validate (ยอดคืนในใบนี้ลดตามใบหักเงินประกันเรียบร้อยแล้ว)
        _check_not_negative(self.filtered('check_show'), 'insurance_refund_amount', 'คืนเงินประกัน')
        return super().proforma_voucher()


def _refresh_chains(partners):
    """คำนวณสาย SO ของลูกค้าใหม่หลังมีรายการเงินประกัน (ให้เมนูตรวจสอบเงินประกันเป็นปัจจุบัน)
    ผิดพลาดก็ไม่ขวางการลงบันทึกเอกสาร"""
    Chain = partners.env['npd.insurance.chain']
    for partner in partners.mapped('commercial_partner_id'):
        try:
            with partners.env.cr.savepoint():
                Chain._refresh_partner(partner)
        except Exception:
            _logger.exception('insurance chain refresh failed for partner %s', partner.id)


class AccountMoveInsuranceChain(models.Model):
    _inherit = 'account.move'

    def _insurance_partners(self):
        accounts = self.env['res.partner']._insurance_accounts()
        if not accounts:
            return self.env['res.partner']
        return self.mapped('line_ids').filtered(lambda l: l.account_id in accounts).mapped('partner_id')

    def _post(self, soft=True):
        # ใบรับชำระ (account.payment) และใบคืนเงินประกันลงบันทึกผ่าน _post ไม่ใช่ action_post
        posted = super()._post(soft=soft)
        _refresh_chains(posted._insurance_partners())
        return posted

    def button_cancel(self):
        partners = self._insurance_partners()
        res = super().button_cancel()
        _refresh_chains(partners)
        return res

    def button_draft(self):
        partners = self._insurance_partners()
        res = super().button_draft()
        _refresh_chains(partners)
        return res
