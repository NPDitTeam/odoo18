# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountStatementImportSheetMapping(models.Model):
    _inherit = 'account.statement.import.sheet.mapping'

    # ค่าตั้งต้นของ OCA เป็นแบบยุโรป (หลักพันจุด ทศนิยมจุลภาค) ไม่มีรหัสภาษาไทย
    # ปรับให้ตรงไฟล์ธนาคารไทย: 1,234.56 / วันที่ dd/mm/yyyy / แยกคอลัมน์ฝาก-ถอน
    # มีผลเฉพาะรูปแบบไฟล์ที่สร้างใหม่ ของเดิมไม่เปลี่ยน
    file_encoding = fields.Selection(
        selection_add=[('cp874', 'ภาษาไทย (Windows-874 / TIS-620)')],
        ondelete={'cp874': 'set default'},
        # utf-8-sig อ่านไฟล์ UTF-8 ธรรมดาได้ด้วย และตัด BOM ที่ Excel ใส่หน้าไฟล์ CSV
        default='utf-8-sig',
    )
    float_thousands_sep = fields.Selection(default='comma')
    float_decimal_sep = fields.Selection(default='dot')
    timestamp_format = fields.Char(default='%d/%m/%Y')
    amount_type = fields.Selection(default='distinct_credit_debit')
