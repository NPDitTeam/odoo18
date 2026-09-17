from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # o14 pfb_npd_add_date_account_move
    start_date = fields.Date(string='วันที่เริ่มต้นการเช่า')
    end_date = fields.Date(string='วันที่สิ้นสุดการเช่า')

    # o14 npd_print_select_account (ยกมาเฉพาะฟิลด์ ปุ่ม "อัพเดท" สร้างรายการค่าปรับยังไม่ได้พอร์ต)
    document_type = fields.Selection([
        ('invoice', 'ใบแจ้งหนี้'),
        ('tax_invoice', 'ใบกำกับภาษี'),
        ('delivery_note', 'ใบส่งสินค้า'),
    ], string='Document Type', default='invoice')
