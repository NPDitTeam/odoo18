# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CommissionPayoutWizard(models.TransientModel):
    _name = 'npd.loan.commission.payout.wizard'
    _description = 'Wizard จ่ายค่าคอม Sale'

    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True)

    # ข้อมูลสินเชื่อ (แสดงอย่างเดียว)
    loan_amount = fields.Float(string='เงินต้นทั้งหมด', related='loan_id.loan_amount')
    customer_name = fields.Char(string='ลูกค้า', related='loan_id.customer_name')
    loan_name = fields.Char(string='เลขที่สินเชื่อ', related='loan_id.name')

    # สรุปค่าคอม
    total_commission_sale = fields.Float(string='รวมค่าคอม Sale (หลัก)',
                                          related='loan_id.total_commission_sale')
    total_commission_installment = fields.Float(string='รวมค่าคอม Sale (รายงวด)',
                                                 related='loan_id.total_commission_installment')

    # รายการ wizard line
    wizard_line_ids = fields.One2many('npd.loan.commission.payout.wizard.line', 'wizard_id',
                                       string='รายการจ่ายค่าคอม')

    @api.model
    def default_get(self, fields_list):
        """สร้าง payout records แยกรายงวด + หลัก แล้วโหลดเข้า wizard"""
        res = super().default_get(fields_list)
        loan_id = self._context.get('default_loan_id')
        if not loan_id:
            return res

        loan = self.env['npd.loan'].browse(loan_id)
        if not loan.exists():
            return res

        payout_model = self.env['npd.loan.commission.payout']
        sale_users = loan.commission_line_ids.mapped('sale_user_id')

        # === สร้าง payout records ที่ยังไม่มี ===

        # 1) ค่าคอมหลัก - 1 record ต่อ Sale
        for sale_user in sale_users:
            existing = payout_model.search([
                ('loan_id', '=', loan_id),
                ('sale_user_id', '=', sale_user.id),
                ('payout_type', '=', 'main'),
            ], limit=1)
            # หา commission_amount จาก commission_line_ids
            comm_amount = 0
            for cl in loan.commission_line_ids:
                if cl.sale_user_id.id == sale_user.id:
                    comm_amount += cl.commission_amount
            if not existing:
                payout_model.create({
                    'loan_id': loan_id,
                    'sale_user_id': sale_user.id,
                    'payout_type': 'main',
                    'commission_amount': comm_amount,
                })
            elif existing.commission_amount != comm_amount:
                existing.write({'commission_amount': comm_amount})

        # 2) ค่าคอมรายงวด - 1 record ต่อ Sale ต่อ งวด
        for inst in loan.installment_ids:
            for ic in inst.commission_ids:
                if ic.commission_amount > 0:
                    existing = payout_model.search([
                        ('loan_id', '=', loan_id),
                        ('sale_user_id', '=', ic.sale_user_id.id),
                        ('payout_type', '=', 'installment'),
                        ('installment_id', '=', inst.id),
                    ], limit=1)
                    if not existing:
                        payout_model.create({
                            'loan_id': loan_id,
                            'sale_user_id': ic.sale_user_id.id,
                            'payout_type': 'installment',
                            'installment_id': inst.id,
                            'commission_amount': ic.commission_amount,
                        })
                    elif existing.commission_amount != ic.commission_amount:
                        existing.write({'commission_amount': ic.commission_amount})

        # === โหลด payout records เข้า wizard lines ===
        all_payouts = payout_model.search([('loan_id', '=', loan_id)],
                                           order='payout_type desc, installment_no, sale_user_id')
        wizard_lines = []
        for po in all_payouts:
            wizard_lines.append((0, 0, {
                'payout_id': po.id,
                'sale_user_id': po.sale_user_id.id,
                'payout_type': po.payout_type,
                'installment_id': po.installment_id.id if po.installment_id else False,
                'installment_no': po.installment_no,
                'commission_amount': po.commission_amount,
                'is_paid': po.is_paid,
                'status': po.status,
                'payment_date': po.payment_date,
                'attachment': po.attachment,

                'note': po.note,
            }))
        if wizard_lines:
            res['wizard_line_ids'] = wizard_lines

        return res

    def action_save(self):
        """บันทึกข้อมูลกลับไปยัง payout records"""
        self.ensure_one()
        for wl in self.wizard_line_ids:
            if wl.payout_id:
                wl.payout_id.write({
                    'is_paid': wl.is_paid,
                    'payment_date': wl.payment_date,
                    'attachment': wl.attachment,

                    'note': wl.note,
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'สำเร็จ',
                'message': 'บันทึกข้อมูลการจ่ายค่าคอม Sale เรียบร้อย',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def action_mark_all_paid(self):
        """จ่ายทั้งหมด (ตั้งสถานะ = จ่ายแล้ว + วันที่วันนี้)"""
        self.ensure_one()
        today = fields.Date.today()
        for wl in self.wizard_line_ids:
            if not wl.is_paid:
                wl.is_paid = True
                wl.status = 'paid'
                wl.payment_date = today


class CommissionPayoutWizardLine(models.TransientModel):
    _name = 'npd.loan.commission.payout.wizard.line'
    _description = 'รายการจ่ายค่าคอม Sale ใน Wizard'

    wizard_id = fields.Many2one('npd.loan.commission.payout.wizard', string='Wizard',
                                 required=True, ondelete='cascade')

    # เชื่อมกลับไปยัง persistent record
    payout_id = fields.Many2one('npd.loan.commission.payout', string='Payout Record')

    sale_user_id = fields.Many2one('res.users', string='Sale', readonly=True)

    # ประเภท
    payout_type = fields.Selection([
        ('main', 'ค่าคอมหลัก'),
        ('installment', 'ค่าคอมรายงวด'),
    ], string='ประเภท', readonly=True)

    installment_id = fields.Many2one('npd.loan.installment', string='งวดที่', readonly=True)
    installment_no = fields.Integer(string='งวด', readonly=True)

    # จำนวนเงินค่าคอม
    commission_amount = fields.Float(string='ค่าคอม', digits=(12, 2), readonly=True)

    # Display
    display_label = fields.Char(string='รายการ', compute='_compute_display_label')

    # ติ๊กจ่ายแล้ว
    is_paid = fields.Boolean(string='จ่ายแล้ว', default=False)

    # สถานะการจ่าย (ซ่อน — ใช้ is_paid แทน)
    status = fields.Selection([
        ('pending', 'รอจ่าย'),
        ('paid', 'จ่ายแล้ว'),
    ], string='สถานะ', default='pending')

    payment_date = fields.Date(string='วันที่จ่าย')

    # สลิปการโอน (แสดงเป็นรูปภาพ)
    attachment = fields.Image(string='สลิปการโอน', max_width=1024, max_height=1024)

    note = fields.Text(string='หมายเหตุ')

    @api.onchange('is_paid')
    def _onchange_is_paid(self):
        """เมื่อติ๊กจ่ายแล้ว → เปลี่ยนสถานะ + วันที่อัตโนมัติ"""
        if self.is_paid:
            self.status = 'paid'
            if not self.payment_date:
                self.payment_date = fields.Date.today()
        else:
            self.status = 'pending'
            self.payment_date = False

    def _compute_display_label(self):
        for rec in self:
            if rec.payout_type == 'main':
                rec.display_label = 'ค่าคอมหลัก'
            else:
                rec.display_label = 'งวดที่ %s' % (rec.installment_no or '-')
