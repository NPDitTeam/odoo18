# -*- coding: utf-8 -*-
u"""หัวข้อที่ 5 : แก้การปัดเศษ VAT ในใบแจ้งหนี้ (สลับได้ทั้งไปและกลับ)

ปัญหาที่เจอหน้างาน
    ลูกค้าทักว่า "ยอดก่อน VAT ต่างจากที่คิดไว้ 1 สตางค์" เช่น ยอดรวม 4,515.00
        แบบรายบรรทัด  ก่อน VAT 4,219.62 + VAT 295.38   <- ค่าตั้งต้นของระบบ
        แบบยอดรวม     ก่อน VAT 4,219.63 + VAT 295.37   <- ที่ลูกค้ามักคิดเอง
    ทั้งคู่ถูกทางเลข ต่างกันแค่ "ปัดเศษตอนไหน"

เมนูนี้ทำอะไร
    สลับใบนั้นไปมาระหว่างสองแบบได้ โดย "ยอดรวมทั้งใบไม่เปลี่ยน" — ย้ายแค่
    เศษสตางค์ระหว่างช่องฐานกับช่อง VAT  ที่ต้องถอยกลับได้เพราะบางทีแก้ให้
    ลูกค้ารายหนึ่งแล้ว อีกฝ่าย (บัญชี/สรรพากร) ขอให้กลับเป็นแบบเดิม

ทำไมต้องเขียนด้วย SQL
    amount_untaxed / amount_tax / price_subtotal เป็น stored compute ถ้าเขียนผ่าน
    ORM Odoo จะคำนวณทับกลับทันที โมดูล npd_rent_price_round ที่คุมการปัดเศษของ
    ระบบนี้ก็เขียนด้วย SQL ด้วยเหตุผลเดียวกัน

ต้องแก้ครบ 4 ที่ ไม่งั้นบัญชีเพี้ยน
    1. บรรทัดรายได้      — แบบยอดรวมใช้ largest remainder, แบบรายบรรทัดหารทีละบรรทัด
    2. บรรทัดภาษี        — ยอดภาษี + ฐานภาษี (tax_base_amount)
    3. หัวใบแจ้งหนี้      — amount_untaxed / amount_tax (+ _signed)
    4. account_move_tax_invoice — ตารางที่ใช้ออกรายงานภาษีขาย (ภ.พ.30)
       ข้อ 4 คือข้อที่ลืมกันบ่อยที่สุด ลืมแล้วใบกับรายงานภาษีจะไม่ตรงกัน
"""
import logging
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from markupsafe import Markup

import odoo
from odoo import SUPERUSER_ID, api, models

_logger = logging.getLogger(__name__)

# อัตรา VAT ที่เมนูนี้รองรับ (ระบบนี้ใช้ภาษีแบบรวมในราคา price_include)
VAT_RATE = Decimal('7')

# เพดานส่วนต่างที่ยอมให้แก้ (บาท)
# เมนูนี้มีไว้แก้ "เศษปัด" เท่านั้น ห้ามกลายเป็นเครื่องมือแก้ยอดตามใจ
# ถ้าคำนวณแล้วต่างเกินนี้ แปลว่าใบนั้นผิดจากเรื่องอื่น ต้องให้คนดู
MAX_DIFF = Decimal('0.05')

CENT = Decimal('0.01')

# สองแบบที่สลับไปมาได้
MODE_TOTAL = 'total'
MODE_LINE = 'line'
MODES = (MODE_TOTAL, MODE_LINE)

MODE_NAME = {
    MODE_TOTAL: u'แบบยอดรวม',
    MODE_LINE: u'แบบรายบรรทัด',
}
MODE_HOW = {
    MODE_TOTAL: u'ปัด VAT ครั้งเดียวจากยอดรวมทั้งใบ',
    MODE_LINE: u'ปัด VAT ทีละบรรทัดแล้วค่อยรวมกัน',
}
MODE_WHO = {
    MODE_TOTAL: u'แบบที่ลูกค้าคิดเองจากใบเสร็จ (ยอดรวม ÷ 1.07)',
    MODE_LINE: u'ค่าตั้งต้นของระบบ Odoo',
}


def _d(value):
    u"""float -> Decimal ที่ไม่เพี้ยนเพราะ binary float"""
    return Decimal(str(value or 0))


def _q(value, rounding=ROUND_HALF_UP):
    return _d(value).quantize(CENT, rounding=rounding)


def _money(value):
    return '{:,.2f}'.format(float(value or 0))


class NpdAiItVatFix(models.AbstractModel):
    _name = 'npd.ai.it.vat.fix'
    _description = u'ตัวช่วย AI-IT : แก้การปัดเศษ VAT ในใบแจ้งหนี้'

    # ------------------------------------------------------------------
    # หาเอกสาร
    # ------------------------------------------------------------------
    @api.model
    def find_move(self, text):
        u"""คืน (move, error_message) — รับได้ทั้ง URL และเลขที่ใบแจ้งหนี้"""
        move, error = self.env['npd.ai.it.invoice.fix'].find_move(text)
        if error or not move:
            return None, error

        if move.move_type not in ('out_invoice', 'out_refund'):
            return None, (u'เอกสาร <b>%s</b> ไม่ใช่ใบแจ้งหนี้ขายหรือใบลดหนี้ขาย<br/>'
                          u'เมนูนี้ใช้ได้เฉพาะเอกสารฝั่งขายเท่านั้น'
                          % (move.name or move.id))
        return move, None

    @api.model
    def mode_name(self, mode):
        return MODE_NAME.get(mode, u'—')

    # ------------------------------------------------------------------
    # คำนวณว่าใบนี้เป็นแบบไหน และอีกแบบจะได้เท่าไร
    # ------------------------------------------------------------------
    @api.model
    def analyze(self, move):
        u"""คืน (plan, error_message)

        plan เป็น dict ธรรมดา (เก็บลง data_json ของ session ได้) มีตัวเลขของ
        ทั้งสองแบบให้เลือก  error_message มีค่าเมื่อใบนี้ "แก้ไม่ได้"
        """
        move = move.sudo()

        error = self._blocking_reason(move)
        if error:
            return None, error

        product_lines = move.line_ids.filtered(
            lambda l: l.display_type == 'product')
        tax_line = move.line_ids.filtered(lambda l: l.display_type == 'tax' and l.tax_line_id)[0]

        gross = sum((_q(l.price_total) for l in product_lines), Decimal('0'))
        old_untaxed = sum((_q(l.price_subtotal) for l in product_lines),
                          Decimal('0'))
        old_tax = _q(move.amount_tax)

        # หัวใบต้องตรงกับผลรวมของบรรทัด ไม่งั้นใบนี้เพี้ยนมาก่อนแล้ว
        # อย่าไปแก้ซ้ำเข้าไปอีก ให้คนดูก่อน
        if _q(move.amount_untaxed) != old_untaxed:
            return None, (u'ยอดก่อน VAT ที่หัวใบ (%s) ไม่ตรงกับผลรวมของบรรทัด (%s)<br/>'
                          u'ใบนี้ผิดปกติมาก่อนแล้ว กรุณาแจ้งฝ่าย IT ตรวจก่อน'
                          % (_money(move.amount_untaxed), _money(old_untaxed)))

        modes = {
            MODE_TOTAL: self._plan_total_mode(product_lines, gross),
            MODE_LINE: self._plan_line_mode(product_lines),
        }

        current_mode = None
        for mode in MODES:
            plan = modes[mode]
            plan['is_current'] = (_q(plan['untaxed']) == old_untaxed
                                  and _q(plan['tax']) == old_tax)
            plan['diff_tax'] = float(_q(plan['tax']) - old_tax)
            if plan['is_current'] and current_mode is None:
                current_mode = mode

        # ทั้งสองแบบให้ผลเท่ากัน = ใบนี้ปัดแล้วลงตัวพอดี ไม่มีอะไรให้เลือก
        same = (_q(modes[MODE_TOTAL]['untaxed']) == _q(modes[MODE_LINE]['untaxed'])
                and _q(modes[MODE_TOTAL]['tax']) == _q(modes[MODE_LINE]['tax']))

        return {
            'move_id': move.id,
            'move_name': move.name or '',
            'gross': float(gross),
            'old_untaxed': float(old_untaxed),
            'old_tax': float(old_tax),
            'current_mode': current_mode,      # None = ไม่ตรงกับแบบไหนเลย
            'same': same,
            'tax_line_id': tax_line.id,
            'modes': {m: self._public(modes[m]) for m in MODES},
        }, None

    @api.model
    def _blocking_reason(self, move):
        u"""คืนข้อความห้ามแก้ — คืน None เมื่อใบนี้แก้ได้"""
        # ---- ต้องลงบันทึกแล้ว ----
        # ถ้าแก้ด้วย SQL ตอนร่าง Odoo จะคำนวณทับกลับตอนบันทึกครั้งถัดไปอยู่ดี
        # (o18 ไม่มีช่อง "คำนวณ VAT จากยอดรวม" แบบ o14)
        if move.state != 'posted':
            state_label = dict(
                move._fields['state']._description_selection(self.env)
            ).get(move.state, move.state)
            return (u'ใบ <b>%s</b> ยังเป็น <b>"%s"</b> ไม่ใช่ใบที่ลงบันทึกแล้ว<br/>'
                    u'ใบฉบับร่างระบบจะคำนวณยอดใหม่ทุกครั้งที่บันทึก จึงแก้ด้วยเมนูนี้ไม่ได้ '
                    u'กรุณาลงบันทึกใบนี้ก่อน แล้วค่อยกลับมาใช้เมนูนี้'
                    % (move.name or move.id, state_label))

        # ---- สกุลเงินต้องเป็นสกุลเดียวกับบริษัท ----
        # ใบสกุลต่างประเทศมีทั้ง balance และ amount_currency คนละอัตรา
        # ต้องแปลงค่าเพิ่ม เกินขอบเขตของเมนูนี้
        if move.currency_id != move.company_id.currency_id:
            return (u'ใบ <b>%s</b> เป็นสกุลเงิน <b>%s</b> ไม่ใช่ %s<br/>'
                    u'เมนูนี้ยังไม่รองรับเอกสารสกุลเงินต่างประเทศ '
                    u'กรุณาแจ้งฝ่าย IT'
                    % (move.name or '', move.currency_id.name or '?',
                       move.company_id.currency_id.name or '?'))

        product_lines = move.line_ids.filtered(
            lambda l: l.display_type == 'product')
        tax_lines = move.line_ids.filtered(lambda l: l.display_type == 'tax' and l.tax_line_id)

        if not product_lines:
            return u'ใบ <b>%s</b> ไม่มีบรรทัดสินค้า' % (move.name or '')

        # ---- ต้องเป็น VAT 7% ตัวเดียวทั้งใบ ----
        if len(tax_lines) != 1:
            return (u'ใบ <b>%s</b> มีบรรทัดภาษี <b>%d</b> บรรทัด<br/>'
                    u'เมนูนี้รองรับเฉพาะใบที่มีภาษีมูลค่าเพิ่ม 7% '
                    u'อย่างเดียวทั้งใบ' % (move.name or '', len(tax_lines)))

        tax = tax_lines[0].tax_line_id
        if abs(_d(tax.amount) - VAT_RATE) > Decimal('0.01'):
            return (u'ภาษีของใบ <b>%s</b> คือ <b>%s%%</b> ไม่ใช่ 7%%<br/>'
                    u'เมนูนี้รองรับเฉพาะภาษีมูลค่าเพิ่ม 7%%'
                    % (move.name or '', tax.amount))
        if not tax.price_include:
            return (u'ภาษีของใบ <b>%s</b> ตั้งเป็นแบบ "แยกนอกราคา"<br/>'
                    u'เมนูนี้รองรับเฉพาะภาษีแบบรวมในราคา (price include)'
                    % (move.name or ''))

        # ทุกบรรทัดสินค้าต้องผูกภาษีตัวเดียวกันนี้ ถ้ามีบรรทัดยกเว้นภาษีปนอยู่
        # การหารยอดรวมด้วย 1.07 ทั้งก้อนจะผิดทันที
        for line in product_lines:
            if line.tax_ids != tax:
                return (u'บรรทัด "<b>%s</b>" ผูกภาษีไม่ตรงกับบรรทัดอื่น<br/>'
                        u'เมนูนี้รองรับเฉพาะใบที่ทุกบรรทัดใช้ VAT 7% '
                        u'เหมือนกันหมด' % (line.name or ''))
        return None

    @api.model
    def _public(self, plan):
        u"""ตัดค่าที่เป็น Decimal ออก ให้เหลือเฉพาะที่เก็บลง JSON ได้"""
        return {
            'untaxed': float(plan['untaxed']),
            'tax': float(plan['tax']),
            'is_current': plan.get('is_current', False),
            'diff_tax': plan.get('diff_tax', 0.0),
            'lines': plan['lines'],
        }

    # ------------------------------------------------------------------
    # แบบที่ 1 : ปัดครั้งเดียวจากยอดรวม
    # ------------------------------------------------------------------
    @api.model
    def _plan_total_mode(self, product_lines, gross):
        tax = _q(gross * VAT_RATE / (Decimal('100') + VAT_RATE))
        untaxed = gross - tax
        return {
            'untaxed': untaxed,
            'tax': tax,
            'lines': self._allocate(product_lines, untaxed),
        }

    @api.model
    def _allocate(self, product_lines, target_untaxed):
        u"""กระจายยอดฐานรวมลงแต่ละบรรทัด ให้ผลรวมเท่ากับ target_untaxed เป๊ะ

        วิธี largest remainder: ปัดลงทุกบรรทัดก่อน แล้วแจกสตางค์ที่เหลือให้
        บรรทัดที่ "เศษทศนิยมมากที่สุด" ก่อน — เป็นวิธีเดียวกับที่ใช้แบ่งที่นั่ง
        ตามสัดส่วน ยุติธรรมและได้ผลเหมือนเดิมทุกครั้งที่คำนวณซ้ำ
        """
        divisor = Decimal('1') + VAT_RATE / Decimal('100')

        rows = []
        for line in product_lines:
            raw = _d(line.price_total) / divisor
            floor = raw.quantize(CENT, rounding=ROUND_DOWN)
            rows.append({
                'id': line.id,
                'name': line.name or '',
                'gross': _q(line.price_total),
                'old': _q(line.price_subtotal),
                'value': floor,
                'remainder': raw - floor,
            })

        allocated = sum((r['value'] for r in rows), Decimal('0'))
        cents_left = int(((target_untaxed - allocated) / CENT)
                         .quantize(Decimal('1'), rounding=ROUND_HALF_UP))

        # เรียงตามเศษมาก -> น้อย  เศษเท่ากันให้บรรทัดยอดมากกว่าได้ก่อน
        # (ผูก id ไว้ท้ายสุดเพื่อให้ลำดับคงที่เสมอ ไม่สลับไปมาระหว่างการคำนวณ)
        order = sorted(
            range(len(rows)),
            key=lambda i: (rows[i]['remainder'], rows[i]['gross'], -rows[i]['id']),
            reverse=True,
        )

        step = CENT if cents_left >= 0 else -CENT
        for n in range(abs(cents_left)):
            rows[order[n % len(order)]]['value'] += step

        return [self._line_row(r) for r in rows]

    # ------------------------------------------------------------------
    # แบบที่ 2 : ปัดทีละบรรทัด (ค่าตั้งต้นของ Odoo)
    # ------------------------------------------------------------------
    @api.model
    def _plan_line_mode(self, product_lines):
        u"""ทำแบบเดียวกับ account.tax._compute_amount ของ Odoo เป๊ะ ๆ

        ภาษีรวมในราคา: ภาษีของบรรทัด = ปัด(ยอดรวมบรรทัด × 7 ÷ 107)
        แล้วฐาน = ยอดรวมบรรทัด − ภาษี  จากนั้นค่อยเอามาบวกกันทั้งใบ
        """
        rows = []
        total_tax = Decimal('0')
        total_untaxed = Decimal('0')
        for line in product_lines:
            gross = _q(line.price_total)
            tax = _q(gross * VAT_RATE / (Decimal('100') + VAT_RATE))
            value = gross - tax
            total_tax += tax
            total_untaxed += value
            rows.append({
                'id': line.id,
                'name': line.name or '',
                'gross': gross,
                'old': _q(line.price_subtotal),
                'value': value,
            })
        return {
            'untaxed': total_untaxed,
            'tax': total_tax,
            'lines': [self._line_row(r) for r in rows],
        }

    @api.model
    def _line_row(self, row):
        return {
            'id': row['id'],
            'name': row['name'],
            'gross': float(row['gross']),
            'old': float(row['old']),
            'new': float(row['value']),
        }

    # ------------------------------------------------------------------
    # ลงมือแก้
    # ------------------------------------------------------------------
    @api.model
    def apply_fix_isolated(self, move_id, mode, note=u'', actor_name=None):
        u"""แก้ในทรานแซกชันแยก (เหตุผลเดียวกับหัวข้ออื่น — ดู ai_it_invoice_fix)

        ถ้าเขียนในทรานแซกชันเดียวกับแชท แล้วมีอะไรพังทีหลัง ข้อความที่พนักงาน
        เพิ่งพิมพ์จะถูก rollback หายไปด้วย
        """
        self.env['account.move'].flush_model()

        registry = odoo.registry(self.env.cr.dbname)
        with registry.cursor() as new_cr:
            new_env = api.Environment(new_cr, SUPERUSER_ID, dict(self.env.context))
            move = new_env['account.move'].browse(move_id)
            if not move.exists():
                raise ValueError(u'ไม่พบใบแจ้งหนี้ id=%s' % move_id)
            result = new_env['npd.ai.it.vat.fix'].apply_fix(
                move, mode, note=note, actor_name=actor_name)

        self.env['account.move'].invalidate_model()
        self.env['account.move.line'].invalidate_model()
        return result

    @api.model
    def apply_fix(self, move, mode, note=u'', actor_name=None):
        if mode not in MODES:
            raise ValueError(u'ไม่รู้จักวิธีคำนวณ "%s"' % mode)

        actor_name = actor_name or self.env.user.display_name
        move = move.sudo()

        # เช็คซ้ำก่อนเขียนจริง — ใบอาจถูกแก้ระหว่างที่คุยกันอยู่ในแชท
        move.invalidate_recordset()
        plan, error = self.analyze(move)
        if error:
            raise ValueError(error)

        target = plan['modes'][mode]
        old_untaxed = _q(plan['old_untaxed'])
        old_tax = _q(plan['old_tax'])
        new_untaxed = _q(target['untaxed'])
        new_tax = _q(target['tax'])

        result = dict(plan, mode=mode, applied=False,
                      new_untaxed=float(new_untaxed), new_tax=float(new_tax))

        if new_untaxed == old_untaxed and new_tax == old_tax:
            return result       # เป็นแบบนี้อยู่แล้ว ไม่ต้องแตะอะไร

        # ด่านสุดท้ายก่อนเขียน: ต่างกันได้แค่เศษสตางค์
        if abs(new_tax - old_tax) > MAX_DIFF:
            raise ValueError(
                u'ยกเลิกการแก้: ยอด VAT จะเปลี่ยนไป %s บาท ซึ่งเกิน %s บาท '
                u'เมนูนี้มีไว้แก้เศษปัดทศนิยมเท่านั้น'
                % (_money(new_tax - old_tax), _money(MAX_DIFF)))

        cr = self.env.cr
        lines_by_id = {l.id: l for l in move.line_ids}

        # ---- 1) บรรทัดรายได้ ----
        for item in target['lines']:
            if _q(item['new']) == _q(item['old']):
                continue
            self._write_amount(cr, lines_by_id[item['id']], _q(item['new']))

        # ---- 2) บรรทัดภาษี ----
        tax_line = lines_by_id[plan['tax_line_id']]
        self._write_amount(cr, tax_line, new_tax, also_price_unit=True,
                           tax_base_amount=new_untaxed)

        # ---- 3) หัวใบแจ้งหนี้ ----
        # รักษาเครื่องหมายของฟิลด์ _signed ตามที่เอกสารนี้ใช้อยู่เดิม
        # (ใบลดหนี้เก็บเป็นลบ ใบแจ้งหนี้เก็บเป็นบวก)
        sign = self._signed_sign(move)
        cr.execute("""
            UPDATE account_move
               SET amount_untaxed = %s,
                   amount_tax = %s,
                   amount_untaxed_signed = %s,
                   amount_tax_signed = %s
             WHERE id = %s
        """, (new_untaxed, new_tax,
              new_untaxed * sign, new_tax * sign, move.id))
        # o18 มีคอลัมน์ยอดตามสกุลเงินเอกสารเพิ่ม (ใบนี้สกุลเดียวกับบริษัท ค่าจึงเท่ากัน)
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'account_move' AND column_name = 'amount_untaxed_in_currency_signed'
        """)
        if cr.fetchone():
            cr.execute("UPDATE account_move SET amount_untaxed_in_currency_signed = %s WHERE id = %s",
                       (new_untaxed * sign, move.id))

        # ---- 4) ตารางใบกำกับภาษีไทย (ใช้ออกรายงานภาษีขาย/ภ.พ.30) ----
        self._sync_thai_tax_invoice(cr, move, tax_line, new_untaxed, new_tax)

        # ---- ด่านปิดท้าย: สมุดรายวันต้องยังสมดุล ----
        cr.execute("""
            SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0),
                   COALESCE(SUM(amount_currency), 0)
              FROM account_move_line
             WHERE move_id = %s
        """, (move.id,))
        debit, credit, amount_currency = cr.fetchone()
        if _q(debit) != _q(credit) or _q(amount_currency) != Decimal('0'):
            # raise = ทรานแซกชันแยกนี้ถูก rollback ทั้งก้อน ใบกลับเป็นค่าเดิม
            raise ValueError(
                u'ยกเลิกการแก้: สมุดรายวันไม่สมดุล (เดบิต %s / เครดิต %s / '
                u'ผลรวม amount_currency %s)'
                % (_money(debit), _money(credit), _money(amount_currency)))

        # ---- บันทึกลงประวัติของเอกสาร ----
        body = Markup(u'<b>ตัวช่วย AI-IT</b> เปลี่ยนวิธีปัดเศษ VAT เป็น <b>%s</b> โดย %s<br/>'
                      u'ยอดก่อน VAT: %s → <b>%s</b><br/>'
                      u'ภาษีมูลค่าเพิ่ม 7%%: %s → <b>%s</b><br/>'
                      u'ยอดรวมทั้งสิ้น: %s (ไม่เปลี่ยนแปลง)') % (
            MODE_NAME[mode], actor_name,
            _money(old_untaxed), _money(new_untaxed),
            _money(old_tax), _money(new_tax),
            _money(plan['gross']))
        if note:
            body += Markup(u'<br/>เหตุผล: %s') % note
        move.message_post(body=body, message_type='notification')

        _logger.info(
            u'ตัวช่วย AI-IT: %s เปลี่ยนวิธีปัด VAT ของ account.move id=%s (%s) '
            u'เป็น %s — ฐาน %s -> %s / VAT %s -> %s',
            actor_name, move.id, move.name, mode,
            old_untaxed, new_untaxed, old_tax, new_tax,
        )
        result['applied'] = True
        return result

    # ------------------------------------------------------------------
    # ตัวช่วยระดับล่าง
    # ------------------------------------------------------------------
    @api.model
    def _write_amount(self, cr, line, amount, also_price_unit=False,
                      tax_base_amount=None):
        u"""เขียนยอดใหม่ลงบรรทัดเดียว โดย "คงข้างเดบิต/เครดิตเดิมไว้"

        ห้ามเดาข้างจาก move_type — ใบลดหนี้กับใบแจ้งหนี้กลับข้างกัน
        อ่านจากค่าปัจจุบันของบรรทัดนั้นปลอดภัยกว่า
        """
        direction = Decimal('-1') if _d(line.balance) < 0 else Decimal('1')
        balance = amount * direction
        debit = balance if balance > 0 else Decimal('0')
        credit = -balance if balance < 0 else Decimal('0')

        columns = ['price_subtotal = %s', 'debit = %s', 'credit = %s',
                   'balance = %s', 'amount_currency = %s']
        params = [amount, debit, credit, balance, balance]

        if also_price_unit:
            # บรรทัดภาษีของ o14 เก็บยอดไว้ใน price_unit และ price_total ด้วย
            # o18 ปกติเป็น 0 — เขียนเฉพาะช่องที่มีค่าอยู่เดิม จะได้ไม่สร้างค่าที่ Odoo ไม่ได้ใช้
            if line.price_unit:
                columns.insert(0, 'price_unit = %s')
                params.insert(0, amount)
            if line.price_total:
                columns.append('price_total = %s')
                params.append(amount)
        if tax_base_amount is not None:
            columns.append('tax_base_amount = %s')
            params.append(tax_base_amount)

        params.append(line.id)
        cr.execute('UPDATE account_move_line SET %s WHERE id = %%s'
                   % ', '.join(columns), tuple(params))

    @api.model
    def _signed_sign(self, move):
        u"""เครื่องหมายของฟิลด์ *_signed ที่เอกสารนี้ใช้อยู่"""
        if move.amount_untaxed and move.amount_untaxed_signed:
            return Decimal('-1') if move.amount_untaxed_signed < 0 else Decimal('1')
        return Decimal('-1') if move.move_type == 'out_refund' else Decimal('1')

    @api.model
    def _sync_thai_tax_invoice(self, cr, move, tax_line, new_untaxed, new_tax):
        u"""อัปเดตตาราง account_move_tax_invoice ของ l10n_th_tax_invoice

        ตารางนี้คือตัวที่ใช้ออกรายงานภาษีขาย ถ้าไม่อัปเดตตาม ใบแจ้งหนี้กับ
        รายงานภาษีจะไม่ตรงกัน (เป็นจุดที่ลืมกันบ่อยที่สุดตอนแก้ยอดด้วยมือ)
        ฐานข้อมูลที่ไม่ได้ติดตั้งโมดูลนี้ก็ข้ามไปเฉย ๆ
        """
        cr.execute("SELECT to_regclass('account_move_tax_invoice')")
        if not cr.fetchone()[0]:
            return

        # ใบลดหนี้เก็บยอดเป็นลบ (l10n ใส่เครื่องหมายตอนสร้างด้วย reverse)
        sign = Decimal('-1') if move.move_type == 'out_refund' else Decimal('1')
        cr.execute("""
            UPDATE account_move_tax_invoice
               SET tax_base_amount = %s,
                   balance = %s
             WHERE move_line_id = %s
        """, (new_untaxed * sign, new_tax * sign, tax_line.id))
