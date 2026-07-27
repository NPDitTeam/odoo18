from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    is_payment_multi = fields.Boolean(
        string='Multi Payment', default=False,
    )
    pfb_so_type = fields.Selection([
        ('sale', 'Sale'),
        ('rent', 'Rent'),
        ('other', 'Other'),
    ], string='SO Type')

    pfb_objective_id = fields.Many2one(
        'sale.objective', string='Objective',
    )

    # ต้องประกาศ depends เดิมซ้ำ เพราะ override ไปแทนที่ method ใน MRO
    @api.depends('available_journal_ids')
    def _compute_journal_id(self):
        super()._compute_journal_id()
        # หน้ารับชำระอิงสมุดรายวันของใบแจ้งหนี้ที่กำลังจะชำระ
        # จับคู่ได้ที่เมนู การขาย > การกำหนดค่า > สมุดรายวันรับชำระ
        JournalMap = self.env['npd.invoice.journal.config']
        for wizard in self:
            invoice_journals = wizard.line_ids.move_id.journal_id
            payment_journal = JournalMap._get_payment_journal(
                wizard.company_id, invoice_journals,
            )
            # เคารพ domain ของ wizard: ถ้าเล่มที่จับคู่ไว้เลือกไม่ได้ในบริบทนี้
            # (เช่นคนละสกุลเงิน) ให้ใช้ค่าที่ Odoo คำนวณมาตามเดิม
            if payment_journal and payment_journal in wizard.available_journal_ids:
                wizard.journal_id = payment_journal

    def _create_payment_vals_from_wizard(self, batch_result):
        """Override to pass custom fields to payment creation."""
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals.update({
            'is_payment_multi': self.is_payment_multi,
            'pfb_so_type': self.pfb_so_type,
            'pfb_objective_id': self.pfb_objective_id.id if self.pfb_objective_id else False,
        })
        return vals
