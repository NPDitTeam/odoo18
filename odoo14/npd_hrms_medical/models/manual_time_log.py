# -*- coding: utf-8 -*-
"""ค่ารักษาพยาบาล — ส่วนขยายของคำขอเพิ่มเวลา (hr.manual.time.log)

พอร์ตจาก medical.expense ของ Odoo 14 แต่ไม่แยกโมเดล: แอปส่งค่ารักษาพยาบาลเข้ามา
เป็นคำขอเพิ่มเวลาประเภทหนึ่งอยู่แล้ว ประเภทที่ติ๊ก "เบิกค่ารักษาพยาบาล" ได้ของเพิ่ม:

1. บัญชีธนาคารที่ให้โอนเข้า + หมายเหตุอัตโนมัติ (แอปแก้หมายเหตุเองไม่ได้)
2. วงเงินต่อปี — ตรวจตอนยื่นจากแอป และตอนอนุมัติ
3. อนุมัติแล้วสร้างใบสำคัญจ่าย (account.voucher) ในบริษัทของพนักงานทันที
   ถอยกลับ / ยกเลิก → ยกเลิกใบสำคัญจ่าย วงเงินคืนเอง อนุมัติใหม่ได้ใบใหม่
4. อนุมัติผ่านแอปไม่ได้ (เหมือน PHP เดิม) — ต้องให้ฝ่ายบุคคลอนุมัติในระบบ

ไฟล์แนบหลายไฟล์ (attachment_ids) ใช้ได้กับทุกประเภท ไม่เฉพาะค่ารักษาพยาบาล
"""
import base64
import logging
from urllib.parse import quote

from odoo import api, Command, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.npd_hrms_base.models.employee_salary import BANK_SELECTION
from odoo.addons.npd_hrms_attendance.models.manual_time import (
    ALLOWED_ATTACHMENT_EXT, MAX_ATTACHMENT_BYTES)

from .thai_banks import THAI_BANKS, bank_short_name

_logger = logging.getLogger(__name__)

MAX_FILES = 10
BANK_CODES = {code for code, _label in BANK_SELECTION}

STATE_PENDING = 'รออนุมัติ'
STATE_APPROVED = 'อนุมัติ'
STATE_CANCELLED = 'ยกเลิก'

NOTE_TRIGGERS = {'amount', 'bank_name', 'bank_account_number', 'bank_account_name',
                 'reason_type_id'}


def _money(value):
    return '{:,.2f}'.format(value or 0.0)


def _url_name(name):
    """ชื่อไฟล์ท้าย URL — แอปดูนามสกุลจากตรงนี้ว่าจะเปิดเป็นรูปหรือ PDF"""
    return quote((name or 'file').replace('/', '_').replace('\\', '_'))


class HrManualTimeLog(models.Model):
    _inherit = 'hr.manual.time.log'

    is_medical = fields.Boolean(
        string='ค่ารักษาพยาบาล', related='reason_type_id.hrms_is_medical',
        store=True, index=True)
    expense_year = fields.Integer(
        string='ปีที่นับวงเงิน', compute='_compute_expense_year', store=True, index=True)

    # ---- บัญชีที่ให้โอนเงินเข้า (กรอกมาจากแอป) ----
    bank_name = fields.Selection(BANK_SELECTION, string='ธนาคารที่โอนเข้า', tracking=True)
    bank_account_number = fields.Char(string='เลขบัญชีธนาคาร', tracking=True)
    bank_account_name = fields.Char(string='ชื่อบัญชี')
    # user_note เป็น Char — ช่องบรรทัดเดียวบนฟอร์มจะกลืนบรรทัดที่สองของหมายเหตุ
    medical_note = fields.Text(
        string='หมายเหตุ (สร้างอัตโนมัติ)', compute='_compute_medical_note')

    attachment_ids = fields.Many2many(
        'ir.attachment', 'hr_manual_time_log_ir_attachment_rel',
        'log_id', 'attachment_id', string='ไฟล์แนบ', copy=False,
        help='ใบเสร็จ / ใบรับรองแพทย์ แนบได้หลายไฟล์ — แสดงในกล่องเอกสารด้านข้างด้วย')

    # ---- ใบสำคัญจ่ายที่สร้างตอนอนุมัติ ----
    voucher_id = fields.Many2one(
        'account.voucher', string='ใบสำคัญจ่าย', readonly=True, copy=False, index=True)
    voucher_number = fields.Char(string='เลขที่ใบสำคัญจ่าย', related='voucher_id.number')
    voucher_state = fields.Selection(string='สถานะใบสำคัญจ่าย', related='voucher_id.state')
    # ใช้ในเงื่อนไขซ่อน/แสดงปุ่มแทน voucher_id — ฝ่ายบุคคลไม่มีสิทธิ์อ่านใบสำคัญจ่าย
    has_medical_voucher = fields.Boolean(
        compute='_compute_has_medical_voucher', compute_sudo=True)

    # ---- วงเงินปีนี้ของพนักงาน (โชว์บนฟอร์ม) ----
    medical_limit = fields.Float(string='วงเงินต่อปี (บาท)', compute='_compute_medical_quota')
    medical_opening = fields.Float(
        string='เบิกก่อนใช้ระบบ (บาท)', compute='_compute_medical_quota')
    medical_approved = fields.Float(
        string='อนุมัติแล้วปีนี้ (บาท)', compute='_compute_medical_quota',
        help='รวมยอดที่เบิกก่อนใช้ระบบ (ยอดยกมา) แล้ว')
    medical_pending = fields.Float(
        string='รออนุมัติปีนี้ (บาท)', compute='_compute_medical_quota')
    medical_remaining = fields.Float(
        string='คงเหลือที่ขอได้ (บาท)', compute='_compute_medical_quota',
        help='วงเงินต่อปี − อนุมัติแล้ว (ยังไม่หักยอดที่รออนุมัติ)')

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('work_date')
    def _compute_expense_year(self):
        for rec in self:
            rec.expense_year = (rec.work_date or fields.Date.context_today(rec)).year

    @api.depends('user_note')
    def _compute_medical_note(self):
        for rec in self:
            rec.medical_note = rec.user_note or False

    @api.depends('voucher_id')
    def _compute_has_medical_voucher(self):
        for rec in self:
            rec.has_medical_voucher = bool(rec.voucher_id)

    @api.depends('employee_id', 'expense_year', 'is_medical', 'state', 'amount')
    def _compute_medical_quota(self):
        # แคชต่อรอบ — list 100 แถวของคนเดิมจะได้ไม่ยิง query ซ้ำ
        cache = {}
        for rec in self:
            if not (rec.is_medical and rec.employee_id):
                rec.medical_limit = rec.medical_opening = 0.0
                rec.medical_approved = rec.medical_pending = rec.medical_remaining = 0.0
                continue
            year = rec.expense_year or fields.Date.context_today(rec).year
            key = (rec.employee_id.id, year)
            if key not in cache:
                approved, pending = self._medical_usage(rec.employee_id, year)
                cache[key] = (
                    self._medical_limit_for(rec.employee_id, year),
                    self._medical_opening_for(rec.employee_id, year),
                    approved, pending)
            limit, opening, approved, pending = cache[key]
            rec.medical_limit = limit
            rec.medical_opening = opening
            rec.medical_approved = approved
            rec.medical_pending = pending
            rec.medical_remaining = limit - approved

    # ------------------------------------------------------------------
    # วงเงิน — ใช้ร่วมกันทั้งฟอร์ม ปุ่มอนุมัติ และ API ของแอป
    # ------------------------------------------------------------------
    @api.model
    def _medical_limit_for(self, employee, year):
        return self.env['hrms.medical.limit'].sudo().get_limit_for(employee, year)

    @api.model
    def _medical_opening_for(self, employee, year):
        return self.env['hrms.medical.opening'].sudo().get_used_before(employee, year)

    @api.model
    def _medical_usage(self, employee, year, exclude_ids=()):
        """(อนุมัติแล้ว + ยอดยกมา, รออนุมัติ) ของพนักงานในปีที่ระบุ

        รวมยอดยกมาเข้าฝั่ง "อนุมัติแล้ว" ไม่งั้นคนที่เบิกผ่านกระดาษไปแล้วครึ่งวงเงิน
        จะดูเหมือนยังมีวงเงินเต็ม
        """
        if not employee:
            return 0.0, 0.0
        domain = [
            ('employee_id', '=', employee.id),
            ('is_medical', '=', True),
            ('expense_year', '=', year),
            ('state', 'in', (STATE_APPROVED, STATE_PENDING)),
        ]
        if exclude_ids:
            domain.append(('id', 'not in', list(exclude_ids)))
        logs = self.sudo().search(domain)
        approved = sum(log.amount for log in logs if log.state == STATE_APPROVED)
        pending = sum(log.amount for log in logs if log.state == STATE_PENDING)
        return approved + self._medical_opening_for(employee, year), pending

    def _check_medical_quota_for_approval(self):
        self.ensure_one()
        year = self.expense_year or fields.Date.context_today(self).year
        limit = self._medical_limit_for(self.employee_id, year)
        approved, _pending = self._medical_usage(self.employee_id, year, exclude_ids=self.ids)
        remaining = limit - approved
        if self.amount > remaining + 0.001:
            raise UserError(
                'ไม่สามารถอนุมัติได้ — เกินวงเงินค่ารักษาพยาบาลประจำปี %s\n\n'
                '• วงเงินต่อปี: %s บาท\n'
                '• อนุมัติไปแล้วปีนี้ (รวมยอดยกมา): %s บาท\n'
                '• คงเหลือที่ขอได้: %s บาท\n'
                '• คำขอนี้: %s บาท'
                % (year, _money(limit), _money(approved), _money(remaining),
                   _money(self.amount)))

    # ------------------------------------------------------------------
    # หมายเหตุอัตโนมัติ — แอปโชว์ข้อความชุดนี้แบบแก้ไม่ได้ ฝั่ง Odoo จึงสร้างซ้ำให้ตรงกัน
    # ------------------------------------------------------------------
    def _build_medical_note(self):
        self.ensure_one()
        lines = ['ค่ารักษาพยาบาล %s บาท' % _money(self.amount)]
        second = [part for part in (
            bank_short_name(self.bank_name),
            self.bank_account_number and 'เลขบัญชี %s' % self.bank_account_number,
            self.bank_account_name,
        ) if part]
        if second:
            lines.append(' '.join(second))
        return '\n'.join(lines)

    def _refresh_medical_note(self):
        """เขียนหมายเหตุทับ เฉพาะใบค่ารักษาพยาบาลที่มีบัญชีครบ (ใบเก่าที่ไม่มีบัญชีไม่แตะ)"""
        for rec in self:
            if not (rec.is_medical and rec.bank_name and rec.bank_account_number):
                continue
            note = rec._build_medical_note()
            if rec.user_note != note:
                rec.with_context(hrms_skip_medical_note=True).sudo().write({'user_note': note})

    def _link_attachments_to_record(self):
        """ผูกไฟล์แนบเข้ากับคำขอ ให้ไปโผล่ในกล่องเอกสารของ chatter

        ไฟล์จากแอปถูกสร้างก่อนมีคำขอ (res_id ยังเป็น 0) ส่วนไฟล์ที่ฝ่ายบุคคลอัปโหลด
        ตอนสร้างคำขอใหม่บนหน้าเว็บก็ res_id เป็น 0 เหมือนกัน
        """
        for rec in self:
            stray = rec.sudo().attachment_ids.filtered(
                lambda a: a.res_model != rec._name or a.res_id != rec.id)
            if stray:
                stray.write({'res_model': rec._name, 'res_id': rec.id})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._link_attachments_to_record()
        records._refresh_medical_note()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'attachment_ids' in vals:
            self._link_attachments_to_record()
        if not self.env.context.get('hrms_skip_medical_note') and NOTE_TRIGGERS & set(vals):
            self._refresh_medical_note()
        return res

    # ------------------------------------------------------------------
    # Constraint — แทนของเดิม ให้นับไฟล์แนบหลายไฟล์ด้วย
    # ------------------------------------------------------------------
    @api.constrains('reason_type_id', 'amount', 'attachment', 'attachment_ids',
                    'allowance_type')
    def _check_reason_requirements(self):
        # ใบเก่าที่ยกมาจากฝั่ง 14 เป็นประวัติที่อนุมัติและจ่ายเงินไปแล้ว
        # ฝั่ง 14 ไม่ได้บังคับเลือกรายการค่าเบี้ยเลี้ยงหรือแนบเอกสาร
        # กฎนี้มีไว้กันใบใหม่ ไม่ได้มีไว้ตีประวัติกลับ
        # (กฎตัวเดียวกันอยู่ใน npd_hrms_attendance ด้วย ตัวนี้ทับของตัวนั้น
        #  เพราะต้องนับไฟล์แนบหลายไฟล์ ต้องเปิดทางให้เหมือนกันทั้งคู่)
        if self.env.context.get('npd_hrms_sync'):
            return
        for rec in self:
            if rec.state not in (STATE_PENDING, STATE_APPROVED):
                continue
            reason = rec.reason_type_id
            if reason.requires_amount and (not rec.amount or rec.amount <= 0):
                raise ValidationError('ประเภท "%s" ต้องกรอกจำนวนเงิน' % reason.name)
            if reason.requires_attachment and not (rec.attachment or rec.attachment_ids):
                raise ValidationError('ประเภท "%s" ต้องแนบเอกสารประกอบ' % reason.name)
            if reason.requires_allowance_type and not rec.allowance_type:
                raise ValidationError(
                    'ประเภท "%s" ต้องเลือกรายการค่าเบี้ยเลี้ยง' % reason.name)

    # ------------------------------------------------------------------
    # หน้าเว็บ — ฝ่ายบุคคลคีย์ให้เอง (เช่น ผู้บริหารที่ไม่ได้เบิกผ่านแอป)
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('hrms_medical_default'):
            if 'reason_type_id' in fields_list and not res.get('reason_type_id'):
                reason = self.env['hrms.manual.time.reason'].search([
                    ('company_id', '=', self.env.company.id),
                    ('hrms_is_medical', '=', True),
                ], limit=1)
                if reason:
                    res['reason_type_id'] = reason.id
            # ค่ารักษาพยาบาลไม่มีเวลาเข้า-ออก แต่ฟิลด์บังคับกรอก
            for name in ('checkin_time', 'checkout_time'):
                if name in fields_list:
                    res.setdefault(name, '00:00')
            if 'work_date' in fields_list:
                res.setdefault('work_date', fields.Date.context_today(self))
        return res

    @api.onchange('employee_id', 'reason_type_id')
    def _onchange_medical_bank(self):
        """เลือกพนักงานแล้วเติมบัญชีที่ผูกไว้ในทะเบียนพนักงานให้"""
        for rec in self:
            if rec.is_medical and rec.employee_id and not rec.bank_name:
                employee = rec.employee_id
                rec.bank_name = employee.bank_name or False
                rec.bank_account_number = employee.bank_account_number or False
                rec.bank_account_name = employee._hrms_name_with_prefix()

    # ------------------------------------------------------------------
    # ปุ่มดำเนินการ
    # ------------------------------------------------------------------
    def action_approve(self, approver=None):
        medical = self.filtered('is_medical')
        numbers = []
        for rec in medical:
            if rec.state != STATE_PENDING:
                raise UserError('อนุมัติได้เฉพาะรายการที่สถานะ "รออนุมัติ"')
            rec._check_medical_quota_for_approval()
            numbers.append(rec._create_medical_voucher().number or '')
        res = super().action_approve(approver=approver)
        if not medical:
            return res
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'อนุมัติและส่งเข้าการรับแล้ว',
                'message': 'ใบสำคัญจ่ายเลขที่ %s' % (', '.join(n for n in numbers if n) or '-'),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_reset_to_pending(self):
        for rec in self.filtered('voucher_id'):
            rec._cancel_medical_voucher()
        return super().action_reset_to_pending()

    def action_cancel(self):
        for rec in self.filtered(lambda r: r.voucher_id and r.state != STATE_CANCELLED):
            rec._cancel_medical_voucher()
        return super().action_cancel()

    def unlink(self):
        if self.filtered('voucher_id'):
            raise UserError('คำขอนี้มีใบสำคัญจ่ายผูกอยู่ — กด "ถอยกลับการอนุมัติ" '
                            'เพื่อยกเลิกใบสำคัญจ่ายก่อนลบ')
        return super().unlink()

    def action_open_medical_voucher(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.voucher',
            'res_id': self.voucher_id.id,
            'view_mode': 'form',
            'views': [(self.env.ref('account_voucher_npd.view_purchase_receipt_form').id,
                       'form')],
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # ใบสำคัญจ่าย
    # ------------------------------------------------------------------
    def _create_medical_voucher(self):
        """สร้างใบสำคัญจ่ายในบริษัทของพนักงานแล้ว post — ทำใน transaction เดียวกับการอนุมัติ"""
        self.ensure_one()
        employee = self.employee_id
        company = (self.company_id or employee.company_id).sudo()
        missing = [label for field, label in (
            ('hrms_medical_account_id', 'บัญชีค่ารักษาพยาบาล'),
            ('hrms_medical_payment_method_id', 'วิธีจ่ายเงิน'),
        ) if not company[field]]
        if missing:
            raise UserError(
                'บริษัท %s ยังไม่ได้ตั้ง %s ของใบสำคัญจ่ายค่ารักษาพยาบาล\n'
                'ตั้งได้ที่ ตั้งค่า > บริษัท > แท็บ "นโยบายระบบบุคคล" '
                '(หรือกดปุ่ม "ตั้งค่าอัตโนมัติ" ในแท็บนั้น)'
                % (company.name, ' และ '.join(missing)))

        partner = employee._hrms_get_payee_partner()
        today = fields.Date.context_today(self)
        Voucher = self.env['account.voucher'].sudo().with_company(company).with_context(
            voucher_type='purchase', default_check_show=False)
        journal = company.hrms_medical_journal_id or Voucher._default_journal()
        if not journal:
            raise UserError('ไม่พบสมุดรายวันใบสำคัญจ่ายของบริษัท %s' % company.name)

        line_vals = {
            'name': company.hrms_medical_line_label or 'ค่าสวัสดิการรักษาพยาบาล',
            'account_id': company.hrms_medical_account_id.id,
            'price_unit': self.amount,
            'quantity': 1.0,
        }
        if company.hrms_medical_product_id:
            line_vals['product_id'] = company.hrms_medical_product_id.id
        if company.hrms_medical_analytic_id:
            analytic = company.hrms_medical_analytic_id
            # ตั้งทั้งสองแบบ — รายการบัญชีใช้ analytic_distribution
            # แต่รายงานค่าคอมยังอ่าน account_analytic_id
            line_vals['account_analytic_id'] = analytic.id
            line_vals['analytic_distribution'] = {str(analytic.id): 100.0}
        if 'payment_date' in self.env['account.voucher.line']._fields:
            line_vals['payment_date'] = today

        vals = {
            'voucher_type': 'purchase',
            'date': today,
            'account_date': today,
            'journal_id': journal.id,
            'partner_id': partner.id,
            'reference': company.hrms_medical_reference or 'เบิกค่ารักษาพยาบาล',
            'narration': self.user_note or self._build_medical_note(),
            'pay_now': 'pay_now',
            'company_id': company.id,
            'payment_method_id': company.hrms_medical_payment_method_id.id,
            'cheque_type': 'outbound',
            # ไม่ใช่ใบคืนเงินประกันค่าเช่า — Check Type Show ต้องเป็น False
            'check_show': False,
            'hrms_medical_log_id': self.id,
            'line_ids': [Command.create(line_vals)],
        }
        # branch_id มาจาก npd_commission_fields — ไม่บังคับติดตั้ง
        if 'branch_id' in Voucher._fields:
            branch = employee.branch_id or company.hrms_medical_branch_id
            vals['branch_id'] = branch.id or False
        if company.hrms_medical_sequence_id:
            # get_seq_voucher() ใช้เลขที่ตั้งไว้แล้ว ไม่ไปดึงลำดับ PA ของใบคืนเงินประกัน
            vals['number'] = company.hrms_medical_sequence_id.next_by_id(sequence_date=today)

        voucher = Voucher.create(vals)
        voucher.proforma_voucher()
        self._copy_attachments_to_voucher(voucher)
        self.sudo().write({'voucher_id': voucher.id})
        # _message_log ไม่ต้องมีอีเมลผู้ส่ง (message_post ฟ้องถ้าผู้ใช้ HR ไม่ได้ตั้งอีเมล)
        self._message_log(body='ส่งเข้าการรับแล้ว: ใบสำคัญจ่าย %s ยอด %s บาท (%s)' % (
            voucher.number or '-', _money(self.amount), company.name))
        return voucher

    def _copy_attachments_to_voucher(self, voucher):
        """ใบเสร็จไปอยู่ในใบสำคัญจ่ายด้วย ฝ่ายบัญชีไม่ต้องกลับมาเปิดคำขอ"""
        self.ensure_one()
        Attachment = self.env['ir.attachment'].sudo()
        sources = self.sudo().attachment_ids | Attachment.search([
            ('res_model', '=', self._name), ('res_id', '=', self.id)])
        legacy = Attachment.search([
            ('res_model', '=', self._name), ('res_id', '=', self.id),
            ('res_field', '=', 'attachment')])
        for attachment in sources | legacy:
            if not attachment.datas:
                continue
            name = attachment.name
            if attachment in legacy:
                name = self.filename or attachment.name
            try:
                with self.env.cr.savepoint():
                    Attachment.create({
                        'name': name,
                        'datas': attachment.datas,
                        'res_model': 'account.voucher',
                        'res_id': voucher.id,
                        'company_id': voucher.company_id.id,
                    })
            except Exception as exc:
                # ไฟล์แนบพลาดไม่ควรทำให้การอนุมัติทั้งก้อนล้ม
                _logger.warning('แนบไฟล์ "%s" เข้าใบสำคัญจ่าย %s ไม่สำเร็จ: %s',
                                name, voucher.id, exc)

    def _cancel_medical_voucher(self):
        """ยกเลิกใบสำคัญจ่ายที่ผูกไว้ แล้วตัดการผูก — อนุมัติรอบใหม่จะได้ใบใหม่"""
        self.ensure_one()
        voucher = self.sudo().voucher_id
        if not voucher:
            return
        voucher = voucher.with_company(voucher.company_id)
        number = voucher.number or str(voucher.id)
        if voucher.state != 'cancel':
            try:
                with self.env.cr.savepoint():
                    voucher.cancel_voucher()
            except UserError as exc:
                # cancel_voucher ลบรายการบัญชีทิ้ง — Odoo 18 ไม่ยอมถ้าไม่ใช่เลขล่าสุดของเล่ม
                # (กันเลขเอกสารขาดช่วง) กรณีนั้นเก็บรายการไว้ในสถานะยกเลิกแทน
                _logger.info('ยกเลิกใบสำคัญจ่าย %s แบบเก็บรายการบัญชีไว้: %s', number, exc)
                move = voucher.move_id
                if move and move.state != 'cancel':
                    move.button_cancel()
                voucher.write({'state': 'cancel'})
        # _message_log ไม่ต้องมีอีเมลผู้ส่ง (message_post ฟ้องถ้าผู้ใช้ HR ไม่ได้ตั้งอีเมล)
        self._message_log(body='ยกเลิกใบสำคัญจ่าย %s แล้ว — คืนวงเงินให้พนักงาน' % number)
        self.sudo().write({'voucher_id': False})

    # ------------------------------------------------------------------
    # API สำหรับแอป
    # ------------------------------------------------------------------
    @api.model
    def _validate_uploads(self, files):
        if len(files) > MAX_FILES:
            raise UserError('แนบไฟล์ได้ไม่เกิน %d ไฟล์' % MAX_FILES)
        allowed = ', '.join(ext.upper() for ext in ALLOWED_ATTACHMENT_EXT)
        for content, name in files:
            ext = name.rsplit('.', 1)[-1].lower() if '.' in (name or '') else ''
            if ext not in ALLOWED_ATTACHMENT_EXT:
                raise UserError('ไฟล์ "%s": รองรับเฉพาะ %s' % (name, allowed))
            if len(base64.b64decode(content)) > MAX_ATTACHMENT_BYTES:
                raise UserError('ไฟล์ "%s" มีขนาดเกิน 5MB' % name)

    @api.model
    def _api_submit_extra_vals(self, vals, employee, reason, record, **extra):
        extra_vals = super()._api_submit_extra_vals(vals, employee, reason, record, **extra)
        editable = bool(record and record.exists() and record.employee_id == employee
                        and record.state == STATE_PENDING)
        files = [f for f in (extra.get('files') or []) if f and f[0]]
        if files:
            self._validate_uploads(files)
            if editable:
                # ส่งไฟล์ชุดใหม่มา = แทนชุดเดิมทั้งหมด (แอปส่งมาครบทุกไฟล์ที่ต้องการเก็บ)
                record.sudo().attachment_ids.unlink()
                if record.with_context(bin_size=True).attachment:
                    extra_vals.update({'attachment': False, 'filename': False})
            attachments = self.env['ir.attachment'].sudo().create([{
                'name': name,
                'datas': content,
                'company_id': employee.company_id.id,
            } for content, name in files])
            extra_vals['attachment_ids'] = [Command.set(attachments.ids)]
        if reason.hrms_is_medical:
            extra_vals.update(self._medical_submit_vals(
                vals, employee, record if editable else self.browse(), extra))
        return extra_vals

    @api.model
    def _medical_submit_vals(self, vals, employee, record, extra):
        """บัญชีธนาคาร + ตรวจวงเงินตอนยื่นจากแอป"""
        res = {}
        bank_name = (extra.get('bank_name') or '').strip().upper()
        account_number = (extra.get('bank_account_number') or '').strip()
        account_name = (extra.get('bank_account_name') or '').strip()
        if bank_name or account_number or account_name:
            if not (bank_name and account_number):
                raise UserError('กรุณาเลือกธนาคารและกรอกเลขบัญชีที่ต้องการให้โอนค่ารักษาพยาบาลเข้า')
            if bank_name not in BANK_CODES:
                raise UserError('ไม่รู้จักรหัสธนาคาร "%s"' % bank_name)
            res.update({
                'bank_name': bank_name,
                'bank_account_number': account_number,
                'bank_account_name': account_name or employee._hrms_name_with_prefix(),
            })
        elif not record.bank_name and employee.bank_name and employee.bank_account_number:
            # แอปรุ่นเก่าไม่ส่งบัญชีมา — ใช้บัญชีที่ผูกไว้ในทะเบียนพนักงาน
            res.update({
                'bank_name': employee.bank_name,
                'bank_account_number': employee.bank_account_number,
                'bank_account_name': employee._hrms_name_with_prefix(),
            })

        amount = vals.get('amount') or 0.0
        work_date = fields.Date.to_date(vals.get('work_date')) or fields.Date.context_today(self)
        year = work_date.year
        limit = self._medical_limit_for(employee, year)
        approved, pending = self._medical_usage(employee, year, exclude_ids=record.ids)
        remaining = limit - approved - pending
        if amount > remaining + 0.001:
            raise UserError(
                'ยอดเบิกเกินวงเงินค่ารักษาพยาบาลคงเหลือของปี %s\n'
                'วงเงินต่อปี %s บาท • ใช้ไปแล้ว %s บาท • รออนุมัติ %s บาท\n'
                'คงเหลือที่ขอได้ %s บาท'
                % (year, _money(limit), _money(approved), _money(pending),
                   _money(max(remaining, 0.0))))
        return res

    @api.model
    def api_get_medical_info(self, employee_id, year=None, exclude_id=None):
        """ข้อมูลที่แอปใช้ตอนกรอกคำขอค่ารักษาพยาบาล — รูปแบบเดียวกับ Odoo 14

        remaining = วงเงินต่อปี − อนุมัติแล้ว − รออนุมัติ (กันยื่นซ้ำจนเกินวงเงิน)
        exclude_id: คำขอที่กำลังแก้ไข — ไม่เอายอดของตัวเองมาหักซ้ำ
        """
        banks = [dict(bank) for bank in THAI_BANKS]
        target_year = int(year) if year else fields.Date.context_today(self).year
        employee = self.env['employee.salary'].sudo().browse(int(employee_id))
        if not employee.exists():
            return {'ok': False, 'message': 'ไม่พบข้อมูลพนักงาน', 'year': target_year,
                    'banks': banks, 'max_files': MAX_FILES}
        exclude = []
        if exclude_id:
            own = self.sudo().browse(int(exclude_id))
            if own.exists() and own.employee_id == employee:
                exclude = own.ids
        limit = self._medical_limit_for(employee, target_year)
        approved, pending = self._medical_usage(employee, target_year, exclude_ids=exclude)
        return {
            'ok': True,
            'year': target_year,
            'employee_name': employee._hrms_name_with_prefix(),
            'limit': float(limit),
            'used_approved': float(approved),
            'used_pending': float(pending),
            'remaining': float(max(limit - approved - pending, 0.0)),
            'bank_name': employee.bank_name or '',
            'bank_account_number': employee.bank_account_number or '',
            'banks': banks,
            'max_files': MAX_FILES,
        }

    @api.model
    def api_get_approval_queue(self, approver_id):
        """ค่ารักษาพยาบาลไม่เข้าคิวอนุมัติของหัวหน้าในแอป (เหมือน PHP เดิม)"""
        result = super().api_get_approval_queue(approver_id)
        keys = ('pending_requests', 'history_requests')
        ids = [row['id'] for key in keys for row in result.get(key, [])]
        if ids:
            medical = set(self.sudo().browse(ids).filtered('is_medical').ids)
            if medical:
                for key in keys:
                    result[key] = [row for row in result.get(key, [])
                                   if row['id'] not in medical]
        return result

    @api.model
    def api_approve_action(self, approver_id, request_id, action, reason=None,
                           new_state=None):
        record = self.sudo().browse(int(request_id or 0))
        if record.exists() and record.is_medical:
            raise UserError(
                'คำขอประเภท "%s" ไม่สามารถอนุมัติผ่านแอปได้ '
                '— ฝ่ายบุคคลอนุมัติในระบบเพื่อส่งเข้าการรับ' % record.reason_type_id.name)
        return super().api_approve_action(
            approver_id, request_id, action, reason=reason, new_state=new_state)

    @api.model
    def api_cancel(self, request_id, employee_id=None):
        record = self.sudo().browse(int(request_id or 0))
        if record.exists() and record.voucher_id:
            raise UserError('คำขอนี้อนุมัติและส่งเข้าบัญชีแล้ว ยกเลิกเองไม่ได้ '
                            'กรุณาติดต่อฝ่ายบุคคล')
        return super().api_cancel(request_id, employee_id=employee_id)

    def _attachment_urls(self, base_url=''):
        """URL ไฟล์แนบทุกไฟล์ — ลงท้ายด้วยชื่อไฟล์ แอปจะรู้นามสกุล"""
        self.ensure_one()
        root = '%s/api/hrms/v1/manual_time/attachment/%s' % (
            (base_url or '').rstrip('/'), self.id)
        urls = []
        if self.with_context(bin_size=True).attachment:
            # ไฟล์เดี่ยวแบบเดิม (แอปรุ่นก่อน) — id 0
            urls.append('%s/0/%s' % (root, _url_name(self.filename or 'attachment')))
        for attachment in self.sudo().attachment_ids.sorted('id'):
            urls.append('%s/%s/%s' % (root, attachment.id, _url_name(attachment.name)))
        return urls

    def _as_dict(self, base_url=''):
        data = super()._as_dict(base_url)
        urls = self._attachment_urls(base_url)
        data.update({
            'file_path': urls[0] if urls else '',
            'file_paths': urls,
            'is_medical': bool(self.is_medical),
            'bank_name': self.bank_name or '',
            'bank_account_number': self.bank_account_number or '',
            'bank_account_name': self.bank_account_name or '',
            'voucher_number': self.voucher_number or '',
        })
        return data
