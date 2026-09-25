# -*- coding: utf-8 -*-
"""ตรวจว่าข้อมูลที่ยกมาครบและตรงกับฝั่ง Odoo 14 จริงไหม

การซิงก์บอกได้แค่ว่ารอบนั้นทำงานจบ ไม่ได้แปลว่าข้อมูลครบ แถวที่พลาดไป
ตั้งแต่รอบก่อน ๆ หรือแถวที่ถูกลบทิ้งฝั่ง 18 โดยไม่ตั้งใจจะไม่โผล่ในใบบันทึกผล
ที่นี่จึงนับของจริงสองฝั่งมาเทียบกันทุกหัวข้อ แล้วบอกว่าขาดเท่าไร

นับสองแบบ
  1. จำนวนแถว — จับกรณีข้อมูลหายทั้งแถว
  2. ยอดเงินรวม — จับกรณีแถวครบแต่ตัวเลขข้างในเพี้ยน ซึ่งจำนวนแถวไม่มีทางจับได้

สลิปเงินเดือนแยกดูรายบริษัทด้วย เพราะฝั่ง 18 แยกข้อมูลตามบริษัท ถ้าจับคู่
บริษัทผิด ยอดรวมทั้งประเทศจะยังตรง แต่เงินไปกองผิดบริษัท ซึ่งเห็นได้เฉพาะ
ตอนแยกดูเท่านั้น
"""
import logging

from odoo import models, fields, api, _

from .sync_spec import SYNC_SPECS, spec_o18_model

_logger = logging.getLogger(__name__)

# หัวข้อที่มียอดเงิน ให้เทียบยอดด้วยไม่ใช่นับแถวอย่างเดียว
AMOUNT_FIELDS = {
    'payroll.salary': 'net_salary',
    'payroll.salary.line': 'amount',
    'payroll.ot.line': 'ot_amount',
    'payroll.deduction.line': 'amount',
}


class HrmsSyncCheck(models.Model):
    _name = 'npd.hrms.sync.check'
    _description = 'ผลการตรวจความครบถ้วนของข้อมูลที่ยกมา'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    date = fields.Datetime(string='ตรวจเมื่อ', required=True,
                           default=lambda self: fields.Datetime.now())
    config_id = fields.Many2one('npd.hrms.sync.config', string='การเชื่อมต่อ',
                                ondelete='set null')
    state = fields.Selection([
        ('ok', 'ครบทุกหัวข้อ'),
        ('diff', 'มีหัวข้อที่ไม่ตรง'),
    ], string='ผลรวม', default='ok')
    topic_total = fields.Integer(string='จำนวนหัวข้อ')
    topic_diff = fields.Integer(string='หัวข้อที่ไม่ตรง')
    line_ids = fields.One2many('npd.hrms.sync.check.line', 'check_id',
                               string='รายหัวข้อ')
    display_name = fields.Char(compute='_compute_display_name', store=False)

    @api.depends('date', 'state', 'topic_diff')
    def _compute_display_name(self):
        for rec in self:
            stamp = fields.Datetime.context_timestamp(rec, rec.date) \
                if rec.date else False
            label = 'ครบ' if rec.state == 'ok' else 'ไม่ตรง %s หัวข้อ' % rec.topic_diff
            rec.display_name = '%s — %s' % (
                stamp.strftime('%d/%m/%Y %H:%M') if stamp else '-', label)

    # ------------------------------------------------------------------
    @api.model
    def run_check(self, config=None):
        """นับสองฝั่งมาเทียบทุกหัวข้อ แล้วคืนใบผลตรวจ"""
        config = config or self.env['npd.hrms.sync.config']._get_active()
        check = self.create({'config_id': config.id})
        Line = self.env['npd.hrms.sync.check.line']

        diff_count = 0
        for spec in sorted(SYNC_SPECS, key=lambda s: s['seq']):
            o14_model = spec['o14_model']
            o18_model = spec_o18_model(spec)
            values = {
                'check_id': check.id,
                'sequence': spec['seq'],
                'name': spec['name'],
                'o14_model': o14_model,
                'o18_model': o18_model,
            }
            if o18_model not in self.env:
                Line.create(dict(values, state='skipped',
                                 message='ฝั่ง 18 ยังไม่มีโมเดลนี้'))
                continue
            try:
                result = self._compare_topic(config, spec)
            except Exception as error:
                _logger.exception('[HRMS-CHECK] ตรวจ %s ไม่สำเร็จ', spec['name'])
                Line.create(dict(values, state='error', message=str(error)))
                diff_count += 1
                continue
            Line.create(dict(values, **result))
            if result['state'] != 'ok':
                diff_count += 1

            # สลิปแยกดูรายบริษัทด้วย เพราะฝั่ง 18 แยกข้อมูลตามบริษัท
            if o14_model == 'payroll.salary':
                for extra in self._compare_payroll_by_company(config):
                    Line.create(dict(values, **extra))
                    if extra['state'] != 'ok':
                        diff_count += 1

        check.write({
            'topic_total': len(check.line_ids),
            'topic_diff': diff_count,
            'state': 'diff' if diff_count else 'ok',
        })
        return check

    # ------------------------------------------------------------------
    def _compare_topic(self, config, spec):
        # หัวข้อที่สองฝั่งเก็บคนละรูปแบบ นับตรง ๆ แล้วตัวเลขไม่มีความหมาย
        # (หนึ่งแถวฝั่ง 14 กลายเป็นแปดแถวฝั่ง 18) จึงมีตัวตรวจของตัวเอง
        if spec.get('check_handler'):
            return getattr(self, spec['check_handler'])(config, spec)
        o14_model = spec['o14_model']
        o18_model = spec_o18_model(spec)
        domain14 = list(spec.get('domain') or [])
        date_field = spec.get('date_field')
        if date_field and config.sync_from_date:
            domain14.append((date_field, '>=', str(config.sync_from_date)))

        count14 = config.execute_kw(o14_model, 'search_count', [domain14])
        # ฝั่ง 18 นับเฉพาะแถวที่ยกมาจากฝั่ง 14 เพื่อไม่ให้ของที่ฝั่ง 18 ทำเอง
        # มาทำให้ตัวเลขดูเกิน
        count18 = self.env['npd.hrms.sync.map'].search_count(
            [('o14_model', '=', o14_model)])

        amount_field = AMOUNT_FIELDS.get(o14_model)
        sum14 = sum18 = 0.0
        if amount_field and amount_field in self.env[o18_model]._fields:
            groups = config.execute_kw(
                o14_model, 'read_group',
                [domain14, [amount_field], []], {'lazy': False})
            sum14 = groups[0].get(amount_field) or 0.0 if groups else 0.0

            mapped_ids = self.env['npd.hrms.sync.map'].search(
                [('o14_model', '=', o14_model)]).mapped('res_id')
            if mapped_ids:
                records = self.env[o18_model].sudo().browse(mapped_ids).exists()
                sum18 = sum(records.mapped(amount_field))

        state = 'ok'
        notes = []
        if count14 != count18:
            state = 'diff'
            notes.append('จำนวนแถวต่างกัน %s แถว' % abs(count14 - count18))
        if amount_field and abs(sum14 - sum18) > 0.01:
            state = 'diff'
            notes.append('ยอดเงินต่างกัน %.2f บาท' % abs(sum14 - sum18))

        return {
            'count14': count14, 'count18': count18,
            'amount14': sum14, 'amount18': sum18,
            'state': state,
            'message': ' / '.join(notes) if notes else 'ตรงกัน',
        }

    def _check_leave_balance(self, config, spec):
        """โควตาวันลา — เทียบจำนวนพนักงานที่มีโควตา ไม่ใช่จำนวนแถว

        ฝั่ง 14 หนึ่งแถวคือหนึ่งพนักงาน ฝั่ง 18 หนึ่งพนักงานมีแปดแถว
        (แถวละประเภทลา) จำนวนแถวจึงเทียบกันไม่ได้ ที่เทียบได้คือจำนวนคน
        และยอดรวมวันลาทั้งหมด ซึ่งจับได้ทั้งกรณีคนหายและกรณีตัวเลขเพี้ยน
        """
        count14 = config.execute_kw(spec['o14_model'], 'search_count', [[]])
        total14 = 0.0
        leave_types = self.env['hrms.leave.type'].sudo().search([])
        remote = config.remote_fields(spec['o14_model'])
        total_fields = ['%s_total' % (t.code or '').strip()
                        for t in leave_types if (t.code or '').strip()]
        total_fields = [f for f in total_fields if f in remote]
        if total_fields:
            groups = config.execute_kw(
                spec['o14_model'], 'read_group', [[], total_fields, []],
                {'lazy': False})
            if groups:
                total14 = sum(groups[0].get(f) or 0 for f in total_fields)

        Balance = self.env['hrms.leave.balance'].sudo()
        year = fields.Date.context_today(self).year
        rows = Balance.search([('year', '=', year)])
        count18 = len(set(rows.mapped('employee_id').ids))
        total18 = sum(rows.mapped('total'))

        notes, state = [], 'ok'
        if count14 != count18:
            state = 'diff'
            notes.append('จำนวนพนักงานที่มีโควตาต่างกัน %s คน'
                         % abs(count14 - count18))
        if abs(total14 - total18) > 0.01:
            state = 'diff'
            notes.append('ยอดวันลารวมต่างกัน %.2f วัน' % abs(total14 - total18))
        return {
            'count14': count14, 'count18': count18,
            'amount14': total14, 'amount18': total18,
            'state': state,
            'message': ' / '.join(notes) if notes else 'ตรงกัน (นับเป็นจำนวนคน)',
        }

    def _check_checkin_distance(self, config, spec):
        """ระยะเช็คอิน — ฝั่ง 18 เก็บบนตัวสาขา จึงนับสาขาที่มีพิกัดแล้ว

        ฝั่ง 14 นับเฉพาะแถวที่ผูกสาขาไว้จริง เพราะแถวที่ไม่ได้ผูก (รายการทดสอบ)
        ยกมาไม่ได้อยู่แล้ว ถ้านับรวมด้วยตัวเลขจะไม่มีวันตรงกันทั้งที่ไม่ได้ผิด
        """
        count14 = config.execute_kw(
            spec['o14_model'], 'search_count', [[('branch_id', '!=', False)]])
        Branch = self.env['res.branch'].sudo().with_context(
            allowed_company_ids=self.env['res.company'].sudo().search([]).ids)
        count18 = Branch.search_count([('hr_checkin_latitude', '!=', False),
                                       ('hr_checkin_latitude', '!=', '')])
        state = 'ok' if count14 == count18 else 'diff'
        return {
            'count14': count14, 'count18': count18,
            'amount14': 0.0, 'amount18': 0.0,
            'state': state,
            'message': 'ตรงกัน (นับเป็นจำนวนสาขาที่มีพิกัด)' if state == 'ok'
                       else 'สาขาที่มีพิกัดต่างกัน %s แห่ง' % abs(count14 - count18),
        }

    def _compare_payroll_by_company(self, config):
        """เทียบสลิปแยกรายบริษัท — จับกรณีจับคู่บริษัทผิด"""
        results = []
        groups = config.execute_kw(
            'payroll.salary', 'read_group',
            [[], ['net_salary'], ['company']], {'lazy': False})
        CompanyMap = self.env['npd.hrms.sync.company.map']

        for group in groups:
            raw = (group.get('company') or '').strip()
            company_id = CompanyMap.resolve(raw)
            label = raw or '(ไม่ระบุบริษัท)'
            count14 = group.get('__count') or 0
            sum14 = group.get('net_salary') or 0.0

            if not company_id:
                results.append({
                    'name': '  ↳ บริษัท %s' % label,
                    'count14': count14, 'count18': 0,
                    'amount14': sum14, 'amount18': 0.0,
                    'state': 'diff',
                    'message': 'ยังไม่ได้จับคู่บริษัทนี้กับบริษัทฝั่ง 18 '
                               'ข้อมูลของบริษัทนี้จะยกมาโดยไม่มีบริษัท',
                })
                continue

            mapped_ids = self.env['npd.hrms.sync.map'].search(
                [('o14_model', '=', 'payroll.salary')]).mapped('res_id')
            records = self.env['payroll.salary'].sudo().browse(mapped_ids).exists()
            same = records.filtered(lambda r: r.company_id.id == company_id)
            sum18 = sum(same.mapped('net_salary'))

            notes = []
            state = 'ok'
            if len(same) != count14:
                state = 'diff'
                notes.append('จำนวนสลิปต่างกัน %s ใบ' % abs(count14 - len(same)))
            if abs(sum14 - sum18) > 0.01:
                state = 'diff'
                notes.append('ยอดสุทธิต่างกัน %.2f บาท' % abs(sum14 - sum18))

            results.append({
                'name': '  ↳ บริษัท %s' % label,
                'count14': count14, 'count18': len(same),
                'amount14': sum14, 'amount18': sum18,
                'state': state,
                'message': ' / '.join(notes) if notes else 'ตรงกัน',
            })
        return results

    def action_recheck(self):
        self.ensure_one()
        new_check = self.run_check(self.config_id or None)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'npd.hrms.sync.check',
            'res_id': new_check.id,
            'view_mode': 'form',
            'target': 'current',
        }


class HrmsSyncCheckLine(models.Model):
    _name = 'npd.hrms.sync.check.line'
    _description = 'ผลการตรวจรายหัวข้อ'
    _order = 'sequence, id'

    check_id = fields.Many2one('npd.hrms.sync.check', string='ใบตรวจ',
                               required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    name = fields.Char(string='หัวข้อ', required=True)
    o14_model = fields.Char(string='โมเดลฝั่ง 14')
    o18_model = fields.Char(string='โมเดลฝั่ง 18')

    count14 = fields.Integer(string='จำนวนฝั่ง 14')
    count18 = fields.Integer(string='จำนวนฝั่ง 18')
    count_diff = fields.Integer(string='ขาด/เกิน', compute='_compute_diff', store=True)
    amount14 = fields.Float(string='ยอดฝั่ง 14', digits=(16, 2))
    amount18 = fields.Float(string='ยอดฝั่ง 18', digits=(16, 2))
    amount_diff = fields.Float(string='ยอดต่างกัน', compute='_compute_diff',
                               store=True, digits=(16, 2))

    state = fields.Selection([
        ('ok', 'ตรงกัน'),
        ('diff', 'ไม่ตรง'),
        ('skipped', 'ข้าม'),
        ('error', 'ตรวจไม่ได้'),
    ], string='ผล', default='ok')
    message = fields.Char(string='รายละเอียด')

    @api.depends('count14', 'count18', 'amount14', 'amount18')
    def _compute_diff(self):
        for rec in self:
            rec.count_diff = rec.count18 - rec.count14
            rec.amount_diff = rec.amount18 - rec.amount14
