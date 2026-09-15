from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    slip_verify_extra_names = fields.Text(
        string='ชื่อบริษัทสำรอง (ตรวจสลิป AI)',
        help='รายชื่อบริษัทเพิ่มเติมที่ยอมรับได้เมื่อ AI ตรวจชื่อผู้รับเงินจากสลิป '
             '(นอกเหนือจากชื่อบริษัทหลัก) — ใส่ 1 ชื่อต่อ 1 บรรทัด\n'
             'เช่น ชื่อภาษาอังกฤษ หรือชื่อที่สะกดแบบต่าง ๆ\n'
             'ตัวอย่าง:\n'
             'NOPPADOL S GROUP CO.,LTD\n'
             'บริษัท นภดล เอสกรุ๊ป จำกัด',
    )
