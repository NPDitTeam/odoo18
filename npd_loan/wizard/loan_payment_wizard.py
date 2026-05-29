# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class AddInstallmentWizard(models.TransientModel):
    _name = 'npd.loan.add.installment.wizard'
    _description = 'เพิ่มงวดชำระใหม่'

    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True)
    
    # ข้อมูลสินเชื่อ (แสดงอย่างเดียว)
    loan_amount = fields.Float(string='เงินต้นทั้งหมด', related='loan_id.loan_amount')
    interest_rate = fields.Float(string='ดอกเบี้ย (%/เดือน)', related='loan_id.interest_rate')
    loan_date = fields.Date(string='ว.ด.ป. ปล่อย', related='loan_id.loan_date')
    
    # ข้อมูลงวดที่จะเพิ่ม (คำนวณอัตโนมัติ แต่แก้ไขได้)
    installment_no = fields.Integer(string='งวดที่')
    previous_remaining = fields.Float(string='เงินต้นก่อนงวดนี้', digits=(12, 2))
    carried_interest = fields.Float(string='ดอกค้างยกมา', digits=(12, 2), default=0)
    due_date = fields.Date(string='วันครบกำหนด')  # แก้ไขได้
    
    # ข้อมูลการชำระ (ให้กรอก)
    actual_payment = fields.Float(string='จ่ายจริง', digits=(12, 2), required=True)
    paid_date = fields.Date(string='วันที่ชำระ', default=fields.Date.today)

    # ใช้หักล่วงหน้า
    advance_used = fields.Float(string='ใช้หักล่วงหน้า', digits=(12, 2), default=0)
    advance_remaining = fields.Float(string='ยอดหักล่วงหน้าคงเหลือ', digits=(12, 2), readonly=True)

    # ตัวเลือกการคำนวณ
    skip_interest = fields.Boolean(string='ไม่คิดดอกเบี้ย (ชำระเงินต้นอย่างเดียว)', default=False)
    skip_late_fee = fields.Boolean(string='ไม่คิดค่าปรับ', default=False)

    # ยินยอมปิดหนี้
    close_debt = fields.Boolean(string='ยินยอมปิดหนี้', default=False)
    can_close_debt = fields.Boolean(string='สามารถปิดหนี้ได้', compute='_compute_can_close_debt')

    # ค่าปรับ
    late_fee = fields.Float(string='ค่าปรับ', digits=(12, 2))
    late_fee_paid = fields.Float(string='ค่าปรับที่จ่าย', digits=(12, 2))
    overdue_days = fields.Integer(string='วันเกิน')

    # ยอดที่คำนวณได้
    interest_amount = fields.Float(string='ยอดชำระดอก', digits=(12, 2))
    principal_amount = fields.Float(string='ยอดชำระเงินต้น', digits=(12, 2))
    remaining_principal = fields.Float(string='เงินต้นคงเหลือ', digits=(12, 2))
    minimum_payment = fields.Float(string='ชำระขั้นต่ำ', digits=(12, 2))
    carry_forward_interest = fields.Float(string='ดอกค้างส่งต่อ', digits=(12, 2))

    # ค่าคอม Sale
    wizard_commission_ids = fields.One2many('npd.loan.wizard.commission.line', 'wizard_id',
                                             string='ค่าคอม Sale')

    @api.model
    def default_get(self, fields_list):
        """คำนวณค่า default เมื่อเปิด wizard"""
        res = super().default_get(fields_list)
        loan_id = self._context.get('default_loan_id')
        if loan_id:
            loan = self.env['npd.loan'].browse(loan_id)
            if loan.exists():
                # หาเลขงวดถัดไป
                existing = self.env['npd.loan.installment'].search(
                    [('loan_id', '=', loan_id)], order='installment_no desc', limit=1)
                next_no = (existing.installment_no if existing else 0) + 1
                res['installment_no'] = next_no
                
                # หา previous_remaining และ carried_interest
                if next_no == 1:
                    res['previous_remaining'] = loan.loan_amount
                    res['carried_interest'] = 0
                else:
                    res['previous_remaining'] = existing.remaining_principal if existing else loan.loan_amount
                    res['carried_interest'] = existing.carry_forward_interest if existing else 0
                
                # คำนวณวันครบกำหนด = ว.ด.ป. ปล่อย + งวดที่ (เดือน)
                if loan.loan_date:
                    res['due_date'] = loan.loan_date + relativedelta(months=next_no)
                
                # คำนวณ minimum_payment (ค่าปรับ + ดอกเบี้ย + ดอกค้าง)
                prev = res.get('previous_remaining', 0)
                carried = res.get('carried_interest', 0)
                rate = (loan.interest_rate / 100) if loan.interest_rate else 0
                current_interest = round(prev * rate, 2)
                total_interest = round(current_interest + carried, 2)

                # คำนวณค่าปรับ (ถ้าเกินกำหนด)
                fee = 0.0
                o_days = 0
                due = res.get('due_date')
                if due:
                    today = fields.Date.today()
                    if today > due:
                        o_days = (today - due).days
                        fee_rate = loan.late_fee_rate or 0
                        base_interest = round(prev * rate, 2)
                        if loan.late_fee_type == 'per_period':
                            fee = round(base_interest * (fee_rate / 100), 2)
                        else:
                            fee = round(base_interest * (fee_rate / 100) * o_days, 2)
                res['overdue_days'] = o_days
                res['late_fee'] = fee

                res['minimum_payment'] = round(fee + total_interest, 2)
                res['interest_amount'] = total_interest

                # ยอดหักล่วงหน้าคงเหลือ
                res['advance_remaining'] = loan.advance_remaining

                # ดึงรายชื่อ Sale จากแท็บค่าคอมมิชชั่นของสินเชื่อ
                commission_lines = []
                for cl in loan.commission_line_ids:
                    commission_lines.append((0, 0, {
                        'sale_user_id': cl.sale_user_id.id,
                        'commission_amount': 0,
                    }))
                if commission_lines:
                    res['wizard_commission_ids'] = commission_lines

        return res

    @api.onchange('close_debt', 'skip_interest', 'skip_late_fee')
    def _onchange_close_debt(self):
        """Trigger คำนวณใหม่เมื่อเปลี่ยนค่า close_debt / skip_interest / skip_late_fee"""
        self._do_calculate()

    @api.onchange('actual_payment', 'previous_remaining', 'carried_interest', 'advance_used', 'due_date', 'paid_date')
    def _onchange_calculate(self):
        """Trigger คำนวณใหม่เมื่อเปลี่ยนค่าการชำระ"""
        self._do_calculate()

    def _do_calculate(self):
        """Logic คำนวณหลัก - เรียกจาก onchange ทั้งหมด

        หลักการ:
        - close_debt = ยินยอมปิดหนี้ → ตัดเงินต้นทั้งหมด ไม่คิดดอก/ค่าปรับ
        - skip_interest = ไม่คิดดอก → ตัดเงินต้นอย่างเดียว
        - skip_late_fee = ไม่คิดค่าปรับ → ข้ามค่าปรับ
        - advance_used = เครดิตล่วงหน้า ใช้จ่ายค่าปรับ + ดอก เท่านั้น ไม่ตัดเงินต้น
        - actual_payment = เงินสดจริง ใช้จ่ายค่าปรับ/ดอก ส่วนที่เหลือ + ตัดเงินต้น

        ลำดับ: ค่าปรับ → ดอก → เงินต้น
        """
        prev = self.previous_remaining or 0
        carried = self.carried_interest or 0
        advance = self.advance_used or 0
        actual = self.actual_payment or 0
        rate = (self.loan_id.interest_rate / 100) if self.loan_id else 0

        # --- คำนวณค่าปรับจากวันเกิน ---
        o_days = 0
        fee = 0.0
        if not self.skip_late_fee and self.due_date and self.loan_id:
            compare_date = self.paid_date or fields.Date.today()
            if compare_date > self.due_date:
                o_days = (compare_date - self.due_date).days
                base_interest = round(prev * rate, 2)
                fee_rate = self.loan_id.late_fee_rate or 0
                fee_type = self.loan_id.late_fee_type or 'per_period'
                if fee_type == 'per_period':
                    fee = round(base_interest * (fee_rate / 100), 2)
                else:  # daily
                    fee = round(base_interest * (fee_rate / 100) * o_days, 2)
        self.overdue_days = o_days
        self.late_fee = fee

        # --- ดอกเบี้ย ---
        if self.skip_interest:
            # ไม่คิดดอก → ตัดเงินต้นอย่างเดียว
            total_interest_due = 0
        else:
            current_interest = round(prev * rate, 2)
            total_interest_due = round(current_interest + carried, 2)

        # ขั้นต่ำ = ค่าปรับ + ดอกเบี้ยรวม
        self.minimum_payment = round(fee + total_interest_due, 2)

        # ตรวจสอบ advance_used ไม่เกิน advance_remaining
        if advance > (self.advance_remaining or 0):
            advance = self.advance_remaining or 0
            self.advance_used = advance

        # ถ้าติ๊กปิดหนี้ → ไม่คิดดอก/ค่าปรับ, ตัดเงินต้นทั้งหมด
        if self.close_debt and actual >= prev and prev > 0:
            self.interest_amount = 0
            self.principal_amount = prev
            self.remaining_principal = 0
            self.carry_forward_interest = 0
            self.late_fee_paid = 0
            return

        # คำนวณปกติ
        if advance > 0 or actual > 0:
            # === ค่าปรับ ===
            advance_for_fee = min(advance, fee)
            fee_remaining = round(fee - advance_for_fee, 2)
            advance_left = round(advance - advance_for_fee, 2)

            actual_for_fee = min(actual, fee_remaining)
            actual_left = round(actual - actual_for_fee, 2)

            self.late_fee_paid = round(advance_for_fee + actual_for_fee, 2)

            # === ดอกเบี้ย ===
            advance_for_interest = min(advance_left, total_interest_due)
            interest_remaining = round(total_interest_due - advance_for_interest, 2)

            actual_for_interest = min(actual_left, interest_remaining)
            interest_still_remaining = round(interest_remaining - actual_for_interest, 2)

            self.interest_amount = round(advance_for_interest + actual_for_interest, 2)
            self.carry_forward_interest = interest_still_remaining

            # === เงินต้น ===
            actual_for_principal = round(actual_left - actual_for_interest, 2)
            self.principal_amount = actual_for_principal

            self.remaining_principal = round(prev - self.principal_amount, 2)
            if self.remaining_principal < 0:
                self.remaining_principal = 0
        else:
            self.interest_amount = 0
            self.principal_amount = 0
            self.remaining_principal = prev
            self.carry_forward_interest = total_interest_due
            self.late_fee_paid = 0

    @api.depends('actual_payment', 'previous_remaining', 'advance_used', 'carried_interest')
    def _compute_can_close_debt(self):
        """แสดง checkbox ปิดหนี้ เมื่อจ่ายจริง >= เงินต้นคงเหลือ"""
        for rec in self:
            prev = rec.previous_remaining or 0
            actual = rec.actual_payment or 0
            rec.can_close_debt = (actual >= prev and prev > 0)

    @api.onchange('loan_id')
    def _onchange_loan_id(self):
        """คำนวณข้อมูลงวดอัตโนมัติเมื่อเปลี่ยน loan"""
        if not self.loan_id:
            return
        
        loan = self.loan_id
        # หาเลขงวดถัดไป
        existing = self.env['npd.loan.installment'].search(
            [('loan_id', '=', loan.id)], order='installment_no desc', limit=1)
        next_no = (existing.installment_no if existing else 0) + 1
        self.installment_no = next_no
        
        # หา previous_remaining และ carried_interest
        if next_no == 1:
            self.previous_remaining = loan.loan_amount
            self.carried_interest = 0
        else:
            self.previous_remaining = existing.remaining_principal if existing else loan.loan_amount
            self.carried_interest = existing.carry_forward_interest if existing else 0
        
        # คำนวณวันครบกำหนด
        if loan.loan_date:
            self.due_date = loan.loan_date + relativedelta(months=next_no)
        
        # คำนวณ minimum_payment (ดอก + ดอกค้าง)
        rate = (loan.interest_rate / 100) if loan.interest_rate else 0
        current_interest = round(self.previous_remaining * rate, 2)
        self.minimum_payment = round(current_interest + self.carried_interest, 2)
        self.interest_amount = self.minimum_payment

    def action_confirm(self):
        """ยืนยันและสร้างงวดใหม่"""
        self.ensure_one()

        if self.actual_payment <= 0 and self.advance_used <= 0:
            raise ValidationError(_('กรุณาใส่ยอดจ่ายจริง หรือใช้หักล่วงหน้า'))

        if self.previous_remaining <= 0:
            raise ValidationError(_('เงินต้นคงเหลือเป็น 0 แล้ว ไม่สามารถเพิ่มงวดได้'))

        # ตรวจสอบ advance_used ไม่เกินยอดคงเหลือ
        if self.advance_used > self.advance_remaining:
            raise ValidationError(_('ยอดหักล่วงหน้าที่ใช้ (%.2f) เกินยอดคงเหลือ (%.2f)') % (
                self.advance_used, self.advance_remaining))

        # เตรียม commission lines สำหรับงวดใหม่
        commission_vals = []
        for wc in self.wizard_commission_ids:
            commission_vals.append((0, 0, {
                'sale_user_id': wc.sale_user_id.id,
                'commission_amount': wc.commission_amount,
            }))

        # ตรวจสอบว่าเป็นการปิดหนี้หรือไม่
        is_close_debt = self.close_debt and self.can_close_debt

        # สร้างงวดใหม่ (ส่ง close_debt / skip_interest / skip_late_fee ไปด้วย)
        installment = self.env['npd.loan.installment'].create({
            'loan_id': self.loan_id.id,
            'installment_no': self.installment_no,
            'due_date': self.due_date,
            'actual_payment': self.actual_payment,
            'paid_date': self.paid_date,
            'previous_remaining': self.previous_remaining,
            'carried_interest': self.carried_interest if not self.skip_interest else 0,
            'advance_used': self.advance_used,
            'close_debt': is_close_debt,
            'skip_interest': self.skip_interest,
            'skip_late_fee': self.skip_late_fee,
            'late_fee_rate': self.loan_id.late_fee_rate,
            'late_fee_type': self.loan_id.late_fee_type,
            'commission_ids': commission_vals,
        })

        # ถ้าปิดหนี้ → ปิดบัญชีสินเชื่อด้วย
        if is_close_debt:
            self.loan_id.action_complete()

            msg = '🎉 ปิดบัญชีสำเร็จ! งวดที่ %s | จ่ายปิดหนี้: %.2f' % (
                self.installment_no, self.actual_payment)
            if self.advance_used > 0:
                msg += ' | หักล่วงหน้า: %.2f' % self.advance_used

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'ปิดบัญชีสำเร็จ',
                    'message': msg,
                    'type': 'success',
                    'sticky': True,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }

        msg = 'เพิ่มงวดที่ %s เรียบร้อย | จ่าย: %.2f' % (self.installment_no, self.actual_payment)
        if self.advance_used > 0:
            msg += ' | หักล่วงหน้า: %.2f' % self.advance_used
        msg += ' | เงินต้นคงเหลือ: %.2f' % self.remaining_principal

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'สำเร็จ',
                'message': msg,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
