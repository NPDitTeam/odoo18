# -*- coding: utf-8 -*-
"""ข้อมูลสำหรับรายงาน "ขอให้รีบชำระหนี้ค้างตามสัญญาเช่า"

รายงานนี้เป็นหนังสือทวงถามที่ออกจากหน้ารวมหนี้ลูกค้า เนื้อหาอ้างถึงสัญญาเช่า
ที่ลูกค้ายังค้างชำระ พร้อมตารางสรุปยอดหนี้ค้างชำระท้ายเอกสาร

การจับคู่ยอดในหนังสือกับแท็บบนหน้าจอ (ตกลงกับผู้ใช้ 19 ส.ค. 2026 ฝั่ง o14):
    1. ค่าเช่า                      = แท็บใบแจ้งหนี้ค่าเช่า
    2. ค่าเช่าเกินกำหนด             = แท็บค่าเช่าส่วนต่าง
    3. ค่าปรับเสียหายหรือสูญหาย     = แท็บค่าปรับหาย + แท็บค่าปรับชำรุด
    4. ค่าขนส่ง                     = แท็บค่าขนส่ง
    5. ค่าใช้จ่ายอื่นๆ               = แท็บใบแจ้งหนี้ค่าประกัน + แท็บค่าหัก ณ ที่จ่าย

ผู้ใช้ระบุ 28 ส.ค. 2026: หนังสือฉบับนี้จะดึงเฉพาะเอกสารค้างชำระที่ตกอยู่ใน
สถานะติดตามหนี้ที่ติ๊ก "เริ่มแสดงที่รายงาน" ไว้เท่านั้น (เมนู กำหนดสถานะติดตามหนี้)

เลขที่สัญญาเช่าดึงจาก sale.order.rental_contract_full (o18 อยู่ในโมดูล
pfb_npd_rental_equipment_contract_jasper) ใบไหนหาสัญญาไม่เจอหรือสัญญาไม่มีเลข
จะไม่พิมพ์บรรทัดเลขที่สัญญาออกมา
"""
import logging
from datetime import date

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# บัญชีรับโอนของแต่ละบริษัท -- o14 แยกด้วยชื่อฐานข้อมูล o18 ใช้คำในชื่อบริษัทแทน
# (ชุดเดียวกับที่ใช้ในใบแจ้งหนี้/ใบวางบิลฝั่ง o14)
COMPANY_BANK_ACCOUNTS = (
    ('เอส กรุ๊ป', 'บริษัท นภดล เอส กรุ๊ป จำกัด', '186-222160-2'),
    ('สตีลเทค', 'บริษัท เอ็นพีดี สตีลเทค จำกัด', '408-582058-4'),
    ('โลจิสติกส์', 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด', '439-044811-6'),
    ('อินเตอร์เทรดดิ้ง', 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด', '408-546107-1'),
    ('กรุงเทพ', 'บริษัท นภดล กรุงเทพ จำกัด', '186-224773-9'),
)
BANK_NAME = 'ธนาคารไทยพาณิชย์'

THAI_MONTHS = [
    '', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]


class NpdDebtSummaryLetter(models.Model):
    _inherit = 'npd.debt.summary'

    # ------------------------------------------------------------------
    # helper ทั่วไป
    # ------------------------------------------------------------------
    @staticmethod
    def letter_thai_date(value):
        """date -> '19 สิงหาคม 2569' (คืนค่าว่างถ้าไม่มีวันที่)"""
        if not value:
            return ''
        return '%d %s %d' % (value.day, THAI_MONTHS[value.month], value.year + 543)

    @staticmethod
    def letter_amount(value):
        return '{:,.2f}'.format(value or 0.0)

    def letter_bank_account(self):
        """ข้อความบัญชีรับโอนของบริษัทที่ออกหนังสือ

        เทียบจากคำในชื่อบริษัท ถ้าไม่เจอจะลองใช้เลขบัญชีธนาคารที่ตั้งไว้ใน
        ข้อมูลบริษัท (res.partner.bank) ถ้ายังไม่มีอีกคืนค่าว่าง
        เทมเพลตจะพิมพ์จุดไข่ปลาให้เขียนมือแทน
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        name = company.name or ''
        for keyword, account_name, number in COMPANY_BANK_ACCOUNTS:
            if keyword in name:
                return '%s เลขที่บัญชี %s ชื่อบัญชี %s' % (BANK_NAME, number, account_name)
        bank = company.partner_id.bank_ids[:1]
        if bank:
            return '%s เลขที่บัญชี %s ชื่อบัญชี %s' % (
                bank.bank_id.name or BANK_NAME, bank.acc_number or '', company.name or '')
        return ''

    def letter_baht_text(self, value):
        """จำนวนเงินเป็นตัวหนังสือ ใช้ helper เดิมของโมดูล"""
        return self._baht(value or 0.0)

    def letter_today_text(self):
        """วันที่พิมพ์หนังสือ แบบไทย (เรียกจากเทมเพลตแทน context_timestamp)"""
        return self.letter_thai_date(fields.Date.context_today(self))

    def letter_user_name(self):
        """ชื่อผู้พิมพ์หนังสือ (ตัวแปร user ไม่ได้มีให้ทุกบริบทของรายงาน o18)"""
        return self.env.user.name or ''

    def _letter_sale_order(self, move):
        """หา sale.order ของใบแจ้งหนี้ 1 ใบ (คืน recordset ว่างถ้าไม่เจอ)

        ไล่หา 3 ทางตามลักษณะของเอกสารแต่ละแบบ
          1. ใบแจ้งหนี้ค่าเช่า/ส่วนต่าง : ผูกผ่านบรรทัดใบสั่งขายตรง ๆ
          2. ใบแจ้งหนี้ค่าประกัน       : ผูกผ่าน sale_order.rent_check (m2m)
          3. ใบเพิ่มหนี้ (ILS/IBK)     : ไม่ผูกกับบรรทัด ใช้ชื่อใน invoice_origin
        """
        SaleOrder = self.env['sale.order'].sudo()
        if not move:
            return SaleOrder
        order = move.invoice_line_ids.mapped('sale_line_ids.order_id')[:1]
        if order:
            return order
        if 'rent_check' in SaleOrder._fields:
            order = SaleOrder.search([('rent_check', 'in', move.id)], limit=1)
            if order:
                return order
        if move.invoice_origin:
            # invoice_origin อาจมีหลายเลขคั่นด้วยจุลภาค เอาตัวแรกที่หาเจอ
            for origin in move.invoice_origin.split(','):
                order = SaleOrder.search([('name', '=', origin.strip())], limit=1)
                if order:
                    return order
        return SaleOrder

    # ------------------------------------------------------------------
    # ข้อมูลหลักของรายงาน
    # ------------------------------------------------------------------
    def _letter_line_groups(self):
        """(ชื่อประเภทที่จะพิมพ์, หมวดยอดในข้อ 1-5, บรรทัดของแท็บนั้น)"""
        self.ensure_one()
        return [
            ('ค่าเช่า', 'rent', self.customer_invoice_line_ids),
            ('ค่าประกัน', 'other', self.customer_deposit_line_ids),
            ('ค่าเช่าเกินกำหนด', 'over', self.customer_rentdiff_line_ids),
            ('ค่าปรับหาย', 'penalty', self.customer_penalty_line_ids),
            ('ค่าปรับชำรุด', 'penalty', self.customer_damage_line_ids),
            ('ค่าขนส่ง', 'transport', self.customer_transport_line_ids),
            ('ค่าหัก ณ ที่จ่าย', 'other', self.customer_tax_line_ids),
        ]

    def _letter_invoice_rows(self):
        """รวมทุกแท็บให้เป็นรายการเดียว เฉพาะใบที่ยังค้างชำระ
        และอยู่ในสถานะติดตามหนี้ที่ติ๊ก "เริ่มแสดงที่รายงาน" ไว้
        """
        self.ensure_one()
        rows = []
        for doc_type, bucket, lines in self._letter_line_groups():
            for line in lines:
                if line.payment_status != 'unpaid':
                    continue
                # ค้างมากี่วันแล้วตกอยู่สถานะไหน ถ้าสถานะนั้นไม่ได้ติ๊กให้ขึ้นรายงาน
                # (หรือยังไม่เข้าช่วงวันของสถานะไหนเลย) ก็ไม่เอาใบนี้เข้าหนังสือ
                if not line.collection_status_id.show_in_report:
                    continue
                amount = getattr(line, 'amount_residual', 0.0)
                if not amount:
                    # แท็บค่าหัก ณ ที่จ่าย ใช้ชื่อฟิลด์ tax_amount
                    amount = getattr(line, 'tax_amount', 0.0)
                # บรรทัดค่าขนส่งเป็นของบริษัทขนส่ง จึงไม่มี invoice_id ให้ไล่หา
                # ใช้เลขเอกสาร SO ต้นทางที่เก็บไว้หาสัญญาแทน
                move = getattr(line, 'invoice_id', False)
                if move:
                    order = self._letter_sale_order(move)
                else:
                    order = self.env['sale.order'].sudo().search(
                        [('name', '=', getattr(line, 'source_so', '') or '')], limit=1)
                rows.append({
                    'doc_type': doc_type,
                    'bucket': bucket,
                    'move': move,
                    'name': line.invoice_name or (move.name if move else ''),
                    'date': getattr(line, 'invoice_date', False)
                            or getattr(line, 'rental_start_date', False),
                    'amount': amount or 0.0,
                    'order': order,
                })
        return rows

    def get_collection_letter_data(self):
        """ข้อมูลทั้งหมดที่เทมเพลตต้องใช้ -- เรียกครั้งเดียวแล้ว t-set เก็บไว้"""
        self.ensure_one()
        rows = self._letter_invoice_rows()
        if not rows:
            # ถ้าปล่อยผ่านจะได้หนังสือทวงถามที่ยอดรวม 0.00 ส่งให้ลูกค้าไม่ได้
            raise UserError(_(
                'พิมพ์หนังสือของ %s ไม่ได้ '
                'เพราะไม่มีเอกสารค้างชำระใบไหนอยู่ในสถานะติดตามหนี้ที่ติ๊ก '
                '"เริ่มแสดงที่รายงาน" ไว้ ตรวจได้ที่คอลัมน์ "สถานะติดตามหนี้" ในแต่ละแท็บ '
                'และที่เมนู ขาย > รวมหนี้ลูกค้า > กำหนดสถานะติดตามหนี้'
            ) % (self.display_name or self.name or ''))

        # จัดกลุ่มตามสัญญาเช่า (ใบที่หาสัญญาไม่เจอ รวมเป็นกลุ่มเดียวท้ายตาราง)
        groups = []
        index = {}
        for row in rows:
            order = row['order']
            key = order.id or 0
            if key not in index:
                contract_no = ''
                if order and 'rental_contract_full' in order._fields:
                    contract_no = order.rental_contract_full or ''
                index[key] = {
                    'contract_no': contract_no,
                    'contract_date': order.date_order.date() if order and order.date_order else False,
                    'order_name': order.name if order else '',
                    'invoices': [],
                    'amount': 0.0,
                }
                groups.append(index[key])
            group = index[key]
            group['invoices'].append(row)
            group['amount'] += row['amount']

        # เรียงตามวันที่ของสัญญา/ใบสั่งขาย (ไม่มีวันที่ไปท้ายสุด)
        groups.sort(key=lambda g: (g['contract_date'] is False,
                                   g['contract_date'] or date.min,
                                   g['contract_no']))
        for seq, group in enumerate(groups, start=1):
            group['seq'] = seq

        # ยอดคิดจาก rows ที่ผ่านการกรองแล้วเท่านั้น ไม่ใช้ยอดรวมที่เก็บไว้บนหัวเอกสาร
        amounts = {'rent': 0.0, 'over': 0.0, 'penalty': 0.0, 'transport': 0.0, 'other': 0.0}
        for row in rows:
            amounts[row['bucket']] += row['amount']
        amounts['total'] = sum(amounts.values())

        # ข้อ 1-5 ในหนังสือ: ตัดข้อที่ยอดเป็น 0 ออก แล้วเรียงเลขใหม่ให้ต่อกัน
        items = [
            ('ค่าเช่า', amounts['rent']),
            ('ค่าเช่าเกินกำหนด', amounts['over']),
            ('ค่าปรับเสียหายหรือสูญหาย', amounts['penalty']),
            ('ค่าขนส่ง', amounts['transport']),
            ('ค่าใช้จ่ายอื่นๆ', amounts['other']),
        ]

        # หัวเรื่อง/ย่อหน้าเปิด: เอ่ยเฉพาะประเภทที่ลูกค้ารายนี้ค้างจริง
        topics = [label for label, amount in (
            ('ค่าเช่าเกินกำหนด', amounts['over']),
            ('ค่าปรับเสียหายหรือสูญหาย', amounts['penalty']),
            ('ค่าขนส่ง', amounts['transport']),
        ) if abs(amount) >= 0.005]

        # อ้างถึง: 1 บรรทัดต่อ 1 สัญญา นับจำนวนใบแจ้งหนี้ในสัญญานั้น
        refs = [g for g in groups if g['contract_no'] or g['order_name']]
        return {
            'groups': groups,
            'refs': refs,
            'amounts': amounts,
            'items': [{'label': label, 'amount': amount}
                      for label, amount in items if abs(amount) >= 0.005],
            'topics': topics,
            'topics_text': (' ' + ' '.join(topics)) if topics else '',
            'has_transport': abs(amounts['transport']) >= 0.005,
        }
