# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..models.res_partner import FIELD_LABELS, npd_tin_digits, npd_tin_valid

MAX_PARTNERS = 300
ADDRESS_FIELDS = ('street', 'street2', 'city', 'state_id', 'zip', 'country_id')


class NpdPartnerRdUpdateWizard(models.TransientModel):
    _name = 'npd.partner.rd.update.wizard'
    _description = 'อัปเดตข้อมูลผู้ติดต่อจากกรมสรรพากร'

    partner_ids = fields.Many2many('res.partner', string='ผู้ติดต่อ')
    update_name = fields.Boolean('อัปเดตชื่อบริษัท', default=True)
    update_address = fields.Boolean('อัปเดตที่อยู่', default=True)
    update_branch = fields.Boolean('อัปเดตรหัสสาขา (เฉพาะที่ยังว่าง)', default=True)
    result = fields.Text('ผลการอัปเดต', readonly=True)
    state = fields.Selection([('draft', 'ตั้งค่า'), ('done', 'เสร็จ')], default='draft')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ids = self.env.context.get('active_ids') or []
        res['partner_ids'] = [(6, 0, ids)]
        return res

    def action_update(self):
        self.ensure_one()
        if not (self.update_name or self.update_address or self.update_branch):
            raise UserError(_('กรุณาเลือกอย่างน้อย 1 อย่างที่จะอัปเดต'))
        partners = self.partner_ids.filtered(lambda p: p.is_company and p.vat)
        if len(partners) > MAX_PARTNERS:
            raise UserError(_('เลือกได้ครั้งละไม่เกิน %s ราย (เลือกมา %s ราย)') % (MAX_PARTNERS, len(partners)))
        updated, not_found, invalid, failed, name_dup = [], [], [], [], []
        skipped = len(self.partner_ids) - len(partners)
        for partner in partners:
            tin = npd_tin_digits(partner.vat)
            if not npd_tin_valid(tin):
                invalid.append(partner.display_name)
                continue
            branch_no = partner._npd_rd_branch_no()
            try:
                data = partner._npd_rd_query(tin, branch_no)
            except UserError:
                failed.append(partner.display_name)
                continue
            if not data:
                not_found.append(partner.display_name)
                continue
            vals = partner._npd_rd_values(data, branch_no)
            write = {}
            if self.update_name and vals.get('name'):
                write['name'] = vals['name']
            if self.update_address:
                write.update({f: vals[f] for f in ADDRESS_FIELDS if vals.get(f)})
            if self.update_branch and 'branch' in partner._fields and not (partner.branch or '').strip():
                write['branch'] = vals.get('branch')
            changed = {f: v for f, v in write.items() if f in partner._fields and (
                partner[f].id if partner._fields[f].type == 'many2one' else partner[f]) != v}
            if changed:
                old_name = partner.display_name
                try:
                    with self.env.cr.savepoint():
                        partner.with_context(skip_email_required=True).write(changed)
                except ValidationError:
                    # ชื่อใหม่ซ้ำกับผู้ติดต่อรายอื่น (กฎห้ามชื่อซ้ำ) — อัปเดตส่วนอื่นได้ ข้ามชื่อ
                    changed.pop('name', None)
                    name_dup.append(old_name)
                    if not changed:
                        continue
                    try:
                        with self.env.cr.savepoint():
                            partner.with_context(skip_email_required=True).write(changed)
                    except (ValidationError, UserError):
                        failed.append(partner.display_name)
                        continue
                partner.message_post(body=_('อัปเดตจากกรมสรรพากร (เลข %s สาขา %05d): %s')
                                     % (tin, branch_no, ', '.join(FIELD_LABELS.get(f, f) for f in changed)))
                updated.append(old_name)
        lines = [_('อัปเดตแล้ว %s ราย') % len(updated)]
        if not_found:
            lines.append(_('ไม่พบในกรมสรรพากร %s ราย (อาจไม่ได้จด VAT หรือรหัสสาขาไม่ตรง): %s')
                         % (len(not_found), ', '.join(not_found[:20])))
        if name_dup:
            lines.append(_('ไม่ได้เปลี่ยนชื่อ %s ราย เพราะชื่อจากกรมซ้ำกับผู้ติดต่อรายอื่น (อาจเป็นรายซ้ำ ควรตรวจ): %s')
                         % (len(name_dup), ', '.join(name_dup[:20])))
        if invalid:
            lines.append(_('เลขผู้เสียภาษีไม่ถูกต้อง %s ราย: %s') % (len(invalid), ', '.join(invalid[:20])))
        if failed:
            lines.append(_('อัปเดตไม่ได้ %s ราย (เชื่อมต่อกรมไม่ได้ หรือติดกฎข้อมูลซ้ำ): %s') % (len(failed), ', '.join(failed[:20])))
        if skipped:
            lines.append(_('ข้าม %s ราย (ไม่ใช่บริษัท หรือไม่มีเลขผู้เสียภาษี)') % skipped)
        self.write({'result': '\n'.join(lines), 'state': 'done'})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new'}
