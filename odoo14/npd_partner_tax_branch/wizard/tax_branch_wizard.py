import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class NpdTaxBranchWizard(models.TransientModel):
    _name = 'npd.tax.branch.wizard'
    _description = 'กรอกรหัสสาขาลูกค้า (Tax Branch)'

    partner_id = fields.Many2one('res.partner', string='ลูกค้า', required=True, readonly=True)
    vat = fields.Char(related='partner_id.vat', string='เลขประจำตัวผู้เสียภาษี')
    branch = fields.Char(string='รหัสสาขา (Tax Branch)', size=5, required=True)

    @api.constrains('branch')
    def _check_branch(self):
        for wizard in self:
            if not re.fullmatch(r'\d{5}', (wizard.branch or '').strip()):
                raise ValidationError(_(
                    'รหัสสาขาต้องเป็นตัวเลข 5 หลัก เช่น 00000 (สำนักงานใหญ่) หรือ 00001'))

    def action_save(self):
        self.ensure_one()
        branch = self.branch.strip()
        try:
            # พนักงานขายบางคนไม่มีสิทธิ์แก้ผู้ติดต่อ แต่ต้องกรอกช่องนี้ได้
            # จึงเขียนด้วย sudo เฉพาะช่องรหัสสาขาช่องเดียว
            # savepoint: ถ้าซ้ำ ให้ทรานแซกชันหลักยังใช้ต่อได้ (แสดงข้อความเราแทน)
            vals = {'branch': branch}
            # เลขภาษีที่เป็นช่องว่างล้วน (ยกมาจากข้อมูลเก่า) ถูกนับเป็นเลขภาษี
            # เดียวกันหมด ลูกค้ารายที่สองที่ใส่ 00000 จะชนกฎห้ามซ้ำทั้งที่ไม่ได้ซ้ำจริง
            if self.partner_id.vat and not self.partner_id.vat.strip():
                vals['vat'] = False
            with self.env.cr.savepoint():
                self.partner_id.sudo().write(vals)
        except ValidationError:
            # l10n_th_partner ห้าม "เลขผู้เสียภาษี + รหัสสาขา" ซ้ำกัน
            # เกิดเมื่อมีลูกค้ารายเดียวกันถูกสร้างซ้ำหลายรายการ
            duplicates = self.env['res.partner'].sudo().search([
                ('vat', '=', self.partner_id.vat), ('branch', '=', branch),
                ('id', '!=', self.partner_id.id)], limit=3)
            raise ValidationError(_(
                'เลขประจำตัวผู้เสียภาษี %(vat)s สาขา %(branch)s ถูกใช้กับลูกค้ารายอื่นแล้ว: %(names)s\n'
                'น่าจะเป็นลูกค้ารายเดียวกันที่ถูกสร้างซ้ำ ให้เลือกลูกค้ารายนั้นในใบสั่งขายแทน '
                'หรือแจ้งฝ่ายบัญชีให้รวมรายชื่อลูกค้า',
                vat=self.partner_id.vat, branch=branch,
                names=', '.join(duplicates.mapped('display_name'))))
        # infos ให้ฝั่ง JS รู้ว่ากรอกแล้ว (ปิดด้วย X / ยกเลิก จะไม่มีค่านี้)
        return {'type': 'ir.actions.act_window_close',
                'infos': {'npd_tax_branch_saved': True}}
