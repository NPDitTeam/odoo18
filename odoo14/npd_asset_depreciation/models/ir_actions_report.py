# -*- coding: utf-8 -*-
"""กันท้ายกระดาษของรายงานค่าสึกหรอหายเวลาโหลดไฟล์ CSS ไม่สำเร็จ

wkhtmltopdf เรนเดอร์ท้ายกระดาษเป็นคนละเอกสารกับเนื้อหา และ Odoo ประกอบเอกสารนั้น
จากเทมเพลต web.minimal_layout ซึ่งแนบ <link> ชี้กลับมาที่ Odoo เอง
รอบไหนโหลดไม่สำเร็จ (เซิร์ฟเวอร์ไม่ว่างรับ / ไม่มี session) มันจะทิ้งท้ายกระดาษทั้งก้อน
เลขหน้าเลยหายไปเงียบ ๆ

ท้ายกระดาษของรายงานนี้ใช้ inline style ล้วน ไม่ต้องใช้ CSS จากภายนอก
จึงตัด <link>/<script src> ออกให้หมด ไม่มีอะไรต้องโหลดก็ไม่มีอะไรให้พลาด
"""
import re

from odoo import models

REPORT_NAME = 'npd_asset_depreciation.report_npd_tax_depreciation'
EXTERNAL_RES_RE = re.compile(
    rb'<link\b[^>]*>|<script\b[^>]*\bsrc=[^>]*>\s*</script>', re.I)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    # o18 เพิ่มพารามิเตอร์ report_model และถูกเรียกจากตัวรายงานที่กำลังเรนเดอร์
    def _prepare_html(self, html, report_model=False):
        res = super()._prepare_html(html, report_model=report_model)
        if not isinstance(res, tuple) or len(res) != 5:
            return res
        bodies, html_ids, header, footer, args = res
        if REPORT_NAME in self.mapped('report_name'):
            header = self._npd_strip_external(header)
            footer = self._npd_strip_external(footer)
        return bodies, html_ids, header, footer, args

    @staticmethod
    def _npd_strip_external(doc):
        """ตัด <link>/<script src> ออกจากเอกสารหัว/ท้ายกระดาษ"""
        if not doc:
            return doc
        is_text = isinstance(doc, str)
        raw = doc.encode('utf-8') if is_text else bytes(doc)
        raw = EXTERNAL_RES_RE.sub(b'', raw)
        return raw.decode('utf-8') if is_text else raw
