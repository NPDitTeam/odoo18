# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

class NpdLoan(models.Model):
    _name = 'npd.loan'
    _description = 'สินเชื่อ'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, name desc'

    name = fields.Char(string='เลขที่สินเชื่อ', required=True, copy=False,
                       readonly=True, default=lambda self: _('New'))

    def name_get(self):
        result = []
        for rec in self:
            display = rec.name or ''
            if rec.customer_name:
                display = '%s - %s' % (display, rec.customer_name)
            result.append((rec.id, display))
        return result

    # ข้อมูลลูกค้า
    customer_id = fields.Many2one('res.partner', string='รายชื่อลูกค้า', required=True, tracking=True)
    customer_name = fields.Char(string='ชื่อลูกค้า', related='customer_id.name', store=True)
    transfer_customer_name = fields.Char(string='ลูกค้ารับโอน', copy=False)
    # dummy field - view เก่าใน DB ยังอ้างถึง ลบได้เมื่อ clean DB แล้ว
    transfer_customer_id = fields.Char(string='(ไม่ใช้แล้ว)', store=False)
    phone = fields.Char(string='เบอร์โทร')
    mobile = fields.Char(string='มือถือ')
    address = fields.Text(string='ที่อยู่')
    id_card = fields.Char(string='เลขบัตรประชาชน')
    contract_status = fields.Selection([
        ('active', 'ส่งต่อเนื่อง'),
        ('overdue', 'ขาดส่ง'),
        ('lawsuit', 'ฟ้องศาล'),
        ('closed_partial', 'ปิดจ่ายต้นบางส่วน'),
        ('closed_none', 'ปิดไม่จ่ายต้นเลย'),
    ], string='สถานะสัญญา', default='active', tracking=True)
    
    # รูปภาพลูกหนี้
    customer_image = fields.Image(string='รูปลูกหนี้', max_width=256, max_height=256)

    # ข้อมูลสินเชื่อ
    loan_type_id = fields.Many2one('npd.loan.type', string='ประเภทสินเชื่อ', 
                                    required=True, tracking=True)
    loan_date = fields.Date(string='ว.ด.ป. ปล่อย', default=fields.Date.today, 
                            required=True, tracking=True)
    loan_amount = fields.Float(string='เงินต้น', required=True, tracking=True)

    # ยกยอดจากสินเชื่อเดิม
    rollover_from_id = fields.Many2one('npd.loan', string='ยกยอดจากสินเชื่อ',
                                        domain="[('state', 'in', ['draft', 'approved']), ('customer_id', '=', customer_id), ('id', '!=', id)]",
                                        tracking=True, copy=False)
    rollover_amount = fields.Float(string='ยอดยกมา', digits=(12, 2),
                                    compute='_compute_rollover_amount', store=True)
    additional_loan = fields.Float(string='เงินกู้เพิ่ม', digits=(12, 2), default=0, copy=False)

    # หักล่วงหน้า
    advance_deduction = fields.Float(string='หักล่วงหน้าสุทธิ', digits=(12, 2), default=0)
    advance_remaining = fields.Float(string='ยอดหักล่วงหน้าคงเหลือ', digits=(12, 2),
                                      compute='_compute_advance_remaining', store=True)
    additional_expense = fields.Float(string='ค่าใช้จ่ายเพิ่มเติม', digits=(12, 2), default=0)
    additional_expense_note = fields.Text(string='หมายเหตุค่าใช้จ่ายเพิ่มเติม')
    customer_received = fields.Float(string='ลูกค้าได้รับจริง', digits=(12, 2),
                                      compute='_compute_customer_received', store=True)

    interest_rate = fields.Float(string='ดอกเบี้ย (%/เดือน)', digits=(5, 2))
    late_fee_rate = fields.Float(string='อัตราค่าปรับล่าช้า (%)', digits=(5, 4), default=0.1)
    late_fee_type = fields.Selection([
        ('daily', 'คิดเป็นรายวัน'),
        ('per_period', 'คิดเป็นรอบ'),
    ], string='วิธีคิดค่าปรับ', default='per_period')
    loan_period = fields.Integer(string='จำนวนงวด (กำหนด)', tracking=True)
    due_date = fields.Date(string='วันครบกำหนด', compute='_compute_due_date', store=True)

    # งวดชำระ
    installment_ids = fields.One2many('npd.loan.installment', 'loan_id', string='งวดชำระ')
    installment_count = fields.Integer(string='จำนวนงวดที่ชำระ', compute='_compute_installment_count')
    
    # กำหนดยอดชำระขั้นต่ำ (เงินต้น × ดอกเบี้ย)
    minimum_payment_initial = fields.Float(string='กำหนดยอดชำระขั้นต่ำ', 
                                            compute='_compute_minimum_payment_initial', store=True)
    
    # เงินต้นคงเหลือปัจจุบัน
    current_remaining_principal = fields.Float(string='เงินต้นคงเหลือ', 
                                                compute='_compute_current_remaining', store=True)

    # สถานะการชำระ
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('approved', 'อนุมัติ'),
        ('completed', 'ปิดบัญชี'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='draft', tracking=True)
    
    # ตรวจสอบว่าชำระครบหรือยัง
    is_fully_paid = fields.Boolean(string='ชำระครบแล้ว', compute='_compute_payment_status', store=True)
    paid_installments = fields.Integer(string='งวดที่ชำระแล้ว', compute='_compute_payment_status', store=True)

    # ข้อมูลการเก็บเงิน
    total_interest = fields.Float(string='ดอกเบี้ยทั้งหมด', compute='_compute_loan_summary', store=True)
    total_principal_paid = fields.Float(string='รวมเงินต้นที่ชำระ', compute='_compute_collected_amount', store=True)
    total_interest_paid = fields.Float(string='รวมดอกเบี้ยที่ชำระ', compute='_compute_collected_amount', store=True)
    actual_collected = fields.Float(string='เก็บได้จริง (รวม)', compute='_compute_collected_amount', store=True)
    outstanding = fields.Float(string='ค้างจ่าย', compute='_compute_collected_amount', store=True)
    
    # วันเกินรวมและค่าปรับรวม
    total_overdue_days = fields.Integer(string='วันเกินรวม', compute='_compute_overdue_summary', store=True)
    total_late_fee = fields.Float(string='ค่าปรับรวม', digits=(12, 2), compute='_compute_overdue_summary', store=True)
    total_late_fee_paid = fields.Float(string='ค่าปรับที่เก็บได้', digits=(12, 2), compute='_compute_overdue_summary', store=True)
    
    # ค่าคอม Sale สรุป
    total_commission_sale = fields.Float(string='รวมค่าคอม Sale (หลัก)', digits=(12, 2),
                                          compute='_compute_commission_summary', store=True)
    total_commission_installment = fields.Float(string='รวมค่าคอม Sale (รายงวด)', digits=(12, 2),
                                                 compute='_compute_commission_summary', store=True)
    net_profit = fields.Float(string='กำไรสุทธิของบริษัท', digits=(12, 2),
                               compute='_compute_commission_summary', store=True)

    collected_ratio = fields.Char(string='แบ่ง 3:1:1')

    # ปัญหาและหมายเหตุ
    problem_note = fields.Text(string='ปัญหา/ทล.')
    note = fields.Text(string='หมายเหตุ')

    # เจ้าของทุน (เลือกได้หลายคน)
    fund_owner_ids = fields.Many2many('res.partner', string='เจ้าของทุน')
    
    # เทมเพลตค่าคอม Sale
    commission_template_id = fields.Many2one('npd.sale.commission.template',
                                              string='เทมเพลตค่าคอม Sale', copy=False)
    commission_line_ids = fields.One2many('npd.loan.commission.line', 'loan_id',
                                           string='รายชื่อ Sale คอมมิชชั่น')

    # การจ่ายค่าคอม Sale (persistent)
    commission_payout_ids = fields.One2many('npd.loan.commission.payout', 'loan_id',
                                             string='การจ่ายค่าคอม Sale')
    commission_all_paid = fields.Boolean(string='จ่ายค่าคอมครบแล้ว',
                                          compute='_compute_commission_all_paid', store=True)
    
    # การใช้งานทรัพย์สิน
    asset_status = fields.Selection([
        ('none', 'ไม่มีกำหนด'),
        ('repair_return', 'ซ่อมรถส่งคืน'),
        ('returning', 'อยู่ระหว่างส่งคืนรถ'),
        ('returned', 'ส่งคืนสำเร็จ'),
        ('company_use', 'บริษัทใช้งาน'),
        ('wait_branch', 'รอจอดสาขา'),
        ('wait_156', 'รอจอด สมอ.156'),
        ('wait_factory', 'รอจอดโรงงาน'),
        ('maintenance', 'รับรักษาใช้งาน'),
        ('not_due', 'ยังไม่ครบกำหนดขาย'),
        ('can_sell', 'ครบกำหนดขายได้'),
        ('sold', 'ไม่อนอม/ขายฝากแล้ว'),
    ], string='การใช้งานทรัพย์สิน', default='none', tracking=True)

    # ข้อมูลทรัพย์สิน/หลักประกัน
    collateral_type = fields.Char(string='ประเภทหลักประกัน')
    collateral_detail = fields.Text(string='รายละเอียดหลักประกัน')
    vehicle_brand = fields.Char(string='ยี่ห้อรถ')
    vehicle_model = fields.Char(string='รุ่น')
    vehicle_year = fields.Char(string='ปี')
    vehicle_color = fields.Char(string='สี')
    license_plate = fields.Char(string='ทะเบียนรถ')
    chassis_no = fields.Char(string='เลขตัวถัง')
    engine_no = fields.Char(string='เลขเครื่อง')
    
    # เอกสารแนบ
    document_ids = fields.One2many('npd.loan.document', 'loan_id', string='เอกสารแนบ')
    document_count = fields.Integer(string='จำนวนเอกสาร', compute='_compute_document_count')
    
    # (sale1_id, sale2_id ย้ายไป commission_line_ids แล้ว)

    # ประวัติการโทร
    call_history_ids = fields.One2many('npd.loan.call.history', 'loan_id', string='ประวัติการโทร')
    call_history_count = fields.Integer(string='จำนวนการโทร', compute='_compute_call_history_count')


    # ===== COMPUTE METHODS =====
    
    @api.depends('loan_date', 'loan_period')
    def _compute_due_date(self):
        for rec in self:
            if rec.loan_date and rec.loan_period:
                rec.due_date = rec.loan_date + relativedelta(months=rec.loan_period)
            else:
                rec.due_date = False


    @api.depends('rollover_from_id', 'rollover_from_id.current_remaining_principal')
    def _compute_rollover_amount(self):
        """ดึงยอดเงินต้นคงเหลือจากสินเชื่อเดิม"""
        for rec in self:
            if rec.rollover_from_id:
                rec.rollover_amount = rec.rollover_from_id.current_remaining_principal
            else:
                rec.rollover_amount = 0

    @api.depends('loan_amount', 'advance_deduction', 'additional_expense')
    def _compute_customer_received(self):
        """ลูกค้าได้รับจริง = เงินต้น - หักล่วงหน้า - ค่าใช้จ่ายเพิ่มเติม"""
        for rec in self:
            rec.customer_received = rec.loan_amount - rec.advance_deduction - rec.additional_expense

    @api.depends('advance_deduction', 'installment_ids.advance_used')
    def _compute_advance_remaining(self):
        """ยอดหักล่วงหน้าคงเหลือ = หักล่วงหน้า - ที่ใช้ไปทุกงวด"""
        for rec in self:
            used = sum(rec.installment_ids.mapped('advance_used'))
            rec.advance_remaining = rec.advance_deduction - used

    @api.depends('loan_amount', 'interest_rate')
    def _compute_minimum_payment_initial(self):
        """กำหนดยอดชำระขั้นต่ำ = เงินต้น × ดอกเบี้ย"""
        for rec in self:
            if rec.loan_amount and rec.interest_rate:
                rec.minimum_payment_initial = rec.loan_amount * (rec.interest_rate / 100)
            else:
                rec.minimum_payment_initial = 0

    @api.depends('installment_ids', 'installment_ids.remaining_principal', 'installment_ids.is_cancelled', 'loan_amount')
    def _compute_current_remaining(self):
        """เงินต้นคงเหลือปัจจุบัน = งวดสุดท้ายที่ชำระ (ไม่รวมงวดที่ยกเลิก) หรือ ยอดปล่อยถ้ายังไม่มีงวด"""
        for rec in self:
            active_installments = rec.installment_ids.filtered(lambda x: not x.is_cancelled)
            if active_installments:
                # หางวดล่าสุดที่ชำระแล้ว (ไม่รวมยกเลิก)
                paid_installments = active_installments.filtered(lambda x: x.state == 'paid')
                if paid_installments:
                    last_paid = paid_installments.sorted('installment_no', reverse=True)[0]
                    rec.current_remaining_principal = last_paid.remaining_principal
                else:
                    rec.current_remaining_principal = rec.loan_amount
            else:
                rec.current_remaining_principal = rec.loan_amount

    @api.depends('installment_ids', 'installment_ids.interest_amount', 'installment_ids.is_cancelled')
    def _compute_loan_summary(self):
        """คำนวณดอกเบี้ยทั้งหมดที่ชำระแล้ว (ไม่รวมงวดที่ยกเลิก)"""
        for rec in self:
            rec.total_interest = sum(rec.installment_ids.filtered(
                lambda x: x.state == 'paid' and not x.is_cancelled
            ).mapped('interest_amount'))


    @api.depends('installment_ids.actual_payment', 'installment_ids.principal_amount', 'installment_ids.interest_amount', 'installment_ids.is_cancelled', 'loan_amount', 'current_remaining_principal')
    def _compute_collected_amount(self):
        for rec in self:
            paid_installments = rec.installment_ids.filtered(lambda x: x.state == 'paid' and not x.is_cancelled)
            rec.actual_collected = sum(paid_installments.mapped('actual_payment'))
            rec.total_principal_paid = sum(paid_installments.mapped('principal_amount'))
            rec.total_interest_paid = sum(paid_installments.mapped('interest_amount'))
            rec.outstanding = rec.current_remaining_principal

    @api.depends('installment_ids.overdue_days', 'installment_ids.late_fee', 'installment_ids.late_fee_paid', 'installment_ids.is_cancelled')
    def _compute_overdue_summary(self):
        """คำนวณวันเกินรวมและค่าปรับรวมจากทุกงวด (ไม่รวมงวดที่ยกเลิก)"""
        for rec in self:
            active = rec.installment_ids.filtered(lambda x: not x.is_cancelled)
            rec.total_overdue_days = sum(active.mapped('overdue_days'))
            rec.total_late_fee = sum(active.mapped('late_fee'))
            rec.total_late_fee_paid = sum(active.mapped('late_fee_paid'))

    @api.depends('installment_ids', 'installment_ids.state', 'installment_ids.is_cancelled', 'current_remaining_principal')
    def _compute_payment_status(self):
        for rec in self:
            paid = len(rec.installment_ids.filtered(lambda x: x.state == 'paid' and not x.is_cancelled))
            rec.paid_installments = paid
            # ปิดบัญชีได้เมื่อเงินต้นคงเหลือ = 0
            rec.is_fully_paid = (rec.current_remaining_principal <= 0 and paid > 0)

    @api.depends('commission_line_ids.commission_amount',
                 'installment_ids.commission_ids.commission_amount',
                 'actual_collected', 'advance_deduction', 'total_principal_paid',
                 'total_late_fee_paid')
    def _compute_commission_summary(self):
        """สรุปค่าคอม Sale หลัก + รายงวด + กำไรสุทธิ

        สูตรกำไร:
        กำไร = (actual_collected - total_principal_paid) + advance_deduction + ค่าปรับที่เก็บได้ - ค่าคอม

        อธิบาย:
        - actual_collected - total_principal_paid = ดอกเบี้ยที่เก็บได้จาก actual_payment
          (หมายเหตุ: actual_collected ไม่รวมค่าปรับ เพราะค่าปรับถูกตัดจาก actual ก่อนตัดดอก/ต้น)
          → จริงๆ actual_collected รวมทุกอย่าง แต่ principal ก็ถูกหักค่าปรับไปแล้ว
          → ดังนั้น (actual - principal) = ดอก + ค่าปรับที่จ่ายจาก actual
        - advance_deduction = เงินหักล่วงหน้าจากลูกค้า (เป็นกำไรของบริษัท)
        - ค่าคอม = ค่าคอม Sale หลัก + ค่าคอม Sale รายงวด
        """
        for rec in self:
            # ค่าคอม Sale หลัก (จากแท็บค่าคอมมิชชั่น - ค่าคอมหาลูกค้า)
            rec.total_commission_sale = sum(rec.commission_line_ids.mapped('commission_amount'))
            # ค่าคอม Sale รายงวด (จากทุกงวดที่ชำระแล้ว)
            total_inst_comm = 0
            for inst in rec.installment_ids:
                total_inst_comm += sum(inst.commission_ids.mapped('commission_amount'))
            rec.total_commission_installment = total_inst_comm
            # กำไรสุทธิ = (เก็บจริง - เงินต้นที่ลูกค้าจ่ายคืน) + หักล่วงหน้า - ค่าคอม
            # actual_collected - principal = ส่วนที่ไม่ใช่เงินต้น (ดอก + ค่าปรับจาก actual)
            non_principal = rec.actual_collected - rec.total_principal_paid
            rec.net_profit = non_principal + rec.advance_deduction - rec.total_commission_sale - rec.total_commission_installment

    @api.depends('commission_payout_ids.status')
    def _compute_commission_all_paid(self):
        """ตรวจสอบว่าจ่ายค่าคอม Sale ครบทุกคนแล้วหรือยัง"""
        for rec in self:
            payouts = rec.commission_payout_ids
            if payouts:
                rec.commission_all_paid = all(po.status == 'paid' for po in payouts)
            else:
                rec.commission_all_paid = False

    @api.depends('installment_ids')
    def _compute_installment_count(self):
        for rec in self:
            rec.installment_count = len(rec.installment_ids)

    @api.depends('document_ids')
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    @api.depends('call_history_ids')
    def _compute_call_history_count(self):
        for rec in self:
            rec.call_history_count = len(rec.call_history_ids)


    # ===== ONCHANGE METHODS =====
    
    @api.onchange('customer_id')
    def _onchange_customer_id(self):
        if self.customer_id:
            partner = self.customer_id
            self.phone = partner.phone or ''
            self.mobile = partner.mobile or ''
            self.id_card = partner.id_card or ''
            address_parts = [
                partner.street or '',
                partner.street2 or '',
                partner.city or '',
                partner.state_id.name if partner.state_id else '',
                partner.zip or '',
                partner.country_id.name if partner.country_id else '',
            ]
            self.address = ', '.join(filter(None, address_parts))
            if partner.image_1920:
                self.customer_image = partner.image_1920

    @api.onchange('rollover_from_id')
    def _onchange_rollover_from(self):
        """เมื่อเลือกยกยอดจากสินเชื่อ → ดึงยอดคงเหลือมาเป็นเงินต้น + ดึงชื่อลูกค้ารับโอน"""
        if self.rollover_from_id:
            old_remaining = self.rollover_from_id.current_remaining_principal
            self.rollover_amount = old_remaining
            self.loan_amount = old_remaining + self.additional_loan
            self.transfer_customer_name = self.rollover_from_id.customer_name
        else:
            self.rollover_amount = 0
            self.additional_loan = 0
            self.loan_amount = 0
            self.transfer_customer_name = False

    @api.onchange('rollover_amount', 'additional_loan')
    def _onchange_loan_amount_rollover(self):
        """เมื่อแก้ไขเงินกู้เพิ่ม → อัพเดทเงินต้น"""
        if self.rollover_from_id:
            self.loan_amount = self.rollover_amount + self.additional_loan

    @api.onchange('commission_template_id')
    def _onchange_commission_template(self):
        """เมื่อเลือกเทมเพลตค่าคอม Sale → เติมรายชื่อ Sale อัตโนมัติ"""
        if self.commission_template_id:
            # สร้าง line ใหม่จาก template
            new_lines = self.env['npd.loan.commission.line']
            for tl in self.commission_template_id.sale_line_ids:
                new_lines += new_lines.new({
                    'sale_user_id': tl.sale_user_id.id,
                    'sequence': tl.sequence,
                    'commission_amount': 0,
                })
            self.commission_line_ids = new_lines
        else:
            self.commission_line_ids = self.env['npd.loan.commission.line']

    @api.onchange('loan_type_id')
    def _onchange_loan_type(self):
        """ดึงอัตราดอกเบี้ยและค่าปรับล่าช้าจากประเภทสินเชื่อ"""
        if self.loan_type_id:
            self.interest_rate = self.loan_type_id.interest_rate
            self.late_fee_rate = self.loan_type_id.late_fee_rate
            self.late_fee_type = self.loan_type_id.late_fee_type


    # ===== CRUD METHODS =====
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('npd.loan') or _('New')
        return super().create(vals_list)


    # ===== ACTION METHODS =====
    
    def action_add_installment(self):
        """เปิด popup เพิ่มงวดชำระใหม่"""
        self.ensure_one()
        
        if not self.loan_amount or self.loan_amount <= 0:
            raise ValidationError(_('กรุณาใส่ยอดเงินต้นก่อน'))
        
        if not self.interest_rate:
            raise ValidationError(_('กรุณาใส่อัตราดอกเบี้ยก่อน'))
        
        # ตรวจสอบว่าเงินต้นคงเหลือยังมีอยู่หรือไม่
        if self.current_remaining_principal <= 0:
            raise ValidationError(_('เงินต้นคงเหลือเป็น 0 แล้ว ไม่สามารถเพิ่มงวดได้'))
        
        return {
            'name': 'เพิ่มงวดชำระใหม่',
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan.add.installment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_loan_id': self.id},
        }

    def action_approve(self):
        """อนุมัติสินเชื่อ + ปิดบัญชีสินเชื่อเดิมถ้ายกยอดมา"""
        for rec in self:
            rec.write({'state': 'approved'})
            # ถ้ายกยอดมาจากสินเชื่อเดิม → ปิดบัญชีเดิมอัตโนมัติ
            if rec.rollover_from_id and rec.rollover_from_id.state != 'completed':
                rec.rollover_from_id.write({'state': 'completed'})

    def action_complete(self):
        """ปิดบัญชี (ต้องชำระครบก่อน)"""
        for rec in self:
            if not rec.is_fully_paid:
                raise ValidationError(_('ไม่สามารถปิดบัญชีได้ เนื่องจากยังมีเงินต้นคงเหลือ'))
            rec.write({'state': 'completed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})


    def action_recalculate_installments(self):
        """คำนวณงวดชำระใหม่ทั้งหมด - แก้ดอกค้างยกมา/ส่งต่อ (ข้ามงวดที่ยกเลิก)"""
        self.ensure_one()
        # ข้ามงวดที่ยกเลิก
        installments = self.installment_ids.filtered(
            lambda x: not x.is_cancelled
        ).sorted('installment_no')
        if not installments:
            return

        rate = (self.interest_rate / 100) if self.interest_rate else 0
        carry = 0  # ดอกค้างสะสม
        prev_remaining = self.loan_amount  # เงินต้นก่อนงวดแรก

        for inst in installments:
            # อัพเดท previous_remaining และ carried_interest
            vals = {
                'previous_remaining': prev_remaining,
                'carried_interest': carry,
            }
            # ใช้ skip_propagate เพื่อไม่ให้ write ส่งต่อซ้ำซ้อน (เราจัดการเองทีละงวด)
            inst.with_context(skip_propagate=True).write(vals)

            # อ่านค่าที่ compute คำนวณแล้ว
            carry = inst.carry_forward_interest or 0
            prev_remaining = inst.remaining_principal or prev_remaining
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'สำเร็จ',
                'message': 'คำนวณงวดชำระใหม่ %s งวด เรียบร้อย' % len(installments),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_update_installment_late_fee(self):
        """อัพเดทการตั้งค่าค่าปรับไปยังทุกงวดชำระ"""
        self.ensure_one()
        if self.installment_ids:
            self.installment_ids.write({
                'late_fee_rate': self.late_fee_rate,
                'late_fee_type': self.late_fee_type,
            })
            # คำนวณค่าปรับใหม่ (อยู่ใน _compute_breakdown แล้ว - write late_fee_rate/type จะ trigger recompute)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'สำเร็จ',
                'message': 'อัพเดทการตั้งค่าค่าปรับไปยัง %s งวด เรียบร้อย' % len(self.installment_ids),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_documents(self):
        return {
            'name': 'เอกสารแนบ',
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan.document',
            'view_mode': 'list,form',
            'domain': [('loan_id', '=', self.id)],
            'context': {'default_loan_id': self.id},
        }

    def action_view_installments(self):
        return {
            'name': 'งวดชำระ - %s' % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan.installment',
            'view_mode': 'list,form',
            'domain': [('loan_id', '=', self.id)],
            'context': {'default_loan_id': self.id},
        }

    def action_call(self):
        """เปิด popup โทรติดตาม"""
        self.ensure_one()
        return {
            'name': 'โทรติดตาม - %s' % self.customer_name,
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan.call.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_loan_id': self.id},
        }

    def action_view_call_history(self):
        """ดูประวัติการโทร"""
        self.ensure_one()
        return {
            'name': 'ประวัติการโทร - %s' % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan.call.history',
            'view_mode': 'list,form',
            'domain': [('loan_id', '=', self.id)],
            'context': {'default_loan_id': self.id},
        }

    def action_open_commission_payout(self):
        """เปิด popup จ่ายค่าคอม Sale"""
        self.ensure_one()
        if not self.commission_line_ids:
            raise ValidationError(_('กรุณาเลือกเทมเพลตค่าคอม Sale และระบุรายชื่อ Sale ก่อน'))
        return {
            'name': 'จ่ายค่าคอม Sale - %s' % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan.commission.payout.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_loan_id': self.id},
        }
