# -*- coding: utf-8 -*-
"""ตั้งรูปแบบเลขที่ใบรับ/จ่ายชำระ และเลขรายการบันทึกบัญชีของสมุดรายวันรับ/จ่ายชำระ ให้ตรงกับ Odoo 14

o14 แยกฐานละบริษัท แต่ละบริษัทตั้งรูปแบบไว้ไม่เหมือนกัน (ข้อมูลจริงจาก production o14 15 ก.ย. 2569)
    - เอส กรุ๊ป / สตีลเทค ใช้ เดือนวันปี (091526) ที่เหลือใช้ ปีเดือนวัน (260915)
    - อินเตอร์เทรดดิ้ง RVINS/RVILS/RVIBK และ กรุงเทพ RVILS ใช้ปี 4 หลัก (20260915)
    - กรุงเทพ สมุด RVIBK เลขขึ้นต้น IBK-
    - จ่ายชำระของ กรุงเทพ/อินเตอร์เทรดดิ้ง = SUPPOUT-2026-0352 (เลขวิ่งต่อเนื่อง ไม่มีช่วงรายวัน)
    - RCN = RCN-202609-1373 เลขวิ่งทั้งปี (o18 ตั้งเป็นช่วงรายวัน เลขจะกลับเป็น 0001 ทุกวันและซ้ำกัน)
o18 อยู่ฐานเดียว ทุกบริษัทใช้ sequence customer.payment ร่วมกัน เลขจึงปนกันข้ามบริษัท
และตั้งรูปแบบเหมือนกันหมด

ฟังก์ชันรันซ้ำได้ (ไม่สร้างซ้ำ ไม่ย้อนเลขที่ออกไปแล้ว)
"""
import logging
import re
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# (คำในชื่อบริษัท,
#  เลขใบรับ/จ่ายชำระ {code: (prefix ของ sequence, strftime ของ prefix ช่วงรายวัน หรือ None = ไม่ใช้ช่วง)},
#  สมุดรายวัน {code: strftime ของ prefix ช่วงรายวัน หรือ 'year' = เลขวิ่งทั้งปี},
#  prefix ของ sequence สมุดรายวันที่ต่างจาก o18 {code: prefix})
O14_NUMBERING = (
    ('โลจิสติกส์',
     {'customer.payment': ('CUST.IN-%(prefix)s-', '%y%m%d'),
      'supplier.payment': ('SUPP.OUT-%(prefix)s-', '%m%d%y')},
     {'PVV': '%y%m%d', 'RVV': '%y%m%d'},
     {}),
    ('กรุงเทพ',
     {'customer.payment': ('CUST.IN-%(prefix)s-', '%y%m%d'),
      'supplier.payment': ('SUPPOUT-%(year)s-', None)},
     {'PVV': '%y%m%d', 'RVV': '%y%m%d', 'RVINS': '%y%m%d', 'RVILS': '%Y%m%d',
      'RVIBK': '%y%m%d', 'RCN': 'year'},
     {'RVIBK': 'IBK-%(prefix)s'}),
    ('อินเตอร์เทรดดิ้ง',
     {'customer.payment': ('CUST.IN-%(prefix)s-', '%y%m%d'),
      'supplier.payment': ('SUPPOUT-%(year)s-', None)},
     {'PVV': '%y%m%d', 'RVV': '%y%m%d', 'RVINS': '%Y%m%d', 'RVILS': '%Y%m%d',
      'RVIBK': '%Y%m%d', 'RCN': 'year'},
     {}),
    ('เอส กรุ๊ป',
     {'customer.payment': ('CUST.IN-%(prefix)s-', '%y%m%d'),
      'supplier.payment': ('SUPP.OUT-%(prefix)s-', '%m%d%y')},
     {'PVV': '%m%d%y', 'RVV': '%m%d%y', 'RVINS': '%m%d%y', 'RVILS': '%m%d%y',
      'RVIBK': '%m%d%y', 'RCN': 'year'},
     {}),
    ('สตีลเทค',
     {'customer.payment': ('CUST.IN-%(prefix)s-', '%m%d%y'),
      'supplier.payment': ('SUPP.OUT-%(prefix)s-', '%m%d%y')},
     {'PVV': '%m%d%y', 'RVV': '%m%d%y'},
     {}),
)
PAYMENT_SEQUENCE_NAMES = {'customer.payment': 'Customer Payment', 'supplier.payment': 'Supplier Payment'}


def _spec_for(company):
    name = re.sub(r'\s+', ' ', company.name or '')
    for keyword, payment_spec, journal_spec, prefix_spec in O14_NUMBERING:
        if keyword in name:
            return payment_spec, journal_spec, prefix_spec
    return None


class AccountPaymentNumbering(models.Model):
    _inherit = 'account.payment'

    @api.model
    def _npd_thai_today(self):
        return fields.Datetime.context_timestamp(
            self.with_context(tz='Asia/Bangkok'), fields.Datetime.now()).date()

    @api.model
    def _npd_used_numbers(self, company, sequence, prefixes):
        """{prefix ที่แสดงบนเลข: เลขสูงสุดที่ใช้ไปแล้ว} ของบริษัทนี้ (ใช้ตั้ง number_next ไม่ให้ซ้ำ)"""
        used = {}
        if not prefixes:
            return used
        self.env.cr.execute(
            "SELECT name FROM account_payment WHERE company_id = %s AND name LIKE %s",
            (company.id, re.split(r'%\(', sequence.prefix)[0] + '%'),
        )
        for (name,) in self.env.cr.fetchall():
            for prefix in prefixes:
                tail = (name or '')[len(prefix):]
                if name and name.startswith(prefix) and tail.isdigit():
                    used[prefix] = max(used.get(prefix, 0), int(tail))
        return used

    @api.model
    def _npd_setup_payment_numbering(self):
        """ตั้งรูปแบบเลขตาม O14_NUMBERING ให้ทุกบริษัท คืน list ข้อความสรุป"""
        Sequence = self.env['ir.sequence'].sudo()
        DateRange = self.env['ir.sequence.date_range'].sudo()
        year = self._npd_thai_today().year
        year_start, year_end = date(year, 1, 1), date(year, 12, 31)
        summary = []
        for company in self.env['res.company'].sudo().search([]):
            spec = _spec_for(company)
            if not spec:
                summary.append('[%s] ไม่มีรูปแบบจาก o14 ข้าม' % company.name)
                continue
            payment_spec, journal_spec, prefix_spec = spec

            # ---- เลขใบรับ/จ่ายชำระ: sequence แยกบริษัท ----
            for code, (prefix, range_fmt) in payment_spec.items():
                sequence = Sequence.search([('code', '=', code), ('company_id', '=', company.id)], limit=1)
                vals = {'prefix': prefix, 'padding': 4, 'use_date_range': bool(range_fmt),
                        'implementation': 'standard'}
                if not sequence:
                    sequence = Sequence.create(dict(
                        vals, code=code, company_id=company.id, number_next=1,
                        name='%s - %s' % (PAYMENT_SEQUENCE_NAMES[code], company.name)))
                    note = 'สร้าง'
                elif any(sequence[k] != v for k, v in vals.items()):
                    sequence.write(vals)
                    note = 'ปรับ'
                else:
                    note = 'มีอยู่แล้ว'
                if range_fmt:
                    existing = set(DateRange.search([
                        ('sequence_id', '=', sequence.id),
                        ('date_from', '>=', year_start), ('date_to', '<=', year_end),
                    ]).mapped('date_from'))
                    days = [year_start + timedelta(days=i) for i in range((year_end - year_start).days + 1)]
                    missing = [d for d in days if d not in existing]
                    if missing:
                        # สร้างทั้งปีในครั้งเดียว (create_date เดียวกัน) cron ขึ้นปีใหม่จะเดารูปแบบจากชุดนี้ได้
                        DateRange.create([{
                            'sequence_id': sequence.id,
                            'date_from': d, 'date_to': d,
                            'prefix': d.strftime(range_fmt),
                        } for d in missing])
                    note += ' + ช่วงรายวัน %s ช่วง' % len(missing)
                    # เลขที่ใช้ไปแล้ว (เช่นออกจาก sequence กลางก่อนแก้) ต้องต่อเลขไม่ให้ซ้ำ
                    # ตั้งผ่าน number_next_actual หลังสร้าง: ช่วงแบบ standard สร้าง PostgreSQL sequence
                    # ตอน create โดยไม่สนค่า number_next ที่ส่งมา
                    ranges = DateRange.search([('sequence_id', '=', sequence.id),
                                               ('date_from', '>=', year_start), ('date_to', '<=', year_end)])
                    shown = {r: prefix.replace('%(prefix)s', r.prefix or '') for r in ranges}
                    used = self._npd_used_numbers(company, sequence, set(shown.values()))
                    bumped = []
                    for date_range, text in shown.items():
                        if used.get(text) and date_range.number_next_actual <= used[text]:
                            date_range.number_next_actual = used[text] + 1
                            bumped.append('%s%04d' % (text, used[text] + 1))
                    if bumped:
                        note += ' (ต่อเลข %s)' % ', '.join(sorted(bumped))
                else:
                    shown = prefix.replace('%(year)s', str(year))
                    used = self._npd_used_numbers(company, sequence, {shown}).get(shown, 0)
                    if used and sequence.number_next_actual <= used:
                        sequence.number_next_actual = used + 1
                        note += ' (ต่อเลข %s%04d)' % (shown, used + 1)
                summary.append('[%s] %s %s %s' % (company.name, code, prefix, note))

            # ---- เลขรายการบันทึกบัญชีของสมุดรายวันรับ/จ่ายชำระ ----
            for journal_code, fmt in journal_spec.items():
                journal = self.env['account.journal'].sudo().search([
                    ('company_id', '=', company.id), ('code', '=', journal_code),
                    ('type', 'in', ('receivable', 'payable')),
                ], limit=1)
                sequence = journal.sequence_id
                if not sequence:
                    continue
                notes = []
                new_prefix = prefix_spec.get(journal_code)
                if new_prefix and sequence.prefix != new_prefix:
                    notes.append('prefix %s -> %s' % (sequence.prefix, new_prefix))
                    sequence.prefix = new_prefix
                ranges = DateRange.search([
                    ('sequence_id', '=', sequence.id),
                    ('date_from', '>=', year_start), ('date_to', '<=', year_end),
                ])
                daily = ranges.filtered(lambda r: r.date_from == r.date_to)
                if fmt == 'year':
                    numbered_domain = [('journal_id', '=', journal.id), ('state', '=', 'posted'),
                                       ('date', '>=', year_start), ('date', '<=', year_end)]
                    numbered = self.env['account.move'].sudo().search_count(numbered_domain)
                    if daily and numbered:
                        notes.append('มีรายการที่ออกเลขช่วงรายวันแล้ว %s ใบ ไม่เปลี่ยนเป็นเลขวิ่งทั้งปี ต้องตรวจ' % numbered)
                    elif daily:
                        daily.unlink()
                        DateRange.create({'sequence_id': sequence.id,
                                          'date_from': year_start, 'date_to': year_end})
                        notes.append('ช่วงรายวัน %s ช่วง -> เลขวิ่งทั้งปี' % len(daily))
                else:
                    wrong = daily.filtered(lambda r: r.prefix != r.date_from.strftime(fmt))
                    for date_range in wrong:
                        date_range.prefix = date_range.date_from.strftime(fmt)
                    if wrong:
                        notes.append('prefix ช่วงรายวัน %s ช่วง -> %s' % (
                            len(wrong), year_start.replace(month=9, day=15).strftime(fmt)))
                if notes:
                    summary.append('[%s] สมุด %s: %s' % (company.name, journal_code, '; '.join(notes)))

        # ใบที่ออกเลข CUST.IN / SUPP ไปแล้วก่อนแก้ ถือว่าออกเลขแล้ว ไม่ให้ Odoo เปลี่ยนตามเลขรายการบันทึกบัญชี
        self.env.cr.execute("""
            UPDATE account_payment SET npd_number_assigned = TRUE
             WHERE npd_number_assigned IS NOT TRUE
               AND (name LIKE 'CUST.IN-%%' OR name LIKE 'CUST.OUT-%%'
                    OR name LIKE 'SUPP.OUT-%%' OR name LIKE 'SUPPOUT-%%')
        """)
        if self.env.cr.rowcount:
            summary.append('ใบรับ/จ่ายชำระเดิมที่มีเลขแล้ว %s ใบ ล็อกเลขไว้' % self.env.cr.rowcount)
        for line in summary:
            _logger.info('account_payment_sequence: %s', line)
        return summary
