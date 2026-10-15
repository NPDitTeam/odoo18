import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# บัญชีลูกหนี้อื่นในผังใหม่ (บริษัทที่ไม่มีบัญชีนี้จะไม่ถูกสร้างวิธีชำระให้)
OTHER_RECEIVABLE_CODE = '1130-03'
# บัญชีรับโอนที่ o14 ใช้คู่กับภาษีถูกหัก ณ ที่จ่ายแทบทุกใบ (นับจากใบรับชำระปี 2569)
# กรุงเทพ SCB 7739 (1,147 ใบ) / อินเตอร์ SCB 1071 (1,385) / เอส กรุ๊ป SCB 160-2 (1,151)
DEFAULT_WHT_BANK_NAMES = ('เงินโอนธนาคาร SCB 7739', 'เงินโอนธนาคาร SCB 1071', 'เงินโอนธนาคาร SCB 160-2')


class CustomPaymentMethod(models.Model):
    _inherit = 'custom.payment.method'

    npd_kind = fields.Selection([
        ('wht', 'ภาษีเงินได้ถูกหัก ณ ที่จ่าย'),
        ('other_receivable', 'ลูกหนี้อื่น (รอใบหัก ณ ที่จ่าย)'),
    ], string='ใช้สำหรับ', copy=False,
        help='ภาษีถูกหัก ณ ที่จ่าย: ซ่อนจากหน้ารับชำระ ใช้เป็นบัญชีปลายทางตอนแนบใบหัก ณ ที่จ่าย\n'
             'ลูกหนี้อื่น: ใช้แทนภาษีถูกหัก ณ ที่จ่ายในหน้ารับชำระ จนกว่าจะได้ใบจากลูกค้า')
    npd_wht_default_bank = fields.Boolean(
        string='รับโอนคู่ภาษีหัก 5% (ตั้งต้น)', copy=False,
        help='ใบแจ้งหนี้ที่ติ๊กหักภาษี ณ ที่จ่าย 5% หน้ารับชำระจะใส่บรรทัดรับโอนด้วยวิธีชำระนี้ให้เอง '
             '(บริษัทละ 1 รายการ)')

    @api.model
    def _npd_setup_wht_receivable(self):
        """ติดป้ายวิธีชำระภาษีถูกหัก ณ ที่จ่ายเดิม + สร้างวิธีชำระ "ลูกหนี้อื่น" รายบริษัท (เรียกซ้ำได้)"""
        Method = self.sudo().with_context(active_test=False)
        for company in self.env['res.company'].sudo().search([]):
            if not Method.search_count([('company_id', '=', company.id), ('npd_wht_default_bank', '=', True)]):
                bank = Method.search([('company_id', '=', company.id), ('name', 'in', DEFAULT_WHT_BANK_NAMES)], limit=1)
                if bank:
                    bank.npd_wht_default_bank = True
            wht = Method.search([('company_id', '=', company.id), ('name', 'ilike', 'ถูกหัก'),
                                 ('npd_kind', '=', False)])
            if wht:
                wht.write({'npd_kind': 'wht'})
            existing = Method.search([('company_id', '=', company.id), ('npd_kind', '=', 'other_receivable')], limit=1)
            if existing:
                # บัญชีที่เพิ่มรุ่นแรกเก็บชื่อแค่ภาษาตั้งต้น ให้มีชื่อไทยเหมือนบริษัทอื่น
                self.env.cr.execute("""
                    UPDATE account_account SET name = name || jsonb_build_object('th_TH', name->>'en_US')
                    WHERE id = %s AND NOT name ? 'th_TH'""", [existing.account_id.id])
                existing.account_id.invalidate_recordset(['name'])
                continue
            Account = self.env['account.account'].sudo().with_company(company)
            account = Account.search([('code', '=', OTHER_RECEIVABLE_CODE), ('company_ids', 'in', company.id)], limit=1)
            if not account:
                # ผังของบริษัทนี้ยังไม่มีลูกหนี้อื่น (เอส กรุ๊ป) → เพิ่มตามแบบของบริษัทอื่น
                account = Account.create({
                    'code': OTHER_RECEIVABLE_CODE,
                    'name': 'ลูกหนี้อื่น ๆ',
                    'account_type': 'asset_current',
                    'reconcile': False,
                    'company_ids': [(6, 0, [company.id])],
                })
                self.env.cr.execute("UPDATE account_account SET name = name || jsonb_build_object('th_TH', name->>'en_US') WHERE id = %s", [account.id])
                _logger.info('npd_payment_wht_receivable: เพิ่มบัญชี %s ลูกหนี้อื่น ๆ ให้ %s',
                             OTHER_RECEIVABLE_CODE, company.name)
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
    npd_auto = fields.Boolean(string='ระบบใส่ให้', copy=False,
                              help='บรรทัดที่ระบบใส่ให้จากการติ๊กหักภาษี 5% บนใบสั่งขาย (แก้ใบแจ้งหนี้แล้วระบบคิดใหม่ให้)')
