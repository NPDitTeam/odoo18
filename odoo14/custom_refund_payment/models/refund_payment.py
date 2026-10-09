from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class FleetChatterService(models.Model):
    _name = 'fleet.refund.service'
    _description = 'Fleet Refund Service'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def log_note_action(self):
        self.message_post(body="นี่คือบันทึกการติดตามสำหรับบริการ Fleet Chatter")

    @api.model
    def schedule_activity_action(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        self.activity_schedule(activity_type.id, 'ติดตามบริการ Fleet Chatter')


class RefundPayment(models.Model):
    _name = 'refund.payment'
    _description = 'Refund Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    date = fields.Date(
        string='วันที่',
        default=lambda self: date.today(),
        required=True,
        tracking=True
    )

    is_date_readonly = fields.Boolean(
        string='Date is Readonly',
        compute='_compute_is_date_readonly'
    )

    transfer_type = fields.Selection([
        ('overpaid_refund', 'คืนเงินโอนเกิน'),
        ('wtax_refund', 'คืนหัก ณ ที่จ่าย'),
        ('rental_difference', 'โอนคืนค่าเช่าส่วนต่าง'),
    ], string='ประเภทการโอน', required=True, default='')

    show_fleet_refund_button = fields.Boolean(
        string='Show Fleet Refund Button',
        compute='_compute_show_fleet_refund_button'
    )

    can_confirm_cancel = fields.Boolean(
        string='Can Confirm/Cancel',
        compute='_compute_can_confirm_cancel'
    )

    show_state = fields.Boolean(string='Show state', default=False)

    name = fields.Char(
        string='เลขเอกสาร',
        required=True,
        default='New',
        tracking=True,
        readonly=True
    )

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'ยืนยันแล้ว'),
        ('cancelled', 'ยกเลิก')
    ], string='สถานะ', default='draft', tracking=True)

    branch_id = fields.Many2one(
        'res.branch',
        string="สาขา",
        default=lambda self: self.env.user.branch_id.id if hasattr(self.env.user, 'branch_id') and self.env.user.branch_id else False,
        readonly=True
    )

    # o18 รวม 5 บริษัทไว้ในฐานเดียว ต้องรู้ว่าเอกสารเป็นของบริษัทไหน
    # ไม่งั้นจะไปหยิบใบรับชำระ/สมุด/บัญชีข้ามบริษัท
    company_id = fields.Many2one('res.company', string='บริษัท', required=True,
                                 default=lambda self: self.env.company, readonly=True)

    move_id = fields.Many2one('account.move', string='รายการบันทึกบัญชี', readonly=True)
    reversed_wtax_move_id = fields.Many2one('account.move', string='รายการบันทึกบัญชีกลับขา (Wtax)', readonly=True)

    payment_ids = fields.Many2many(
        'account.payment',
        string='เลือกการชำระเงิน',
        domain=[],
    )

    payment_lines = fields.One2many(
        'refund.payment.line',
        'refund_payment_id',
        string='รายการชำระเงิน'
    )

    # สรุปไว้แสดงในหน้ารายการ (ตามที่ทีมเพิ่มใน o14)
    payment_ref = fields.Char(string='เลขที่การชำระเงิน', compute='_compute_payment_summary', store=True)
    total_amount = fields.Float(string='จำนวนเงินรวม', compute='_compute_payment_summary', store=True)

    # Odoo 18 เลิกให้ onchange ส่ง domain กลับมาแล้ว จึงคำนวณ domain เป็นฟิลด์ให้หน้าจอใช้
    payment_ids_domain = fields.Binary(compute='_compute_payment_ids_domain')

    @api.depends('payment_lines', 'payment_lines.payment_name', 'payment_lines.amount')
    def _compute_payment_summary(self):
        for rec in self:
            names = [l.payment_name for l in rec.payment_lines if l.payment_name]
            rec.payment_ref = ', '.join(names)
            rec.total_amount = sum(rec.payment_lines.mapped('amount'))

    @api.depends('transfer_type', 'branch_id', 'company_id')
    def _compute_payment_ids_domain(self):
        for rec in self:
            domain = [('payment_type', '=', 'inbound'), ('company_id', '=', rec.company_id.id)]
            if rec.branch_id:
                domain.append(('branch_id', '=', rec.branch_id.id))
            # ใบที่คืนเงินประเภทนี้ไปแล้วไม่ให้เลือกซ้ำ
            if rec.transfer_type == 'overpaid_refund':
                domain.append(('overpaid_refund_status', '=', False))
            elif rec.transfer_type == 'wtax_refund':
                domain.append(('wtax_refund_status', '=', False))
            elif rec.transfer_type == 'rental_difference':
                domain.append(('rental_difference_status', '=', False))
            rec.payment_ids_domain = domain

    @api.depends('create_uid')
    def _compute_show_fleet_refund_button(self):
        for rec in self:
            rec.show_fleet_refund_button = getattr(rec.env.user, 'fleet_refund', False)

    @api.depends('create_uid')
    def _compute_is_date_readonly(self):
        for rec in self:
            rec.is_date_readonly = not getattr(rec.env.user, 'allow_edit_refund_date', False)

    @api.depends('create_uid')
    def _compute_can_confirm_cancel(self):
        for rec in self:
            rec.can_confirm_cancel = getattr(rec.env.user, 'can_confirm_refund_payment', False)

    def show_overpaid_reverse_button(self):
        for rec in self:
            rec.show_reverse_button = rec.transfer_type == 'overpaid_refund'

    show_reverse_button = fields.Boolean(
        string='Show Reverse Button',
        compute='show_overpaid_reverse_button'
    )

    def _get_journal(self):
        # o14 แยกฐานต่อบริษัทจึงหาสมุดด้วยชื่อได้ แต่ o18 ชื่อเดียวกันมีทุกบริษัท
        # หาด้วยชื่ออย่างเดียวจะได้สมุดของบริษัทอื่น จึงยึดค่าที่ตั้งไว้ของบริษัท
        self.ensure_one()
        if not self.company_id.refund_journal_id:
            self.company_id._npd_refund_fill_defaults()
        journal = self.company_id.refund_journal_id
        if not journal:
            raise UserError(_('บริษัท %s ยังไม่ได้ตั้ง "สมุดรายวันโอนคืนเงิน" '
                              '(ตั้งค่า > บริษัท > แท็บโอนคืนเงินลูกค้า)') % self.company_id.name)
        return journal

    def _refund_account(self, field):
        self.ensure_one()
        if not self.company_id[field]:
            # ฝ่ายบัญชีอาจเพิ่มบัญชีในผังทีหลัง ลองจับจากชื่ออีกรอบก่อนแจ้งว่าไม่ได้ตั้ง
            self.company_id._npd_refund_fill_defaults()
        account = self.company_id[field]
        if not account:
            label = self.company_id._fields[field].string
            raise UserError(_('บริษัท %s ยังไม่ได้ตั้ง "%s" '
                              '(ตั้งค่า > บริษัท > แท็บโอนคืนเงินลูกค้า)') % (self.company_id.name, label))
        return account

    def action_cancel(self):
        for rec in self:
            if not rec.env.user.can_confirm_refund_payment:
                raise UserError(_("คุณไม่มีสิทธิ์ยกเลิกเอกสารนี้"))

            if rec.state not in ['draft', 'confirmed']:
                raise UserError(_("ไม่สามารถยกเลิกเอกสารที่ถูกยกเลิกแล้ว"))

            if rec.move_id:
                if rec.move_id.state == 'posted':
                    try:
                        rec.move_id.button_draft()
                    except Exception as e:
                        raise UserError(_("ไม่สามารถเปลี่ยนสถานะเอกสารบัญชีให้เป็นร่างได้: %s" % str(e)))

            rec.state = 'cancelled'
            rec.show_state = False

            for p in rec.payment_ids:
                if rec.transfer_type == 'overpaid_refund' and hasattr(p, 'overpaid_refund_status'):
                    p.overpaid_refund_status = ''
                elif rec.transfer_type == 'wtax_refund' and hasattr(p, 'wtax_refund_status'):
                    p.wtax_refund_status = ''
                elif rec.transfer_type == 'rental_difference' and hasattr(p, 'rental_difference_status'):
                    p.rental_difference_status = ''

            rec.message_post(body='เอกสารถูกยกเลิกเรียบร้อยแล้ว')

    def action_reset_to_draft(self):
        for rec in self:
            if rec.move_id:
                if rec.move_id.state == 'posted':
                    try:
                        rec.move_id.button_draft()
                    except Exception as e:
                        raise UserError(_("ไม่สามารถเปลี่ยนสถานะเอกสารบัญชีให้เป็นร่างได้: %s" % str(e)))

            rec.state = 'draft'
            rec.show_state = False

            for p in rec.payment_ids:
                if rec.transfer_type == 'overpaid_refund' and hasattr(p, 'overpaid_refund_status'):
                    p.overpaid_refund_status = ''
                elif rec.transfer_type == 'wtax_refund' and hasattr(p, 'wtax_refund_status'):
                    p.wtax_refund_status = ''
                elif rec.transfer_type == 'rental_difference' and hasattr(p, 'rental_difference_status'):
                    p.rental_difference_status = ''

            rec.message_post(body='ยกเลิกรายการและกลับเป็นฉบับร่างเรียบร้อยแล้ว')

    @api.onchange('payment_ids')
    def _onchange_payment_ids(self):
        self.payment_lines = [(5, 0, 0)]
        line_vals = []
        for p in self.payment_ids:
            line_vals.append((0, 0, {
                'payment_name': p.name,
                'payment_id': p.id,
                'partner_id': p.partner_id.id,
                'payment_date': p.date,
            }))
        self.payment_lines = line_vals

    def _set_date_from_payment_lines(self):
        for rec in self:
            if rec.transfer_type in ('overpaid_refund', 'wtax_refund'):
                dates = [l.payment_date for l in rec.payment_lines if l.payment_date]
                if dates:
                    effective_date = max(dates)
                    if rec.date != effective_date:
                        rec.date = effective_date

    def action_reverse_overpaid(self):
        for rec in self:
            if rec.transfer_type != 'overpaid_refund':
                raise UserError("ปุ่มนี้ใช้ได้เฉพาะกรณีคืนเงินโอนเกินเท่านั้น")
            if rec.state != 'confirmed':
                raise UserError("สามารถกลับขาบัญชีได้เมื่อเอกสารอยู่ในสถานะ Confirmed เท่านั้น")

            journal = rec._get_journal()
            debit_account = rec._refund_account('refund_bank_current_account_id')
            credit_account = rec._refund_account('refund_suspense_account_id')

            lines = []
            for line in rec.payment_lines:
                lines.append((0, 0, {
                    'account_id': debit_account.id,
                    'name': f'REVERSE: {line.payment_name}',
                    'debit': 0,
                    'credit': line.amount,
                    'partner_id': line.partner_id.id,
                }))
                lines.append((0, 0, {
                    'account_id': credit_account.id,
                    'name': f'REVERSE: {line.payment_name}',
                    'debit': line.amount,
                    'credit': 0,
                    'partner_id': line.partner_id.id,
                }))

            move = self.env['account.move'].create({
                'journal_id': journal.id,
                'date': fields.Date.today(),
                'ref': rec.name + '-REVERSE',
                'line_ids': lines,
            })
            move.action_post()

            rec.move_id = move.id
            rec.message_post(body='กลับขาบัญชีสำเร็จ: %s' % move.name)
            rec.show_state = True

            if rec.transfer_type == 'overpaid_refund':
                for p in rec.payment_ids:
                    if hasattr(p, 'overpaid_refund_status'):
                        p.overpaid_refund_status = 'overpaid_refund'

    def action_reverse_wtax(self):
        for rec in self:
            if rec.transfer_type != 'wtax_refund':
                raise UserError("ปุ่มนี้ใช้ได้เฉพาะกรณีคืนหัก ณ ที่จ่ายเท่านั้น")
            if rec.state != 'confirmed':
                raise UserError("สามารถกลับขาบัญชีได้เมื่อเอกสารอยู่ในสถานะ Confirmed เท่านั้น")
            if not rec.env.user.can_confirm_refund_payment:
                raise UserError(_("คุณไม่มีสิทธิ์ในการกลับขาบัญชี"))
            if not rec.move_id:
                raise UserError("ไม่พบรายการบัญชีต้นฉบับ กรุณายืนยันเอกสารก่อน")
            if rec.move_id.state != 'posted':
                raise UserError("รายการบัญชีต้นฉบับยังไม่ได้ post กรุณา post ก่อนทำการกลับขา")
            if rec.reversed_wtax_move_id:
                raise UserError("เอกสารนี้ได้ทำการกลับขาบัญชีไปแล้ว: %s" % rec.reversed_wtax_move_id.name)

            journal = rec._get_journal()
            debit_account = rec._refund_account('refund_suspense_account_id')
            credit_account = rec._refund_account('refund_bank_current_account_id')

            lines = []
            for line in rec.payment_lines:
                lines.append((0, 0, {
                    'account_id': debit_account.id,
                    'name': f'REVERSE WTAX: {line.payment_name}',
                    'debit': line.amount,
                    'credit': 0,
                    'partner_id': line.partner_id.id,
                }))
                lines.append((0, 0, {
                    'account_id': credit_account.id,
                    'name': f'REVERSE WTAX: {line.payment_name}',
                    'debit': 0,
                    'credit': line.amount,
                    'partner_id': line.partner_id.id,
                }))

            reverse_move = self.env['account.move'].create({
                'journal_id': journal.id,
                'date': fields.Date.today(),
                'ref': rec.name + '-REVERSE-WTAX',
                'line_ids': lines,
            })
            reverse_move.action_post()

            rec.reversed_wtax_move_id = reverse_move.id
            rec.message_post(body='กลับขาบัญชีหัก ณ ที่จ่ายสำเร็จ: %s' % reverse_move.name)

    @api.onchange('transfer_type', 'payment_lines')
    def _onchange_effective_date(self):
        self._set_date_from_payment_lines()

    def action_confirm(self):
        for rec in self:
            if (not rec.env.user.can_confirm_refund_payment) and (rec.transfer_type == 'rental_difference'):
                raise UserError(_("คุณไม่มีสิทธิ์ยืนยันเอกสารนี้ ต้องเป็นเจ้าหน้าที่การเงินส่วนกลางเท่านั้น"))

            if rec.state != 'draft':
                continue

            for line in rec.payment_lines:
                if not line.amount or line.amount == 0.0:
                    raise UserError(_("กรุณาระบุจำนวนเงิน ให้มากกว่า 0 ในรายการ: %s" % line.payment_name))

            if not rec.name or rec.name in ['New', '/']:
                rec.name = self.env['ir.sequence'].with_context(
                    ir_sequence_date=rec.date or fields.Date.context_today(self)
                ).next_by_code('overpaid_refund.payment') or '/'

            journal = rec._get_journal()

            # คู่บัญชีเหมือน o14 ทุกประเภท เปลี่ยนแค่ที่มาของบัญชีจากรหัสเป็นค่าที่ตั้งต่อบริษัท
            if rec.transfer_type == 'overpaid_refund':
                debit_account = rec._refund_account('refund_suspense_account_id')
                credit_account = rec._refund_account('refund_bank_savings_account_id')
            elif rec.transfer_type == 'wtax_refund':
                debit_account = rec._refund_account('refund_wht_account_id')
                credit_account = rec._refund_account('refund_suspense_account_id')
            elif rec.transfer_type == 'rental_difference':
                debit_account = rec._refund_account('refund_rental_income_account_id')
                credit_account = rec._refund_account('refund_bank_current_account_id')
            else:
                raise UserError("กรุณาเลือกประเภทการโอน")

            lines = []
            for line in rec.payment_lines:
                if rec.transfer_type == 'overpaid_refund':
                    lines.append((0, 0, {
                        'account_id': debit_account.id,
                        'name': f'Refund: {line.payment_name}',
                        'debit': 0, 'credit': line.amount,
                        'partner_id': line.partner_id.id,
                    }))
                    lines.append((0, 0, {
                        'account_id': credit_account.id,
                        'name': f'Refund: {line.payment_name}',
                        'debit': line.amount, 'credit': 0,
                        'partner_id': line.partner_id.id,
                    }))
                else:
                    lines.append((0, 0, {
                        'account_id': debit_account.id,
                        'name': f'Refund: {line.payment_name}',
                        'debit': line.amount, 'credit': 0,
                        'partner_id': line.partner_id.id,
                    }))
                    lines.append((0, 0, {
                        'account_id': credit_account.id,
                        'name': f'Refund: {line.payment_name}',
                        'debit': 0, 'credit': line.amount,
                        'partner_id': line.partner_id.id,
                    }))

            rec._set_date_from_payment_lines()

            move = self.env['account.move'].create({
                'journal_id': journal.id,
                'date': rec.date or fields.Date.context_today(self),
                'ref': rec.name,
                'line_ids': lines,
            })
            move.action_post()
            rec.move_id = move.id
            rec.state = 'confirmed'
            rec.message_post(body='บันทึกบัญชีสำเร็จ: %s' % move.name)

            if rec.transfer_type == 'wtax_refund':
                rec.show_state = True
                for p in rec.payment_ids:
                    if hasattr(p, 'wtax_refund_status'):
                        p.wtax_refund_status = 'wtax_refund'

            if rec.transfer_type == 'rental_difference':
                rec.show_state = True
                for p in rec.payment_ids:
                    if hasattr(p, 'rental_difference_status'):
                        p.rental_difference_status = 'rental_difference'


class RefundPaymentLine(models.Model):
    _name = 'refund.payment.line'
    _description = 'Refund Payment Detail Line'

    refund_payment_id = fields.Many2one('refund.payment', string='การคืนเงิน', ondelete='cascade')
    payment_name = fields.Char(string='รหัสการชำระเงิน')
    payment_id = fields.Many2one('account.payment', string='รายการชำระเงิน')
    partner_id = fields.Many2one('res.partner', string='ลูกค้า')
    amount = fields.Float(string='จำนวนเงิน', required=True)
    payment_date = fields.Date(string='วันที่ชำระเงิน')
