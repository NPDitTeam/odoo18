from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FleetChatterService(models.Model):
    _name = 'fleet.chatter.service'
    _description = 'Fleet Chatter Service'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def log_note_action(self):
        self.message_post(body="นี่คือบันทึกการติดตามสำหรับบริการ Fleet Chatter")

    @api.model
    def schedule_activity_action(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        self.activity_schedule(activity_type.id, 'ติดตามบริการ Fleet Chatter')


class CashPayment(models.Model):
    _name = 'cash.payment'
    _description = 'Cash Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference',
        required=True,
        default='New',
        tracking=True,
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed')],
        string='Status', default='draft', tracking=True)

    # บริษัทที่สร้างเอกสาร (ใช้กรองข้อมูล + กรองรายการ payment) เลือกได้ตอน Draft
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    # สาขา: ค่าเริ่มต้น = สาขาของผู้ใช้ แต่เลือกเปลี่ยนได้ตอน Draft
    branch_id = fields.Many2one(
        'res.branch',
        string="Branch",
        default=lambda self: self.env.user.branch_id.id if self.env.user.branch_id else False,
    )
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)

    payment_ids = fields.Many2many(
        'account.payment',
        string='Payments',
        domain="[('payment_method_one_id.name', '=', 'เงินสด'),"
               " ('payment_type', '=', 'inbound'),"
               " ('company_id', '=', company_id),"
               " ('branch_id', '=', branch_id),"
               " ('cash_status', '=', False)]"
    )

    payment_lines = fields.One2many(
        'cash.payment.line',
        'cash_payment_id',
        string='รายการชำระเงิน'
    )

    date_created = fields.Date(
        string='วันที่สร้างเอกสาร',
        default=fields.Date.today,
        tracking=True
    )

    total_amount = fields.Float(
        string='ยอดรวม',
        compute='_compute_total_amount',
        store=True,
        tracking=True
    )

    def copy(self, default=None):
        raise UserError(_("ไม่อนุญาตให้ทำรายการซ้ำ (Duplicate) สำหรับเอกสารนี้"))

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("ห้ามลบเอกสารเมื่อไม่ใช่ Draft"))
        return super().unlink()

    @api.depends('payment_lines.amount')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.payment_lines.mapped('amount'))

    def _next_document_number(self):
        """รันเลขเอกสารแยกตามสาขา (และบริษัท).

        ใช้ ir.sequence หนึ่งชุดต่อ (branch_id, company_id) โดย code = 'cash.payment'
        ถ้ายังไม่มีจะสร้างให้อัตโนมัติ พร้อม prefix ที่ระบุชื่อสาขา เพื่อให้แต่ละสาขา
        มีเลขรันของตัวเองเป็นอิสระจากกัน. ถ้าเอกสารไม่มีสาขา จะถอยไปใช้ sequence กลาง.
        """
        self.ensure_one()
        Sequence = self.env['ir.sequence'].sudo()
        company = self.company_id or self.env.company
        branch = self.branch_id
        if not branch:
            # ไม่มีสาขา -> ใช้ sequence กลาง (branch_id ว่าง) ที่ติดตั้งจาก data
            base_seq = Sequence.search([
                ('code', '=', 'cash.payment'),
                ('branch_id', '=', False),
            ], limit=1)
            if base_seq:
                return base_seq.next_by_id() or "CP/%s/0001" % fields.Date.today().year
            return Sequence.with_company(company).next_by_code('cash.payment') \
                or "CP/%s/0001" % fields.Date.today().year

        seq = Sequence.search([
            ('code', '=', 'cash.payment'),
            ('branch_id', '=', branch.id),
            ('company_id', 'in', (company.id, False)),
        ], limit=1)
        if not seq:
            seq = Sequence.create({
                'name': 'Cash Payment - %s' % (branch.name or ''),
                'code': 'cash.payment',
                'branch_id': branch.id,
                'company_id': company.id,
                'prefix': 'CP/' + (branch.name or '') + '/%(year)s/%(month)s/',
                'padding': 4,
                'number_next': 1,
                'number_increment': 1,
            })
        return seq.next_by_id() or "CP/%s/0001" % fields.Date.today().year

    def action_reset_to_draft(self):
        for rec in self:
            if rec.move_id:
                try:
                    if rec.move_id.state == 'posted':
                        rec.move_id.button_draft()
                except Exception as e:
                    raise UserError(_("ไม่สามารถเปลี่ยนสถานะเอกสารบัญชีให้เป็นร่างได้: %s" % str(e)))

            rec.state = 'draft'

            for p in rec.payment_ids:
                p.cash_status = ''
                if hasattr(p, 'cash_invoice_id'):
                    p.cash_invoice_id = False

            rec.message_post(body='ยกเลิกรายการและกลับเป็นฉบับร่างเรียบร้อยแล้ว')

    @api.onchange('company_id', 'branch_id')
    def _onchange_company_branch(self):
        """เปลี่ยนบริษัท/สาขา -> ล้างรายการ payment ที่เลือกไว้ เพราะ domain เปลี่ยน"""
        self.payment_ids = [(5, 0, 0)]
        self.payment_lines = [(5, 0, 0)]

    @api.onchange('payment_ids')
    def _onchange_payment_ids(self):
        self.payment_lines = [(5, 0, 0)]
        line_vals = []
        for p in self.payment_ids:
            line_vals.append((0, 0, {
                'payment_name': p.name,
                'payment_id': p.id,
                'partner_id': p.partner_id.id,
                'amount': p.amount,
                'payment_date': p.date,
            }))
        self.payment_lines = line_vals

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.payment_lines:
                raise UserError(_("กรุณาเลือกรายการชำระเงินอย่างน้อย 1 รายการ"))

            company = rec.company_id or self.env.company

            if rec.name in ['New', '/']:
                rec.name = rec._next_document_number()

            cash_account = self.env['account.account'].with_company(company).search(
                [('code', '=', '1111-00')], limit=1)
            ar_account = self.env['account.account'].with_company(company).search(
                [('code', '=', '1113-01')], limit=1)

            if not cash_account or not ar_account:
                raise UserError(_("กรุณาตั้งค่าบัญชี 1111-00 หรือ 1113-01 ของบริษัท %s ให้เรียบร้อยก่อน" % company.name))

            journal = self.env['account.journal'].search(
                [('type', '=', 'cash'), ('company_id', '=', company.id)], limit=1)
            if not journal:
                raise UserError(_("ไม่พบสมุดรายวันประเภทเงินสดของบริษัท %s กรุณาสร้างหรือเปิดใช้งาน" % company.name))

            lines = []
            total_amount = 0

            for line in rec.payment_lines:
                lines.append((0, 0, {
                    'account_id': cash_account.id,
                    'name': 'Cash Payment: ' + (line.payment_name or ''),
                    'credit': line.amount,
                    'debit': 0,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'branch_id': rec.branch_id.id if rec.branch_id else False,
                }))

                lines.append((0, 0, {
                    'account_id': ar_account.id,
                    'name': 'Receive: ' + (line.payment_name or ''),
                    'debit': line.amount,
                    'credit': 0,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'branch_id': rec.branch_id.id if rec.branch_id else False,
                }))

                total_amount += line.amount

            if not lines:
                raise UserError(_("ไม่สามารถสร้างรายการบัญชีได้ กรุณาตรวจสอบข้อมูล"))

            move_vals = {
                'journal_id': journal.id,
                'company_id': company.id,
                'date': fields.Date.today(),
                'ref': rec.name,
                'line_ids': lines,
            }
            if rec.branch_id:
                move_vals['branch_id'] = rec.branch_id.id

            move = self.env['account.move'].with_company(company).create(move_vals)
            move.action_post()
            rec.move_id = move.id

            for p in rec.payment_ids:
                if p.state == 'draft':
                    try:
                        p.action_post()
                    except Exception as e:
                        rec.message_post(body='Warning: ไม่สามารถ post payment %s: %s' % (p.name, str(e)))

                p.cash_status = 'returned'

                if hasattr(p, 'cash_invoice_id'):
                    if p.reconciled_invoice_ids:
                        p.cash_invoice_id = p.reconciled_invoice_ids[0].id
                    else:
                        rec.message_post(
                            body='Warning: Payment %s ไม่มี invoice ที่ reconcile' % p.name
                        )

            rec.state = 'confirmed'

            rec.message_post(
                body='ยืนยันการชำระเงินและสร้างรายการบัญชีสำเร็จ: %s (จำนวน %.2f บาท)' % (move.name, total_amount)
            )


class CashPaymentLine(models.Model):
    _name = 'cash.payment.line'
    _description = 'Cash Payment Detail Line'

    cash_payment_id = fields.Many2one('cash.payment', string='Cash Payment', ondelete='cascade')
    payment_name = fields.Char(string='Payment Name')
    payment_id = fields.Many2one('account.payment', string='Payment')
    partner_id = fields.Many2one('res.partner', string='Customer')
    amount = fields.Float(string='Amount')
    payment_date = fields.Date(string='Payment Date')
