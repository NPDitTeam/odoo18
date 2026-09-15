import logging
import re

from odoo import api, models

from .th_terms import TH_TERMS, norm

_logger = logging.getLogger(__name__)

# โมเดลที่อยู่ในหน้าจอบัญชี (ขึ้นต้นด้วย) + โมเดลที่ถูกเปิดจากหน้าจอบัญชี
SCOPE_PREFIXES = (
    'account.', 'withholding.', 'mis.report', 'npd.asset', 'advance.clear', 'cash.payment',
    'personal.income.tax', 'npd.commission', 'generate.commission', 'custom.payment',
    'refund.payment', 'wiz.account.asset', 'npd.head.office.branch',
)
SCOPE_MODELS = {
    'aged.partner.balance.report.wizard', 'general.ledger.report.wizard', 'journal.ledger.report.wizard',
    'open.items.report.wizard', 'trial.balance.report.wizard', 'vat.report.wizard', 'tax.report.wizard',
    'res.config.settings', 'res.company', 'res.partner', 'product.template', 'product.category',
    'payment.provider',
}
VIEW_TYPES = ['form', 'list', 'search', 'kanban', 'pivot', 'graph', 'calendar']
TAG_RE = re.compile(r'(<[^>]*>)')


class NpdThLabels(models.AbstractModel):
    _name = 'npd.th.labels'
    _description = 'เติมคำแปลภาษาไทยให้หน้าจอบัญชี'

    @api.model
    def _npd_scope_models(self):
        return sorted(
            name for name in self.env.registry
            if name in SCOPE_MODELS or name.startswith(SCOPE_PREFIXES)
        )

    @api.model
    def _npd_translate_text(self, en):
        """แปลข้อความ ถ้าเป็นข้อความผสมแท็ก เช่น <span class="oe_inline">To</span> แปลเฉพาะส่วนข้อความ"""
        th = TH_TERMS.get(norm(en))
        if th or '<' not in (en or ''):
            return th or False
        changed = False
        parts = TAG_RE.split(en)
        for i, part in enumerate(parts):
            if part.startswith('<') or not part.strip():
                continue
            th_part = TH_TERMS.get(norm(part))
            if th_part:
                parts[i] = part.replace(part.strip(), th_part)
                changed = True
        return ''.join(parts) if changed else False

    @api.model
    def _npd_untranslated(self, en, current):
        """คืนคำแปลไทยถ้าข้อความนี้ยังไม่มีคำแปล (ว่าง หรือยังเป็นคำเดียวกับภาษาอังกฤษ)"""
        if current and norm(current) != norm(en):
            return False
        return self._npd_translate_text(en)

    @api.model
    def _npd_fill_jsonb(self, table, column, from_where, params, lang):
        # ตาราง/คอลัมน์มาจากโค้ดนี้เท่านั้น ไม่ได้รับจากผู้ใช้
        cr = self.env.cr
        cr.execute(
            f"SELECT t.id, t.{column}->>'en_US', t.{column}->>%s FROM {table} t {from_where}",
            [lang] + list(params),
        )
        done = 0
        for rid, en, current in cr.fetchall():
            th = self._npd_untranslated(en, current)
            if th:
                cr.execute(
                    f"UPDATE {table} SET {column} = COALESCE({column}, '{{}}'::jsonb) || jsonb_build_object(%s, %s::text) WHERE id = %s",
                    [lang, th, rid],
                )
                done += 1
        return done

    @api.model
    def _npd_apply_th_labels(self, lang='th_TH'):
        if lang not in dict(self.env['res.lang'].get_installed()):
            _logger.info('npd_th_labels: ภาษา %s ไม่ได้เปิดใช้ ข้าม', lang)
            return {}
        env = self.sudo().env
        scope = self._npd_scope_models()
        res = {}

        # ชื่อฟิลด์ + ตัวเลือก (อ่านผ่าน get_field_string/get_field_selection)
        res['fields'] = self._npd_fill_jsonb(
            'ir_model_fields', 'field_description', 'WHERE t.model = ANY(%s)', [scope], lang)
        res['selections'] = self._npd_fill_jsonb(
            'ir_model_fields_selection', 'name',
            'JOIN ir_model_fields f ON f.id = t.field_id WHERE f.model = ANY(%s)', [scope], lang)

        # เมนูทุกแอป + action ของเมนูนั้น (ชื่อเมนูไม่มีปัญหาคำกำกวม)
        menus = env['ir.ui.menu'].with_context(active_test=False).search([])
        res['menus'] = self._npd_fill_jsonb('ir_ui_menu', 'name', 'WHERE t.id = ANY(%s)', [menus.ids], lang)
        action_ids = {}
        for menu in menus:
            if menu.action:
                action_ids.setdefault(menu.action._table, set()).add(menu.action.id)
        env.cr.execute('SELECT id FROM ir_act_window WHERE res_model = ANY(%s)', [scope])
        action_ids.setdefault('ir_act_window', set()).update(r[0] for r in env.cr.fetchall())
        env.cr.execute('SELECT id FROM ir_act_report_xml WHERE model = ANY(%s)', [scope])
        action_ids.setdefault('ir_act_report_xml', set()).update(r[0] for r in env.cr.fetchall())
        res['actions'] = sum(
            self._npd_fill_jsonb(table, 'name', 'WHERE t.id = ANY(%s)', [list(ids)], lang)
            for table, ids in action_ids.items() if ids
        )
        env.invalidate_all()

        # ข้อความในหน้าจอ (ปุ่ม แท็บ ตัวกรอง หัวข้อ) เก็บเป็นคำแปลรายคำของ arch_db
        View = env['ir.ui.view'].with_context(active_test=False)
        arch_field = View._fields['arch_db']
        views = View.search([('model', 'in', scope), ('type', 'in', VIEW_TYPES)])
        res['views'] = res['view_terms'] = 0
        for view in views:
            en = view.with_context(lang='en_US').arch_db
            if not en:
                continue
            current = view.with_context(lang=lang).arch_db
            todo = {}
            for term_en, trans in arch_field.get_translation_dictionary(en, {lang: current}).items():
                th = self._npd_untranslated(term_en, trans.get(lang))
                if th:
                    todo[term_en] = th
            if not todo:
                continue
            # การเขียน arch จะตรวจ view ซ้ำ ถ้า view เดิมมีปัญหาอยู่แล้วให้ข้ามเฉพาะ view นั้น
            try:
                with env.cr.savepoint():
                    view.update_field_translations('arch_db', {lang: todo})
            except Exception as err:
                _logger.warning('npd_th_labels: ข้าม view %s (%s): %s', view.id, view.xml_id, err)
                continue
            res['views'] += 1
            res['view_terms'] += len(todo)

        env.invalidate_all()
        self.env.registry.clear_all_caches()
        _logger.info('npd_th_labels: เติมคำแปลไทย %s', res)
        return res
