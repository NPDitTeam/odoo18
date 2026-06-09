import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


def _thai_date(d):
    if not d:
        return ''
    return '{}/{}/{}'.format(d.strftime('%d'), d.strftime('%m'), d.year + 543)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ===== รายละเอียดภาษี (จาก tax_invoice_ids - l10n_th_account_tax) =====
    # เก็บแต่ละคอลัมน์เป็นข้อความหลายบรรทัด (คั่นด้วย \n) เพื่อให้แสดงเป็นตาราง
    # โดยไม่ต้องใช้ ODOO_RELATIONS ตัวที่สอง (เลี่ยง cartesian กับ line_ids)
    jasper_pv_tax_names = fields.Char(compute='_compute_jasper_pv_tax')
    jasper_pv_tax_numbers = fields.Char(compute='_compute_jasper_pv_tax')
    jasper_pv_tax_dates = fields.Char(compute='_compute_jasper_pv_tax')
    jasper_pv_tax_bases = fields.Char(compute='_compute_jasper_pv_tax')
    jasper_pv_tax_amounts = fields.Char(compute='_compute_jasper_pv_tax')

    @api.depends(
        'tax_invoice_ids', 'tax_invoice_ids.tax_line_id',
        'tax_invoice_ids.tax_invoice_number', 'tax_invoice_ids.tax_invoice_date',
        'tax_invoice_ids.tax_base_amount', 'tax_invoice_ids.balance',
    )
    def _compute_jasper_pv_tax(self):
        for rec in self:
            names, numbers, dates, bases, amounts = [], [], [], [], []
            for t in rec.tax_invoice_ids:
                names.append(t.tax_line_id.name or '')
                numbers.append(t.tax_invoice_number or '')
                dates.append(_thai_date(t.tax_invoice_date))
                bases.append('{:,.2f}'.format(t.tax_base_amount or 0.0))
                amounts.append('{:,.2f}'.format(t.balance or 0.0))
            rec.jasper_pv_tax_names = '\n'.join(names)
            rec.jasper_pv_tax_numbers = '\n'.join(numbers)
            rec.jasper_pv_tax_dates = '\n'.join(dates)
            rec.jasper_pv_tax_bases = '\n'.join(bases)
            rec.jasper_pv_tax_amounts = '\n'.join(amounts)
