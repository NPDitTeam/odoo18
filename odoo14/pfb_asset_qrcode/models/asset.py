# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
from io import BytesIO

from odoo import api, fields, models

try:
    import qrcode
except ImportError:
    qrcode = None


def make_qr_png(text):
    """PNG (base64) ของ QR code จากข้อความ ใช้ร่วมกับ pfb_std_asset_free_field"""
    if not text or not qrcode:
        return False
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    temp = BytesIO()
    qr.make_image().save(temp, format="PNG")
    return base64.b64encode(temp.getvalue())


class AccountAsset(models.Model):
    _inherit = "account.asset"

    sh_qr_code_img = fields.Binary(string="QR Code Image", copy=False)

    @api.onchange('code')
    def onchange_code(self):
        for asset in self:
            asset.sh_qr_code_img = make_qr_png(asset.code)
