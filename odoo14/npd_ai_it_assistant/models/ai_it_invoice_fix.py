# -*- coding: utf-8 -*-
u"""หัวข้อที่ 2 : แก้ไขวันที่ใบแจ้งหนี้

รับ "URL ของหน้าเอกสาร" แทนเลขที่เอกสาร เพราะใบแจ้งหนี้ฉบับร่างยังไม่มีเลขที่
แต่ใน URL มี id ของเอกสารอยู่เสมอ เช่น

    http://localhost:8079/web#id=66121&model=account.move&view_type=form&cids=1

แล้วแยกทางเดินตาม "ประเภทสินค้า" (account.move.reason_code_id) กับสถานะเอกสาร

    สินค้าหาย / ค่าเช่าส่วนต่าง / สินค้าชำรุด
        ร่าง            -> ให้พนักงานระบุวันที่เอง (ต้องอยู่ในเดือนเดิม)
        ลงบันทึก/ชำระแล้ว -> ยกเลิกการชำระ + ยกเลิกเอกสาร แล้วให้ไปสร้างใหม่

    ใบแจ้งหนี้ค่าเช่า
        ร่าง + สมุดรายวันลดหนี้ขาย -> ให้พนักงานระบุวันที่เอง (ต้องอยู่ในเดือนเดิม)
        ร่าง + สมุดรายวันอื่น      -> ดึง "วันที่สั่งซื้อ" จาก sale.order ที่ผูกไว้
                                     ผ่านฟิลด์ Source Document ใส่ให้เอง
        ลงบันทึก/ชำระแล้ว          -> เหมือนกลุ่มบน

หมายเหตุเรื่องสิทธิ์: การยกเลิกใช้ sudo() ข้ามด่าน user_cancel_control และ
npd_payment_reprocess ตามที่ผู้ใช้ระบุ จึงต้องมีด่านของตัวเองแทน —
เช็คสาขาของพนักงาน + บังคับให้พิมพ์ "ยืนยัน" + เขียน log ทั้งใน session,
chatter ของเอกสาร และ log ฝั่งเซิร์ฟเวอร์
"""
import calendar
import logging
import re

from markupsafe import Markup

import odoo
from odoo import SUPERUSER_ID, api, fields, models

_logger = logging.getLogger(__name__)

# ชื่อประเภทสินค้าใน scrap.reason.code (ยึดชื่อตามที่โมดูลอื่นในระบบใช้อยู่แล้ว)
REASON_LOST = u'สินค้าหาย'
REASON_RENT_DIFF = u'ค่าเช่าส่วนต่าง'
REASON_RENT_INVOICE = u'ใบแจ้งหนี้ค่าเช่า'
REASON_DAMAGED = u'สินค้าชำรุด'

# ประเภทที่ "ฉบับร่าง" ให้พนักงานระบุวันที่เอง
MANUAL_DATE_REASONS = (REASON_LOST, REASON_RENT_DIFF, REASON_DAMAGED)
SUPPORTED_REASONS = MANUAL_DATE_REASONS + (REASON_RENT_INVOICE,)

# สมุดรายวันลดหนี้ขาย — ชื่อ/รหัสต่างกันได้ในแต่ละฐานข้อมูล จึงเปิดให้ตั้งค่าทับได้
CN_JOURNAL_NAMES_PARAM = 'npd_ai_it_assistant.credit_note_journal_names'
CN_JOURNAL_CODES_PARAM = 'npd_ai_it_assistant.credit_note_journal_codes'
CN_JOURNAL_NAMES_DEFAULT = u'สมุดรายวันลดหนี้ขาย'
CN_JOURNAL_CODES_DEFAULT = u'CN'

# แผนงานที่เป็นไปได้หลังวิเคราะห์เอกสาร
PLAN_CANCEL = 'cancel'            # ยกเลิกการชำระ + ยกเลิกเอกสาร
PLAN_ASK_DATE = 'ask_date'        # ให้พนักงานระบุวันที่
PLAN_FROM_ORDER = 'from_order'    # ดึงวันที่จากใบสั่งขายให้เอง


class NpdAiItInvoiceFix(models.AbstractModel):
    _name = 'npd.ai.it.invoice.fix'
    _description = u'ตัวช่วย AI-IT : แก้ไขวันที่ใบแจ้งหนี้'

    # ------------------------------------------------------------------
    # อ่าน URL / หาเอกสาร
    # ------------------------------------------------------------------
    @api.model
    def parse_move_reference(self, text):
        """ดึง id ของ account.move ออกจากข้อความที่พนักงานวางมา

        คืน (move_id, model_in_url) — move_id เป็น None ถ้าอ่านไม่ออก
        """
        text = (text or '').strip()

        model_match = re.search(r'model=([a-zA-Z0-9_.]+)', text)
        model_in_url = model_match.group(1) if model_match else None

        # id=66121 ทั้งใน hash (#id=) และ query (?id=) — URL แบบเดิมของ o14/o18
        id_match = re.search(r'(?:^|[#&?])id=(\d+)', text)
        if id_match:
            return int(id_match.group(1)), model_in_url

        # URL แบบใหม่ของ Odoo 18: /odoo/<action หรือ model>/<id>
        #   /odoo/action-account.action_move_out_invoice_type/66121
        #   /odoo/account.move/66121   /odoo/invoicing/66121
        path_match = re.search(r'/odoo/((?:[\w.\-]+/)*?)([\w.\-]+)/(\d+)(?:[/?#]|$)', text)
        if path_match:
            segment = path_match.group(2)
            if '.' in segment and not segment.startswith('action-') and not model_in_url:
                model_in_url = segment
            return int(path_match.group(3)), model_in_url

        # วางมาแต่ตัวเลขล้วน ก็ถือว่าเป็น id
        if re.match(r'^\d+$', text):
            return int(text), model_in_url

        return None, model_in_url

    @api.model
    def find_move(self, text):
        """คืน (move, error_message)"""
        move_id, model_in_url = self.parse_move_reference(text)

        if model_in_url and model_in_url != 'account.move':
            return None, (u'URL ที่วางมาเป็นหน้าของ %s ไม่ใช่ใบแจ้งหนี้ '
                          u'กรุณาเปิดหน้าใบแจ้งหนี้แล้วคัดลอก URL มาใหม่' % model_in_url)

        Move = self.env['account.move'].sudo()
        if move_id:
            move = Move.browse(move_id)
            if not move.exists():
                return None, u'ไม่พบเอกสาร id=%s ในระบบ (อาจอยู่คนละฐานข้อมูล)' % move_id
            return move, None

        # ไม่มี id ในข้อความ -> ลองมองเป็นเลขที่เอกสาร (ใบที่ลงบันทึกแล้วจะมีเลข)
        name = text.strip()
        if name:
            move = Move.search([('name', '=', name)], limit=1)
            if move:
                return move, None

        return None, (u'อ่าน URL ไม่ออกครับ 🙏 กรุณาคัดลอก URL ของหน้าใบแจ้งหนี้'
                      u'ทั้งบรรทัดมาวาง เช่น<br/>'
                      u'<span class="text-muted">http://119.59.124.50:8070/odoo/action-account.action_move_out_invoice_type/66121</span>')

    # ------------------------------------------------------------------
    # วิเคราะห์ว่าจะทำอะไรกับเอกสารนี้
    # ------------------------------------------------------------------
    @api.model
    def is_credit_note_journal(self, journal):
        """สมุดรายวันนี้เป็น "สมุดรายวันลดหนี้ขาย" หรือไม่"""
        if not journal:
            return False
        Param = self.env['ir.config_parameter'].sudo()
        names = Param.get_param(CN_JOURNAL_NAMES_PARAM, CN_JOURNAL_NAMES_DEFAULT) or ''
        codes = Param.get_param(CN_JOURNAL_CODES_PARAM, CN_JOURNAL_CODES_DEFAULT) or ''
        name_set = {n.strip().lower() for n in names.split(',') if n.strip()}
        code_set = {c.strip().lower() for c in codes.split(',') if c.strip()}
        return bool(
            (journal.name or '').strip().lower() in name_set
            or (journal.code or '').strip().lower() in code_set
        )

    @api.model
    def is_settled(self, move):
        """ลงบันทึกแล้ว หรือมีการชำระเงินแล้ว"""
        return bool(
            move.state == 'posted'
            or (move.payment_state and move.payment_state not in ('not_paid',))
            or move._get_reconciled_payments()
        )

    @api.model
    def analyze(self, move):
        """คืน dict อธิบายว่าเอกสารนี้ทำอะไรได้ / ทำไม่ได้เพราะอะไร

        {'plan': PLAN_*, 'error': str|None, 'reason': str, 'payments': recordset, ...}
        """
        reason = ((move.reason_code_id.name if 'reason_code_id' in move._fields else '')
                  or '').strip()
        info = {
            'plan': None,
            'error': None,
            'reason': reason,
            'state': move.state,
            'payment_state': move.payment_state or 'not_paid',
            'payments': self.env['account.payment'].sudo(),
            'is_credit_note': self.is_credit_note_journal(move.journal_id),
        }

        if move.state == 'cancel':
            info['error'] = u'เอกสารนี้ถูกยกเลิกไปแล้ว ไม่มีอะไรให้แก้'
            return info

        if reason not in SUPPORTED_REASONS:
            info['error'] = (
                u'ประเภทสินค้าของเอกสารนี้คือ "%s" ซึ่งยังไม่รองรับในเมนูนี้<br/>'
                u'รองรับเฉพาะ: %s'
                % (reason or u'(ยังไม่ได้ระบุ)', u' / '.join(SUPPORTED_REASONS))
            )
            return info

        if self.is_settled(move):
            info['plan'] = PLAN_CANCEL
            info['payments'] = move._get_reconciled_payments()
            return info

        if move.state != 'draft':
            info['error'] = u'สถานะเอกสาร "%s" ยังไม่รองรับในเมนูนี้' % move.state
            return info

        # ---- ฉบับร่าง ----
        if reason in MANUAL_DATE_REASONS:
            info['plan'] = PLAN_ASK_DATE
        elif info['is_credit_note']:
            # ใบแจ้งหนี้ค่าเช่าที่ออกในสมุดรายวันลดหนี้ขาย ไม่ผูกกับวันที่สั่งซื้อ
            info['plan'] = PLAN_ASK_DATE
        else:
            info['plan'] = PLAN_FROM_ORDER
        return info

    # ------------------------------------------------------------------
    # เดือนที่อนุญาต
    # ------------------------------------------------------------------
    @api.model
    def reference_date(self, move):
        """วันที่ที่ใช้เป็นตัวตั้งของ "เดือนนั้น ๆ" """
        return move.invoice_date or move.date

    @api.model
    def month_window(self, move):
        """คืน (วันแรกของเดือน, วันสุดท้ายของเดือน) ที่อนุญาตให้เปลี่ยนไปได้"""
        ref = self.reference_date(move)
        first = ref.replace(day=1)
        last = ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])
        return first, last

    # ------------------------------------------------------------------
    # ดึงวันที่จากใบสั่งขาย (Source Document)
    # ------------------------------------------------------------------
    @api.model
    def order_date_from_origin(self, move):
        """คืน (วันที่สั่งซื้อ, order, error_message)"""
        origin = (move.invoice_origin or '').strip()
        if not origin:
            return None, None, (u'เอกสารนี้ไม่มีข้อมูลในช่อง Source Document '
                                u'จึงหาใบสั่งขายต้นทางไม่ได้')

        Order = self.env['sale.order'].sudo()
        order = Order.search([('name', '=', origin)], limit=1)
        if not order:
            # Source Document อาจมีหลายเลขคั่นด้วยจุลภาค เอาตัวแรกที่หาเจอ
            for part in re.split(r'[,\s]+', origin):
                part = part.strip()
                if not part:
                    continue
                order = Order.search([('name', '=', part)], limit=1)
                if order:
                    break

        if not order:
            return None, None, (u'หาใบสั่งขาย "%s" ตามช่อง Source Document ไม่เจอ' % origin)
        if not order.date_order:
            return None, order, (u'ใบสั่งขาย %s ไม่มีวันที่สั่งซื้อ' % order.name)

        return self._to_user_date(order.date_order), order, None

    @api.model
    def _to_user_date(self, value):
        """Datetime (UTC) -> Date ตามโซนเวลาของผู้ใช้

        date_order เก็บเป็น UTC ถ้าแปลงตรง ๆ วันที่จะเพี้ยนไป 1 วันสำหรับ
        เอกสารที่สร้างช่วงเช้าตรู่/ดึกตามเวลาไทย
        """
        return fields.Date.context_today(self, value)

    # ------------------------------------------------------------------
    # ลงมือแก้
    # ------------------------------------------------------------------
    @api.model
    def apply_date_isolated(self, move_id, new_date, note=u'', actor_name=None):
        u"""เปลี่ยนวันที่ในทรานแซกชันแยก (เหตุผลเดียวกับ cancel_move_isolated)

        โมดูลในระบบนี้มี ``cr.commit()`` กระจายอยู่หลายที่ ถ้าโดนสักตัวระหว่าง
        write ทรานแซกชันของแชทจะพังทั้งก้อนและข้อความพนักงานหาย จึงกันไว้ก่อน
        """
        self.env['account.move'].flush_model()

        registry = odoo.registry(self.env.cr.dbname)
        with registry.cursor() as new_cr:
            new_env = api.Environment(new_cr, SUPERUSER_ID, dict(self.env.context))
            move = new_env['account.move'].browse(move_id)
            if not move.exists():
                raise ValueError(u'ไม่พบเอกสาร id=%s' % move_id)
            if move.state != 'draft':
                raise ValueError(u'เอกสารไม่ได้อยู่สถานะฉบับร่างแล้ว (%s)' % move.state)
            result = new_env['npd.ai.it.invoice.fix'].apply_date(
                move, new_date, note=note, actor_name=actor_name)

        self.env['account.move'].invalidate_model()
        return result

    @api.model
    def apply_date(self, move, new_date, note=u'', actor_name=None):
        """เปลี่ยนวันที่ใบแจ้งหนี้ + วันที่ลงบัญชี (ทำได้เฉพาะฉบับร่าง)"""
        actor_name = actor_name or self.env.user.display_name
        old_invoice_date = move.invoice_date
        old_date = move.date
        move.sudo().write({
            'invoice_date': new_date,
            'date': new_date,
        })
        # Odoo 18 escape body ที่เป็น str ทั้งก้อน ต้องส่ง Markup (ค่าจากผู้ใช้ถูก escape ตอน %)
        body = Markup(u'<b>ตัวช่วย AI-IT</b> แก้วันที่เอกสารโดย %s<br/>'
                      u'วันที่ใบแจ้งหนี้: %s → %s<br/>'
                      u'วันที่ลงบัญชี: %s → %s') % (
            actor_name, old_invoice_date or '-', new_date, old_date or '-', new_date)
        if note:
            body += Markup(u'<br/>') + note
        move.sudo().message_post(body=body)
        _logger.info(
            u'ตัวช่วย AI-IT: %s แก้วันที่ account.move id=%s (%s) %s -> %s',
            actor_name, move.id, move.name or u'ร่าง',
            old_invoice_date, new_date,
        )
        return {
            'old_invoice_date': old_invoice_date,
            'old_date': old_date,
            'new_date': new_date,
        }

    @api.model
    def cancel_move_isolated(self, move_id, actor_name=None, note=None):
        u"""ยกเลิกเอกสารใน "ทรานแซกชันแยก"

        ทำไมต้องแยก (เจอของจริง 31 ส.ค. 2026 กับ INV-2608140005):
        account_payment_invoice.action_draft() เรียก ``self.env.cr.commit()``
        กลางคัน (ราวบรรทัด 1439) ถ้ารันในทรานแซกชันเดียวกับ message_post ของแชท
        commit นั้นจะ "ทำลาย savepoint" ที่เราวางไว้ พอออกจาก savepoint แล้วสั่ง
        RELEASE SAVEPOINT จึงเจอ ``savepoint ... does not exist`` ทรานแซกชันเสีย
        ทั้งก้อน ต่อด้วย ``current transaction is aborted`` ตอน _notify_thread
        ของ message_post — ผลคือข้อความที่พนักงานเพิ่งพิมพ์หายไปทั้งข้อความ
        และงานถูก commit ค้างไว้ครึ่งทาง

        เปิด cursor ใหม่จึงเป็นทางเดียวที่กันได้จริง: โมดูลอื่นจะ commit ยังไง
        ก็กระทบแค่ทรานแซกชันของมันเอง ส่วนของแชทไม่สะเทือน และถ้าพังกลางทาง
        cursor ใหม่จะถูก rollback ทิ้งทั้งก้อน ไม่เหลือสถานะครึ่ง ๆ กลาง ๆ

        ใช้ ``with_user(SUPERUSER_ID)`` ไม่ใช่ ``sudo()`` เพราะตั้งแต่ Odoo 13
        sudo() "ไม่เปลี่ยน env.user" แค่ข้าม access rights เท่านั้น ด่านของ
        user_cancel_control ที่เช็ค ``env.user.allow_cancel`` จึงยังเจอผู้ใช้คนเดิม
        (ดู hooks.py ที่ติ๊ก allow_cancel ให้ผู้ใช้ระบบไว้คู่กัน)
        """
        # ดันงานที่ ORM ค้างอยู่ลง DB ก่อน กันสองทรานแซกชันจับล็อกชนกัน
        self.env['account.move'].flush_model()

        registry = odoo.registry(self.env.cr.dbname)
        with registry.cursor() as new_cr:
            new_env = api.Environment(new_cr, SUPERUSER_ID, dict(self.env.context))
            move = new_env['account.move'].browse(move_id)
            if not move.exists():
                raise ValueError(u'ไม่พบเอกสาร id=%s' % move_id)
            result = new_env['npd.ai.it.invoice.fix'].cancel_move(
                move, actor_name=actor_name, note=note)

        # ทรานแซกชันแยก commit ไปแล้ว ค่าที่ ORM ฝั่ง request จำไว้จึงเก่า
        self.env['account.move'].invalidate_model()
        self.env['account.payment'].invalidate_model()
        return result

    @api.model
    def cancel_move(self, move, actor_name=None, note=None):
        """ยกเลิกการชำระ (ถ้ามี) แล้วยกเลิกเอกสาร

        ปกติควรเรียกผ่าน cancel_move_isolated() ผู้เรียกต้องเช็คสาขา
        และให้พนักงานยืนยันมาก่อนแล้ว
        """
        actor_name = actor_name or self.env.user.display_name
        move = move.sudo()
        payments = move._get_reconciled_payments()
        cancelled_payments = []

        for payment in payments:
            label = payment.name or (payment.move_id.name if payment.move_id else '') or str(payment.id)
            state_before = payment.state
            payment_sudo = payment.sudo().with_context(skip_draft_permission_check=True)
            if hasattr(payment_sudo, 'action_cancel_payment'):
                # o18 account_payment_invoice: unreconcile + ยกเลิก move + รีเซ็ตสถานะใบแจ้งหนี้ครบในตัว
                if payment_sudo.state not in ('canceled', 'cancel'):
                    payment_sudo.action_cancel_payment()
            else:
                # o18 ไม่มีสถานะ posted แล้ว ใบที่ลงบันทึกคือ in_process / paid
                if state_before in ('in_process', 'paid'):
                    payment_sudo.action_draft()
                if payment_sudo.state == 'draft':
                    payment_sudo.action_cancel()
            payment.invalidate_recordset(['state'])
            cancelled_payments.append({
                'name': label,
                'amount': payment.amount,
                'state_before': state_before,
                'state_after': payment.state,
            })

        state_before = move.state
        move.invalidate_recordset()
        if move.state == 'posted':
            move.button_draft()
        if move.state != 'cancel':
            move.button_cancel()

        body = Markup(u'<b>ตัวช่วย AI-IT</b> ยกเลิกเอกสารนี้ตามคำสั่งของ %s<br/>'
                      u'สถานะเดิม: %s | ยกเลิกการชำระ %d รายการ') % (
            actor_name, state_before, len(cancelled_payments))
        if note:
            body += Markup(u'<br/>เหตุผล: %s') % note
        move.message_post(body=body)
        _logger.info(
            u'ตัวช่วย AI-IT: %s ยกเลิก account.move id=%s (%s) สถานะเดิม=%s '
            u'พร้อมยกเลิกการชำระ %d รายการ',
            actor_name, move.id, move.name or u'ร่าง',
            state_before, len(cancelled_payments),
        )
        return {
            'state_before': state_before,
            'state_after': move.state,
            'payments': cancelled_payments,
        }
