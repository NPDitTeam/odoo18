import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# บัญชีลูกหนี้อื่นในผังใหม่ (บริษัทที่ไม่มีบัญชีนี้จะไม่ถูกสร้างวิธีชำระให้)
OTHER_RECEIVABLE_CODE = '1130-03'


class CustomPaymentMethod(models.Model):
    _inherit = 'custom.payment.method'

    npd_kind = fields.Selection([
        ('wht', 'ภาษีเงินได้ถูกหัก ณ ที่จ่าย'),
        ('other_receivable', 'ลูกหนี้อื่น (รอใบหัก ณ ที่จ่าย)'),
    ], string='ใช้สำหรับ', copy=False,
        help='ภาษีถูกหัก ณ ที่จ่าย: ซ่อนจากหน้ารับชำระ ใช้เป็นบัญชีปลายทางตอนแนบใบหัก ณ ที่จ่าย\n'
             'ลูกหนี้อื่น: ใช้แทนภาษีถูกหัก ณ ที่จ่ายในหน้ารับชำระ จนกว่าจะได้ใบจากลูกค้า')

    @api.model
    def _npd_setup_wht_receivable(self):
        """ติดป้ายวิธีชำระภาษีถูกหัก ณ ที่จ่ายเดิม + สร้างวิธีชำระ "ลูกหนี้อื่น" รายบริษัท (เรียกซ้ำได้)"""
        Method = self.sudo().with_context(active_test=False)
        for company in self.env['res.company'].sudo().search([]):
            wht = Method.search([('company_id', '=', company.id), ('name', 'ilike', 'ถูกหัก'),
                                 ('npd_kind', '=', False)])
            if wht:
                wht.write({'npd_kind': 'wht'})
            if Method.search_count([('company_id', '=', company.id), ('npd_kind', '=', 'other_receivable')]):
                continue
            account = self.env['account.account'].sudo().with_company(company).search([
                ('code', '=', OTHER_RECEIVABLE_CODE), ('company_ids', 'in', company.id)], limit=1)
            if not account:
                _logger.warning('npd_payment_wht_receivable: %s ไม่มีบัญชี %s ไม่ได้สร้างวิธีชำระลูกหนี้อื่น',
                                company.name, OTHER_RECEIVABLE_CODE)
                continue
            Method.create({
                'name': 'ลูกหนี้อื่น',
                'type': 'other',
                'account_id': account.id,
                'company_id': company.id,
                'npd_kind': 'other_receivable',
            })
        return True


class AccountPaidLine(models.Model):
    _inherit = 'account.paid.line'

    # ไม่ให้เลือกภาษีถูกหัก ณ ที่จ่ายตรง ๆ แล้ว (ใช้ลูกหนี้อื่น แล้วแนบใบทีหลัง)
    payment_method_id = fields.Many2one(
        domain="[('is_active', '=', True), ('company_id', 'in', [company_id, False]), ('npd_kind', '!=', 'wht')]",
    )
    npd_kind = fields.Selection(related='payment_method_id.npd_kind', store=True)
