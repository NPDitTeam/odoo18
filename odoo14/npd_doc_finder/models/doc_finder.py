# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

# id ของแถว = res_id * ID_FACTOR + ลำดับแหล่งข้อมูล (ไม่ซ้ำกันข้ามตาราง และพอดี int4 ของ many2one)
ID_FACTOR = 256
# ลำดับแหล่งข้อมูลอัตโนมัติ (โมดูลใหม่) เริ่มที่เลขนี้
AUTO_IDX_START = 32

# เอกสารหลัก/ข้อมูลตั้งต้น ไม่ใช่เลขเอกสาร: ไม่ดึงอัตโนมัติ
AUTO_EXCLUDE = {
    'res.partner', 'res.users', 'res.company', 'res.partner.bank', 'product.template', 'product.product',
    'hr.employee', 'hr.department', 'hr.job', 'account.account', 'account.journal', 'account.analytic.account',
    'account.move.line', 'stock.move', 'stock.move.line', 'stock.location', 'stock.warehouse',
    'stock.production.lot', 'stock.lot', 'crm.lead', 'crm.team', 'mail.channel', 'discuss.channel',
    'calendar.event', 'project.project', 'project.task', 'note.note', 'utm.campaign', 'fleet.vehicle',
    'maintenance.equipment', 'res.branch', 'procurement.group', 'npd.doc.finder.line',
    'fetchmail.server', 'res.currency.rate.provider', 'dms.directory', 'dms.file', 'hr.announcement',
    'hr.contract', 'tier.correction', 'tier.definition', 'mail.mass_mailing', 'mailing.mailing',
    'fleet.vehicle.model', 'fleet.vehicle.model.brand', 'product.category', 'iap.account', 'uom.uom',
    'approval.type', 'partner.category', 'purchase.request.line', 'yalecom.call.log', 'npd.signature',
}

# kind -> (model, [xmlid ของเมนูที่ใช้เปิด เรียงตามลำดับที่ลอง])
KIND_ACTIONS = {
    'out_invoice': ('account.move', ['account.action_move_out_invoice_type']),
    'out_debit': ('account.move', ['account.action_move_out_invoice_type']),
    'out_refund': ('account.move', ['account.action_move_out_refund_type']),
    'in_invoice': ('account.move', ['account.action_move_in_invoice_type']),
    'in_debit': ('account.move', ['account.action_move_in_invoice_type']),
    'in_refund': ('account.move', ['account.action_move_in_refund_type']),
    'out_receipt': ('account.move', ['account.action_move_out_receipt_type']),
    'in_receipt': ('account.move', ['account.action_move_in_receipt_type']),
    'entry': ('account.move', ['account.action_move_journal_line']),
    'pay_in': ('account.payment', ['account.action_account_payments']),
    'pay_out': ('account.payment', ['account.action_account_payments_payable']),
    'voucher_sale': ('account.voucher', ['account_voucher_npd.action_sale_receipt']),
    'voucher_deposit': ('account.voucher', ['account_voucher_npd.action_purchase_receipt']),
    'voucher_purchase': ('account.voucher', ['account_voucher_npd.action_purchase_receipt_general']),
    'quotation': ('sale.order', ['sale.action_quotations_with_onboarding', 'sale.action_quotations']),
    'sale_order': ('sale.order', ['sale.action_orders']),
    'rfq': ('purchase.order', ['purchase.purchase_rfq']),
    'purchase_order': ('purchase.order', ['purchase.purchase_form_action']),
    'picking': ('stock.picking', ['stock.action_picking_tree_all']),
    'advance_request': ('account.advance.request', ['account_advance.action_account_advance_request']),
    'advance': ('account.advance', ['account_advance.action_account_advance']),
    'advance_clear': ('account.advance.clear', ['account_advance.action_account_advance_clear']),
    'wht_cert': ('withholding.tax.cert', ['l10n_th_account_tax.action_withholding_tax_cert_menu']),
    'refund_payment': ('refund.payment', ['custom_refund_payment.action_refund_payment_form']),
    'cash_payment': ('cash.payment', ['custom_cash_payment.action_cash_payment_form']),
    'scrap': ('stock.scrap', ['stock.action_stock_scrap']),
    'purchase_request': ('purchase.request', ['purchase_request.purchase_request_form_action']),
}

# ชื่อสมุดรายวัน/ประเภทการโอน เป็น jsonb (แปลภาษา) ใน o18
JNAME = "COALESCE(j.name->>'th_TH', j.name->>'en_US', '')"
TNAME = "COALESCE(t.name->>'th_TH', t.name->>'en_US', '')"

MOVE_LABEL = """CASE m.move_type
    WHEN 'out_invoice' THEN CASE WHEN {debit} THEN 'ใบเพิ่มหนี้ลูกค้า' ELSE 'ใบแจ้งหนี้ลูกค้า' END
    WHEN 'out_refund' THEN 'ใบลดหนี้ลูกค้า'
    WHEN 'in_invoice' THEN CASE WHEN {debit} THEN 'ใบเพิ่มหนี้ผู้ขาย' ELSE 'บิลผู้ขาย' END
    WHEN 'in_refund' THEN 'ใบลดหนี้ผู้ขาย'
    WHEN 'out_receipt' THEN 'ใบเสร็จขาย'
    WHEN 'in_receipt' THEN 'ใบเสร็จซื้อ'
    ELSE 'สมุดรายวัน: ' || """ + JNAME + """ END"""

MOVE_KIND = """CASE WHEN m.move_type IN ('out_invoice', 'in_invoice') AND {debit}
    THEN replace(m.move_type, 'invoice', 'debit') ELSE m.move_type END"""

# แหล่งข้อมูล: (ลำดับ, ตาราง, คอลัมน์ที่ต้องมี, SQL) — ลำดับห้ามเปลี่ยนเพราะเป็นส่วนหนึ่งของ id
SOURCES = [
    (0, 'account_move', ['name', 'move_type', 'date', 'partner_id', 'company_id', 'state', 'journal_id'], """
        SELECT m.id, 'account.move', {kind}, m.name,
               {label}, m.date, m.partner_id, m.company_id, m.state::varchar
        FROM account_move m LEFT JOIN account_journal j ON j.id = m.journal_id
        WHERE m.name IS NOT NULL AND m.name <> '/' {no_payment}"""),
    (1, 'account_payment', ['name', 'payment_type', 'date', 'partner_id', 'company_id', 'state'], """
        SELECT p.id, 'account.payment', CASE WHEN p.payment_type = 'inbound' THEN 'pay_in' ELSE 'pay_out' END,
               p.name, CASE WHEN p.payment_type = 'inbound' THEN 'รับชำระเงิน' ELSE 'จ่ายชำระเงิน' END,
               p.date, p.partner_id, p.company_id, p.state::varchar
        FROM account_payment p
        WHERE p.name IS NOT NULL AND p.name NOT IN ('/', '')"""),
    (2, 'account_voucher', ['number', 'voucher_type', 'date', 'partner_id', 'company_id', 'state'], """
        SELECT v.id, 'account.voucher',
               CASE WHEN v.voucher_type = 'sale' THEN 'voucher_sale'
                    WHEN {check_show} THEN 'voucher_deposit' ELSE 'voucher_purchase' END,
               COALESCE(NULLIF(v.number, ''), v.name),
               CASE WHEN v.voucher_type = 'sale' THEN 'Sale Receipt'
                    WHEN {check_show} THEN 'คืนเงินประกันค่าเช่า' ELSE 'การรับ' END,
               v.date, v.partner_id, v.company_id, v.state::varchar
        FROM account_voucher v
        WHERE COALESCE(NULLIF(v.number, ''), v.name) IS NOT NULL
          AND COALESCE(NULLIF(v.number, ''), v.name) NOT IN ('/', '')"""),
    (3, 'sale_order', ['name', 'date_order', 'partner_id', 'company_id', 'state'], """
        SELECT s.id, 'sale.order',
               CASE WHEN s.state IN ('draft', 'sent', 'cancel') THEN 'quotation' ELSE 'sale_order' END,
               s.name, CASE WHEN s.state IN ('draft', 'sent', 'cancel') THEN 'ใบเสนอราคา' ELSE 'ใบสั่งขาย' END,
               s.date_order::date, s.partner_id, s.company_id, s.state::varchar
        FROM sale_order s"""),
    (4, 'purchase_order', ['name', 'date_order', 'partner_id', 'company_id', 'state'], """
        SELECT o.id, 'purchase.order',
               CASE WHEN o.state IN ('draft', 'sent', 'to approve') THEN 'rfq' ELSE 'purchase_order' END,
               o.name, CASE WHEN o.state IN ('draft', 'sent', 'to approve') THEN 'ใบขอใบเสนอราคา (RFQ)'
                            ELSE 'ใบสั่งซื้อ' END,
               o.date_order::date, o.partner_id, o.company_id, o.state::varchar
        FROM purchase_order o"""),
    (5, 'stock_picking', ['name', 'scheduled_date', 'partner_id', 'company_id', 'state', 'picking_type_id'], """
        SELECT sp.id, 'stock.picking', 'picking', sp.name, 'การโอนสินค้า: ' || """ + TNAME + """,
               COALESCE(sp.date_done, sp.scheduled_date)::date, sp.partner_id, sp.company_id, sp.state::varchar
        FROM stock_picking sp LEFT JOIN stock_picking_type t ON t.id = sp.picking_type_id
        WHERE sp.name IS NOT NULL AND sp.name <> '/'"""),
    (6, 'account_advance_request', ['name', 'company_id', 'state'], """
        SELECT a.id, 'account.advance.request', 'advance_request', a.name, 'ขอเบิกเงินทดรอง',
               {date}, NULL::int, a.company_id, a.state::varchar
        FROM account_advance_request a WHERE a.name IS NOT NULL AND a.name <> '/'"""),
    (7, 'account_advance', ['name', 'company_id', 'state'], """
        SELECT a.id, 'account.advance', 'advance', a.name, 'เงินทดรอง',
               {date}, NULL::int, a.company_id, a.state::varchar
        FROM account_advance a WHERE a.name IS NOT NULL AND a.name <> '/'"""),
    (8, 'account_advance_clear', ['name', 'company_id', 'state'], """
        SELECT a.id, 'account.advance.clear', 'advance_clear', a.name, 'เคลียร์เงินทดรอง',
               {date}, NULL::int, a.company_id, a.state::varchar
        FROM account_advance_clear a WHERE a.name IS NOT NULL AND a.name <> '/'"""),
    (9, 'withholding_tax_cert', ['name', 'date', 'company_id', 'state'], """
        SELECT w.id, 'withholding.tax.cert', 'wht_cert', {wht_name}, 'หนังสือรับรองหัก ณ ที่จ่าย',
               w.date, {wht_partner}, w.company_id, w.state::varchar
        FROM withholding_tax_cert w WHERE {wht_name} IS NOT NULL AND {wht_name} NOT IN ('/', '')"""),
    (10, 'refund_payment', ['name', 'state'], """
        SELECT r.id, 'refund.payment', 'refund_payment', r.name, 'โอนคืนเงินลูกค้า',
               {date}, {partner}, {company}, r.state::varchar
        FROM refund_payment r WHERE r.name IS NOT NULL AND r.name <> '/'"""),
    (11, 'cash_payment', ['name', 'state'], """
        SELECT c.id, 'cash.payment', 'cash_payment', c.name, 'ชำระเงินสด',
               {date}, {partner}, {company}, c.state::varchar
        FROM cash_payment c WHERE c.name IS NOT NULL AND c.name <> '/'"""),
    (12, 'stock_scrap', ['name', 'company_id', 'state'], """
        SELECT x.id, 'stock.scrap', 'scrap', x.name, 'ตัดสินค้าเสีย',
               {date}, NULL::int, x.company_id, x.state::varchar
        FROM stock_scrap x WHERE x.name IS NOT NULL AND x.name NOT IN ('/', 'New', 'ใหม่')"""),
    (13, 'purchase_request', ['name', 'company_id', 'state'], """
        SELECT q.id, 'purchase.request', 'purchase_request', q.name, 'ใบขอซื้อ (PR)',
               {date}, NULL::int, q.company_id, q.state::varchar
        FROM purchase_request q WHERE q.name IS NOT NULL AND q.name <> '/'"""),
]

# วันที่ของตารางที่ชื่อคอลัมน์ไม่เหมือนกัน: ลองตามลำดับ
DATE_COLUMNS = ['date', 'request_date', 'date_request', 'date_advance', 'date_clear', 'date_start',
                'date_done', 'payment_date']


class NpdDocFinderLine(models.Model):
    _name = 'npd.doc.finder.line'
    _description = 'เลขเอกสาร (ค้นหา)'
    _auto = False
    _order = 'date desc, id desc'
    _rec_name = 'name'
    _rec_names_search = ['name']

    name = fields.Char('เลขที่เอกสาร', readonly=True)
    menu_label = fields.Char('เมนู', readonly=True)
    kind = fields.Char('ประเภท', readonly=True)
    res_model = fields.Char('Model', readonly=True)
    res_id = fields.Integer('Record ID', readonly=True)
    date = fields.Date('วันที่', readonly=True)
    partner_id = fields.Many2one('res.partner', 'คู่ค้า', readonly=True)
    company_id = fields.Many2one('res.company', 'บริษัท', readonly=True)
    state = fields.Char('สถานะ', readonly=True)

    def _table_columns(self, table):
        self.env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
        return {r[0] for r in self.env.cr.fetchall()}

    def _source_sql(self, idx, table, required, sql):
        cols = self._table_columns(table)
        if not cols or not set(required) <= cols:
            return None
        alias = sql.split('FROM %s ' % table, 1)[1].split()[0]
        date_col = next((c for c in DATE_COLUMNS if c in cols), None)
        subst = {
            'date': '%s.%s::date' % (alias, date_col) if date_col else 'NULL::date',
            'partner': '%s.partner_id' % alias if 'partner_id' in cols else 'NULL::int',
            'company': '%s.company_id' % alias if 'company_id' in cols else 'NULL::int',
            'check_show': 'COALESCE(v.check_show, false)' if 'check_show' in cols else 'false',
            'debit': 'm.debit_origin_id IS NOT NULL' if 'debit_origin_id' in cols else 'false',
            'no_payment': 'AND m.origin_payment_id IS NULL' if 'origin_payment_id' in cols else '',
            'wht_name': "COALESCE(NULLIF(w.number, ''), w.name)" if 'number' in cols else 'w.name',
            'wht_partner': next(('w.%s' % c for c in ('partner_id', 'supplier_partner_id') if c in cols), 'NULL::int'),
        }
        subst['label'] = MOVE_LABEL.format(**subst)
        subst['kind'] = MOVE_KIND.format(**subst)
        body = sql.format(**subst)
        return """SELECT (src.res_id::bigint * %d + %d) AS id, src.*
                  FROM (%s) src(res_id, res_model, kind, name, menu_label, date, partner_id, company_id, state)
               """ % (ID_FACTOR, idx, body)

    def _menu_actions(self):
        """res_model -> (act_window id, ชื่อเมนู) จากเมนูที่เปิดหน้ารายการของ model นั้น (เมนูแรกที่เจอ)"""
        Menu = self.env['ir.ui.menu'].sudo().with_context(**{'ir.ui.menu.full_list': True, 'lang': 'th_TH'})
        res = {}
        for menu in Menu.search([('action', '!=', False)], order='id'):
            try:
                act = menu.action and menu.action.exists()
            except Exception:  # เมนูชี้ไป action ที่ถูกลบ
                continue
            if act and act._name == 'ir.actions.act_window' and act.res_model and act.res_model not in res \
                    and 'form' in (act.view_mode or ''):
                res[act.res_model] = (act.id, menu.name)
        return res

    def _auto_sources(self, fixed_models):
        """เอกสารจากโมดูลอื่น/โมดูลใหม่ที่มีเลขรัน: มีช่อง name, มีประวัติ (chatter) และมีเมนูของตัวเอง
        กรองแถวให้เหลือค่าที่เป็นเลขเอกสาร (มีตัวเลข ไม่มีช่องว่าง) ตัดชื่อสินค้า/ชื่อคนออก"""
        menus = self._menu_actions()
        found = []
        for model_name in sorted(self.env.registry.models):
            if model_name in fixed_models or model_name in AUTO_EXCLUDE or model_name not in menus:
                continue
            Model = self.env[model_name]
            name_field = Model._fields.get('name')
            if Model._transient or Model._abstract or not Model._auto or 'message_ids' not in Model._fields \
                    or not name_field or name_field.type != 'char' or not name_field.store \
                    or getattr(name_field, 'translate', False):
                continue
            cols = self._table_columns(Model._table)
            if 'name' not in cols:
                continue
            found.append((model_name, Model._table, cols) + menus[model_name])
        parts, auto = [], {}
        for i, (model_name, table, cols, act_id, label) in enumerate(found[:256 - AUTO_IDX_START]):
            date_col = next((c for c in DATE_COLUMNS + ['date_order', 'scheduled_date', 'create_date'] if c in cols), None)
            partner = 'x.partner_id' if 'partner_id' in cols and \
                self.env[model_name]._fields.get('partner_id', fields.Char()).comodel_name == 'res.partner' else 'NULL::int'
            body = """SELECT x.id, %s, %s, x.name, %s, %s, %s, %s, %s
                      FROM "%s" x
                      WHERE x.name ~ '[0-9]' AND x.name !~ '\\s' AND x.name NOT IN ('/', 'New', 'ใหม่')""" % (
                self._quote(model_name), self._quote('auto:%d' % act_id), self._quote(label),
                'x.%s::date' % date_col if date_col else 'NULL::date', partner,
                'x.company_id' if 'company_id' in cols else 'NULL::int',
                'x.state::varchar' if 'state' in cols else 'NULL::varchar', table)
            parts.append("""SELECT (src.res_id::bigint * %d + %d) AS id, src.*
                  FROM (%s) src(res_id, res_model, kind, name, menu_label, date, partner_id, company_id, state)
               """ % (ID_FACTOR, AUTO_IDX_START + i, body))
            auto[model_name] = act_id
        return parts, auto

    def _quote(self, value):
        return self.env.cr.mogrify('%s', (value,)).decode()

    def _build_view(self):
        parts = []
        for idx, table, required, sql in SOURCES:
            part = self._source_sql(idx, table, required, sql)
            if part:
                parts.append(part)
            else:
                _logger.info('npd_doc_finder: ข้ามตาราง %s (ไม่มีในฐานนี้)', table)
        fixed_models = {m for m, _x in KIND_ACTIONS.values()}
        auto_parts, auto = self._auto_sources(fixed_models)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT u.id, u.res_id, u.res_model, u.kind, u.name, u.menu_label, u.date,
                       u.partner_id, u.company_id, u.state
                FROM (%s) u
            )""" % (self._table, '\nUNION ALL\n'.join(parts + auto_parts)))
        self.env['ir.config_parameter'].sudo().set_param('npd_doc_finder.auto_models', json.dumps(auto))
        _logger.info('npd_doc_finder: เอกสารอัตโนมัติ %s ประเภท: %s', len(auto), ', '.join(sorted(auto)))
        return auto

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self._build_view()

    @api.model
    def _cron_refresh_view(self):
        # รายวัน: เพิ่มประเภทเอกสารจากโมดูลที่ติดตั้งใหม่ โดยไม่ต้องอัปเดตโมดูลนี้
        self._build_view()

    @api.model
    def _auto_models(self):
        try:
            return json.loads(self.env['ir.config_parameter'].sudo().get_param('npd_doc_finder.auto_models') or '{}')
        except ValueError:
            return {}

    @api.depends('name', 'menu_label', 'partner_id')
    def _compute_display_name(self):
        for rec in self:
            label = '%s  —  %s' % (rec.name or '', rec.menu_label or '')
            if rec.partner_id:
                label += '  (%s)' % rec.partner_id.display_name
            rec.display_name = label

    @api.model
    def _readable_models(self):
        models_ = {m for m, _x in KIND_ACTIONS.values()} | set(self._auto_models())
        Access = self.env['ir.model.access']
        return sorted(m for m in models_ if m in self.env and Access.check(m, 'read', raise_exception=False))

    def _apply_ir_rules(self, query, mode='read'):
        """ให้เหลือเฉพาะเอกสารที่ผู้ใช้เปิดได้จริง: สิทธิระดับเมนู + กฎของเอกสารนั้น (สาขา/บริษัท/ของตัวเอง)
        บริษัทนับทุกบริษัทที่ผู้ใช้มีสิทธิ เพราะ widget ติ๊กบริษัทเพิ่มให้ก่อนเปิด"""
        super()._apply_ir_rules(query, mode)
        if self.env.su:
            return
        user = self.env.user
        Rule = self.env['ir.rule'].with_context(allowed_company_ids=user.company_ids.ids)
        clauses = []
        for model in self._readable_models():
            clause = SQL('%s = %s', SQL.identifier(self._table, 'res_model'), model)
            rule_domain = Rule._compute_domain(model, 'read')
            if rule_domain:
                Model = self.env[model].sudo().with_context(active_test=False)
                sub = Model._search(rule_domain)
                clause = SQL('(%s AND %s IN %s)', clause, SQL.identifier(self._table, 'res_id'), sub.subselect())
            clauses.append(clause)
        query.add_where(SQL('(%s)', SQL(' OR ').join(clauses)) if clauses else SQL('FALSE'))

    def _get_action(self):
        self.ensure_one()
        model, xmlids = KIND_ACTIONS.get(self.kind, (self.res_model, []))
        model = model or self.res_model
        auto_act = int(self.kind.split(':')[1]) if (self.kind or '').startswith('auto:') else False
        if model not in self.env:
            raise UserError(_('ไม่พบประเภทเอกสาร %s ในฐานนี้') % model)
        target = self.env[model].sudo().browse(self.res_id).exists()
        if not target:
            raise UserError(_('ไม่พบเอกสาร %s (อาจถูกลบไปแล้ว)') % self.name)
        try:
            # ตรวจกฎตามบริษัทที่ผู้ใช้มีสิทธิทั้งหมด (widget ติ๊กบริษัทให้เอง) เหลือแค่กฎอื่น เช่น สาขา
            target.with_user(self.env.user).with_context(
                allowed_company_ids=self.env.user.company_ids.ids).check_access('read')
        except AccessError:
            raise UserError(_('คุณไม่มีสิทธิเปิดเอกสาร %s (%s)\nอาจเป็นเอกสารของสาขา/บริษัทที่คุณไม่ได้รับสิทธิ '
                              'ติดต่อผู้ดูแลระบบหากต้องการเข้าถึง') % (self.name, self.menu_label))
        action = None
        if auto_act:
            act = self.env['ir.actions.act_window'].sudo().browse(auto_act).exists()
            if act and act.res_model == model:
                action = act.read()[0]
        for xmlid in ([] if action else xmlids):
            act = self.env.ref(xmlid, raise_if_not_found=False)
            if act and act._name == 'ir.actions.act_window' and act.res_model == model:
                action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
                break
        form_view = False
        if action:
            form_view = next((v for v, m in (action.get('views') or []) if m == 'form'), False)
        else:
            action = {'type': 'ir.actions.act_window', 'res_model': model, 'name': self.menu_label}
        action.update({
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(form_view, 'form')],
            'target': 'current',
            # widget ใช้ติ๊กบริษัทให้ก่อนเปิด ถ้าเอกสารอยู่บริษัทที่ยังไม่ได้ติ๊กใช้งาน
            'npd_company_id': self.company_id.id or False,
        })
        action.pop('domain', None)
        action.pop('search_view_id', None)
        return action

    def action_open(self):
        return self._get_action()


class NpdDocFinderWizard(models.TransientModel):
    _name = 'npd.doc.finder.wizard'
    _description = 'ค้นหาเลขเอกสาร'

    doc_id = fields.Many2one('npd.doc.finder.line', string='เลขที่เอกสาร')
