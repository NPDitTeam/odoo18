# Copyright 2009-2018 Noviat
# Copyright 2019 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.pfb_asset_qrcode.models.asset import make_qr_png


class AccountAssetProfile(models.Model):
    _inherit = "account.asset.profile"

    std_asset_sequence_id = fields.Many2one('ir.sequence', string='Entry Sequence')


class AccountAsset(models.Model):
    _inherit = "account.asset"

    # o18 ไม่มีพารามิเตอร์ states บนฟิลด์แล้ว ย้ายเงื่อนไขอ่านอย่างเดียวไปไว้ที่วิว
    std_invoice = fields.Char(string="Invoice No")
    std_asset_purchase_id = fields.Many2one('purchase.order', string='Purchase No.', readonly=True)
    std_purchase_price = fields.Float(string="Purchase Price")
    std_model = fields.Char(string="Model")
    std_purchase_date = fields.Date(string="Purchase Date")
    std_serial_no = fields.Char(string="Serial No")
    std_employee_id = fields.Many2one('hr.employee', string='Employee')
    std_location_id = fields.Many2one('stock.location', string='Location')
    std_barcode = fields.Char(string="Asset Number ", copy=False)
    std_condition_type_id = fields.Many2one(
        comodel_name='account.condition.type',
        string='Asset condition',
    )
    std_condition_remark = fields.Text(string="Remark")
    std_no_compute_asset = fields.Boolean(string='No compute Asset')

    def account_asset_sequence(self):
        for asset in self:
            sequence = asset.profile_id.std_asset_sequence_id
            if not sequence:
                raise UserError(_('หมวดสินทรัพย์ %s ยังไม่ได้ตั้ง Entry Sequence')
                                % (asset.profile_id.name or ''))
            barcode = sequence.next_by_id(sequence_date=asset.date_start)
            asset.write({
                'std_barcode': barcode,
                'code': barcode,
                'sh_qr_code_img': make_qr_png(barcode),
            })
        return True

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("create_asset_from_move_line"):
            for vals in vals_list:
                vals.update({
                    "std_invoice": vals.get('code'),
                    "std_purchase_date": vals.get('date_start'),
                    "std_purchase_price": vals.get('purchase_value'),
                })
        return super().create(vals_list)

    def validate(self):
        """สินทรัพย์ที่ติ๊กไม่คิดค่าเสื่อม ยอดคงเหลือเป็น 0 ก็ยังให้อยู่สถานะเปิดใช้งาน

        o14 เขียนทับ validate ทั้งก้อน o18 เรียก super ให้โมดูลอื่นในสาย
        (เลขสินทรัพย์ OCA / สถานะย่อยของไทย) ทำงานครบก่อน แล้วค่อยแก้สถานะ
        """
        res = super().validate()
        self.filtered(
            lambda a: a.std_no_compute_asset and a.state == 'close'
        ).write({'state': 'open'})
        return res
