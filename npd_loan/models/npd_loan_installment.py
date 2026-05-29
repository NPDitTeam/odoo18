# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class NpdLoanInstallment(models.Model):
    _name = 'npd.loan.installment'
    _description = 'งวดชำระสินเชื่อ'
    _order = 'installment_no'
    _rec_name = 'display_name'

    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True, ondelete='cascade')
    installment_no = fields.Integer(string='งวดที่', default=0)
    due_date = fields.Date(string='วันครบกำหนด')
    display_name = fields.Char(string='ชื่อ', compute='_compute_display_name', store=True)
    
    # จ่ายจริง
    actual_payment = fields.Float(string='จ่ายจริง', digits=(12, 2), default=0)
    
    # เงินต้นก่อนงวดนี้
    previous_remaining = fields.Float(string='เงินต้นก่อนงวดนี้', digits=(12, 2))
    
    # ดอกเบี้ยค้างยกมาจากงวดก่อน (ทบดอก)
    carried_interest = fields.Float(string='ดอกค้างยกมา', digits=(12, 2), default=0)
    
    # ยอดที่คำนวณได้ - ใช้ compute
    principal_amount = fields.Float(string='ยอดชำระเงินต้น', digits=(12, 2),
                                     compute='_compute_breakdown', store=True)
    interest_amount = fields.Float(string='ยอดชำระดอก', digits=(12, 2),
                                    compute='_compute_breakdown', store=True)
    remaining_principal = fields.Float(string='คงเหลือ', digits=(12, 2),
                                        compute='_compute_breakdown', store=True)
    minimum_payment = fields.Float(string='กำหนดยอดชำระขั้นต่ำ', digits=(12, 2),
                                    compute='_compute_breakdown', store=True)
    # ดอกค้างส่งต่องวดถัดไป
    carry_forward_interest = fields.Float(string='ดอกค้างส่งต่อ', digits=(12, 2),
                                           compute='_compute_breakdown', store=True)

    # ค่าปรับล่าช้า
    late_fee_rate = fields.Float(string='อัตราค่าปรับล่าช้า (%)', digits=(5, 4), default=0.1)
    late_fee_type = fields.Selection([
        ('daily', 'คิดเป็นรายวัน'),
        ('per_period', 'คิดเป็นรอบ'),
    ], string='วิธีคิดค่าปรับ', default='per_period')

    overdue_days = fields.Integer(string='วันเกิน', compute='_compute_breakdown', store=True)
    late_fee = fields.Float(string='ค่าปรับ', digits=(12, 2), compute='_compute_breakdown', store=True)
    late_fee_paid = fields.Float(string='ค่าปรับที่จ่าย', digits=(12, 2), compute='_compute_breakdown', store=True)
    
    paid_date = fields.Date(string='วันที่ชำระ')
    
    state = fields.Selection([
        ('pending', 'รอชำระ'),
        ('paid', 'ชำระแล้ว'),
        ('overdue', 'เกินกำหนด'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='pending', compute='_compute_state', store=True)

    payment_proof_ids = fields.One2many('npd.loan.payment.proof', 'installment_id', string='หลักฐานการโอน')
    payment_proof_count = fields.Integer(string='จำนวนหลักฐาน', compute='_compute_proof_count')
    # ใช้หักล่วงหน้า
    advance_used = fields.Float(string='ใช้หักล่วงหน้า', digits=(12, 2), default=0)
    # ปิดหนี้ (ไม่คิดดอก ตัดเงินต้นทั้งหมด)
    close_debt = fields.Boolean(string='ยินยอมปิดหนี้', default=False)
    # ตัวเลือกการคำนวณ
    skip_interest = fields.Boolean(string='ไม่คิดดอกเบี้ย', default=False)
    skip_late_fee = fields.Boolean(string='ไม่คิดค่าปรับ', default=False)

    commission_ids = fields.One2many('npd.loan.installment.commission', 'installment_id',
                                      string='ค่าคอม Sale งวดนี้')
    total_commission = fields.Float(string='ค่าคอม Sale รวม', digits=(12, 2),
                                     compute='_compute_total_commission', store=True)
    note = fields.Text(string='หมายเหตุ')
    is_cancelled = fields.Boolean(string='ยกเลิกแล้ว', default=False)

    # ===== DEFAULT =====
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        loan_id = self._context.get('default_loan_id')
        if loan_id:
            loan = self.env['npd.loan'].browse(loan_id)
            if loan.exists():
                # หาเลขงวดถัดไป
                existing = self.search([('loan_id', '=', loan_id)], order='installment_no desc', limit=1)
                next_no = (existing.installment_no if existing else 0) + 1
                res['installment_no'] = next_no
                
                # หา previous_remaining และ carried_interest
                if next_no == 1:
                    res['previous_remaining'] = loan.loan_amount
                    res['carried_interest'] = 0
                else:
                    prev = self.search([('loan_id', '=', loan_id), ('installment_no', '=', next_no - 1)], limit=1)
                    res['previous_remaining'] = prev.remaining_principal if prev else loan.loan_amount
                    res['carried_interest'] = prev.carry_forward_interest if prev else 0
                
                # ค่าปรับ
                res['late_fee_rate'] = loan.late_fee_rate
                res['late_fee_type'] = loan.late_fee_type
        return res

    # ===== COMPUTE =====

    @api.depends('commission_ids.commission_amount')
    def _compute_total_commission(self):
        """รวมค่าคอม Sale ทั้งหมดในงวดนี้"""
        for rec in self:
            rec.total_commission = sum(rec.commission_ids.mapped('commission_amount'))

    @api.depends('actual_payment', 'previous_remaining', 'carried_interest',
                 'loan_id.interest_rate', 'advance_used', 'close_debt',
                 'due_date', 'paid_date', 'late_fee_rate', 'late_fee_type',
                 'skip_interest', 'skip_late_fee')
    def _compute_breakdown(self):
        """คำนวณทันทีเมื่อ actual_payment เปลี่ยน"""
        for rec in self:
            rec._calculate_breakdown()

    def _calculate_breakdown(self):
        """Logic คำนวณแยกออกมาเพื่อใช้ร่วมกับ onchange

        หลักการ:
        - close_debt = ยินยอมปิดหนี้ → ไม่คิดดอก/ค่าปรับ ตัดเงินต้นทั้งหมด
        - skip_interest = ไม่คิดดอก → ตัดเงินต้นอย่างเดียว
        - skip_late_fee = ไม่คิดค่าปรับ → ข้ามค่าปรับ
        - advance_used = เครดิตล่วงหน้า ใช้จ่ายค่าปรับ + ดอก เท่านั้น ไม่ตัดเงินต้น
        - actual_payment = เงินสดจริง ใช้จ่ายค่าปรับ/ดอก ส่วนที่เหลือ + ตัดเงินต้น

        ลำดับการตัด:
        1. คำนวณค่าปรับจากวันเกิน (ถ้าไม่ skip)
        2. advance_used จ่ายค่าปรับก่อน → จ่ายดอก (ไม่ตัดเงินต้น)
        3. actual_payment จ่ายค่าปรับที่เหลือ → จ่ายดอกที่เหลือ → ตัดเงินต้น
        """
        prev = self.previous_remaining or 0
        rate = (self.loan_id.interest_rate / 100) if self.loan_id else 0
        carried = self.carried_interest or 0
        advance = self.advance_used or 0
        actual = self.actual_payment or 0

        # --- คำนวณค่าปรับจากวันเกิน ---
        today = fields.Date.today()
        o_days = 0
        fee = 0.0
        if not self.skip_late_fee and self.due_date:
            compare_date = self.paid_date or today
            if compare_date > self.due_date:
                o_days = (compare_date - self.due_date).days
                # ฐานค่าปรับ = ดอกเบี้ยงวดนี้ (คิดจากเงินต้นก่อนงวดนี้)
                base_interest = round(prev * rate, 2)
                if self.late_fee_type == 'per_period':
                    fee = round(base_interest * (self.late_fee_rate / 100), 2)
                else:  # daily
                    fee = round(base_interest * (self.late_fee_rate / 100) * o_days, 2)
        self.overdue_days = o_days
        self.late_fee = fee

        # --- ดอกเบี้ย ---
        if self.skip_interest:
            total_interest_due = 0
        else:
            # ดอกเบี้ยปกติงวดนี้ (คิดจากเงินต้นคงเหลือ)
            current_interest = round(prev * rate, 2)
            # ดอกเบี้ยรวมที่ต้องจ่าย (ปกติ + ค้างยกมา)
            total_interest_due = round(current_interest + carried, 2)

        # ขั้นต่ำ = ค่าปรับ + ดอกเบี้ยรวม
        self.minimum_payment = round(fee + total_interest_due, 2)

        # ถ้าปิดหนี้ → ไม่คิดดอก/ค่าปรับ ตัดเงินต้นทั้งหมด
        if self.close_debt and actual >= prev and prev > 0:
            self.interest_amount = 0
            self.principal_amount = prev
            self.remaining_principal = 0
            self.carry_forward_interest = 0
            self.late_fee_paid = 0
            return

        if advance > 0 or actual > 0:
            # === ค่าปรับ ===
            # 1a) advance จ่ายค่าปรับก่อน
            advance_for_fee = min(advance, fee)
            fee_remaining = round(fee - advance_for_fee, 2)
            advance_left_after_fee = round(advance - advance_for_fee, 2)

            # 1b) actual จ่ายค่าปรับที่เหลือ
            actual_for_fee = min(actual, fee_remaining)
            fee_still_remaining = round(fee_remaining - actual_for_fee, 2)
            actual_left_after_fee = round(actual - actual_for_fee, 2)

            # ค่าปรับที่จ่ายจริง
            self.late_fee_paid = round(advance_for_fee + actual_for_fee, 2)

            # === ดอกเบี้ย ===
            # 2a) advance (ส่วนเหลือจากค่าปรับ) จ่ายดอก
            advance_for_interest = min(advance_left_after_fee, total_interest_due)
            interest_remaining = round(total_interest_due - advance_for_interest, 2)

            # 2b) actual (ส่วนเหลือจากค่าปรับ) จ่ายดอกที่เหลือ
            actual_for_interest = min(actual_left_after_fee, interest_remaining)
            interest_still_remaining = round(interest_remaining - actual_for_interest, 2)

            # ยอดชำระดอก = advance จ่ายดอก + actual จ่ายดอก
            self.interest_amount = round(advance_for_interest + actual_for_interest, 2)

            # ดอกค้างส่งต่อ (ถ้าจ่ายดอกไม่ครบ)
            self.carry_forward_interest = interest_still_remaining

            # === เงินต้น ===
            # 3) actual ส่วนที่เหลือหลังจ่ายค่าปรับ+ดอก → ตัดเงินต้น
            actual_left = round(actual_left_after_fee - actual_for_interest, 2)
            self.principal_amount = actual_left

            # คงเหลือ
            self.remaining_principal = round(prev - self.principal_amount, 2)
            if self.remaining_principal < 0:
                self.remaining_principal = 0
        else:
            self.interest_amount = 0
            self.principal_amount = 0
            self.remaining_principal = prev
            self.carry_forward_interest = total_interest_due
            self.late_fee_paid = 0

    @api.onchange('actual_payment')
    def _onchange_actual_payment(self):
        """Trigger คำนวณทันทีเมื่อแก้ไข actual_payment ใน UI"""
        self._calculate_breakdown()

    @api.depends('installment_no', 'actual_payment', 'minimum_payment', 'state')
    def _compute_display_name(self):
        for rec in self:
            amount = rec.actual_payment or rec.minimum_payment or 0
            status = ''
            if rec.state == 'paid':
                status = ' ✓'
            elif rec.state == 'overdue':
                status = ' ⚠'
            rec.display_name = 'งวด %s - %.0f บาท%s' % (rec.installment_no, amount, status)


    @api.depends('payment_proof_ids')
    def _compute_proof_count(self):
        for rec in self:
            rec.payment_proof_count = len(rec.payment_proof_ids)

    @api.depends('actual_payment', 'advance_used', 'due_date', 'paid_date', 'is_cancelled')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if rec.is_cancelled:
                rec.state = 'cancelled'
                continue
            total = (rec.actual_payment or 0) + (rec.advance_used or 0)
            if total > 0 and rec.paid_date:
                rec.state = 'paid'
            elif rec.due_date and rec.due_date < today and total <= 0:
                rec.state = 'overdue'
            else:
                rec.state = 'pending'


    # ===== CRUD =====
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            loan_id = vals.get('loan_id')
            if loan_id:
                loan = self.env['npd.loan'].browse(loan_id)
                
                # กำหนดเลขงวดอัตโนมัติ
                if not vals.get('installment_no'):
                    existing = self.search([('loan_id', '=', loan_id)], order='installment_no desc', limit=1)
                    vals['installment_no'] = (existing.installment_no if existing else 0) + 1
                
                # กำหนด previous_remaining และ carried_interest
                inst_no = vals.get('installment_no', 1)
                if not vals.get('previous_remaining'):
                    if inst_no == 1:
                        vals['previous_remaining'] = loan.loan_amount
                    else:
                        prev = self.search([
                            ('loan_id', '=', loan_id),
                            ('installment_no', '=', inst_no - 1)
                        ], limit=1)
                        vals['previous_remaining'] = prev.remaining_principal if prev else loan.loan_amount
                
                # ดึงดอกค้างจากงวดก่อน
                if 'carried_interest' not in vals and inst_no > 1:
                    prev_inst = self.search([
                        ('loan_id', '=', loan_id),
                        ('installment_no', '=', inst_no - 1)
                    ], limit=1)
                    if prev_inst:
                        vals['carried_interest'] = prev_inst.carry_forward_interest or 0
                
                # ค่าปรับ
                if not vals.get('late_fee_rate'):
                    vals['late_fee_rate'] = loan.late_fee_rate
                if not vals.get('late_fee_type'):
                    vals['late_fee_type'] = loan.late_fee_type
                    
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)

        # ถ้าเปลี่ยน actual_payment ให้อัพเดทงวดถัดไป (เงินต้นคงเหลือ + ดอกค้างส่งต่อ)
        # ข้ามถ้าอยู่ระหว่าง recalculate (เพื่อไม่ให้ซ้ำซ้อน)
        if not self._context.get('skip_propagate') and ('actual_payment' in vals or 'carried_interest' in vals):
            for rec in self:
                # หางวดถัดไปที่ไม่ถูกยกเลิก
                next_inst = self.search([
                    ('loan_id', '=', rec.loan_id.id),
                    ('installment_no', '>', rec.installment_no),
                    ('is_cancelled', '=', False),
                ], order='installment_no', limit=1)
                if next_inst:
                    update_vals = {'previous_remaining': rec.remaining_principal}
                    # ส่งดอกค้างไปงวดถัดไป
                    update_vals['carried_interest'] = rec.carry_forward_interest
                    next_inst.write(update_vals)

        return res


    # ===== ACTIONS =====

    def action_view_payment_proofs(self):
        self.ensure_one()
        return {
            'name': 'หลักฐานการโอน - งวดที่ %s' % self.installment_no,
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan.payment.proof',
            'view_mode': 'list,form',
            'domain': [('installment_id', '=', self.id)],
            'context': {'default_installment_id': self.id, 'default_loan_id': self.loan_id.id},
        }

    def action_confirm_payment(self):
        self.ensure_one()
        total = (self.actual_payment or 0) + (self.advance_used or 0)
        if total <= 0:
            raise ValidationError(_('กรุณาใส่ยอดจ่ายจริง หรือใช้หักล่วงหน้า'))
        if not self.paid_date:
            self.paid_date = fields.Date.today()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'สำเร็จ', 'message': 'บันทึกงวดที่ %s แล้ว' % self.installment_no, 'type': 'success'}}

    def action_cancel_installment(self):
        """ยกเลิกงวดชำระ - คืนยอดชำระดอก (advance_used) กลับไปที่หักล่วงหน้าคงเหลือ"""
        self.ensure_one()

        # เงื่อนไข: จ่ายจริง = 0 และ ยอดชำระเงินต้น = 0
        if (self.actual_payment or 0) != 0:
            raise ValidationError(_('ไม่สามารถยกเลิกได้ เนื่องจากฟิลด์จ่ายจริงไม่เป็น 0'))
        if (self.principal_amount or 0) != 0:
            raise ValidationError(_('ไม่สามารถยกเลิกได้ เนื่องจากยอดชำระเงินต้นไม่เป็น 0'))
        if self.is_cancelled:
            raise ValidationError(_('งวดนี้ถูกยกเลิกไปแล้ว'))

        # เก็บค่า advance_used ก่อนยกเลิก (เพื่อแสดงข้อความ)
        advance_to_return = self.advance_used or 0

        # ตั้ง is_cancelled = True, เคลียร์ advance_used, paid_date
        # การ set advance_used = 0 จะทำให้ advance_remaining (computed field)
        # เพิ่มขึ้นอัตโนมัติ (advance_remaining = advance_deduction - sum(advance_used))
        self.with_context(skip_propagate=True).write({
            'is_cancelled': True,
            'advance_used': 0,
            'paid_date': False,
        })

        # คำนวณงวดถัดไปใหม่ - ข้ามงวดที่ยกเลิก ใช้ข้อมูลจากงวดก่อนหน้า
        self._recalculate_after_cancel()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'ยกเลิกสำเร็จ',
                'message': 'ยกเลิกงวดที่ %s แล้ว คืนหักล่วงหน้า %.2f กลับ' % (
                    self.installment_no, advance_to_return),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def _recalculate_after_cancel(self):
        """คำนวณงวดถัดไปใหม่หลังยกเลิกงวดนี้ - ข้ามงวดที่ยกเลิก"""
        loan = self.loan_id
        all_installments = loan.installment_ids.filtered(
            lambda x: not x.is_cancelled
        ).sorted('installment_no')

        if not all_installments:
            return

        rate = (loan.interest_rate / 100) if loan.interest_rate else 0
        carry = 0
        prev_remaining = loan.loan_amount

        for inst in all_installments:
            vals = {
                'previous_remaining': prev_remaining,
                'carried_interest': carry,
            }
            inst.with_context(skip_propagate=True).write(vals)
            carry = inst.carry_forward_interest or 0
            prev_remaining = inst.remaining_principal or prev_remaining


class NpdLoanPaymentProof(models.Model):
    _name = 'npd.loan.payment.proof'
    _description = 'หลักฐานการโอนเงิน'
    _order = 'payment_date desc, id desc'

    installment_id = fields.Many2one('npd.loan.installment', string='งวดชำระ', required=True, ondelete='cascade')
    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', related='installment_id.loan_id', store=True)
    name = fields.Char(string='รายละเอียด')
    payment_date = fields.Date(string='วันที่โอน', default=fields.Date.today)
    amount = fields.Float(string='จำนวนเงิน', digits=(12, 2))
    attachment = fields.Binary(string='ไฟล์หลักฐาน', attachment=True)
    attachment_name = fields.Char(string='ชื่อไฟล์')
    bank_name = fields.Char(string='ธนาคาร')
    reference_no = fields.Char(string='เลขอ้างอิง')
    note = fields.Text(string='หมายเหตุ')
    uploaded_by = fields.Many2one('res.users', string='อัพโหลดโดย', default=lambda self: self.env.user)
    upload_date = fields.Datetime(string='วันที่อัพโหลด', default=fields.Datetime.now)
