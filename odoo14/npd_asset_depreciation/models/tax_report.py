# -*- coding: utf-8 -*-
"""ตัวป้อนข้อมูลให้รายงานค่าสึกหรอ (พ.ร.ฎ.)

ปุ่มพิมพ์เปิด PDF ด้วย URL ซึ่งเป็นคนละ request กับตอนกดปุ่ม ถ้าฝากเงื่อนไข
การพิมพ์ไว้กับ record ของหน้าต่างคำนวณ (TransientModel) พอถึงเวลาเรนเดอร์
record นั้นอาจถูกเก็บกวาดไปแล้ว (อายุเกิน 1 ชม. หรือมีคนเปิดหน้าต่างอื่นจนถึงโควตา)
จะได้ MissingError: Record does not exist

จึงส่งเงื่อนไข (บริษัท/ปี/ช่วงเดือน/หมวด/สินทรัพย์) ไปกับ URL แล้วสร้างหน้าต่างคำนวณ
ตัวใหม่ตอนเรนเดอร์ ลิงก์เดิมจึงเปิดซ้ำได้เสมอ ไม่มีวันหมดอายุ
"""
from odoo import _, api, models
from odoo.exceptions import UserError

WIZARD = 'npd.asset.depreciation.compute'


class ReportNpdTaxDepreciation(models.AbstractModel):
    _name = 'report.npd_asset_depreciation.report_npd_tax_depreciation'
    _description = 'ข้อมูลรายงานค่าสึกหรอและค่าเสื่อมราคา (พ.ร.ฎ.)'

    @api.model
    def _ids_from(self, raw):
        """'1,2,3' -> [1, 2, 3] (ค่าที่มาจาก URL เป็นข้อความเสมอ)"""
        return [int(i) for i in str(raw or '').split(',') if i.strip().isdigit()]

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        Wizard = self.env[WIZARD]

        if data.get('year'):
            # มาจากปุ่มพิมพ์ -- สร้างหน้าต่างคำนวณตัวใหม่จากเงื่อนไขใน URL
            month_from = str(int(data.get('month_from') or 1))
            company_ids = self._ids_from(data.get('company'))
            # ต้องเป็นบริษัทที่ผู้ใช้เข้าถึงได้เท่านั้น ไม่งั้นใช้บริษัทปัจจุบัน
            company = self.env['res.company'].browse(company_ids[:1]) & self.env.user.company_ids \
                or self.env.company
            docs = Wizard.with_company(company).create({
                'company_id': company.id,
                'year': int(data['year']),
                'month_from': month_from,
                'month_to': str(int(data.get('month_to') or month_from)),
                'profile_ids': [(6, 0, self._ids_from(data.get('profiles')))],
                'asset_ids': [(6, 0, self._ids_from(data.get('assets')))],
            })
        else:
            # เผื่อมีคนสั่งพิมพ์จาก record ตรง ๆ (เมนูพิมพ์มาตรฐาน)
            docs = Wizard.browse(docids or []).exists()
            if not docs:
                raise UserError(_(
                    'ลิงก์รายงานนี้หมดอายุแล้ว\n\n'
                    'กรุณากดพิมพ์ใหม่จากเมนู "คำนวณค่าเสื่อมประจำปี"'))

        return {
            'doc_ids': docs.ids,
            'doc_model': WIZARD,
            'docs': docs,
        }
