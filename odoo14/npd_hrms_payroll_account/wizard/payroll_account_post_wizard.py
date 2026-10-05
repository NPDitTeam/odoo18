# -*- coding: utf-8 -*-
"""หน้าดูตัวอย่าง + ลงบัญชีเงินเดือน 1 แถวต่อบริษัทของสลิปในรอบ

ตัวอย่างคำนวณใน Python ล้วน ตอนกดลงบัญชีคำนวณใหม่อีกรอบเสมอ
ไม่เชื่อบรรทัดในหน้าตัวอย่าง (สลิปอาจถูกซิงก์ทับระหว่างเปิดหน้าค้างไว้)
"""
from odoo import Command, fields, models
from odoo.exceptions import AccessError, UserError


class NpdPayrollAccountPostWizard(models.TransientModel):
    _name = 'npd.payroll.account.post.wizard'
    _description = 'ลงบัญชีเงินเดือน'

    period_id = fields.Many2one(
        'payroll.period', string='รอบเงินเดือน', required=True, readonly=True,
        ondelete='cascade')
    company_line_ids = fields.One2many(
        'npd.payroll.account.post.wizard.company', 'wizard_id', string='บริษัท')

    def _npd_reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'ลงบัญชีเงินเดือน — %s' % self.period_id.sudo().display_name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def _npd_build_preview(self):
        self.ensure_one()
        Config = self.env['npd.payroll.account.config']
        Config._npd_check_poster()
        period = self.period_id.sudo()
        # คงวันที่/ตัวเลือกที่ผู้ใช้แก้ไว้ตอนกดคำนวณใหม่
        kept = {row.company_id.id: (row.date, row.to_post)
                for row in self.company_line_ids if row.state == 'ready'}
        self.company_line_ids.unlink()

        slips = self.env['payroll.salary'].sudo().search([('period_id', '=', period.id)])
        allowed = Config._npd_allowed_companies()
        Link = self.env['npd.payroll.account.move'].sudo()
        vals_list = []
        for company in slips.company_id.sorted('id'):
            vals = {'wizard_id': self.id, 'company_id': company.id}
            if company not in allowed:
                # ไม่คำนวณยอดของบริษัทที่ไม่มีสิทธิ์เลย กันเงินเดือนรั่ว
                vals.update(state='no_access', to_post=False)
                vals_list.append(vals)
                continue
            company_slips = slips.filtered(lambda slip: slip.company_id == company)
            config = Config.sudo().search([('company_id', '=', company.id)], limit=1)
            if not config:
                vals.update(
                    state='blocked', to_post=False, slip_count=len(company_slips),
                    issue_count=1,
                    issue_ids=[Command.create({
                        'severity': 'block',
                        'message': 'บริษัท %s ยังไม่มีการตั้งค่าลงบัญชีเงินเดือน — ไปที่ '
                                   'ผังบัญชีเงินเดือน แล้วกด "สร้างการตั้งค่าให้ทุกบริษัท'
                                   'ที่ยังไม่มี"' % company.name,
                    })])
                vals_list.append(vals)
                continue
            date, to_post = kept.get(company.id, (False, True))
            date = date or config._npd_posting_date(period, company_slips)
            result = config._npd_prepare_entries(period, company_slips, date)
            vals.update(self._npd_row_vals(config, result))
            existing = Link.search([
                ('period_id', '=', period.id), ('company_id', '=', company.id),
                ('state', '=', 'posted')], limit=1)
            if existing:
                vals.update(state='posted', existing_link_id=existing.id,
                            existing_move_name=existing.move_id.name)
            elif any(issue['severity'] == 'block' for issue in result['issues']):
                vals['state'] = 'blocked'
            else:
                vals['state'] = 'ready'
            vals['to_post'] = vals['state'] == 'ready' and to_post
            vals['date'] = date
            vals_list.append(vals)
        self.env['npd.payroll.account.post.wizard.company'].create(vals_list)
        return True

    def _npd_row_vals(self, config, result):
        company = config.company_id
        totals = result['totals']
        line_commands = []
        for sequence, line in enumerate(result['lines'], start=1):
            account = line['account'].with_company(company)
            line_commands.append(Command.create({
                'sequence': sequence,
                'account_id': account.id,
                'account_code': account.code or '',
                'account_name': account.name or '',
                'branch_id': line['branch'].id or False,
                'branch_name': line['branch'].sudo().name or '',
                'label': ', '.join(line['labels']),
                'debit': line['debit'],
                'credit': line['credit'],
            }))
        issue_commands = [Command.create({
            'severity': issue['severity'],
            'message': issue['message'],
            'amount': issue['amount'],
        }) for issue in sorted(result['issues'], key=lambda i: i['severity'] != 'block')]
        journal = config.journal_id
        return {
            'config_id': config.id,
            'journal_name': ('%s (%s)' % (journal.name, journal.code)) if journal else '',
            'slip_count': totals['slip_count'],
            'total_gross': totals['total_gross'],
            'total_deduction': totals['total_deduction'],
            'total_net': totals['total_net'],
            'total_debit': totals['total_debit'],
            'total_credit': totals['total_credit'],
            'employer_sso_amount': totals['employer_sso'],
            'rounding_residue': totals['rounding_residue'],
            'issue_count': len(result['issues']),
            'line_ids': line_commands,
            'issue_ids': issue_commands,
        }

    def action_refresh(self):
        self._npd_build_preview()
        return self._npd_reopen()

    def action_post(self):
        self.ensure_one()
        Config = self.env['npd.payroll.account.config']
        Config._npd_check_poster()
        rows = self.company_line_ids.filtered(lambda row: row.to_post and row.state == 'ready')
        if not rows:
            raise UserError('ยังไม่ได้เลือกบริษัทที่จะลงบัญชี หรือไม่มีบริษัทที่พร้อมลงบัญชี')
        period = self.period_id.sudo()
        # ล็อกแถวรอบไว้ก่อนตรวจซ้ำ แล้วแตะแถวไว้หนึ่งครั้ง: อีกคนที่กดพร้อมกัน
        # จะชนกันที่แถวนี้ (serialization failure -> Odoo ลองใหม่และเห็นว่าลงแล้ว)
        # แทนที่จะเห็นข้อมูลเก่าแล้วไปชน unique index หลังเสียเลขเอกสารไปแล้ว
        self.env.cr.execute(
            'SELECT id FROM payroll_period WHERE id = %s FOR UPDATE', [period.id])
        self.env.cr.execute(
            'UPDATE payroll_period SET write_date = write_date WHERE id = %s', [period.id])
        self.env.invalidate_all()

        allowed = Config._npd_allowed_companies()
        prepared = []
        errors = []
        # ตรวจครบทุกบริษัทก่อนสร้างรายการใบแรก ล้มกลางทางจะได้ไม่เสียเลขเอกสาร
        for row in rows:
            company = row.company_id
            if company not in allowed:
                raise AccessError('คุณไม่มีสิทธิ์บริษัท %s' % company.name)
            config = Config.sudo().search([('company_id', '=', company.id)], limit=1)
            if not config:
                errors.append('บริษัท %s ยังไม่มีการตั้งค่าลงบัญชีเงินเดือน' % company.name)
                continue
            result = config._npd_prepare_entries(period, config._npd_get_slips(period), row.date)
            blocks = [issue['message'] for issue in result['issues']
                      if issue['severity'] == 'block']
            if blocks:
                errors.append('บริษัท %s:\n- %s' % (company.name, '\n- '.join(blocks)))
                continue
            prepared.append((config, result, row.date))
        if errors:
            raise UserError('ลงบัญชีเงินเดือนไม่ได้\n\n%s' % '\n\n'.join(errors))

        links = self.env['npd.payroll.account.move']
        for config, result, date in prepared:
            links |= config._npd_post_period(period, date, result=result)
        moves = links.sudo().move_id
        return {
            'type': 'ir.actions.act_window',
            'name': 'รายการบัญชีเงินเดือน — %s' % period.display_name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False},
        }


class NpdPayrollAccountPostWizardCompany(models.TransientModel):
    _name = 'npd.payroll.account.post.wizard.company'
    _description = 'ลงบัญชีเงินเดือน: บริษัท'
    _order = 'company_id'

    wizard_id = fields.Many2one(
        'npd.payroll.account.post.wizard', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='บริษัท', readonly=True)
    config_id = fields.Many2one(
        'npd.payroll.account.config', string='การตั้งค่า', readonly=True)
    state = fields.Selection([
        ('ready', 'พร้อมลงบัญชี'),
        ('blocked', 'ติดปัญหา'),
        ('posted', 'ลงบัญชีแล้ว'),
        ('no_access', 'ไม่มีสิทธิ์บริษัทนี้'),
    ], string='สถานะ', readonly=True)
    to_post = fields.Boolean(string='ลงบัญชี')
    date = fields.Date(string='วันที่ลงบัญชี')
    journal_name = fields.Char(string='สมุดรายวัน', readonly=True)
    slip_count = fields.Integer(string='สลิป', readonly=True)
    total_gross = fields.Float(string='รวมรายได้', digits=(16, 2), readonly=True)
    total_deduction = fields.Float(string='รวมรายการหัก', digits=(16, 2), readonly=True)
    total_net = fields.Float(string='เงินสุทธิ (ยอดโอน)', digits=(16, 2), readonly=True)
    total_debit = fields.Float(string='รวมเดบิต', digits=(16, 2), readonly=True)
    total_credit = fields.Float(string='รวมเครดิต', digits=(16, 2), readonly=True)
    employer_sso_amount = fields.Float(
        string='ประกันสังคมส่วนนายจ้าง', digits=(16, 2), readonly=True)
    rounding_residue = fields.Float(string='เศษสตางค์', digits=(16, 2), readonly=True)
    existing_link_id = fields.Many2one(
        'npd.payroll.account.move', string='ลงบัญชีไว้แล้ว', readonly=True)
    existing_move_name = fields.Char(string='เลขที่รายการเดิม', readonly=True)
    line_ids = fields.One2many(
        'npd.payroll.account.post.wizard.line', 'company_line_id', string='รายการบัญชี',
        readonly=True)
    issue_ids = fields.One2many(
        'npd.payroll.account.post.wizard.issue', 'company_line_id',
        string='ปัญหาและคำเตือน', readonly=True)
    issue_count = fields.Integer(string='ปัญหา/คำเตือน', readonly=True)


class NpdPayrollAccountPostWizardLine(models.TransientModel):
    _name = 'npd.payroll.account.post.wizard.line'
    _description = 'ลงบัญชีเงินเดือน: บรรทัดตัวอย่าง'
    _order = 'sequence, id'

    company_line_id = fields.Many2one(
        'npd.payroll.account.post.wizard.company', required=True, ondelete='cascade')
    sequence = fields.Integer(string='ลำดับ')
    account_id = fields.Many2one('account.account', string='บัญชี', readonly=True)
    # เก็บรหัส/ชื่อเป็นข้อความ: รหัสบัญชีขึ้นกับบริษัท ถ้าแสดงจาก account_id
    # จะได้รหัสตามบริษัทที่ติ๊กอยู่ ไม่ใช่บริษัทของรายการ
    account_code = fields.Char(string='รหัสบัญชี', readonly=True)
    account_name = fields.Char(string='ชื่อบัญชี', readonly=True)
    # ห้ามใส่ branch_id ในวิว: กฎสาขาทำให้คนที่ไม่มีสาขานั้น AccessError ทั้งหน้า
    branch_id = fields.Many2one('res.branch', string='สาขา', readonly=True)
    branch_name = fields.Char(string='สาขา', readonly=True)
    label = fields.Char(string='คำอธิบาย', readonly=True)
    debit = fields.Float(string='เดบิต', digits=(16, 2), readonly=True)
    credit = fields.Float(string='เครดิต', digits=(16, 2), readonly=True)


class NpdPayrollAccountPostWizardIssue(models.TransientModel):
    _name = 'npd.payroll.account.post.wizard.issue'
    _description = 'ลงบัญชีเงินเดือน: ปัญหา'
    _order = 'id'

    company_line_id = fields.Many2one(
        'npd.payroll.account.post.wizard.company', required=True, ondelete='cascade')
    severity = fields.Selection([
        ('block', 'ห้ามลงบัญชี'),
        ('warn', 'คำเตือน'),
    ], string='ระดับ', readonly=True)
    message = fields.Text(string='รายละเอียด', readonly=True)
    amount = fields.Float(string='ยอด', digits=(16, 2), readonly=True)
