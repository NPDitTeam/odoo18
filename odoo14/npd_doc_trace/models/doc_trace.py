# -*- coding: utf-8 -*-
import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# ช่องข้อความที่มักพิมพ์เลขเอกสารอื่นไว้อ้างอิง
TEXT_FIELDS = ('origin', 'invoice_origin', 'ref', 'payment_reference', 'reference', 'client_order_ref',
               'partner_ref', 'communication', 'source_document', 'memo')
# ช่องที่ไม่ใช่ความเชื่อมโยงทางธุรกิจ
SKIP_FIELDS = {'message_ids', 'activity_ids', 'website_message_ids', 'message_follower_ids',
               'previous_statement_id', 'current_revision_id', 'old_revision_ids', 'duplicated_ref_ids',
               'available_invoice_ids'}
# เส้นทางพิเศษ (ผ่านบรรทัดรายการ): model -> [(path, ป้าย)]
LINE_PATHS = {
    'account.move': [('invoice_line_ids.sale_line_ids.order_id', 'ใบสั่งขายของรายการ'),
                     ('invoice_line_ids.purchase_line_id.order_id', 'ใบสั่งซื้อของรายการ')],
}
# ป้ายภาษาไทยของช่องที่ยังไม่มีคำแปล
FIELD_LABELS = {
    'reversed_entry_id': 'ใบเดิมที่ถูกลดหนี้/กลับรายการ',
    'reversal_move_id': 'ใบลดหนี้/กลับรายการ',
    'refund_invoice_ids': 'ใบลดหนี้',
    'debit_origin_id': 'ใบแจ้งหนี้เดิม (ที่ถูกเพิ่มหนี้)',
    'debit_note_ids': 'ใบเพิ่มหนี้',
    'picking_ids': 'ใบส่ง/รับสินค้า',
    'reconciled_invoice_ids': 'ใบแจ้งหนี้ที่ตัดชำระ',
    'reconciled_bill_ids': 'บิลผู้ขายที่ตัดชำระ',
    'invoice_ids': 'ใบแจ้งหนี้',
    'move_id': 'รายการบัญชี',
    'payment_id': 'การชำระเงิน',
    'payment_ids': 'การชำระเงิน',
    'sale_id': 'ใบสั่งขาย',
    'purchase_id': 'ใบสั่งซื้อ',
    'backorder_id': 'ใบค้างส่งจาก',
    'backorder_ids': 'ใบค้างส่ง',
    'wt_cert_ids': 'หนังสือรับรองหัก ณ ที่จ่าย',
    'tax_cash_basis_move_id': 'รายการภาษีตามรับชำระ',
    'rent_ids': 'ใบแจ้งหนี้ค่าเช่า',
}
TOKEN_SPLIT = re.compile(r'[\s,;:()\[\]]+')
MAX_PER_RELATION = 30
MAX_CHILDREN = 15
MAX_LINES = 300
AMOUNT_FIELDS = ('amount_total', 'amount', 'amount_total_signed', 'amount_untaxed')


class NpdDocTrace(models.AbstractModel):
    _name = 'npd.doc.trace'
    _description = 'หาเอกสารที่เชื่อมโยง'

    @api.model
    def _doc_models(self):
        return set(self.env['npd.doc.finder.line']._readable_models())

    @api.model
    def _normalize(self, record):
        """รายการบัญชีที่เป็นของการรับ/จ่ายชำระ ให้แสดงเป็นใบชำระ (ในเมนูค้นหาก็แสดงแบบนี้)"""
        if record._name == 'account.move':
            pay = record['payment_id'] if 'payment_id' in record._fields else \
                (record['origin_payment_id'] if 'origin_payment_id' in record._fields else False)
            if pay:
                return pay
        return record

    @api.model
    def _reconciled_moves(self, moves):
        lines = moves.mapped('line_ids').filtered(lambda l: l.account_id.reconcile)
        partner = lines.mapped('matched_debit_ids.debit_move_id') | lines.mapped('matched_credit_ids.credit_move_id')
        return partner.mapped('move_id') - moves

    @api.model
    def _links(self, record, doc_models, full=True):
        """คืน [(ป้ายความสัมพันธ์, record ปลายทาง)] ของเอกสารหนึ่งใบ
        full=False (ชั้น 2) ข้ามการค้นย้อนกลับทั้งตาราง เพื่อให้เร็ว"""
        out = []

        def add(label, recs):
            for r in recs[:MAX_PER_RELATION]:
                out.append((label, r))

        # 1) ช่องที่ผูกเอกสาร (ไปข้างหน้า)
        for fname, field in record._fields.items():
            if field.type not in ('many2one', 'many2many', 'one2many') or fname in SKIP_FIELDS \
                    or field.comodel_name not in doc_models or getattr(field, 'inherited', False):
                continue
            try:
                with self.env.cr.savepoint():
                    add(self._field_label(record._name, fname), record[fname])
            except Exception as e:  # ช่องคำนวณบางตัวอาจพังกับข้อมูลเก่า ข้ามไป
                _logger.debug('npd_doc_trace: skip %s.%s: %s', record._name, fname, e)
        # 2) ช่องของเอกสารอื่นที่ชี้มาที่ใบนี้ (ย้อนกลับ)
        Finder = self.env['npd.doc.finder.line']
        for model_name in (doc_models if full else []):
            Model = self.env[model_name]
            for fname, field in Model._fields.items():
                if field.type != 'many2one' or not field.store or field.comodel_name != record._name \
                        or fname in SKIP_FIELDS or getattr(field, 'inherited', False):
                    continue
                if model_name == record._name and fname in ('id',):
                    continue
                try:
                    with self.env.cr.savepoint():
                        recs = Model.search([(fname, '=', record.id)], limit=MAX_PER_RELATION)
                        recs.mapped('display_name')
                except Exception:
                    continue
                add('%s (%s)' % (self._field_label(model_name, fname), self._model_label(model_name)), recs)
        # 3) การตัดชำระ
        moves = record if record._name == 'account.move' else (
            record['move_id'] if 'move_id' in record._fields and record._fields['move_id'].comodel_name == 'account.move'
            else self.env['account.move'])
        if moves:
            try:
                add('ตัดชำระกัน', self._reconciled_moves(moves))
            except Exception as e:
                _logger.debug('npd_doc_trace: reconcile %s', e)
        # 4) ผ่านบรรทัดรายการ
        for path, label in LINE_PATHS.get(record._name, []):
            try:
                with self.env.cr.savepoint():
                    add(label, record.mapped(path))
            except Exception:
                continue
        # 5) เลขเอกสารที่พิมพ์อ้างอิงไว้ (ไปข้างหน้า): ช่องข้อความของใบนี้มีเลขของใบอื่น
        tokens = set()
        for f in TEXT_FIELDS:
            if f in record._fields and record._fields[f].type == 'char' and record[f]:
                tokens |= {t for t in TOKEN_SPLIT.split(record[f]) if len(t) >= 4}
        own = self._numbers_of(record)
        tokens -= own
        if tokens:
            for line in Finder.search([('name', 'in', list(tokens))], limit=MAX_PER_RELATION):
                out.append(('อ้างอิงในช่องข้อความ', self.env[line.res_model].browse(line.res_id)))
        # 6) ใบอื่นที่พิมพ์เลขของใบนี้ไว้ (ย้อนกลับ)
        for number in (own if full else []):
            if len(number) < 5:
                continue
            for model_name in doc_models:
                Model = self.env[model_name]
                for f in TEXT_FIELDS:
                    field = Model._fields.get(f)
                    if not field or field.type != 'char' or not field.store:
                        continue
                    try:
                        with self.env.cr.savepoint():
                            recs = Model.search([(f, 'ilike', number)], limit=MAX_PER_RELATION)
                            recs = recs.filtered(lambda r: number in TOKEN_SPLIT.split(r[f] or ''))
                    except Exception:
                        continue
                    add('อ้างอิงเลขนี้ในช่อง %s' % self._field_label(model_name, f), recs)
        return out

    @api.model
    def _numbers_of(self, record):
        nums = set()
        for f in ('name', 'number'):
            if f in record._fields and record._fields[f].type == 'char' and record[f]:
                nums.add(record[f])
        if 'move_id' in record._fields and record._fields['move_id'].comodel_name == 'account.move' \
                and record._name == 'account.payment' and record.move_id.name:
            nums.add(record.move_id.name)
        return nums - {'/', 'New', 'ใหม่'}

    @api.model
    def _field_label(self, model_name, fname):
        if fname in FIELD_LABELS:
            return FIELD_LABELS[fname]
        cache = self.env.context.get('npd_trace_labels')
        key = (model_name, fname)
        if cache is not None and key in cache:
            return cache[key]
        f = self.env['ir.model.fields'].sudo().with_context(lang='th_TH')._get(model_name, fname)
        label = (f and f.field_description) or self.env[model_name]._fields[fname].string
        if cache is not None:
            cache[key] = label
        return label

    @api.model
    def _model_label(self, model_name):
        return self.env['ir.model'].sudo().with_context(lang='th_TH')._get(model_name).name or model_name

    @api.model
    def _info(self, record):
        Finder = self.env['npd.doc.finder.line']
        line = Finder.search([('res_model', '=', record._name), ('res_id', '=', record.id)], limit=1,
                             order='id')
        amount = 0.0
        for f in AMOUNT_FIELDS:
            if f in record._fields and record._fields[f].type == 'monetary':
                amount = record[f]
                break
        if not amount and record._name == 'account.move' and record.move_type == 'entry':
            amount = sum(record.line_ids.mapped('debit'))
        numbers = sorted(self._numbers_of(record))
        return {
            'finder_id': line.id,
            'display_number': ' / '.join(numbers) or record.display_name,
            'menu_label': line.menu_label or self._model_label(record._name),
            'date': line.date,
            'partner_id': line.partner_id.id,
            'state': line.state,
            'amount': amount,
            'res_model': record._name,
            'res_id': record.id,
        }

    @api.model
    def trace(self, record):
        """ชั้น 0 = ใบที่ค้น, ชั้น 1 = เชื่อมกับใบที่ค้น, ชั้น 2 = เชื่อมกับชั้น 1 (ไม่ซ้ำกับที่แสดงแล้ว)"""
        self = self.with_context(npd_trace_labels={})
        record = record.with_context(npd_trace_labels=self.env.context['npd_trace_labels'])
        doc_models = self._doc_models()
        root = self._normalize(record.sudo())
        root = self.env[root._name].browse(root.id)
        seen = {(root._name, root.id)}

        def children(rec, full):
            # หาความเชื่อมโยงด้วย sudo (บรรทัด/ใบกลางทางอาจอยู่สาขาอื่น) แล้วแสดงเฉพาะใบที่ผู้ใช้มีสิทธิเห็น
            res = []
            for label, target in self.sudo()._links(rec.sudo(), doc_models, full=full):
                target = self._normalize(target.sudo())
                target = self.env[target._name].browse(target.id)
                key = (target._name, target.id)
                if not target.id or key in seen:
                    continue
                if not target.has_access('read'):
                    continue
                seen.add(key)
                res.append((label, target))
            return res

        def info(rec):
            try:
                with self.env.cr.savepoint():
                    return self._info(rec)
            except Exception as e:
                _logger.warning('npd_doc_trace: อ่าน %s,%s ไม่ได้: %s', rec._name, rec.id, e)
                return None

        root_row = info(root)
        if not root_row:
            raise UserError(_('อ่านเอกสารนี้ไม่ได้ (อาจไม่มีสิทธิ หรือข้อมูลเสีย)'))
        result = [dict(root_row, level=0, relation='เอกสารที่ค้น')]
        for label, rec in children(root, True):
            if len(result) >= MAX_LINES:
                break
            row = info(rec)
            if not row:
                continue
            result.append(dict(row, level=1, relation=label))
            # ชั้น 2 ต่อท้ายใต้แม่ของมัน
            for label2, rec2 in children(rec, False)[:MAX_CHILDREN]:
                if len(result) >= MAX_LINES:
                    break
                row2 = info(rec2)
                if row2:
                    result.append(dict(row2, level=2, relation='└ %s' % label2))
        return result


class NpdDocTraceWizard(models.TransientModel):
    _name = 'npd.doc.trace.wizard'
    _description = 'ตรวจสอบเอกสารที่เชื่อมโยง'

    doc_id = fields.Many2one('npd.doc.finder.line', string='เลขที่เอกสาร')
    trail = fields.Char('เส้นทาง')
    summary = fields.Char('สรุป')
    line_ids = fields.One2many('npd.doc.trace.line', 'wizard_id', string='เอกสารที่เชื่อมโยง')

    def _compute_lines(self):
        self.ensure_one()
        doc = self.doc_id
        record = self.env[doc.res_model].browse(doc.res_id).exists()
        if not record:
            raise UserError(_('ไม่พบเอกสาร %s') % doc.name)
        rows = self.env['npd.doc.trace'].trace(record)
        n1 = len([r for r in rows if r['level'] == 1])
        n2 = len([r for r in rows if r['level'] == 2])
        self.write({
            'line_ids': [(5, 0, 0)] + [(0, 0, r) for r in rows],
            'summary': 'พบเอกสารที่เชื่อมโดยตรง %s ใบ และเชื่อมต่ออีกชั้น %s ใบ' % (n1, n2) if n1
                       else 'ไม่พบเอกสารที่เชื่อมโยงกับใบนี้',
        })

    @api.model
    def action_start(self, finder_id, trail=False):
        """เรียกจาก widget เมื่อเลือกเลขเอกสาร: สร้างผลตรวจเก็บไว้ แล้วเปิด popup ผล (ปุ่มในแถวต้องเป็นแถวที่บันทึกแล้วจึงกดได้)"""
        finder = self.env['npd.doc.finder.line'].browse(finder_id).exists()
        if not finder:
            raise UserError(_('ไม่พบเลขเอกสารนี้ หรือคุณไม่มีสิทธิเห็น'))
        wiz = self.create({'doc_id': finder.id, 'trail': trail or finder.name})
        wiz._compute_lines()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': wiz.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'name': _('ตรวจสอบเอกสารที่เชื่อมโยง'),
            'context': {'dialog_size': 'extra-large'},
        }


class NpdDocTraceLine(models.TransientModel):
    _name = 'npd.doc.trace.line'
    _description = 'เอกสารที่เชื่อมโยง'
    _order = 'id'

    wizard_id = fields.Many2one('npd.doc.trace.wizard', ondelete='cascade')
    level = fields.Integer('ชั้น')
    relation = fields.Char('เชื่อมกันทาง')
    finder_id = fields.Many2one('npd.doc.finder.line', string='เลขเอกสาร (ค้นหา)')
    display_number = fields.Char('เลขที่เอกสาร')
    menu_label = fields.Char('เมนู')
    date = fields.Date('วันที่')
    partner_id = fields.Many2one('res.partner', 'คู่ค้า')
    amount = fields.Float('ยอด', digits=(16, 2))
    state = fields.Char('สถานะ')
    res_model = fields.Char('Model')
    res_id = fields.Integer('Record ID')

    def action_open(self):
        self.ensure_one()
        if self.finder_id:
            action = self.finder_id.action_open()
            action.pop('npd_company_id', None)
            return action
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'views': [(False, 'form')], 'target': 'current', 'name': self.menu_label}

    def action_trace(self):
        self.ensure_one()
        if not self.finder_id:
            raise UserError(_('เอกสารนี้ไม่มีเลขในระบบค้นหา ตรวจต่อไม่ได้ กด เปิด เพื่อดูเอกสารแทน'))
        trail = '%s → %s' % (self.wizard_id.trail or self.wizard_id.doc_id.name,
                             (self.display_number or self.finder_id.name).split(' / ')[0])
        return self.env['npd.doc.trace.wizard'].action_start(self.finder_id.id, trail)
