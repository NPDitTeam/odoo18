from odoo import fields, models, api, _


class CashBillWizard(models.TransientModel):
    _name = 'cash.bill.wizard'
    _description = 'Cash Bill Entry Wizard'

    advance_clear_id = fields.Many2one(
        'account.advance.clear',
        string='Advance Clear',
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'cash.bill.wizard.line',
        'wizard_id',
        string='รายการบิลเงินสด',
    )
    total_amount = fields.Float(
        string='ยอดรวม',
        compute='_compute_total_amount',
        store=False,
    )
    total_vat = fields.Float(
        string='VAT รวม',
        compute='_compute_total_amount',
        store=False,
    )
    grand_total = fields.Float(
        string='ยอดรวมทั้งสิ้น',
        compute='_compute_total_amount',
        store=False,
    )

    @api.depends('line_ids.amount', 'line_ids.vat_amount')
    def _compute_total_amount(self):
        for wiz in self:
            wiz.total_amount = sum(wiz.line_ids.mapped('amount'))
            wiz.total_vat = sum(wiz.line_ids.mapped('vat_amount'))
            wiz.grand_total = wiz.total_amount + wiz.total_vat

    def action_save(self):
        """Save wizard lines as persistent cash bill records."""
        self.ensure_one()
        # Delete existing cash bill entries for this advance clear
        self.advance_clear_id.cash_bill_ids.unlink()
        # Create new entries from wizard lines
        for line in self.line_ids:
            self.env['advance.clear.cash.bill'].create({
                'advance_clear_id': self.advance_clear_id.id,
                'description': line.description,
                'amount': line.amount,
                'vat_amount': line.vat_amount,
                'sequence': line.sequence,
            })
        return {'type': 'ir.actions.act_window_close'}


class CashBillWizardLine(models.TransientModel):
    _name = 'cash.bill.wizard.line'
    _description = 'Cash Bill Wizard Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'cash.bill.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(
        string='ลำดับ',
        default=10,
    )
    description = fields.Char(
        string='รายการสินค้า',
        required=True,
    )
    amount = fields.Float(
        string='จำนวนเงิน',
        required=True,
        digits='Product Price',
    )
    vat_amount = fields.Float(
        string='VAT',
        digits='Product Price',
        default=0,
    )
