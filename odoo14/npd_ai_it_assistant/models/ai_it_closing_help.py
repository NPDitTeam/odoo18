# -*- coding: utf-8 -*-
u"""ช่วยปิดงบ (Odoo 18) -- ผู้ช่วยค้นหาสำหรับงานปิดงบสิ้นปี (อ่านอย่างเดียว)

หัวข้อนี้ทำ 4 อย่าง
  1. บอก "ลำดับงาน" ว่าต้องดูเมนูไหนก่อน อะไรหลัง แต่ละเมนูอยู่ที่ไหน เอาไว้ทำอะไร
     -> เส้นทางเมนูไม่ได้เขียนตายไว้ แต่ค้นจาก ir.ui.menu ของฐานนั้นจริง ๆ
        และบอกด้วยว่า "ผู้ใช้คนนี้เห็นเมนูนั้นหรือเปล่า"
  2. ตรวจว่าปีที่ถามปิดงบสมบูรณ์แล้วหรือยัง "ติดที่รายการไหน" และ "เท่าไหร่ถึงจะถูก"
  3. ตอบคำถามอิสระด้วย AI โดยยึดจาก "คู่มือในโค้ด + ผลตรวจจริง + เมนูจริง" เท่านั้น
  4. ออกไฟล์ Excel ให้ในแชท

ต่างจากฝั่ง Odoo 14 ตรงไหน (สำคัญ อย่าลอกข้ามเวอร์ชัน)
  - ไม่มี account.account.user_type_id แล้ว ใช้ account_account.account_type
    (selection) แทน และ internal_group เป็นฟิลด์คำนวณ ไม่ได้ store จึงใช้ใน SQL ไม่ได้
  - ไม่มีโมดูล account_fiscal_year / account_fiscal_year_closing บน o18
    การ "ปิดงบ" จึงจบที่การล็อกวันที่ ไม่ได้ออกใบปิดบัญชีเหมือน o14
    -> ตัวตรวจ "การล็อกวันที่" จึงเป็นตัวชี้ขาดว่าปิดงบสมบูรณ์หรือยัง
  - res.company ไม่มี period_lock_date แล้ว มี fiscalyear_lock_date /
    tax_lock_date / hard_lock_date (hard_lock_date ย้อนกลับไม่ได้)
  - ir.ui.menu กรองเมนูที่มองไม่เห็นใน search_fetch() ไม่ใช่ search()
  - แอปบัญชีชื่อ "Invoicing" ไม่ใช่ "Accounting" เส้นทางเมนูจึงคนละชุดกับ o14

ทำไม sudo(): บัญชีส่วนกลางต้องเห็นตัวเลขทั้งบริษัท ความปลอดภัยอยู่ที่
"อ่านอย่างเดียว" + หัวข้อนี้เปิดให้เฉพาะคนที่ถูกติ๊กสิทธิ์ (group_ai_it_closing)
"""
import calendar
import io
import json
import logging
import re
from datetime import date

from odoo import api, models
from odoo.tools.misc import html_escape

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - เครื่องที่ไม่มีไลบรารี
    xlsxwriter = None

_logger = logging.getLogger(__name__)

MAX_EXCEL_ROWS = 3000
SAMPLE_ROWS = 8
EPS = 0.005
MAX_YEARS = 6

# ชนิดบัญชีของ Odoo 18 (แทน account.account.user_type_id ของ o14)
RECEIVABLE_PAYABLE_TYPES = ('asset_receivable', 'liability_payable')
INCOME_TYPES = ('income', 'income_other')
EXPENSE_TYPES = ('expense', 'expense_depreciation', 'expense_direct_cost')
UNAFFECTED_TYPE = 'equity_unaffected'

EXCEL_WORDS = (u'excel', u'xlsx', u'เอ็กเซล', u'เอกเซล', u'ไฟล์แนบ', u'ออกไฟล์',
               u'ส่งไฟล์', u'ขอไฟล์', u'เป็นไฟล์', u'export', u'ดาวน์โหลด', u'โหลดไฟล์')
CHECK_WORDS = (u'ตรวจ', u'เช็ค', u'เช็ก', u'ติดอะไร', u'ติดตรงไหน', u'ติดที่ไหน',
               u'ปิดได้ยัง', u'ปิดงบได้ไหม', u'สมบูรณ์', u'ครบไหม', u'พร้อมปิด',
               u'ค้างอะไร', u'เหลืออะไร', u'check', u'status')
STEP_WORDS = (u'ขั้นตอน', u'ลำดับ', u'เริ่มยังไง', u'เริ่มตรงไหน', u'ทำอะไรก่อน',
              u'แผนที่', u'ภาพรวม', u'roadmap', u'step', u'overview', u'คู่มือ')
MENU_WORDS = (u'เมนู', u'อยู่ไหน', u'อยู่ตรงไหน', u'หาไม่เจอ', u'เข้าไปที่ไหน',
              u'menu', u'where')

STATUS_LABEL = {'block': u'ต้องแก้ก่อน', 'warn': u'ควรดูก่อนปิด', 'ok': u'ผ่าน',
                'skip': u'ไม่มีข้อมูล'}
STATUS_ICON = {'block': u'🔴', 'warn': u'🟡', 'ok': u'🟢', 'skip': u'⚪'}


# ======================================================================
# คู่มือปิดงบของ Odoo 18 (เส้นทางเมนูตามที่มีอยู่จริงในระบบนี้)
# ======================================================================
CLOSING_STEPS = [
    {
        'order': 1,
        'key': 'collect',
        'title': u'ตรวจรายการให้ครบ',
        'goal': u'รายการทั้งปีลงบัญชีครบ ไม่มีใบค้างร่าง',
        'why': u'ใบร่างไม่เข้างบ ถ้ายังค้างอยู่ตัวเลขในงบจะไม่ใช่ตัวจริง',
        'items': [
            {'name': u'เคลียร์ใบค้างร่าง',
             'find': u'Journal Entries',
             'path': u'Invoicing > Accounting > Journal Entries',
             'what': u'กรอง Draft + ปีที่จะปิด แล้วไล่ Post หรือ Cancel ทีละใบ',
             'pass': u'เหลือ 0 รายการ'},
            {'name': u'ไล่สมุดรายวันทีละเล่ม',
             'find': u'Journals',
             'path': u'Invoicing > Configuration > Accounting > Journals',
             'what': u'ดูว่าเลขที่เอกสารเรียงต่อเนื่อง ไม่ขาดช่วง',
             'pass': u'ไม่มีเลขขาดช่วงที่อธิบายไม่ได้'},
            {'name': u'กระทบยอดลูกหนี้-เจ้าหนี้',
             'find': u'Open Items',
             'path': u'Invoicing > Reporting > OCA accounting reports > Open Items',
             'what': u'ดูรายการที่ยังไม่ถูกจับคู่ แล้วไปจับคู่ที่ Journal Items',
             'pass': u'เหลือเฉพาะรายการที่ยังค้างชำระจริง'},
            {'name': u'สอบยอดลูกหนี้-เจ้าหนี้คงค้าง',
             'find': u'Aged Partner Balance',
             'path': u'Invoicing > Reporting > OCA accounting reports > Aged Partner Balance',
             'what': u'ยอด ณ วันสิ้นปี ต้องตรงกับที่บัญชีคุมไว้',
             'pass': u'ยอดตรงกับทะเบียนคุม'},
            {'name': u'ปิดภาษีให้เรียบร้อย',
             'find': u'Thai Tax Report',
             'path': u'Invoicing > Reporting > Thai Tax Report',
             'what': u'กระทบภาษีซื้อ-ขายรายเดือนกับที่ยื่นจริง และตรวจ ภ.ง.ด. ให้ครบ '
                     u'(ดูที่ Reporting > Thai Accounting Reports)',
             'pass': u'ครบทุกเดือน ตรงกับที่ยื่น (มีผลกับ Tax Lock Date ในขั้นที่ 4)'},
        ],
    },
    {
        'order': 2,
        'key': 'adjust',
        'title': u'ลงรายการปรับปรุงสิ้นปี',
        'goal': u'รายการที่ไม่ได้เกิดจากการซื้อขายประจำวัน แต่ต้องมีก่อนงบจะถูก',
        'why': u'ตัวเลขต้องนิ่งก่อนล็อก ไม่งั้นต้องปลดล็อกกลับมาแก้',
        'items': [
            {'name': u'ค่าเสื่อมราคา',
             'find': u'Compute Assets',
             'path': u'Invoicing > Assets > Compute Assets',
             'what': u'ยืนยันสินทรัพย์ที่ยังเป็นร่างที่ Invoicing > Assets > Assets '
                     u'แล้วสั่ง Compute Assets ให้สร้างใบค่าเสื่อม',
             'pass': u'ค่าเสื่อมลงครบถึงเดือนสุดท้ายของปี และใบ JE ค่าเสื่อม Post หมด'},
            {'name': u'ตรวจค่าเสื่อมทั้งปี',
             'find': u'คำนวณค่าเสื่อมประจำปี',
             'path': u'Invoicing > Assets > คำนวณค่าเสื่อมประจำปี',
             'what': u'สรุปค่าเสื่อมทั้งปี ใช้คู่กับ ค่าเสื่อมราคารายเดือน '
                     u'และ สรุปค่าเสื่อมตามหมวด ไว้แนบงบ',
             'pass': u'ยอดตรงกับที่ลงบัญชี'},
            {'name': u'รายการปรับปรุงสิ้นปีอื่น ๆ',
             'find': u'Journal Entries',
             'path': u'Invoicing > Accounting > Journal Entries',
             'what': u'กดสร้างใบใหม่ในสมุดรายวันทั่วไป — ค้างรับ-ค้างจ่าย · '
                     u'รับ-จ่ายล่วงหน้า · ปรับสินค้าคงเหลือให้ตรงที่นับจริง · '
                     u'ผลต่างอัตราแลกเปลี่ยน · ค่าเผื่อหนี้สงสัยจะสูญ · '
                     u'ภาษีเงินได้นิติบุคคล (ลงเป็นรายการสุดท้าย)',
             'pass': u'ลงครบและ Post แล้ว'},
        ],
    },
    {
        'order': 3,
        'key': 'report',
        'title': u'ออกงบมาตรวจ',
        'goal': u'มีงบฉบับก่อนล็อกเก็บไว้เป็นหลักฐาน',
        'why': u'ต้องเซฟไว้ก่อนล็อก เพราะหลังล็อกแล้วแก้อะไรไม่ได้',
        'items': [
            {'name': u'1) งบทดลอง (Trial Balance)',
             'find': u'Trial Balance',
             'path': u'Invoicing > Reporting > OCA accounting reports > Trial Balance',
             'what': u'ตัวหลัก เดบิตรวมต้องเท่าเครดิตรวม',
             'pass': u'เดบิต = เครดิต'},
            {'name': u'2) งบการเงิน (งบดุล / งบกำไรขาดทุน)',
             'find': u'MIS Reports',
             'path': u'Invoicing > Reporting > MIS Reporting > MIS Reports',
             'what': u'งบดุลและงบกำไรขาดทุนของ o18 ออกจาก MIS Report '
                     u'(แม่แบบตั้งไว้ที่ Configuration > MIS Reporting > MIS Report Templates)',
             'pass': u'พิมพ์เก็บเป็น PDF/Excel แล้ว'},
            {'name': u'3) งบกระแสเงินสด',
             'find': u'Cash Flow Report',
             'path': u'Invoicing > Reporting > Financial reports > Cash Flow Report',
             'what': u'กระแสเงินสดทั้งปี',
             'pass': u'พิมพ์เก็บแล้ว'},
            {'name': u'4) แยกประเภท (General Ledger)',
             'find': u'General Ledger',
             'path': u'Invoicing > Reporting > OCA accounting reports > General Ledger',
             'what': u'ไว้เจาะดูเมื่อยอดไม่ตรง ใช้คู่กับ Journal Ledger',
             'pass': u'-'},
            {'name': u'5) รายงานภาษี',
             'find': u'VAT Report',
             'path': u'Invoicing > Reporting > OCA accounting reports > VAT Report',
             'what': u'กระทบกับ Thai Tax Report และแบบที่ยื่นจริง',
             'pass': u'ตรงกับที่ยื่น'},
        ],
    },
    {
        'order': 4,
        'key': 'close',
        'title': u'ปิดงบจริง = ล็อกวันที่',
        'goal': u'ล็อกไม่ให้ใครแก้ย้อนหลัง',
        'why': u'Odoo 18 ไม่มีใบปิดบัญชีแบบ o14 แล้ว ระบบยกยอดงบดุลข้ามปีให้เอง '
               u'ผ่านบัญชีกำไร(ขาดทุน)ที่ยังไม่ได้จัดสรร การปิดงบจึงจบที่การล็อกวันที่',
        'items': [
            {'name': u'4.1 ตรวจความต่อเนื่องของเลขที่เอกสาร',
             'find': u'Secure Entries',
             'path': u'Invoicing > Accounting > Secure Entries',
             'what': u'ดูว่ารายการในงวดถูกผูกลำดับเรียบร้อย ไม่มีช่องโหว่',
             'pass': u'ไม่มีรายการค้างที่ยังไม่ถูกผูกลำดับ'},
            {'name': u'4.2 ล็อกวันที่',
             'find': u'Settings',
             'path': u'Invoicing > Configuration > Settings (หัวข้อ Fiscal Periods / Lock Dates)',
             'what': u'Lock Date = วันสิ้นงวด · Tax Lock Date = วันสิ้นงวดภาษีที่ยื่นแล้ว '
                     u'· Hard Lock Date ใส่เมื่อมั่นใจจริงเท่านั้น',
             'pass': u'Lock Date ครอบถึงวันสิ้นงวดที่ปิด'},
        ],
    },
]

PITFALLS = [
    (u'หาเมนูปิดงบไม่เจอ',
     u'สิทธิ์ผู้ใช้ไม่พอ เมนูบัญชีครึ่งหนึ่งจะไม่ขึ้นเลย',
     u'ให้ IT เพิ่มสิทธิ์บัญชีระดับผู้ดูแล (Billing Administrator / Accountant)'),
    (u'งบกำไรขาดทุนยอดไม่ตรงกับงบทดลอง',
     u'ช่วงวันที่ในรายงานไม่ใช่ช่วงเดียวกัน หรือเลือกบริษัทไม่ตรงกัน',
     u'ระบบนี้มีหลายบริษัท ต้องเลือกบริษัทให้ตรงก่อนออกรายงานทุกครั้ง'),
    (u'ล็อกแล้วกลับไปแก้เอกสารย้อนหลังไม่ได้',
     u'ตั้ง Lock Date เร็วเกินไป',
     u'เลื่อนวันออกชั่วคราวที่ Settings แก้เสร็จแล้วล็อกกลับ '
     u'— แต่ถ้าเป็น Hard Lock Date จะย้อนกลับไม่ได้เลย'),
    (u'ตั้ง Hard Lock Date ไปแล้วอยากแก้',
     u'Hard Lock Date ของ Odoo 18 เป็นการล็อกถาวร',
     u'แก้ไม่ได้อีกเลย ใส่เฉพาะตอนปิดงบเสร็จสมบูรณ์และส่งงบแล้วเท่านั้น'),
    (u'ยอดยกมาต้นปีไม่ตรง',
     u'ปีก่อนหน้ายังปิดไม่เรียบร้อย หรือยกข้อมูลจาก o14 มาไม่ครบ',
     u'ไล่ปีเก่าก่อน พิมพ์ "ตรวจปี <ปีก่อนหน้า>" ให้ผมดูให้ได้'),
]


def _money(value):
    return u'{:,.2f}'.format(float(value or 0.0))


def _thai_date(value):
    if not value:
        return u'—'
    text = str(value)[:10].split('-')
    return u'%s/%s/%s' % (text[2], text[1], text[0]) if len(text) == 3 else str(value)


class NpdAiItClosing(models.AbstractModel):
    _name = 'npd.ai.it.closing'
    _description = u'ตัวช่วย AI-IT : ช่วยปิดงบ (ค้นหา/ตรวจสอบ อ่านอย่างเดียว)'

    # ==================================================================
    # ปี และงวดบัญชี
    # ==================================================================
    @api.model
    def _company(self):
        return self.env.company

    @api.model
    def fiscal_window(self, year):
        u"""คืน (วันเริ่มงวด, วันสิ้นงวด) ของปีบัญชีที่จบในปีนั้น"""
        company = self._company()
        last_month = int(company.fiscalyear_last_month or 12)
        last_day = int(company.fiscalyear_last_day or 31)
        last_day = min(last_day, calendar.monthrange(year, last_month)[1])
        anchor = date(year, last_month, last_day)
        try:
            window = company.compute_fiscalyear_dates(anchor)
            return window['date_from'], window['date_to']
        except Exception:  # noqa: BLE001
            _logger.debug(u'ช่วยปิดงบ: compute_fiscalyear_dates ใช้ไม่ได้ คำนวณงวดเอง')
        if (last_month, last_day) == (12, 31):
            return date(year, 1, 1), date(year, 12, 31)
        start_year = year - 1
        start_month = last_month + 1
        if start_month > 12:
            start_month, start_year = 1, year
        return date(start_year, start_month, 1), anchor

    @api.model
    def available_years(self):
        u"""ปีที่มีรายการลงบันทึกอยู่จริงของบริษัทที่เลือกอยู่ (ใหม่ไปเก่า)"""
        self.env.cr.execute(
            """SELECT DISTINCT EXTRACT(YEAR FROM date)::int AS y
                 FROM account_move
                WHERE company_id = %s AND state = 'posted' AND date IS NOT NULL
                ORDER BY y DESC""", (self._company().id,))
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def parse_years(self, text):
        u"""อ่านปีจากข้อความ รองรับ พ.ศ. / ค.ศ. / "ปีนี้" / "ปีที่แล้ว" """
        text = text or u''
        years = []
        for raw in re.findall(r'\b(\d{4})\b', text):
            value = int(raw)
            if 2500 <= value <= 2600:
                value -= 543
            if 2000 <= value <= 2100:
                years.append(value)
        today = date.today()
        if not years:
            if u'ปีที่แล้ว' in text or u'ปีก่อน' in text or u'ปีที่ผ่านมา' in text:
                years.append(today.year - 1)
            elif u'ปีนี้' in text or u'ปีปัจจุบัน' in text:
                years.append(today.year)
        if not years and (u'ทุกปี' in text or u'แต่ละปี' in text or u'ทุกๆปี' in text):
            years = sorted(self.available_years())[-MAX_YEARS:]
        return sorted(set(years))[:MAX_YEARS]

    @api.model
    def default_year(self):
        years = self.available_years()
        return years[0] if years else date.today().year

    # ==================================================================
    # ค้นเมนูจริงในฐานนี้
    # ==================================================================
    @api.model
    def find_menus(self, keyword, limit=4, hint=None):
        u"""ค้นเมนูจาก ir.ui.menu ของฐานนี้จริง ๆ

        ต่างจาก o14: Odoo 18 กรองเมนูที่ผู้ใช้มองไม่เห็นใน ``search_fetch()``
        (ดู ir_ui_menu.py) ไม่ใช่ ``search()`` การเช็ค "เห็นหรือไม่เห็น" จึงต้อง
        ใช้ search_fetch ไม่งั้นจะได้ว่าเห็นหมดทุกเมนู ซึ่งไม่จริง
        """
        keyword = (keyword or u'').strip()
        if not keyword:
            return []
        Menu = self.env['ir.ui.menu']
        # ชื่อเมนูเป็นฟิลด์แปลภาษา การค้นจะค้นเฉพาะภาษาที่ผู้ใช้เปิดอยู่
        # ผู้ใช้เปิดหน้าจอภาษาไทย แต่ชื่อเมนูจริงเป็นอังกฤษ (Trial Balance)
        # ถ้าค้นภาษาเดียวจะไม่เจอ จึงต้องค้นทั้งภาษาผู้ใช้และอังกฤษแล้วรวมกัน
        base = Menu.sudo().with_context(**{'ir.ui.menu.full_list': True})
        candidates = Menu.browse()
        for lang in (self.env.lang or 'en_US', 'en_US'):
            try:
                found = base.with_context(lang=lang).search(
                    [('name', 'ilike', keyword)], limit=60)
            except Exception:  # noqa: BLE001
                continue
            candidates |= found.with_env(base.env)
        if not candidates:
            return []
        try:
            visible_ids = set(Menu.search_fetch([('id', 'in', candidates.ids)], ['id']).ids)
        except Exception:  # noqa: BLE001 - เผื่อเวอร์ชันที่ยังไม่มี search_fetch
            visible_ids = set(Menu.search([('id', 'in', candidates.ids)]).ids)

        hint_parts = []
        for part in re.split(r'[>/]', hint or u''):
            part = part.strip().lower()
            if part and part not in hint_parts:
                hint_parts.append(part)
        hint_path = u'/'.join(part.strip().lower()
                              for part in re.split(r'[>/]', hint or u'') if part.strip())
        keyword_lower = keyword.lower()

        scored = []
        seen = set()
        for menu in candidates:
            try:
                path = menu.complete_name
            except Exception:  # noqa: BLE001
                path = menu.name
            if not path or path in seen:
                continue
            if u'hide menu' in path.lower():
                continue
            seen.add(path)
            path_lower = path.lower()
            score = 0
            if hint_path and path_lower == hint_path:
                score += 500
            if (menu.name or u'').strip().lower() == keyword_lower:
                score += 100
            elif path_lower.split('/')[-1].startswith(keyword_lower):
                score += 40
            for part in hint_parts:
                if part in path_lower:
                    score += 10
            score -= path.count('/')
            if menu.id in visible_ids:
                score += 2
            scored.append((score, path, menu.id in visible_ids))

        scored.sort(key=lambda row: (-row[0], len(row[1])))
        return [{'path': path, 'visible': visible} for _score, path, visible in scored[:limit]]

    @api.model
    def _item_menu_text(self, item):
        hint = item.get('path') or u''
        found = self.find_menus(item.get('find') or u'', limit=1, hint=hint)
        if found:
            note = u'' if found[0]['visible'] else u' (สิทธิ์ของคุณยังไม่เห็นเมนูนี้)'
            return found[0]['path'] + note
        return hint

    # ==================================================================
    # ตัวตรวจ -- "ติดที่รายการไหน" และ "เท่าไหร่ถึงจะถูก"
    # ==================================================================
    def _blank(self, key, title, menu_find, menu_path):
        return {
            'key': key, 'title': title, 'status': 'ok',
            'found': u'', 'need': u'', 'fix': u'',
            'menu_find': menu_find, 'menu_path': menu_path,
            'amount': 0.0, 'count': 0,
            'columns': [], 'rows': [],
        }

    def _check_draft_moves(self, year, dfrom, dto):
        check = self._blank('draft_moves', u'ใบค้างร่างในปี', u'Journal Entries',
                            u'Invoicing > Accounting > Journal Entries')
        Move = self.env['account.move'].sudo()
        domain = [('company_id', '=', self._company().id),
                  ('date', '>=', dfrom), ('date', '<=', dto),
                  ('state', '=', 'draft')]
        count = Move.search_count(domain)
        check['count'] = count
        if not count:
            check['found'] = u'ไม่มีใบค้างร่าง'
            check['need'] = u'—'
            return check
        check['status'] = 'block'
        groups = Move.read_group(domain, [], ['journal_id'], lazy=False)
        parts = [u'%s %s ใบ' % (g['journal_id'][1] if g.get('journal_id') else u'ไม่ระบุ',
                                g['__count'])
                 for g in sorted(groups, key=lambda g: -g['__count'])[:6]]
        check['found'] = u'ค้าง %s ใบ (%s)' % ('{:,}'.format(count), u' · '.join(parts))
        check['need'] = u'ต้องเหลือ 0 ใบ — ยังเหลืออีก %s ใบ' % '{:,}'.format(count)
        check['fix'] = u'กรอง Draft + ปี %s แล้วไล่กด Post ถ้ารายการถูก หรือ Cancel ถ้าไม่ใช้' % year
        check['columns'] = [(u'เลขที่', 'name'), (u'วันที่', 'date'),
                            (u'สมุดรายวัน', 'journal_id'), (u'คู่ค้า', 'partner_id'),
                            (u'ยอดรวม', 'amount_total')]
        check['rows'] = Move.search_read(domain, ['name', 'date', 'journal_id',
                                                  'partner_id', 'amount_total'],
                                         limit=MAX_EXCEL_ROWS, order='date, name')
        return check

    def _check_balance(self, year, dfrom, dto):
        check = self._blank('trial_balance', u'งบทดลองสมดุล (เดบิต = เครดิต)',
                            u'Trial Balance',
                            u'Invoicing > Reporting > OCA accounting reports > Trial Balance')
        self.env.cr.execute(
            """SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
                 FROM account_move_line
                WHERE company_id = %s AND parent_state = 'posted'
                  AND date >= %s AND date <= %s""",
            (self._company().id, dfrom, dto))
        debit, credit = self.env.cr.fetchone()
        diff = float(debit) - float(credit)
        check['amount'] = abs(diff)
        if abs(diff) < EPS:
            check['found'] = u'เดบิต = เครดิต = %s บาท' % _money(debit)
            check['need'] = u'—'
            return check
        check['status'] = 'block'
        check['found'] = u'เดบิต %s / เครดิต %s' % (_money(debit), _money(credit))
        check['need'] = u'ต่างกัน %s บาท ต้องเป็น 0' % _money(abs(diff))
        check['fix'] = u'เปิดงบทดลองช่วง %s ถึง %s แล้วไล่หาบัญชีที่ทำให้ไม่สมดุล' % (
            _thai_date(dfrom), _thai_date(dto))
        return check

    def _check_unreconciled(self, year, dfrom, dto):
        check = self._blank('unreconciled', u'ลูกหนี้-เจ้าหนี้ที่ยังไม่กระทบยอด',
                            u'Open Items',
                            u'Invoicing > Reporting > OCA accounting reports > Open Items')
        Line = self.env['account.move.line'].sudo()
        # o18: ชนิดบัญชีอยู่ที่ account_account.account_type ไม่ใช่ user_type_id แล้ว
        domain = [('company_id', '=', self._company().id),
                  ('parent_state', '=', 'posted'),
                  ('date', '<=', dto),
                  ('reconciled', '=', False),
                  ('account_id.account_type', 'in', list(RECEIVABLE_PAYABLE_TYPES))]
        count = Line.search_count(domain)
        if not count:
            check['found'] = u'กระทบยอดครบแล้ว'
            check['need'] = u'—'
            return check
        # ฝั่งลูกหนี้เป็นบวก ฝั่งเจ้าหนี้เป็นลบ ถ้ารวมตรง ๆ จะหักล้างกัน ต้องรวมค่าสัมบูรณ์
        self.env.cr.execute(
            """SELECT COALESCE(SUM(ABS(l.amount_residual)), 0)
                 FROM account_move_line l
                 JOIN account_account a ON a.id = l.account_id
                WHERE l.company_id = %s AND l.parent_state = 'posted'
                  AND l.date <= %s AND l.reconciled = FALSE
                  AND a.account_type IN %s""",
            (self._company().id, dto, RECEIVABLE_PAYABLE_TYPES))
        total = float((self.env.cr.fetchone() or [0.0])[0] or 0.0)
        check['count'] = count
        check['amount'] = total
        check['status'] = 'warn'
        check['found'] = u'ค้าง %s บรรทัด ยอดคงเหลือรวม %s บาท' % (
            '{:,}'.format(count), _money(total))
        check['need'] = (u'ไม่จำเป็นต้องเป็น 0 — ที่เหลือต้องเป็นหนี้ที่ยังค้างชำระจริง '
                         u'ณ %s เท่านั้น' % _thai_date(dto))
        check['fix'] = u'จับคู่ใบแจ้งหนี้กับการรับ/จ่ายชำระที่ค้าง แล้วสอบยอดกับ Aged Partner Balance'
        check['columns'] = [(u'วันที่', 'date'), (u'เลขที่', 'move_name'),
                            (u'คู่ค้า', 'partner_id'), (u'บัญชี', 'account_id'),
                            (u'คงเหลือ', 'amount_residual')]
        check['rows'] = Line.search_read(
            domain, ['date', 'move_name', 'partner_id', 'account_id', 'amount_residual'],
            limit=MAX_EXCEL_ROWS, order='date desc')
        return check

    def _check_assets(self, year, dfrom, dto):
        check = self._blank('assets', u'ค่าเสื่อมราคา', u'Compute Assets',
                            u'Invoicing > Assets > Compute Assets')
        if 'account.asset' not in self.env:
            check['status'] = 'skip'
            check['found'] = u'ฐานนี้ไม่ได้ติดตั้งโมดูลสินทรัพย์'
            return check
        Asset = self.env['account.asset'].sudo()
        company_id = self._company().id
        draft = Asset.search_count([('company_id', '=', company_id), ('state', '=', 'draft')])
        pending, pending_amount = 0, 0.0
        if 'account.asset.line' in self.env:
            Line = self.env['account.asset.line'].sudo()
            line_domain = [('asset_id.company_id', '=', company_id),
                           ('type', '=', 'depreciate'),
                           ('init_entry', '=', False),
                           ('move_check', '=', False),
                           ('line_date', '>=', dfrom), ('line_date', '<=', dto)]
            pending = Line.search_count(line_domain)
            if pending:
                groups = Line.read_group(line_domain, ['amount'], [], lazy=False)
                pending_amount = (groups[0].get('amount') if groups else 0.0) or 0.0
                check['columns'] = [(u'สินทรัพย์', 'asset_id'), (u'งวดวันที่', 'line_date'),
                                    (u'ค่าเสื่อม', 'amount')]
                check['rows'] = Line.search_read(line_domain,
                                                 ['asset_id', 'line_date', 'amount'],
                                                 limit=MAX_EXCEL_ROWS, order='line_date')
        check['count'] = draft + pending
        check['amount'] = pending_amount
        if not draft and not pending:
            check['found'] = u'ค่าเสื่อมลงครบถึงสิ้นปีแล้ว'
            check['need'] = u'—'
            return check
        check['status'] = 'block' if pending else 'warn'
        found, need = [], []
        if draft:
            found.append(u'สินทรัพย์สถานะร่าง %s รายการ' % '{:,}'.format(draft))
            need.append(u'ต้องยืนยันให้ครบอีก %s รายการ' % '{:,}'.format(draft))
        if pending:
            found.append(u'งวดค่าเสื่อมที่ยังไม่ลงบัญชี %s งวด' % '{:,}'.format(pending))
            need.append(u'ยังขาดค่าเสื่อมอีก %s บาท' % _money(pending_amount))
        check['found'] = u' · '.join(found)
        check['need'] = u' · '.join(need)
        check['fix'] = (u'ยืนยันสินทรัพย์ที่ยังเป็นร่างที่ Invoicing > Assets > Assets '
                        u'แล้วสั่ง Compute Assets จากนั้น Post ใบ JE ค่าเสื่อม')
        return check

    def _check_result(self, year, dfrom, dto):
        u"""กำไร(ขาดทุน) ของปี -- ตัวเลขที่ต้องยกเข้ากำไรสะสม"""
        check = self._blank('pl_result', u'กำไร(ขาดทุน) ของปี', u'MIS Reports',
                            u'Invoicing > Reporting > MIS Reporting > MIS Reports')
        self.env.cr.execute(
            """SELECT COALESCE(SUM(CASE WHEN a.account_type IN %s THEN l.balance END), 0),
                      COALESCE(SUM(CASE WHEN a.account_type IN %s THEN l.balance END), 0)
                 FROM account_move_line l
                 JOIN account_account a ON a.id = l.account_id
                WHERE l.company_id = %s AND l.parent_state = 'posted'
                  AND l.date >= %s AND l.date <= %s""",
            (INCOME_TYPES, EXPENSE_TYPES, self._company().id, dfrom, dto))
        row = self.env.cr.fetchone() or (0.0, 0.0)
        income = -float(row[0] or 0.0)      # รายได้เป็นเครดิต -> balance ติดลบ
        expense = float(row[1] or 0.0)
        profit = income - expense
        check['amount'] = profit
        check['found'] = u'รายได้ %s − ค่าใช้จ่าย %s = %s %s' % (
            _money(income), _money(expense), _money(abs(profit)),
            u'กำไร' if profit >= 0 else u'ขาดทุน')
        check['need'] = u'ตัวเลขนี้ต้องตรงกับงบกำไรขาดทุนที่พิมพ์เก็บไว้'
        check['fix'] = u'พิมพ์งบกำไรขาดทุนเก็บไว้ก่อนล็อกวันที่'
        return check

    def _check_unaffected_earnings(self, year, dfrom, dto):
        u"""ยอดในบัญชี "กำไร(ขาดทุน) ที่ยังไม่ได้จัดสรร" ณ สิ้นงวด

        o18 ยกยอดข้ามปีให้เองผ่านบัญชีชนิด equity_unaffected
        """
        check = self._blank('unaffected', u'กำไร(ขาดทุน) ที่ยังไม่ได้จัดสรร',
                            u'General Ledger',
                            u'Invoicing > Reporting > OCA accounting reports > General Ledger')
        self.env.cr.execute(
            """SELECT COALESCE(SUM(l.balance), 0)
                 FROM account_move_line l
                 JOIN account_account a ON a.id = l.account_id
                WHERE l.company_id = %s AND l.parent_state = 'posted'
                  AND l.date <= %s AND a.account_type = %s""",
            (self._company().id, dto, UNAFFECTED_TYPE))
        balance = float((self.env.cr.fetchone() or [0.0])[0] or 0.0)
        check['amount'] = abs(balance)
        check['found'] = u'ยอดสะสม ณ %s = %s บาท' % (_thai_date(dto), _money(-balance))
        check['need'] = u'เป็นตัวชี้ว่ากำไรปีก่อน ๆ ถูกยกเข้ากำไรสะสมแล้วหรือยัง'
        check['fix'] = u'ถ้ายอดค้างอยู่มาก ให้ลงใบปรับปรุงโอนเข้ากำไรสะสม'
        return check

    def _check_month_gaps(self, year, dfrom, dto):
        check = self._blank('month_gaps', u'เดือนที่ไม่มีรายการเลย', u'Journal Entries',
                            u'Invoicing > Accounting > Journal Entries')
        self.env.cr.execute(
            """SELECT DISTINCT EXTRACT(MONTH FROM date)::int
                 FROM account_move
                WHERE company_id = %s AND state = 'posted'
                  AND date >= %s AND date <= %s""",
            (self._company().id, dfrom, dto))
        have = {row[0] for row in self.env.cr.fetchall()}
        today = date.today()
        months = []
        cursor = date(dfrom.year, dfrom.month, 1)
        while cursor <= dto:
            if cursor <= today:
                months.append(cursor.month)
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
        missing = [m for m in months if m not in have]
        if not missing:
            check['found'] = u'มีรายการครบทุกเดือน'
            check['need'] = u'—'
            return check
        check['status'] = 'warn'
        check['count'] = len(missing)
        check['found'] = u'เดือน %s ไม่มีรายการลงบันทึกเลย' % u', '.join(str(m) for m in missing)
        check['need'] = u'ยืนยันว่าเดือนนั้นไม่มีรายการจริง ไม่ใช่ลืมลง'
        check['fix'] = u'ถ้าเป็นเดือนที่ยังไม่ได้เปิดใช้ระบบ ถือว่าปกติ'
        return check

    def _check_date_range(self, year, dfrom, dto):
        u"""ช่วงวันที่ "ปีบัญชี" ของปีนั้น (o18 ใช้ date.range แทน account.fiscal.year)

        รายงาน MIS/OCA เลือกงวดจาก date.range ถ้าปีนั้นยังไม่มีช่วง จะออกงบ
        เทียบปีไม่ได้ (โมดูล npd_l10n_th_account_closing สร้างล่วงหน้าให้ด้วย cron)
        """
        check = self._blank('date_range', u'ช่วงวันที่ปีบัญชี', u'MIS Reports',
                            u'Invoicing > Reporting > MIS Reporting > MIS Reports')
        if 'date.range' not in self.env:
            check['status'] = 'skip'
            check['found'] = u'ฐานนี้ไม่มีโมดูลช่วงวันที่'
            return check
        found = self.env['date.range'].sudo().search([
            ('company_id', 'in', (self._company().id, False)),
            ('date_start', '<=', dfrom), ('date_end', '>=', dto),
        ], limit=1)
        if found:
            check['found'] = u'%s (%s – %s)' % (found.name, _thai_date(found.date_start),
                                                _thai_date(found.date_end))
            check['need'] = u'—'
            return check
        check['status'] = 'warn'
        check['found'] = u'ยังไม่มีช่วงวันที่ครอบคลุมปี %s' % year
        check['need'] = u'ต้องมี 1 ช่วง: %s ถึง %s' % (_thai_date(dfrom), _thai_date(dto))
        check['fix'] = (u'ปกติระบบสร้างให้เองทุกวัน ถ้ายังไม่มีให้แจ้ง IT '
                        u'ตรวจประเภทช่วงวันที่ "ปีบัญชี" ของบริษัทนี้')
        return check

    def _check_mis_reports(self, year, dfrom, dto):
        u"""แม่แบบงบการเงินของบริษัทนี้ -- ไม่มีก็พิมพ์งบดุล/งบกำไรขาดทุนไม่ได้"""
        check = self._blank('mis_reports', u'แม่แบบงบการเงิน (MIS)', u'MIS Reports',
                            u'Invoicing > Reporting > MIS Reporting > MIS Reports')
        if 'mis.report.instance' not in self.env:
            check['status'] = 'skip'
            check['found'] = u'ฐานนี้ไม่ได้ติดตั้งรายงาน MIS'
            return check
        instances = self.env['mis.report.instance'].sudo().search(
            [('company_id', '=', self._company().id)])
        if instances:
            check['found'] = u'มี %s รายงาน (%s)' % (
                len(instances), u' · '.join(instances.mapped('name')[:3]))
            check['need'] = u'—'
            return check
        check['status'] = 'warn'
        check['found'] = u'บริษัทนี้ยังไม่มีแม่แบบงบการเงิน'
        check['need'] = u'ต้องมีงบแสดงฐานะการเงินและงบกำไรขาดทุนอย่างละ 1 รายงาน'
        check['fix'] = u'แจ้ง IT ให้ตั้งรายงาน MIS ของบริษัทนี้ (ตั้งได้จากโมดูลตั้งค่าปิดงบไทย)'
        return check

    def _check_lock_dates(self, year, dfrom, dto):
        u"""บน o18 การล็อกวันที่ = การปิดงบ ตัวนี้จึงเป็นตัวชี้ขาด

        o18 ไม่มี period_lock_date แล้ว และเพิ่ม hard_lock_date ที่ย้อนกลับไม่ได้
        """
        check = self._blank('lock_dates', u'การล็อกวันที่ (= การปิดงบของ o18)',
                            u'Settings',
                            u'Invoicing > Configuration > Settings (Fiscal Periods / Lock Dates)')
        company = self._company()
        fiscal = company.fiscalyear_lock_date
        tax = company.tax_lock_date
        hard = getattr(company, 'hard_lock_date', False)
        check['found'] = u'ล็อกงวด %s · ล็อกภาษี %s · ล็อกถาวร %s' % (
            _thai_date(fiscal), _thai_date(tax), _thai_date(hard))
        if fiscal and fiscal >= dto:
            check['need'] = u'—'
            check['fix'] = (u'ล็อกเรียบร้อยแล้ว ถ้าต้องแก้ย้อนหลังให้เลื่อนวันออกชั่วคราว '
                            u'(ยกเว้น Hard Lock Date ที่ย้อนกลับไม่ได้)')
            return check
        check['status'] = 'block'
        check['need'] = u'ต้องตั้ง Lock Date = %s จึงถือว่าปิดงบปีนี้แล้ว' % _thai_date(dto)
        check['fix'] = (u'ทำขั้นที่ 1–3 ให้ครบก่อน แล้วค่อยตั้ง Lock Date '
                        u'ส่วน Hard Lock Date ใส่เมื่อส่งงบแล้วเท่านั้น เพราะย้อนกลับไม่ได้')
        return check

    @api.model
    def run_checks(self, year):
        u"""รันตัวตรวจทั้งหมดของปีนั้น (อ่านอย่างเดียว)

        ตัวตรวจตัวไหนพังไม่ควรทำให้ทั้งหัวข้อพัง จึงห่อ try ทีละตัว
        """
        dfrom, dto = self.fiscal_window(year)
        checkers = [
            self._check_draft_moves, self._check_balance, self._check_unreconciled,
            self._check_assets, self._check_month_gaps, self._check_result,
            self._check_unaffected_earnings, self._check_date_range,
            self._check_mis_reports, self._check_lock_dates,
        ]
        results = []
        for checker in checkers:
            try:
                results.append(checker(year, dfrom, dto))
            except Exception as exc:  # noqa: BLE001
                _logger.warning(u'ช่วยปิดงบ: ตัวตรวจ %s ของปี %s ล้ม (%s)',
                                checker.__name__, year, exc)
                broken = self._blank(checker.__name__, checker.__name__, u'', u'')
                broken['status'] = 'skip'
                broken['found'] = u'ตรวจรายการนี้ไม่สำเร็จ'
                results.append(broken)
        return results

    @api.model
    def verdict(self, year, checks=None):
        u"""ฟันธงว่าปีนั้นปิดงบสมบูรณ์แล้วหรือยัง

        o18 ไม่มีใบปิดบัญชี "ปิดงบสมบูรณ์" จึงหมายถึง
        ไม่มีรายการติดค้าง และล็อกวันที่ครอบถึงวันสิ้นงวดแล้ว
        """
        checks = checks if checks is not None else self.run_checks(year)
        blocking = [c for c in checks if c['status'] == 'block']
        warnings = [c for c in checks if c['status'] == 'warn']
        dfrom, dto = self.fiscal_window(year)
        return {
            'year': year,
            'date_from': dfrom,
            'date_to': dto,
            'complete': not blocking,
            'blocking': blocking,
            'warnings': warnings,
            'checks': checks,
        }

    # ==================================================================
    # จัดรูปคำตอบสำหรับแชท
    # ==================================================================
    @api.model
    def steps_blocks(self):
        blocks = [u'<b>ปิดงบใน Odoo 18 มี 4 ขั้น เรียงกันเสมอ ห้ามสลับ</b>']
        rows = [u'<tr><th style="text-align:left">ขั้น</th>'
                u'<th style="text-align:left">ทำอะไร</th>'
                u'<th style="text-align:left">ทำไมต้องลำดับนี้</th></tr>']
        for step in CLOSING_STEPS:
            rows.append(u'<tr><td>%s</td><td><b>%s</b></td><td>%s</td></tr>' % (
                step['order'], html_escape(step['title']), html_escape(step['why'])))
        blocks.append(u'<table class="table table-sm" style="width:100%%">%s</table>'
                      % u''.join(rows))
        blocks.append(u'<span class="text-muted">พิมพ์ "ขั้นที่ 1" ถึง "ขั้นที่ 4" '
                      u'เพื่อดูเมนูของแต่ละขั้น</span>')
        return blocks

    @api.model
    def step_detail_blocks(self, order):
        step = next((s for s in CLOSING_STEPS if s['order'] == order), None)
        if not step:
            return []
        blocks = [u'<b>ขั้นที่ %s — %s</b><br/><span class="text-muted">%s</span>'
                  % (step['order'], html_escape(step['title']), html_escape(step['goal']))]
        rows = [u'<tr><th style="text-align:left">ทำอะไร</th>'
                u'<th style="text-align:left">เมนู</th>'
                u'<th style="text-align:left">ผ่านเมื่อไร</th></tr>']
        for item in step['items']:
            rows.append(u'<tr><td><b>%s</b><br/><span class="text-muted">%s</span></td>'
                        u'<td>%s</td><td>%s</td></tr>' % (
                            html_escape(item['name']), html_escape(item['what']),
                            html_escape(self._item_menu_text(item)),
                            html_escape(item['pass'])))
        blocks.append(u'<table class="table table-sm" style="width:100%%">%s</table>'
                      % u''.join(rows))
        return blocks

    @api.model
    def verdict_line(self, year, checks=None, verdict=None):
        u"""บรรทัดฟันธงสั้น ๆ ต่อท้ายทุกคำตอบ"""
        verdict = verdict or self.verdict(year, checks=checks)
        if verdict['complete']:
            text = u'<b>🟢 สรุป: ปี %s ปิดงบสมบูรณ์แล้ว</b>' % year
            if verdict['warnings']:
                text += u'<br/><span class="text-muted">ยังมีเรื่องที่ควรดูอีก %s รายการ</span>' \
                        % len(verdict['warnings'])
            return text
        titles = u' · '.join(c['title'] for c in verdict['blocking'][:5])
        return (u'<b>🔴 สรุป: ปี %s ยังปิดงบไม่สมบูรณ์ — ติด %s เรื่อง</b>'
                u'<br/><span class="text-muted">%s</span>'
                u'<br/><span class="text-muted">พิมพ์ "ตรวจปี %s" '
                u'เพื่อดูว่าต้องแก้เท่าไหร่และทำที่เมนูไหน</span>'
                % (year, len(verdict['blocking']), html_escape(titles), year))

    @api.model
    def checks_blocks(self, year, checks=None, verdict=None):
        checks = checks if checks is not None else self.run_checks(year)
        verdict = verdict or self.verdict(year, checks=checks)
        blocks = []
        if verdict['complete']:
            head = u'<b>🟢 ปี %s ปิดงบสมบูรณ์แล้ว</b>' % year
            if verdict['warnings']:
                head += u'<br/>เหลือเรื่องที่ควรดู %s รายการ' % len(verdict['warnings'])
        else:
            head = (u'<b>🔴 ปี %s ยังปิดงบไม่สมบูรณ์</b><br/>ติด <b>%s เรื่อง</b>'
                    % (year, len(verdict['blocking'])))
            if verdict['warnings']:
                head += u' · ควรดูอีก %s เรื่อง' % len(verdict['warnings'])
        head += (u'<br/><span class="text-muted">%s · งวด %s ถึง %s</span>'
                 % (html_escape(self._company().name or u''),
                    _thai_date(verdict['date_from']), _thai_date(verdict['date_to'])))
        blocks.append(head)

        rows = [u'<tr><th style="text-align:left">รายการ</th>'
                u'<th style="text-align:left">ที่พบ</th>'
                u'<th style="text-align:left">เท่าไหร่ถึงจะถูก</th></tr>']
        for check in checks:
            rows.append(u'<tr><td>%s <b>%s</b></td><td>%s</td><td>%s</td></tr>' % (
                STATUS_ICON.get(check['status'], u''), html_escape(check['title']),
                html_escape(check['found'] or u'—'), html_escape(check['need'] or u'—')))
        blocks.append(u'<table class="table table-sm" style="width:100%%">%s</table>'
                      % u''.join(rows))

        if verdict['blocking']:
            fixes = []
            for check in verdict['blocking']:
                fixes.append(u'<div class="mb-1"><b>%s</b><br/>%s<br/>'
                             u'<span class="text-muted">เมนู: %s</span></div>' % (
                                 html_escape(check['title']),
                                 html_escape(check['fix'] or check['need'] or u''),
                                 html_escape(self._item_menu_text(
                                     {'find': check['menu_find'], 'path': check['menu_path']}))))
            blocks.append(u'<b>วิธีแก้ เรียงตามลำดับที่ควรทำ</b>%s' % u''.join(fixes))
        return blocks

    @api.model
    def years_blocks(self, years):
        rows = [u'<tr><th style="text-align:left">ปี</th>'
                u'<th style="text-align:left">สถานะ</th>'
                u'<th style="text-align:left">ติดที่</th></tr>']
        details = []
        for year in years:
            verdict = self.verdict(year)
            details.append(verdict)
            if verdict['complete']:
                status, blocked = u'🟢 ปิดสมบูรณ์', u'—'
            else:
                status = u'🔴 ยังไม่สมบูรณ์'
                blocked = u' · '.join(c['title'] for c in verdict['blocking'][:4]) or u'—'
            rows.append(u'<tr><td>%s (พ.ศ. %s)</td><td>%s</td><td>%s</td></tr>'
                        % (year, year + 543, status, html_escape(blocked)))
        blocks = [u'<b>สรุปสถานะการปิดงบแต่ละปี — %s</b>'
                  % html_escape(self._company().name or u''),
                  u'<table class="table table-sm" style="width:100%%">%s</table>'
                  % u''.join(rows),
                  u'<span class="text-muted">พิมพ์ "ปี 2026" เพื่อดูรายละเอียดทีละปี</span>']
        return blocks, details

    @api.model
    def search_guide(self, keyword):
        u"""หารายการในคู่มือที่ตรงกับคำค้น -- รองรับคำไทย

        เมนู o18 เป็นภาษาอังกฤษเกือบทั้งหมด แต่บัญชีถามเป็นไทย การค้น ir.ui.menu
        ตรง ๆ จึงไม่เจอ ต้องผ่านคู่มือที่เก็บชื่อไทยคู่กับชื่ออังกฤษไว้ก่อน
        """
        keyword = (keyword or u'').strip().lower()
        if len(keyword) < 2:
            return []
        hits = []
        for step in CLOSING_STEPS:
            for item in step['items']:
                haystack = u' '.join([item['name'], item['what'], item['path'],
                                      item['find']]).lower()
                if keyword in haystack:
                    hits.append((step, item))
        return hits

    @api.model
    def menu_blocks(self, keyword):
        u"""คืน [] ถ้าไม่รู้จริง ๆ เพื่อให้ผู้เรียกส่งต่อให้ AI ตอบแทน"""
        blocks = []
        hits = self.search_guide(keyword)
        if hits:
            rows = []
            for step, item in hits[:4]:
                rows.append(u'<div class="mb-2"><b>%s</b><br/>%s<br/>'
                            u'<span class="text-muted">เอาไว้ %s · อยู่ในขั้นที่ %s (%s)</span>'
                            u'</div>' % (
                                html_escape(item['name']),
                                html_escape(self._item_menu_text(item)),
                                html_escape(item['what']), step['order'],
                                html_escape(step['title'])))
            blocks.append(u'<b>เมนูที่เกี่ยวกับ "%s"</b>' % html_escape(keyword))
            blocks += rows

        found = self.find_menus(keyword, limit=4)
        known = u' '.join(blocks)
        extra = [item for item in found if item['path'] not in known]
        if extra:
            rows = []
            for item in extra:
                note = u'' if item['visible'] else \
                    u'<br/><span class="text-muted">สิทธิ์ของคุณยังไม่เห็นเมนูนี้ — ' \
                    u'ให้ IT เพิ่มสิทธิ์บัญชีให้</span>'
                rows.append(u'<div class="mb-1">%s%s</div>' % (html_escape(item['path']), note))
            if not blocks:
                blocks.append(u'<b>เมนูที่ใกล้เคียง "%s"</b>' % html_escape(keyword))
            blocks += rows
        return blocks

    # ==================================================================
    # ไฟล์ Excel
    # ==================================================================
    @api.model
    def build_excel(self, years):
        u"""คืน (ชื่อไฟล์, ไบต์, จำนวนแถว) -- (None, None, 0) ถ้าสร้างไม่ได้"""
        if not xlsxwriter:
            return None, None, 0
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        head = book.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1,
                                'font_name': 'Tahoma', 'font_size': 10, 'text_wrap': True,
                                'valign': 'top'})
        text = book.add_format({'font_name': 'Tahoma', 'font_size': 10, 'valign': 'top'})
        wrap = book.add_format({'font_name': 'Tahoma', 'font_size': 10, 'text_wrap': True,
                                'valign': 'top'})
        money = book.add_format({'num_format': '#,##0.00', 'font_name': 'Tahoma',
                                 'font_size': 10})
        title = book.add_format({'bold': True, 'font_name': 'Tahoma', 'font_size': 12})

        summary = book.add_worksheet(u'เช็คลิสต์ปิดงบ')
        headers = [u'ปี', u'สถานะ', u'รายการ', u'ที่พบ', u'เท่าไหร่ถึงจะถูก',
                   u'เมนูที่ต้องไปทำ', u'วิธีแก้']
        widths = [8, 14, 30, 44, 44, 50, 50]
        for index, header in enumerate(headers):
            summary.write(0, index, header, head)
            summary.set_column(index, index, widths[index])
        summary.freeze_panes(1, 0)

        row_index = 1
        total_rows = 0
        detail_sheets = []
        for year in years:
            checks = self.run_checks(year)
            verdict = self.verdict(year, checks=checks)
            for check in checks:
                summary.write(row_index, 0, year, text)
                summary.write(row_index, 1, STATUS_LABEL.get(check['status'], u''), text)
                summary.write(row_index, 2, check['title'], wrap)
                summary.write(row_index, 3, check['found'] or u'-', wrap)
                summary.write(row_index, 4, check['need'] or u'-', wrap)
                summary.write(row_index, 5, check['menu_path'] or u'-', wrap)
                summary.write(row_index, 6, check['fix'] or u'-', wrap)
                row_index += 1
                total_rows += 1
                if check['rows']:
                    detail_sheets.append((year, check))
            summary.write(row_index, 0, year, text)
            summary.write(row_index, 1, u'สรุป', text)
            summary.write(row_index, 2,
                          u'ปิดงบสมบูรณ์' if verdict['complete'] else u'ยังปิดงบไม่สมบูรณ์', wrap)
            summary.write(row_index, 3,
                          u'ติด %s เรื่อง / ควรดู %s เรื่อง'
                          % (len(verdict['blocking']), len(verdict['warnings'])), wrap)
            row_index += 2

        used_names = set()
        for year, check in detail_sheets:
            name = (u'%s-%s' % (year, check['title']))[:28]
            suffix = 1
            while name in used_names:
                suffix += 1
                name = (u'%s-%s(%s)' % (year, check['title'], suffix))[:28]
            used_names.add(name)
            sheet = book.add_worksheet(name)
            sheet.write(0, 0, u'%s ปี %s' % (check['title'], year), title)
            headers = [column[0] for column in check['columns']]
            keys = [column[1] for column in check['columns']]
            for index, header in enumerate(headers):
                sheet.write(2, index, header, head)
                sheet.set_column(index, index, max(14, min(40, len(header) + 10)))
            sheet.freeze_panes(3, 0)
            for offset, record in enumerate(check['rows']):
                for col_index, key in enumerate(keys):
                    value = record.get(key)
                    if isinstance(value, (list, tuple)) and len(value) == 2:
                        sheet.write(3 + offset, col_index, str(value[1] or u''), text)
                    elif value in (False, None):
                        sheet.write(3 + offset, col_index, u'', text)
                    elif isinstance(value, (int, float)) and not isinstance(value, bool):
                        sheet.write_number(3 + offset, col_index, value, money)
                    else:
                        sheet.write(3 + offset, col_index, str(value)[:200], text)
                total_rows += 1

        book.close()
        label = u'-'.join(str(y) for y in years) or str(date.today().year)
        return u'ปิดงบ-%s.xlsx' % label, stream.getvalue(), total_rows

    # ==================================================================
    # ตอบคำถามอิสระด้วย AI
    # ==================================================================
    @api.model
    def _kb_text(self):
        parts = []
        for step in CLOSING_STEPS:
            lines = [u'ขั้นที่ %s %s — %s (เหตุผล: %s)'
                     % (step['order'], step['title'], step['goal'], step['why'])]
            for item in step['items']:
                lines.append(u'  - %s | เมนู: %s | ทำอะไร: %s | ผ่านเมื่อ: %s'
                             % (item['name'], item['path'], item['what'], item['pass']))
            parts.append(u'\n'.join(lines))
        parts.append(u'อาการที่เจอบ่อย:\n' + u'\n'.join(
            u'  - %s => สาเหตุ: %s => แก้: %s' % row for row in PITFALLS))
        parts.append(u'ข้อควรรู้ของ Odoo 18: ไม่มีใบปิดบัญชี/แม่แบบใบปิดแบบ Odoo 14 แล้ว '
                     u'ระบบยกยอดงบดุลข้ามปีให้เองผ่านบัญชีกำไร(ขาดทุน)ที่ยังไม่ได้จัดสรร '
                     u'การปิดงบจึงจบที่การล็อกวันที่ และ Hard Lock Date ย้อนกลับไม่ได้')
        return u'\n\n'.join(parts)

    @api.model
    def _checks_text(self, year, checks):
        lines = [u'ผลตรวจจริงของปี %s (ค.ศ.) / พ.ศ. %s บริษัท %s:'
                 % (year, year + 543, self._company().name or u'')]
        for check in checks:
            lines.append(u'  - [%s] %s | พบ: %s | ต้องเป็น: %s | เมนู: %s'
                         % (STATUS_LABEL.get(check['status'], check['status']),
                            check['title'], check['found'] or u'-',
                            check['need'] or u'-', check['menu_path'] or u'-'))
        return u'\n'.join(lines)

    @api.model
    def ai_answer(self, question, year, checks, history=None, extra=None):
        u"""ให้ AI ตอบคำถามอิสระ โดยห้ามออกนอกข้อมูลที่ให้ไป"""
        Gemini = self.env['npd.ai.it.gemini']
        if not Gemini.is_available():
            return [], u'ยังไม่ได้ตั้งค่า AI Key'

        menu_hits = []
        for word in re.findall(r'[A-Za-z][A-Za-z ]{2,}', question or u''):
            for item in self.find_menus(word.strip(), limit=2):
                if item['path'] not in menu_hits:
                    menu_hits.append(item['path'])
        for step in CLOSING_STEPS:
            for item in step['items']:
                if item['name'] in (question or u''):
                    path = self._item_menu_text(item)
                    if path not in menu_hits:
                        menu_hits.append(path)

        history_text = u''
        if history:
            history_text = u'\nคำถามก่อนหน้า (ใช้ต่อยอดได้):\n%s\n' % json.dumps(
                history, ensure_ascii=False)[:800]

        prompt = (
            u'คุณเป็นผู้ช่วยฝ่ายบัญชีของบริษัทให้เช่าอุปกรณ์ก่อสร้าง ที่ใช้ Odoo 18\n'
            u'ตอบคำถามเรื่อง "การปิดงบสิ้นปี" ให้นักบัญชีเข้าใจ\n\n'
            u'=== คู่มือปิดงบของระบบนี้ (ข้อมูลจริง ห้ามขัดแย้ง) ===\n%s\n\n'
            u'=== ผลตรวจจากฐานข้อมูลจริง ===\n%s\n%s\n'
            u'=== เมนูจริงที่ค้นเจอในระบบนี้ ===\n%s\n'
            u'%s\n'
            u'=== คำถาม ===\n"""%s"""\n\n'
            u'กติกาการตอบ\n'
            u'- ตอบสั้น สรุป แบบที่นักบัญชีอ่านแล้วทำงานต่อได้ทันที ห้ามเยิ่นเย้อ\n'
            u'- อ้างตัวเลขได้เฉพาะตัวเลขที่อยู่ในผลตรวจข้างบนเท่านั้น ห้ามคิดเลขใหม่เอง\n'
            u'- อ้างชื่อเมนูได้เฉพาะที่อยู่ในคู่มือหรือรายการเมนูจริงข้างบนเท่านั้น '
            u'ห้ามแต่งชื่อเมนูขึ้นมาเอง และห้ามอ้างเมนูของ Odoo 14 ที่ไม่มีใน o18 '
            u'(เช่น Fiscal year closings, Closing templates, Cut-offs)\n'
            u'- ถ้าคำถามอยู่นอกเรื่องปิดงบ ให้ตอบ {"error": "เหตุผลสั้น ๆ"}\n'
            u'- ถ้าข้อมูลที่ให้มาไม่พอจะตอบ ให้บอกตรง ๆ ว่าต้องไปดูเมนูไหนเพิ่ม\n\n'
            u'ตอบเป็น JSON เท่านั้น\n'
            u'{\n'
            u'  "answer": "คำตอบหลัก 1-3 ประโยค",\n'
            u'  "bullets": ["ข้อย่อยสั้น ๆ ไม่เกิน 4 ข้อ"],\n'
            u'  "menus": ["เส้นทางเมนูที่ต้องไป ถ้ามี"]\n'
            u'}'
            % (self._kb_text(), self._checks_text(year, checks), extra or u'',
               u'\n'.join(u'  - %s' % path for path in menu_hits[:12]) or u'  (ไม่มี)',
               history_text, (question or u'')[:600])
        )
        data = Gemini.extract_json(prompt, max_output_tokens=2048)
        if not data:
            return [], u'เรียก AI ไม่สำเร็จ'
        if data.get('error'):
            return [], str(data['error'])[:300]

        blocks = []
        answer = str(data.get('answer') or u'').strip()
        if answer:
            blocks.append(html_escape(answer))
        bullets = [str(b).strip() for b in (data.get('bullets') or []) if str(b).strip()]
        if bullets:
            blocks.append(u'<ul class="mb-0 pl-4">%s</ul>' % u''.join(
                u'<li>%s</li>' % html_escape(b) for b in bullets[:4]))
        menus = [str(m).strip() for m in (data.get('menus') or []) if str(m).strip()]
        if menus:
            blocks.append(u'<span class="text-muted">เมนู</span><br/>%s' % u'<br/>'.join(
                html_escape(m) for m in menus[:4]))
        if not blocks:
            return [], u'AI ตอบกลับมาว่าง'
        return blocks, u''

    # ==================================================================
    # ทางเข้าเดียวที่ session เรียกใช้
    # ==================================================================
    @api.model
    def wants_excel(self, question):
        text = (question or u'').lower()
        return any(word in text for word in EXCEL_WORDS)

    @api.model
    def strip_excel_words(self, question):
        text = question or u''
        for word in EXCEL_WORDS:
            text = text.replace(word, u' ').replace(word.upper(), u' ')
        for word in (u'ขอ', u'เป็น', u'ให้', u'หน่อย', u'ครับ', u'ค่ะ', u'ด้วย', u'ที'):
            text = text.replace(word, u' ')
        return u' '.join(text.split())

    @api.model
    def _has(self, question, words):
        text = (question or u'').lower()
        return any(word in text for word in words)

    @api.model
    def answer(self, question, history=None, years=None):
        u"""คืน (blocks, meta, error)"""
        question = (question or u'').strip()
        parsed = self.parse_years(question)
        meta = {'years': years or parsed or [self.default_year()], 'kind': 'ai'}

        # พิมพ์แค่ "ขอเป็นไฟล์ Excel" -> แสดงเช็คลิสต์ของปีเดิมซ้ำ ไม่ต้องเรียก AI
        if self.wants_excel(question) and len(self.strip_excel_words(question)) < 8:
            meta['kind'] = 'checks'
            if len(meta['years']) > 1:
                blocks, _details = self.years_blocks(meta['years'])
                return blocks, meta, u''
            return self.checks_blocks(meta['years'][0]), meta, u''

        # 1) ขอแผนที่ขั้นตอน
        step_match = re.search(u'ขั้น(?:ที่)?\\s*([1-4])', question)
        if step_match:
            meta['kind'] = 'steps'
            blocks = self.step_detail_blocks(int(step_match.group(1)))
            return blocks + [self.verdict_line(meta['years'][0])], meta, u''
        if self._has(question, STEP_WORDS) and not self._has(question, CHECK_WORDS):
            meta['kind'] = 'steps'
            return (self.steps_blocks() + [self.verdict_line(meta['years'][0])],
                    meta, u'')

        # 2) ขอผลตรวจ (หลายปี / ปีเดียว)
        wants_check = self._has(question, CHECK_WORDS) or bool(parsed) or bool(years)
        if wants_check:
            meta['kind'] = 'checks'
            if len(meta['years']) > 1:
                blocks, details = self.years_blocks(meta['years'])
                if not self._has(question, CHECK_WORDS) and details:
                    summary = u'สถานะปีอื่นที่ถามมาด้วย:\n' + u'\n'.join(
                        u'  - ปี %s: %s%s' % (
                            item['year'],
                            u'ปิดงบสมบูรณ์แล้ว' if item['complete'] else u'ยังไม่สมบูรณ์',
                            u'' if item['complete'] else u' (ติด %s)' % u', '.join(
                                c['title'] for c in item['blocking'][:4]))
                        for item in details[:-1])
                    extra, _error = self.ai_answer(
                        question, details[-1]['year'], details[-1]['checks'],
                        history=history, extra=summary)
                    blocks += extra
                return blocks, meta, u''
            year = meta['years'][0]
            checks = self.run_checks(year)
            blocks = self.checks_blocks(year, checks=checks)
            if not self._has(question, CHECK_WORDS):
                extra, _error = self.ai_answer(question, year, checks, history=history)
                blocks += extra
            return blocks, meta, u''

        # 3) ถามหาเมนู
        if self._has(question, MENU_WORDS):
            keyword = question
            for word in MENU_WORDS + (u'อยู่', u'ที่', u'ไหน', u'ขอ', u'หน่อย', u'ครับ', u'ค่ะ'):
                keyword = keyword.replace(word, u' ')
            keyword = u' '.join(keyword.split())
            if keyword:
                blocks = self.menu_blocks(keyword)
                if blocks:
                    meta['kind'] = 'menu'
                    return (blocks + [self.verdict_line(meta['years'][0])],
                            meta, u'')
                # หาไม่เจอ -> ตกไปให้ AI ตอบ ดีกว่าตอบว่า "ไม่พบ" แล้วจบ

        # 4) คำถามอิสระ -> AI (มีผลตรวจของปีล่าสุดเป็นบริบทเสมอ)
        year = meta['years'][0]
        checks = self.run_checks(year)
        blocks, error = self.ai_answer(question, year, checks, history=history)
        if not error:
            blocks = blocks + [self.verdict_line(year, checks=checks)]
            return blocks, meta, u''
        fallback = self.steps_blocks()
        fallback.append(u'<span class="text-muted">ตอบคำถามนี้ตรง ๆ ไม่ได้ (%s) '
                        u'จึงสรุปขั้นตอนกับผลตรวจปี %s ให้แทน</span>'
                        % (html_escape(error), year))
        fallback += self.checks_blocks(year, checks=checks)
        meta['kind'] = 'fallback'
        return fallback, meta, u''
