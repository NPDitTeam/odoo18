# -*- coding: utf-8 -*-
"""ตรวจสอบค่าใช้จ่าย -- ให้ AI ค้นข้อมูลเอกสารค่าใช้จ่ายแล้วตอบพนักงานบัญชี

แนวคิด: พนักงานบัญชีถามเป็นภาษาคนได้เลย ("บิลผู้ขายเดือนนี้ของสาขาสำนักงานใหญ่
มีกี่ใบ ยอดเท่าไร", "ใบไหนยังค้างจ่ายเกิน 30 วัน") ระบบจะ
  1. ส่ง "รายชื่อฟิลด์ทั้งหมดของโมเดลนั้น" (อ่านสดจาก _fields ทุกครั้ง) ไปให้ AI
     -> มีฟิลด์ใหม่เพิ่มมาเมื่อไร AI เห็นเองทันที ไม่ต้องแก้โค้ด
  2. ให้ AI แปลงคำถามเป็น "แผนการค้นหา" (JSON: model / domain / fields / group_by ...)
  3. ตรวจแผนก่อนรัน (โมเดลต้องอยู่ในรายการที่อนุญาต ฟิลด์ต้องมีจริง ตัวดำเนินการ
     ต้องอยู่ในรายการที่อนุญาต จำกัดจำนวนแถว)
  4. รันแบบ "อ่านอย่างเดียว" ด้วย sudo() แล้วสรุปเป็นตารางในแชท

ทำไมต้อง sudo(): ผู้ใช้สั่งว่าให้สิทธิ AI เต็มที่ เพราะบัญชีต้องตามข้ามสาขา/
ข้ามบริษัทได้ ถ้ากรองตามสิทธิ์ผู้ใช้ ตัวเลขที่ตอบจะไม่ตรงกับที่บัญชีต้องการ
ความปลอดภัยอยู่ที่ "อ่านอย่างเดียว" — ไม่มีเส้นทางไหนในไฟล์นี้ที่เขียนข้อมูลเอกสาร

หัวข้อนี้ใช้ AI เป็นหลัก ถ้าไม่ได้ตั้งค่า Gemini API key จะบอกให้ไปตั้งค่าก่อน
(หัวข้ออื่นมีทางสำรองเป็น regex แต่หัวข้อนี้ทำแบบนั้นไม่ได้)
"""
import io
import json
import logging
from datetime import date, datetime

from odoo import api, models
from odoo.tools.misc import html_escape

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - เครื่องที่ไม่มีไลบรารี
    xlsxwriter = None

_logger = logging.getLogger(__name__)

# จำนวนแถวสูงสุดที่ยอมให้ดึง/แสดง (กันคำถามกว้าง ๆ ลากทั้งตารางมาแสดงในแชท)
MAX_LIMIT = 50
MAX_GROUPS = 30
# ไฟล์ Excel ไม่ได้อ่านในแชท จึงใส่ได้มากกว่าที่แสดงบนจอ
MAX_EXCEL_ROWS = 5000

# คำที่แปลว่า "ขอเป็นไฟล์ Excel" (ตรวจเองด้วย keyword จะได้ไม่ต้องเสียรอบเรียก AI)
EXCEL_WORDS = ('excel', 'xlsx', 'เอ็กเซล', 'เอกเซล', 'ไฟล์แนบ', 'ออกไฟล์',
               'ส่งไฟล์', 'ขอไฟล์', 'เป็นไฟล์', 'export', 'ดาวน์โหลด', 'โหลดไฟล์')
# ความลึกสูงสุดของ field path ใน domain เช่น partner_id.country_id.code = 3
MAX_PATH_DEPTH = 3

# ตัวดำเนินการที่อนุญาตใน domain (อ่านอย่างเดียวอยู่แล้ว แต่กันรูปแบบแปลก ๆ)
ALLOWED_OPERATORS = {
    '=', '!=', '>', '>=', '<', '<=', 'in', 'not in',
    'like', 'not like', 'ilike', 'not ilike', 'child_of', '=like', '=ilike',
}

# โมเดลที่ยอมให้ถาม (ตั้งทับได้ที่ System Parameter ด้านล่าง เผื่อเพิ่มเมนูใหม่
# โดยไม่ต้องแก้โค้ด — รูปแบบเดียวกับ dict นี้)
EXPENSE_MODELS_PARAM = 'npd_ai_it_assistant.expense_models'


class NpdAiItExpense(models.AbstractModel):
    _name = 'npd.ai.it.expense'
    _description = 'ตัวช่วย AI-IT : ตรวจสอบค่าใช้จ่าย (ค้นข้อมูลด้วย AI)'

    # ------------------------------------------------------------------
    # รายการเมนูค่าใช้จ่ายที่ตอบได้
    # ------------------------------------------------------------------
    @api.model
    def _default_models(self):
        """เมนูค่าใช้จ่าย 3 ตัวตามที่ผู้ใช้ระบุ

        key   = ชื่อโมเดล
        label = ชื่อที่พนักงานเรียก
        domain= เงื่อนไขพื้นฐาน กันไม่ให้ปนกับเอกสารประเภทอื่นในโมเดลเดียวกัน
        date/amount/name = ฟิลด์หลักที่ใช้สรุปยอดและจัดเรียงเวลาไม่ได้ระบุ
        """
        return {
            # 1) บิลผู้ขาย — เมนู บัญชี > ผู้ขาย > บิลผู้ขาย
            'account.move': {
                'label': 'บิลผู้ขาย',
                'aliases': ['บิลผู้ขาย', 'ใบแจ้งหนี้ผู้ขาย', 'vendor bill', 'บิลซื้อ', 'ใบลดหนี้ผู้ขาย'],
                'domain': [('move_type', 'in', ('in_invoice', 'in_refund'))],
                'date_field': 'invoice_date',
                'amount_field': 'amount_total',
                'name_field': 'name',
                'default_fields': ['name', 'partner_id', 'invoice_date', 'invoice_date_due',
                                   'amount_total', 'amount_residual', 'payment_state', 'state'],
            },
            # 2) Avance Clear — เคลียร์เงินทดรอง (โมดูล account_advance)
            'account.advance.clear': {
                'label': 'Avance Clear (เคลียร์เงินทดรอง)',
                'aliases': ['avance clear', 'advance clear', 'เคลียร์เงินทดรอง', 'เงินทดรอง',
                            'เคลียร์แอดวานซ์', 'ใบเคลียร์'],
                'domain': [],
                'date_field': 'doc_date',
                'amount_field': 'amount',
                'name_field': 'name',
                'default_fields': ['name', 'employee_id', 'doc_date', 'advance_id', 'amount',
                                   'clear_amount', 'wht_amount', 'branch_id', 'state'],
            },
            # 3) การรับ — ใบสำคัญจ่ายฝั่งซื้อ (account.voucher) ตามเมนู "การรับ"
            #    เงื่อนไขเดียวกับเมนูจริง: voucher_type=purchase + สมุดรายวันเจ้าหนี้
            #    และไม่ใช่ใบคืนเงินประกันค่าเช่า (check_type_show_selection = true)
            'account.voucher': {
                'label': 'การรับ (ใบสำคัญจ่ายฝั่งซื้อ)',
                'aliases': ['การรับ', 'ใบสำคัญจ่าย', 'purchase receipt', 'voucher', 'ใบรับ'],
                'domain': [('voucher_type', '=', 'purchase'),
                           ('journal_id.type', '=', 'payable'),
                           '|', ('check_type_show_selection', '=', False),
                           ('check_type_show_selection', '!=', 'true')],
                'date_field': 'date',
                'amount_field': 'amount',
                'name_field': 'number',
                'default_fields': ['number', 'partner_id', 'date', 'account_date', 'amount',
                                   'tax_amount', 'wht_amount', 'branch_id', 'state'],
            },
        }

    @api.model
    def _menu_labels_text(self):
        """ชื่อเมนูที่ตอบได้ ใช้ในข้อความแนะนำ/ข้อความเมื่อตอบไม่ได้"""
        return ' · '.join(conf.get('label') or name
                          for name, conf in self._expense_models().items())

    @api.model
    def _expense_models(self):
        """รายการโมเดลที่ตอบได้ (ค่าเริ่มต้น + ที่ตั้งทับไว้ที่ System Parameter)

        เพิ่มเมนูใหม่ได้โดยไม่ต้องแก้โค้ด: ตั้ง System Parameter
        npd_ai_it_assistant.expense_models เป็น JSON หน้าตาเดียวกับ _default_models
        โมเดลไหนไม่มีในฐานนี้จะถูกข้ามให้เอง (แต่ละบริษัทติดตั้งโมดูลไม่เท่ากัน)
        """
        models_conf = dict(self._default_models())
        raw = self.env['ir.config_parameter'].sudo().get_param(EXPENSE_MODELS_PARAM)
        if raw:
            try:
                extra = json.loads(raw)
                if isinstance(extra, dict):
                    models_conf.update(extra)
            except (ValueError, TypeError):
                _logger.warning('ตัวช่วย AI-IT: อ่าน %s ไม่ได้ (ต้องเป็น JSON)', EXPENSE_MODELS_PARAM)
        available = {}
        for name, conf in models_conf.items():
            if name in self.env:
                available[name] = conf
        return available

    # ------------------------------------------------------------------
    # โครงสร้างฟิลด์ (อ่านสดทุกครั้ง -> มีฟิลด์ใหม่ AI เห็นเอง)
    # ------------------------------------------------------------------
    @api.model
    def _field_info(self, model_name):
        """ฟิลด์ที่ค้นหา/อ่านได้ของโมเดลนั้น {ชื่อฟิลด์: {...}}

        เอาเฉพาะฟิลด์ที่เก็บในฐานข้อมูล (หรือ related ที่ค้นหาได้) เพราะฟิลด์
        คำนวณสดที่ไม่มี store จะใส่ใน domain ไม่ได้ ส่วนชนิดที่เอาไปแสดงในแชท
        ไม่ได้ (binary) ตัดทิ้ง
        """
        info = {}
        model = self.env[model_name].sudo()
        for name, field in model._fields.items():
            if field.type in ('binary', 'image'):
                continue
            searchable = bool(field.store) or bool(getattr(field, 'search', None))
            entry = {
                'name': name,
                'type': field.type,
                'string': field.string or name,
                'searchable': searchable,
                'relation': getattr(field, 'comodel_name', '') or '',
            }
            if field.type in ('selection', 'selection_add'):
                try:
                    selection = field.selection
                    if callable(selection):
                        selection = selection(model)
                    entry['selection'] = [str(key) for key, _label in (selection or [])]
                except Exception:  # noqa: BLE001 - ฟิลด์แปลก ๆ ไม่ควรทำให้ทั้งหัวข้อพัง
                    entry['selection'] = []
            info[name] = entry
        return info

    @api.model
    def _schema_text(self, model_name, conf):
        """คำอธิบายฟิลด์แบบย่อสำหรับใส่ใน prompt ของ AI"""
        info = self._field_info(model_name)
        lines = []
        for name in sorted(info):
            entry = info[name]
            if not entry['searchable']:
                continue
            part = '%s|%s|%s' % (entry['name'], entry['type'], entry['string'])
            if entry['relation']:
                part += '|->%s' % entry['relation']
            if entry.get('selection'):
                part += '|ค่า:%s' % ','.join(entry['selection'][:12])
            lines.append(part)
        scope = conf.get('domain')
        scope_text = ('\nขอบเขตที่ระบบบังคับไว้เสมอ (ห้ามใช้ตอบเรื่องอื่น): %s'
                      % json.dumps(scope, ensure_ascii=False, default=str)) if scope else ''
        return '%s (%s)%s\nฟิลด์: \n%s' % (model_name, conf.get('label') or model_name,
                                            scope_text, '\n'.join(lines))

    # ------------------------------------------------------------------
    # ให้ AI แปลงคำถาม -> แผนการค้นหา
    # ------------------------------------------------------------------
    @api.model
    def build_plan(self, question, history=None):
        """คืน (plan, error_text)"""
        conf_by_model = self._expense_models()
        if not conf_by_model:
            return None, 'ยังไม่ได้ตั้งค่าเมนูค่าใช้จ่ายที่ให้ค้นหา กรุณาแจ้งฝ่าย IT'
        Gemini = self.env['npd.ai.it.gemini']
        if not Gemini.is_available():
            return None, ('หัวข้อนี้ต้องใช้ AI ช่วยอ่านคำถาม แต่ยังไม่ได้ตั้งค่า AI Key '
                          'กรุณาแจ้งฝ่าย IT')

        today = date.today()
        schema_parts = [self._schema_text(name, conf) for name, conf in conf_by_model.items()]
        history_text = ''
        if history:
            history_text = ('\nคำถามก่อนหน้าและแผนที่ใช้ (ใช้ต่อยอดได้ถ้าคำถามใหม่พูดต่อเนื่อง):\n%s\n'
                            % json.dumps(history, ensure_ascii=False)[:1500])

        prompt = (
            'คุณเป็นผู้ช่วยฝ่ายบัญชีของบริษัทให้เช่าอุปกรณ์ก่อสร้าง ทำหน้าที่แปลง "คำถามภาษาไทย" '
            'ให้เป็นคำสั่งค้นข้อมูลของ Odoo 14 (อ่านอย่างเดียว)\n'
            'วันนี้คือ %s (ค.ศ.) ปี พ.ศ. คือ %s\n'
            'เลือกโมเดลได้เฉพาะในรายการนี้เท่านั้น:\n%s\n'
            '%s'
            'คำถามของพนักงานบัญชี:\n"""%s"""\n\n'
            'ตอบเป็น JSON เท่านั้น ตามรูปแบบนี้\n'
            '{\n'
            '  "model": "ชื่อโมเดลจากรายการข้างบน",\n'
            '  "intent": "list | count | sum | group",\n'
            '  "domain": [["ชื่อฟิลด์", "ตัวดำเนินการ", ค่า]],\n'
            '  "fields": ["ฟิลด์ที่ควรแสดงในตาราง"],\n'
            '  "group_by": ["ฟิลด์ที่จัดกลุ่ม (ถ้า intent=group)"],\n'
            '  "measures": ["ฟิลด์ตัวเลขที่ต้องรวมยอด"],\n'
            '  "order": "ฟิลด์ desc/asc",\n'
            '  "limit": 20,\n'
            '  "explain": "อธิบายสั้น ๆ เป็นภาษาไทยว่าคุณค้นอะไรให้"\n'
            '}\n'
            'กติกา:\n'
            '- ใช้ได้เฉพาะชื่อฟิลด์ที่มีในรายการฟิลด์ของโมเดลนั้นเท่านั้น ห้ามเดาชื่อฟิลด์\n'
            '- ถ้าคำที่พนักงานพูดตรงกับ "ชื่อฟิลด์ภาษาไทย" ตัวไหน ให้ใช้ฟิลด์นั้นก่อนเสมอ '
            '(เช่น "วางบิล" -> ฟิลด์ที่ชื่อสถานะการวางบิล, "ตรวจสอบแล้ว" -> ฟิลด์สถานะตรวจสอบ) '
            'อย่าเปลี่ยนไปใช้ฟิลด์สถานะการชำระเงินแทน\n'
            '- ตอบได้เฉพาะ 3 เมนูค่าใช้จ่ายข้างบนเท่านั้น ถ้าคำถามเป็นเรื่องอื่น '
            '(ยอดขาย ใบแจ้งหนี้ลูกค้า ใบเสนอราคา สต๊อก เงินเดือน ฯลฯ) '
            'ห้ามเดาว่าเป็นเมนูใดเมนูหนึ่ง ให้ตอบ {"error": "คำถามนี้ไม่ใช่เรื่องค่าใช้จ่าย ..."} แทน\n'
            '- ฟิลด์ความสัมพันธ์ (Many2one) เจาะลึกได้ไม่เกิน 3 ชั้น เช่น partner_id.name\n'
            '- วันที่เขียนเป็น "YYYY-MM-DD" ถ้าพนักงานพูดเป็น พ.ศ. ให้ลบ 543 ก่อน\n'
            '- "เดือนนี้/ปีนี้/เมื่อวาน" ให้คำนวณเป็นช่วงวันที่จริงจากวันที่วันนี้\n'
            '- ตัวดำเนินการที่ใช้ได้: %s\n'
            '- ถ้าคำถามกว้างมากให้ใส่ limit ไม่เกิน %s และเรียงจากใหม่ไปเก่า\n'
            '- ถ้าไม่เข้าใจคำถามหรือไม่มีฟิลด์ที่ตอบได้ ให้ตอบ {"error": "เหตุผลสั้น ๆ"}\n'
            % (today.isoformat(), today.year + 543, '\n\n'.join(schema_parts), history_text,
               (question or '')[:800], ', '.join(sorted(ALLOWED_OPERATORS)), MAX_LIMIT)
        )
        plan = Gemini.extract_json(prompt, max_output_tokens=2048)
        if not plan:
            return None, 'ตอนนี้เรียก AI ไม่สำเร็จ ลองพิมพ์คำถามอีกครั้งได้ครับ'
        if plan.get('error'):
            return None, str(plan['error'])[:300]
        return plan, ''

    # ------------------------------------------------------------------
    # ตรวจแผนก่อนรัน
    # ------------------------------------------------------------------
    @api.model
    def _check_path(self, model_name, path):
        """ตรวจว่า field path ใช้ได้จริง คืน (ok, ข้อความผิดพลาด, ชนิดฟิลด์ปลายทาง)"""
        parts = (path or '').split('.')
        if not parts or len(parts) > MAX_PATH_DEPTH:
            return False, 'ฟิลด์ %s ลึกเกินไป' % path, ''
        current = model_name
        field_type = ''
        for index, part in enumerate(parts):
            # read_group ใช้ group by แบบ date:month ได้
            part = part.split(':')[0]
            info = self._field_info(current)
            entry = info.get(part)
            if not entry:
                return False, 'ไม่มีฟิลด์ %s ในโมเดล %s' % (part, current), ''
            if not entry['searchable']:
                return False, 'ฟิลด์ %s ค้นหาไม่ได้ (เป็นค่าคำนวณสด)' % part, ''
            field_type = entry['type']
            if index < len(parts) - 1:
                if not entry['relation']:
                    return False, 'ฟิลด์ %s ไม่ใช่ความสัมพันธ์ เจาะต่อไม่ได้' % part, ''
                current = entry['relation']
        return True, '', field_type

    @api.model
    def validate_plan(self, plan):
        """คืน (plan ที่ทำความสะอาดแล้ว, ข้อความผิดพลาด)"""
        conf_by_model = self._expense_models()
        model_name = plan.get('model')
        if model_name not in conf_by_model:
            return None, 'ยังตอบเรื่องนี้ไม่ได้ ตอนนี้ค้นได้เฉพาะ: %s' % ', '.join(
                '%s (%s)' % (conf.get('label') or name, name)
                for name, conf in conf_by_model.items())

        clean = {
            'model': model_name,
            'intent': plan.get('intent') if plan.get('intent') in ('list', 'count', 'sum', 'group') else 'list',
            'explain': str(plan.get('explain') or '')[:300],
        }

        # ---- domain ----
        domain = []
        for leaf in (plan.get('domain') or []):
            if isinstance(leaf, str):
                if leaf in ('&', '|', '!'):
                    domain.append(leaf)
                    continue
                return None, 'เงื่อนไข %s ไม่ถูกต้อง' % leaf
            if not isinstance(leaf, (list, tuple)) or len(leaf) != 3:
                return None, 'เงื่อนไขไม่ครบ 3 ส่วน: %s' % (leaf,)
            field_path, operator, value = leaf
            operator = str(operator).strip()
            if operator not in ALLOWED_OPERATORS:
                return None, 'ตัวดำเนินการ %s ใช้ไม่ได้' % operator
            ok, error, _ftype = self._check_path(model_name, str(field_path))
            if not ok:
                return None, error
            if isinstance(value, (list, tuple)):
                value = list(value)
            domain.append((str(field_path), operator, value))
        clean['domain'] = domain

        # ---- fields / group_by / measures / order ----
        conf = conf_by_model[model_name]
        fields_list = []
        for name in (plan.get('fields') or conf.get('default_fields') or []):
            ok, _error, _ftype = self._check_path(model_name, str(name))
            if ok and '.' not in str(name):
                fields_list.append(str(name))
        if not fields_list:
            fields_list = [f for f in (conf.get('default_fields') or [])
                           if f in self._field_info(model_name)]
        clean['fields'] = fields_list[:12]

        group_by = []
        for name in (plan.get('group_by') or []):
            ok, error, _ftype = self._check_path(model_name, str(name))
            if not ok:
                return None, error
            group_by.append(str(name))
        clean['group_by'] = group_by[:2]

        measures = []
        info = self._field_info(model_name)
        for name in (plan.get('measures') or []):
            entry = info.get(str(name).split(':')[0])
            if entry and entry['type'] in ('integer', 'float', 'monetary'):
                measures.append(str(name))
        if not measures:
            amount_field = conf.get('amount_field')
            if amount_field and amount_field in info:
                measures = [amount_field]
        clean['measures'] = measures[:3]

        order = str(plan.get('order') or '').strip()
        if order:
            field_name = order.split()[0]
            ok, _error, _ftype = self._check_path(model_name, field_name)
            if not ok or '.' in field_name:
                order = ''
        if not order:
            date_field = conf.get('date_field')
            order = '%s desc' % date_field if date_field in info else ''
        clean['order'] = order

        try:
            limit = int(plan.get('limit') or MAX_LIMIT)
        except (TypeError, ValueError):
            limit = MAX_LIMIT
        clean['limit'] = max(1, min(limit, MAX_LIMIT))
        return clean, ''

    # ------------------------------------------------------------------
    # รันแผน (อ่านอย่างเดียว)
    # ------------------------------------------------------------------
    @api.model
    def _group_orderby(self, plan):
        """order ที่ใช้กับ read_group ได้

        Odoo 18 ยอมให้เรียงเฉพาะฟิลด์ที่จัดกลุ่มหรือค่าที่รวมยอดเท่านั้น
        (Odoo 14 ยอมทุกฟิลด์) ถ้า order ที่ AI ให้มาไม่เข้าเงื่อนไข ให้ปล่อยว่าง
        ไม่งั้นได้ ValueError: Order term ... is not a valid aggregate nor valid groupby
        """
        order = (plan.get('order') or '').strip()
        if not order:
            return None
        field_name = order.split()[0]
        allowed = [g.split(':')[0] for g in plan.get('group_by') or []] + list(plan.get('measures') or [])
        return order if field_name in allowed else None

    @api.model
    def run_plan(self, plan):
        """คืน dict ผลลัพธ์ {count, total, rows/groups, ...}"""
        conf = self._expense_models()[plan['model']]
        Model = self.env[plan['model']].sudo().with_context(active_test=False)
        domain = list(conf.get('domain') or []) + list(plan['domain'])
        result = {
            'label': conf.get('label') or plan['model'],
            'count': Model.search_count(domain),
            'measures': plan['measures'],
            'totals': {},
        }
        # ยอดรวมของทั้งผลลัพธ์ (ไม่ใช่เฉพาะแถวที่แสดง)
        if plan['measures']:
            groups = Model.read_group(domain, plan['measures'], [], lazy=False)
            if groups:
                for measure in plan['measures']:
                    result['totals'][measure] = groups[0].get(measure) or 0.0

        if plan['intent'] == 'count':
            result['rows'] = []
            return result
        if plan['intent'] == 'group' and plan['group_by']:
            groups = Model.read_group(domain, plan['measures'] + plan['group_by'],
                                      plan['group_by'], lazy=False,
                                      orderby=self._group_orderby(plan), limit=MAX_GROUPS)
            result['groups'] = groups
            return result

        result['rows'] = Model.search_read(domain, plan['fields'],
                                           limit=plan['limit'], order=plan['order'] or None)
        return result

    # ------------------------------------------------------------------
    # จัดรูปคำตอบสำหรับแชท
    # ------------------------------------------------------------------
    @api.model
    def _format_value(self, value, field_entry):
        if value is False or value is None:
            return '—'
        ftype = (field_entry or {}).get('type')
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return html_escape(str(value[1]))          # many2one -> (id, ชื่อ)
        if ftype in ('float', 'monetary'):
            return '{:,.2f}'.format(value)
        if ftype == 'integer':
            return '{:,}'.format(value)
        if ftype in ('date', 'datetime') or isinstance(value, (date, datetime)):
            text = str(value)[:10]
            parts = text.split('-')
            if len(parts) == 3:
                return '%s/%s/%s' % (parts[2], parts[1], parts[0])
            return html_escape(text)
        if ftype == 'selection':
            return html_escape(str(value))
        return html_escape(str(value)[:80])

    @api.model
    def format_answer(self, plan, result):
        """สร้าง HTML ของคำตอบ (ตาราง + ยอดรวม)"""
        info = self._field_info(plan['model'])
        parts = []
        head = 'พบ <b>{:,}</b> รายการ'.format(result['count'])
        for measure, total in (result.get('totals') or {}).items():
            label = (info.get(measure) or {}).get('string') or measure
            head += ' · %s รวม <b>%s</b>' % (html_escape(label), '{:,.2f}'.format(total or 0.0))
        parts.append(head)

        if result.get('groups'):
            rows = ['<tr><th style="text-align:left">%s</th>%s<th style="text-align:right">จำนวน</th></tr>' % (
                ' / '.join(html_escape((info.get(g.split(':')[0]) or {}).get('string') or g)
                           for g in plan['group_by']),
                ''.join('<th style="text-align:right">%s</th>'
                        % html_escape((info.get(m) or {}).get('string') or m)
                        for m in plan['measures']))]
            for group in result['groups']:
                keys = []
                for name in plan['group_by']:
                    keys.append(self._format_value(group.get(name), info.get(name.split(':')[0])))
                cells = ''.join('<td style="text-align:right">%s</td>'
                                % '{:,.2f}'.format(group.get(m) or 0.0) for m in plan['measures'])
                rows.append('<tr><td>%s</td>%s<td style="text-align:right">%s</td></tr>'
                            % (' / '.join(keys), cells, group.get('__count', 0)))
            parts.append('<table class="table table-sm" style="width:100%%">%s</table>'
                         % ''.join(rows))
        elif result.get('rows'):
            headers = ''.join('<th>%s</th>' % html_escape((info.get(f) or {}).get('string') or f)
                              for f in plan['fields'])
            rows = ['<tr>%s</tr>' % headers]
            for row in result['rows']:
                cells = ''.join('<td>%s</td>' % self._format_value(row.get(f), info.get(f))
                                for f in plan['fields'])
                rows.append('<tr>%s</tr>' % cells)
            parts.append('<table class="table table-sm" style="width:100%%">%s</table>'
                         % ''.join(rows))
            if result['count'] > len(result['rows']):
                parts.append('<i>แสดง %s จาก %s รายการแรกเท่านั้น '
                             'ถ้าต้องการดูมากกว่านี้ ให้ระบุเงื่อนไขเพิ่ม</i>'
                             % (len(result['rows']), '{:,}'.format(result['count'])))
        return parts

    # ------------------------------------------------------------------
    # ไฟล์ Excel (พนักงานบัญชีขอเอาไปทำงานต่อ)
    # ------------------------------------------------------------------
    @api.model
    def wants_excel(self, question):
        """ข้อความนี้ขอเป็นไฟล์ Excel หรือเปล่า"""
        text = (question or '').lower()
        return any(word in text for word in EXCEL_WORDS)

    @api.model
    def strip_excel_words(self, question):
        """ตัดคำที่แปลว่า "ขอเป็นไฟล์" ออก เหลือแต่เนื้อคำถามจริง"""
        text = question or ''
        for word in EXCEL_WORDS:
            text = text.replace(word, ' ').replace(word.upper(), ' ')
        for word in ('ขอ', 'เป็น', 'ให้', 'หน่อย', 'ครับ', 'ค่ะ', 'ด้วย', 'ที'):
            text = text.replace(word, ' ')
        return ' '.join(text.split())

    @api.model
    def build_excel(self, plan):
        """สร้างไฟล์ Excel จากแผนเดิม (ดึงได้มากกว่าที่แสดงในแชท)

        คืน (ชื่อไฟล์, ไบต์ของไฟล์, จำนวนแถว) — คืน (None, None, 0) ถ้าสร้างไม่ได้
        """
        if not xlsxwriter:
            return None, None, 0
        conf = self._expense_models()[plan['model']]
        Model = self.env[plan['model']].sudo().with_context(active_test=False)
        domain = list(conf.get('domain') or []) + list(plan['domain'])
        info = self._field_info(plan['model'])

        if plan['intent'] == 'group' and plan['group_by']:
            columns = plan['group_by'] + plan['measures'] + ['__count']
            headers = ([(info.get(g.split(':')[0]) or {}).get('string') or g for g in plan['group_by']]
                       + [(info.get(m) or {}).get('string') or m for m in plan['measures']]
                       + ['จำนวนเอกสาร'])
            records = Model.read_group(domain, plan['measures'] + plan['group_by'], plan['group_by'],
                                       lazy=False, orderby=self._group_orderby(plan), limit=MAX_EXCEL_ROWS)
        else:
            columns = plan['fields']
            headers = [(info.get(f) or {}).get('string') or f for f in columns]
            records = Model.search_read(domain, columns, limit=MAX_EXCEL_ROWS,
                                        order=plan['order'] or None)

        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True, 'default_date_format': 'dd/mm/yyyy'})
        sheet = book.add_worksheet((conf.get('label') or plan['model'])[:28])
        head_fmt = book.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1,
                                    'font_name': 'Tahoma', 'font_size': 10})
        text_fmt = book.add_format({'font_name': 'Tahoma', 'font_size': 10})
        money_fmt = book.add_format({'num_format': '#,##0.00', 'font_name': 'Tahoma', 'font_size': 10})
        date_fmt = book.add_format({'num_format': 'dd/mm/yyyy', 'font_name': 'Tahoma', 'font_size': 10})

        for index, header in enumerate(headers):
            sheet.write(0, index, header, head_fmt)
            sheet.set_column(index, index, max(12, min(38, len(str(header)) + 6)))
        sheet.freeze_panes(1, 0)

        for row_index, record in enumerate(records, start=1):
            for col_index, column in enumerate(columns):
                value = record.get(column)
                entry = info.get(str(column).split(':')[0]) or {}
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    # read_group คืนชื่อของ many2one เป็น lazy object ต้อง str() ก่อน
                    # ไม่งั้น xlsxwriter ล้ม (TypeError: expected string or bytes-like object)
                    sheet.write(row_index, col_index, str(value[1] or ''), text_fmt)
                elif value in (False, None):
                    sheet.write(row_index, col_index, '', text_fmt)
                elif entry.get('type') in ('float', 'monetary', 'integer') or column == '__count':
                    sheet.write_number(row_index, col_index, value or 0, money_fmt)
                elif entry.get('type') in ('date', 'datetime'):
                    sheet.write(row_index, col_index, str(value)[:10], date_fmt)
                else:
                    sheet.write(row_index, col_index, str(value), text_fmt)

        book.close()
        stamp = date.today().strftime('%Y%m%d')
        filename = '%s-%s.xlsx' % ((conf.get('label') or plan['model']).split(' ')[0], stamp)
        return filename, stream.getvalue(), len(records)

    # ------------------------------------------------------------------
    # ทางเข้าเดียวที่ session เรียกใช้
    # ------------------------------------------------------------------
    @api.model
    def answer(self, question, history=None, plan=None):
        """คืน (list ของบล็อก HTML, plan ที่ใช้จริง, ข้อความผิดพลาด)

        ส่ง plan เข้ามาเองได้ (เช่นตอนขอไฟล์ Excel ของคำถามเดิม) จะได้ไม่ต้อง
        เรียก AI ซ้ำ — แต่ยังตรวจแผนใหม่ทุกครั้งก่อนรัน
        """
        if plan is None:
            plan, error = self.build_plan(question, history=history)
            if error:
                return [], None, error
        clean, error = self.validate_plan(plan)
        if error:
            return [], None, error
        try:
            result = self.run_plan(clean)
        except Exception as exc:  # noqa: BLE001 - คำถามแปลก ๆ ไม่ควรทำให้แชทพัง
            _logger.warning('ตัวช่วย AI-IT: ค้นค่าใช้จ่ายไม่สำเร็จ (%s)', exc)
            return [], clean, 'ค้นข้อมูลตามคำถามนี้ไม่สำเร็จ (%s) ลองถามใหม่อีกแบบได้ครับ' % (
                html_escape(str(exc)[:120]))
        return self.format_answer(clean, result), clean, ''
