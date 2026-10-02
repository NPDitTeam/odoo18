from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WithholdingTaxType(models.Model):
    _name = 'withholding.tax.type'
    _description = 'ประเภทภาษีหัก ณ ที่จ่าย'

    wt_cert_income_type = fields.Selection([
        ('1', '40(1) เงินเดือน ค่าจ้าง'),
        ('2', '40(2) ค่านายหน้า'),
        ('3', '40(3) ค่าลิขสิทธิ์'),
        ('5', '40(4)ก การลงทุน'),
        ('6', '40(4)ข อื่นๆ'),
        ('7', '40(5)-(8)'),
        ('8', 'อื่นๆ (3 เตรส)'),
    ], string='ประเภทเงินได้', required=True)
    percent_tax = fields.Float(string='อัตราภาษี (%)')
    title_number_form = fields.Char(string='แบบฟอร์ม')

    _sql_constraints = [
        ('unique_income_type', 'unique(wt_cert_income_type)', 'ประเภทเงินได้ซ้ำ!'),
    ]


class WithholdingTaxCert(models.Model):
    _inherit = 'withholding.tax.cert'

    # Extra fields needed by account_advance and other modules
    # readonly/default ยกมาจากนิยามเดิมของ l10n_th_account_tax
    # (เลขออกจาก ir.sequence "withholding.tax.cert" ตอนใบเปลี่ยนเป็น done)
    # ประกาศ readonly ซ้ำไว้ตรงนี้ด้วย กันการพิมพ์เลขเองถ้านิยามเดิมเปลี่ยนไป
    number = fields.Char(string='เลขที่หนังสือ', readonly=True)
    advance_clear_id = fields.Many2one('account.advance.clear', string='Account Advance Clear', ondelete='cascade')
    base_amount = fields.Monetary(string='ฐานภาษี', compute='_compute_amounts_custom', store=True)
    tax_amount = fields.Monetary(string='ภาษีที่หัก', compute='_compute_amounts_custom', store=True)

    @api.depends('wht_line.base', 'wht_line.amount')
    def _compute_amounts_custom(self):
        for cert in self:
            cert.base_amount = sum(cert.wht_line.mapped('base'))
            cert.tax_amount = sum(cert.wht_line.mapped('amount'))

    @api.constrains('number', 'company_id')
    def _check_wht_cert_number_unique(self):
        """เลขที่หนังสือรับรองห้ามซ้ำกันภายในบริษัทเดียวกัน

        ไม่นับใบที่ยกเลิก (เลขคืนเข้าระบบ) ไม่นับใบที่ยังไม่ออกเลข (ค่า "/")
        เช็กตอนเลขถูกตั้ง/ถูกแก้เท่านั้น ไม่ผูกกับ state เพราะใบเก่าที่เลขซ้ำ
        กันอยู่ก่อนแล้วจะถูกบล็อกตอนเปลี่ยนสถานะ ทั้งที่ไม่ได้แตะเลข
        """
        for rec in self:
            number = (rec.number or '').strip()
            if not number or number == '/' or rec.state == 'cancel':
                continue
            domain = [
                ('id', '!=', rec.id),
                ('number', '=', number),
                ('state', '!=', 'cancel'),
            ]
            if 'company_id' in self._fields:
                domain.append(('company_id', '=', rec.company_id.id))
            duplicate = self.sudo().search(domain, limit=1)
            if duplicate:
                raise ValidationError(
                    _(
                        'เลขที่หนังสือรับรองหัก ณ ที่จ่าย "%s" ถูกใช้ไปแล้ว\n\n'
                        'ซ้ำกับเอกสาร id=%s (สถานะ %s)\n'
                        'เลขที่ชุดนี้ระบบออกให้อัตโนมัติ ถ้าเลขชนกันแปลว่า '
                        'ลำดับเลขของบริษัทนี้ถูกตั้งค่าซ้ำ กรุณาแจ้งฝ่ายบัญชี'
                    )
                    % (number, duplicate.id, duplicate.state)
                )
