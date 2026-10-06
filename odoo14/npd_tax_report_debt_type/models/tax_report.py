from odoo import api, fields, models

INVOICE_TYPES = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')


class TaxReportView(models.TransientModel):
    _inherit = 'tax.report.view'

    npd_debt_type = fields.Char(string='ประเภทหนี้', compute='_compute_npd_debt_type')
    npd_bk_debt_type = fields.Char(
        string='ประเภทหนี้ (บ้านเขียว)', compute='_compute_npd_debt_type')

    def _npd_source_invoices(self):
        """ใบแจ้งหนี้ต้นทางของบรรทัดรายงานนี้

        เอกสารภาษีของใบแจ้งหนี้ = ตัวใบแจ้งหนี้เอง ส่วนเอกสารภาษีที่เกิดตอนรับชำระ
        (ภาษีขายรอรับชำระ) = ใบแจ้งหนี้ที่รายการรับชำระนั้นตัดชำระ
        """
        self.ensure_one()
        number = (self.tax_invoice_number or '').replace(' (VOID)', '').strip()
        if not number:
            return self.env['account.move']
        domain = [('tax_invoice_number', '=', number)]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        moves = self.env['account.move']
        for tax_inv in self.env['account.move.tax.invoice'].search(domain, limit=10):
            # บางใบไม่ได้เก็บ move_id ไว้ ต้องตามจากบรรทัดบัญชีแทน
            move = tax_inv.move_id or tax_inv.move_line_id.move_id
            if move.move_type in INVOICE_TYPES:
                moves |= move
            elif tax_inv.payment_id:
                payment = tax_inv.payment_id
                moves |= payment.reconciled_invoice_ids | payment.reconciled_bill_ids
            elif move:
                moves |= move
        return moves

    @api.depends('tax_invoice_number', 'company_id')
    def _compute_npd_debt_type(self):
        Move = self.env['account.move']
        bk_labels = dict(Move._fields['bk_debt_type'].selection) if 'bk_debt_type' in Move._fields else {}
        for line in self:
            invoices = line._npd_source_invoices()
            line.npd_debt_type = ', '.join(dict.fromkeys(
                invoices.mapped('reason_code_id.name')))
            line.npd_bk_debt_type = ', '.join(dict.fromkeys(
                bk_labels.get(value, value) for value in invoices.mapped('bk_debt_type')
                if value)) if bk_labels else ''


class TaxReportWizard(models.TransientModel):
    _inherit = 'tax.report.wizard'

    def _get_extra_line_columns(self):
        return super()._get_extra_line_columns() + [
            ('ประเภทหนี้', lambda line: line.npd_debt_type),
            ('ประเภทหนี้ (บ้านเขียว)', lambda line: line.npd_bk_debt_type),
        ]
