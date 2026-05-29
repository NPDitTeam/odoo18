# -*- coding: utf-8 -*-
from odoo import models, fields, api


class NpdSaleCommissionTemplate(models.Model):
    _name = 'npd.sale.commission.template'
    _description = 'เทมเพลตค่าคอม Sale'
    _order = 'sequence, id'

    name = fields.Char(string='ชื่อเทมเพลต', required=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    active = fields.Boolean(string='ใช้งาน', default=True)
    sale_line_ids = fields.One2many('npd.sale.commission.template.line', 'template_id', string='รายชื่อ Sale')
    description = fields.Text(string='หมายเหตุ')


class NpdSaleCommissionTemplateLine(models.Model):
    _name = 'npd.sale.commission.template.line'
    _description = 'รายชื่อ Sale ในเทมเพลต'
    _order = 'sequence, id'

    template_id = fields.Many2one('npd.sale.commission.template', string='เทมเพลต',
                                   required=True, ondelete='cascade')
    sequence = fields.Integer(string='ลำดับ', default=10)
    sale_user_id = fields.Many2one('res.users', string='Sale', required=True)
    sale_name = fields.Char(string='ชื่อ Sale', related='sale_user_id.name', store=True)


class NpdLoanCommissionLine(models.Model):
    _name = 'npd.loan.commission.line'
    _description = 'ค่าคอม Sale ในสินเชื่อ'
    _order = 'sequence, id'

    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True, ondelete='cascade')
    sequence = fields.Integer(string='ลำดับ', default=10)
    sale_user_id = fields.Many2one('res.users', string='Sale', required=True)
    commission_amount = fields.Float(string='ค่าคอม', digits=(12, 2))


class NpdLoanInstallmentCommission(models.Model):
    _name = 'npd.loan.installment.commission'
    _description = 'ค่าคอม Sale แต่ละงวด'
    _order = 'id'

    installment_id = fields.Many2one('npd.loan.installment', string='งวดชำระ',
                                      required=True, ondelete='cascade')
    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ',
                               related='installment_id.loan_id', store=True)
    sale_user_id = fields.Many2one('res.users', string='Sale', required=True)
    commission_amount = fields.Float(string='ค่าคอม Sale', digits=(12, 2), default=0)
    minimum_payment = fields.Float(string='ชำระขั้นต่ำ (ดอก+ค้าง)',
                                    related='installment_id.minimum_payment', readonly=True)
    net_amount = fields.Float(string='ยอดสุทธิเหลือ', digits=(12, 2),
                               compute='_compute_net_amount', store=True)

    @api.depends('minimum_payment', 'commission_amount')
    def _compute_net_amount(self):
        """ยอดสุทธิ = ชำระขั้นต่ำ - ค่าคอม Sale"""
        for rec in self:
            rec.net_amount = rec.minimum_payment - rec.commission_amount


class NpdLoanWizardCommissionLine(models.TransientModel):
    _name = 'npd.loan.wizard.commission.line'
    _description = 'ค่าคอม Sale ใน Wizard เพิ่มงวด'

    wizard_id = fields.Many2one('npd.loan.add.installment.wizard', string='Wizard',
                                 required=True, ondelete='cascade')
    sale_user_id = fields.Many2one('res.users', string='Sale', required=True)
    commission_amount = fields.Float(string='ค่าคอม Sale', digits=(12, 2), default=0)
    minimum_payment = fields.Float(string='ชำระขั้นต่ำ (ดอก+ค้าง)',
                                    related='wizard_id.minimum_payment', readonly=True)
    net_amount = fields.Float(string='ยอดสุทธิเหลือ', digits=(12, 2),
                               compute='_compute_net_amount')

    @api.depends('minimum_payment', 'commission_amount')
    def _compute_net_amount(self):
        for rec in self:
            rec.net_amount = rec.minimum_payment - rec.commission_amount
