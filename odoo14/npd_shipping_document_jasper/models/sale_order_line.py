from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # ฟิลด์ string สำหรับแสดงในตาราง Jasper (จัดรูปแบบตัวเลขแล้ว)
    jasper_qty = fields.Char(
        string='Qty (str)', compute='_compute_jasper_line_strings')
    jasper_uom_weight = fields.Char(
        string='Weight/Unit (str)', compute='_compute_jasper_line_strings')
    jasper_line_weight = fields.Char(
        string='Total Weight (str)', compute='_compute_jasper_line_strings')

    def _compute_jasper_line_strings(self):
        for line in self:
            try:
                qty = float(getattr(line, 'pfb_quantity', 0.0) or 0.0)
            except Exception:
                qty = 0.0
            try:
                uomw = float(getattr(line, 'second_uom_qty', 0.0) or 0.0)
            except Exception:
                uomw = 0.0
            try:
                tw = float(getattr(line, 'total_weight', 0.0) or 0.0)
            except Exception:
                tw = 0.0
            line.jasper_qty = '{:,.2f}'.format(qty)
            line.jasper_uom_weight = '{:,.2f}'.format(uomw)
            line.jasper_line_weight = '{:,.2f}'.format(tw)
