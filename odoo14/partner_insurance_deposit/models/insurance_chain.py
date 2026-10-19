# -*- coding: utf-8 -*-
# models/insurance_chain.py
# กระทบยอดเงินประกันแยกตาม "สาย SO" (SO ใบแรก + บิลต่ออายุทั้งหมด)
#
# ที่มาของแต่ละรายการในบัญชี 2133-01:
#   รับเงินประกัน  : INS-xxx            → SO จาก invoice_origin
#   คืนเงินประกัน  : PV จากใบคืนเงิน    → SO จาก account.voucher.reference (Bill Reference)
#   หักเงินประกัน  : RV / RVILS / RVIBK → ใบแจ้งหนี้ที่ชำระ (search_invoice_name) → invoice_origin
#   สาย SO         : SO ใบแรก = เลขแรกใน deposit_ref (บิลต่ออายุ) หรือตัวมันเอง
#
# o18: account.move.payment_id → origin_payment_id, mail.tracking.value.field → field_id
# ตัวคำนวณนี้ใช้ร่วมกันทั้ง Error ตอนพนักงานทำเอกสาร และรายงานให้ผู้ตรวจ → คำอธิบายตรงกันเสมอ

from odoo import models, fields, api, _

from .res_partner import INSURANCE_ACCOUNT_CODE

STATUS_SELECTION = [
    ('wrong_partner', 'เลือกชื่อลูกค้าผิด'),
    ('no_ins', 'เงินประกันไม่เคยเข้าระบบ'),
    ('over', 'ใช้เงินประกันเกินยอดที่รับ'),
    ('unpaid', 'ใบแจ้งหนี้ค่าประกันยังไม่รับชำระ'),
    ('unmapped', 'รายการไม่ทราบ SO'),
    ('ok', 'ปกติ'),
]
DOC_TYPE_SELECTION = [
    ('receive', 'รับเงินประกัน'),
    ('deduct', 'หักเงินประกัน'),
    ('refund', 'คืนเงินประกัน'),
    ('other', 'อื่น ๆ'),
]
NO_SO = 'ไม่ระบุ SO'
# ส่วนต่างจากการปัดเศษ (เช่น 0.01) ไม่ถือว่าใช้เงินประกันเกิน
TOLERANCE = 1.0


def _fmt(amount):
    return '{:,.2f}'.format(amount or 0.0)


def _d(date):
    return date.strftime('%d/%m/%Y') if date else '-'


class InsuranceChainEngine(models.AbstractModel):
    _name = 'npd.insurance.chain.engine'
    _description = 'ตัวคำนวณเงินประกันตามสาย SO'

    # ------------------------------------------------------------------ สาย SO
    @api.model
    def chain_root(self, so_name, cache=None):
        """SO ใบแรกของสาย (เลขแรกใน deposit_ref ของบิลต่ออายุ)"""
        if not so_name:
            return NO_SO
        cache = {} if cache is None else cache
        if so_name not in cache:
            so = self.env['sale.order'].sudo().search([('name', '=', so_name)], limit=1)
            refs = [r.strip() for r in (so.deposit_ref or '').split(',') if r.strip().startswith('SO')]
            cache[so_name] = refs[0] if refs else so_name
        return cache[so_name]

    @api.model
    def chain_so_names(self, root):
        """SO ทั้งหมดในสาย: SO ใบแรก + SO ที่มี deposit_ref ขึ้นต้นด้วย SO ใบแรก"""
        if root == NO_SO:
            return []
        renewals = self.env['sale.order'].sudo().search([('deposit_ref', '=like', root + '%')])
        names = [root] + [so.name for so in renewals.sorted('id') if so.name != root]
        return names

    # ------------------------------------------------------------- รายการ 2133-01
    @api.model
    def collect_entries(self, partner, exclude_move_ids=None):
        """รายการ 2133-01 ที่ลงบันทึกแล้วของลูกค้า พร้อม SO และสายที่เป็นเจ้าของ"""
        partner = partner.commercial_partner_id
        accounts = self.env['res.partner']._insurance_accounts()
        if not accounts:
            return []
        domain = [('account_id', 'in', accounts.ids), ('parent_state', '=', 'posted'),
                  ('partner_id', 'child_of', partner.id)]
        if exclude_move_ids:
            domain.append(('move_id', 'not in', list(exclude_move_ids)))
        lines = self.env['account.move.line'].sudo().search(domain, order='date, move_id, id')

        moves = lines.mapped('move_id')
        vouchers = {v.move_id.id: v for v in self.env['account.voucher'].sudo().search([('move_id', 'in', moves.ids)])}
        inv_names = set(m.origin_payment_id.search_invoice_name for m in moves if m.origin_payment_id and m.origin_payment_id.search_invoice_name)
        invoices = {i.name: i for i in self.env['account.move'].sudo().search([('name', 'in', list(inv_names))])} if inv_names else {}

        cache, entries = {}, []
        for l in lines:
            m = l.move_id
            so_name, invoice_ref, doc_type = False, False, 'other'
            if l.credit and m.move_type == 'out_invoice':
                # ใบแจ้งหนี้ค่าประกัน INS (และ IV รุ่นเก่าก่อนใช้ INS)
                doc_type, so_name = 'receive', m.invoice_origin
            elif m.id in vouchers:
                doc_type, so_name = 'refund', vouchers[m.id].reference
            elif m.origin_payment_id and m.origin_payment_id.search_invoice_name:
                doc_type = 'deduct'
                invoice_ref = m.origin_payment_id.search_invoice_name
                inv = invoices.get(invoice_ref.split(',')[0].strip())
                so_name = inv.invoice_origin if inv else False
            so_name = so_name if so_name and so_name.startswith('SO') else False
            entries.append({
                'line': l, 'move': m, 'date': l.date, 'doc_type': doc_type,
                'so_name': so_name or False, 'root': self.chain_root(so_name, cache),
                'invoice_ref': invoice_ref, 'voucher': vouchers.get(m.id),
                'amount_in': l.credit, 'amount_out': l.debit,
            })
        return entries

    # ---------------------------------------------------------------- วิเคราะห์สาย
    @api.model
    def _cancelled_ins(self, so_names, partner):
        """INS ของสาย SO ที่ถูกยกเลิก พร้อมผู้ยกเลิกและวันที่"""
        ins = self.env['account.move'].sudo().search([
            ('invoice_origin', 'in', so_names), ('name', '=like', 'INS-%'),
            ('partner_id', 'child_of', partner.id), ('state', '=', 'cancel')], order='id')
        result = []
        for m in ins:
            user_name, when = m.write_uid.name, m.write_date
            tv = self.env['mail.tracking.value'].sudo().search([
                ('mail_message_id.model', '=', 'account.move'), ('mail_message_id.res_id', '=', m.id),
                ('field_id.name', '=', 'state'), ('new_value_char', 'in', ['ยกเลิกแล้ว', 'Cancelled'])],
                order='id desc', limit=1)
            if tv:
                user_name, when = tv.mail_message_id.author_id.name or user_name, tv.mail_message_id.date
            result.append({'move': m, 'user': user_name, 'date': when})
        return result

    @api.model
    def _family_ids(self, partner):
        """ผู้ติดต่อทุกคนในบริษัทเดียวกับลูกค้า"""
        return self.env['res.partner'].sudo().with_context(active_test=False).search(
            [('id', 'child_of', partner.commercial_partner_id.id)]).ids

    @api.model
    def _elsewhere_in(self, so_names, partner):
        """เงินประกันของ SO ในสาย ที่รับเข้าในชื่อลูกค้าคนอื่น (เช่น ลูกค้ามี 2 ชื่อในระบบ)"""
        accounts = self.env['res.partner']._insurance_accounts()
        lines = self.env['account.move.line'].sudo().search([
            ('account_id', 'in', accounts.ids), ('parent_state', '=', 'posted'), ('credit', '>', 0),
            ('move_id.move_type', '=', 'out_invoice'), ('move_id.invoice_origin', 'in', so_names),
            ('partner_id', '!=', False), ('partner_id', 'not in', self._family_ids(partner))])
        result = []
        for l in lines:
            pays = l.move_id._get_reconciled_payments() if hasattr(l.move_id, '_get_reconciled_payments') else []
            result.append({'move': l.move_id, 'partner': l.partner_id.commercial_partner_id,
                           'amount': l.credit, 'payments': ', '.join(p.name for p in pays if p.name)})
        return result

    @api.model
    def _elsewhere_out(self, so_names, partner):
        """ใบคืนเงินประกันของ SO ในสาย ที่ทำในชื่อลูกค้าคนอื่น"""
        vouchers = self.env['account.voucher'].sudo().search([
            ('reference', 'in', so_names), ('state', '=', 'posted'), ('check_show', '=', True),
            ('partner_id', 'not in', self._family_ids(partner))])
        return [{'voucher': v, 'partner': v.partner_id.commercial_partner_id, 'amount': v.amount} for v in vouchers]

    @api.model
    def _wrong_partner_text(self, c, partner_name):
        """อธิบายกรณีรับเงินประกันกับคืน/หัก อยู่คนละชื่อลูกค้า"""
        label = self.chain_label(c)
        if c.get('elsewhere_in'):
            got = ' / '.join('%s ในชื่อ %s %s บาท%s' % (
                x['move'].name, x['partner'].display_name, _fmt(x['amount']),
                (' รับชำระแล้ว ' + x['payments']) if x['payments'] else '') for x in c['elsewhere_in'])
            return ('%s: เลือกชื่อลูกค้าผิด เงินประกันของ SO นี้รับเข้าในชื่อลูกค้าอื่น แต่คืน/หักในชื่อ %s\n'
                    'รับเข้า: %s\nใช้ไปในชื่อ %s: %s' % (
                        label, partner_name, got, partner_name, self.used_text(c) or '-'))
        out = ' / '.join('คืนเงิน %s ในชื่อ %s %s บาท' % (
            x['voucher'].number or '-', x['partner'].display_name, _fmt(x['amount'])) for x in c['elsewhere_out'])
        return ('%s: เลือกชื่อลูกค้าผิด เงินประกันยังค้างในชื่อ %s %s บาท แต่ถูกคืนในชื่อลูกค้าอื่นไปแล้ว\n'
                'คืนเงิน: %s' % (label, partner_name, _fmt(c['balance']), out))

    @api.model
    def analyse(self, partner, exclude_move_ids=None):
        """คืนค่า dict {root: chain} ของลูกค้า (คำนวณสด ไม่เก็บลง DB)"""
        partner = partner.commercial_partner_id
        chains = {}
        for e in self.collect_entries(partner, exclude_move_ids):
            c = chains.setdefault(e['root'], {'root': e['root'], 'entries': []})
            c['entries'].append(e)
        for root, c in chains.items():
            self._summarise(c, partner)
        return chains

    @api.model
    def chain_for_so(self, partner, so_name, exclude_move_ids=None):
        """สถานะสายของ SO หนึ่งใบ (ใช้ตอนตรวจใบคืน/ใบหักเงินประกัน)"""
        root = self.chain_root(so_name)
        chains = self.analyse(partner, exclude_move_ids)
        if root in chains:
            return chains[root]
        c = {'root': root, 'entries': []}
        self._summarise(c, partner.commercial_partner_id)
        return c

    @api.model
    def _summarise(self, c, partner):
        root = c['root']
        so_names = self.chain_so_names(root) if root != NO_SO else []
        running, first_negative = 0.0, None
        for e in c['entries']:
            running += e['amount_in'] - e['amount_out']
            e['running'] = running
            if first_negative is None and running < -TOLERANCE:
                first_negative = e
        received = sum(e['amount_in'] for e in c['entries'] if e['doc_type'] == 'receive')
        other_in = sum(e['amount_in'] for e in c['entries'] if e['doc_type'] != 'receive')
        deducted = sum(e['amount_out'] for e in c['entries'] if e['doc_type'] == 'deduct')
        refunded = sum(e['amount_out'] for e in c['entries'] if e['doc_type'] == 'refund')
        other_out = sum(e['amount_out'] for e in c['entries'] if e['doc_type'] == 'other')
        root_so = self.env['sale.order'].sudo().search([('name', '=', root)], limit=1) if root != NO_SO else False
        c.update({
            'partner': partner, 'so_names': so_names, 'root_so': root_so,
            'received': received + other_in, 'deducted': deducted, 'refunded': refunded + other_out,
            'balance': running, 'first_negative': first_negative,
            'elsewhere_in': self._elsewhere_in(so_names, partner) if so_names else [],
            'elsewhere_out': self._elsewhere_out(so_names, partner) if so_names else [],
            'cancelled_ins': self._cancelled_ins(so_names, partner) if so_names else [],
            'unpaid_ins': self.env['account.move'].sudo().search([
                ('invoice_origin', 'in', so_names), ('name', '=like', 'INS-%'), ('state', '=', 'posted'),
                ('payment_state', 'not in', ['paid', 'in_payment', 'reversed'])]) if so_names else self.env['account.move'],
        })
        c['status'], c['reason'], c['action'] = self._explain(c)
        return c

    # ---------------------------------------------------------------- คำอธิบาย
    @api.model
    def chain_label(self, c):
        names = c.get('so_names') or []
        if c['root'] == NO_SO:
            return NO_SO
        if len(names) > 1:
            return 'สาย %s → %s' % (names[0], names[-1])
        return c['root']

    @api.model
    def _ins_text(self, c):
        """อธิบายว่าทำไมเงินประกันของสายนี้ไม่เข้าระบบ"""
        pfb = c['root_so'].pfb_amount if c.get('root_so') else 0.0
        head = '%s มีเงินประกัน %s บาท แต่' % (c['root'], _fmt(pfb)) if pfb else '%s ' % c['root']
        if c['cancelled_ins']:
            parts = ['%s ถูกยกเลิกเมื่อ %s โดย %s' % (x['move'].name, _d(x['date']), x['user'] or '-')
                     for x in c['cancelled_ins']]
            return head + 'ใบแจ้งหนี้ค่าประกัน ' + ', '.join(parts) + ' และไม่มีใบรับชำระค่าประกัน'
        return head + 'ไม่เคยออกใบแจ้งหนี้ค่าประกัน (INS) และไม่มีใบรับชำระค่าประกัน'

    @api.model
    def used_text(self, c, limit=8):
        # รวมยอดต่อเอกสาร (ใบหักเงินประกัน 1 ใบอาจมีหลายบรรทัด 2133-01)
        out, by_move = [], {}
        for e in c['entries']:
            if not e['amount_out']:
                continue
            if e['move'].id in by_move:
                by_move[e['move'].id]['amount_out'] += e['amount_out']
            else:
                by_move[e['move'].id] = dict(e)
                out.append(by_move[e['move'].id])
        txt = []
        for e in out[:limit]:
            if e['doc_type'] == 'refund' and e['voucher']:
                txt.append('คืนเงิน %s (%s) %s' % (e['voucher'].number or '-', e['move'].name, _fmt(e['amount_out'])))
            elif e['doc_type'] == 'deduct':
                txt.append('หักชำระ %s (%s) %s' % (e['invoice_ref'], e['move'].name, _fmt(e['amount_out'])))
            else:
                txt.append('%s %s' % (e['move'].name, _fmt(e['amount_out'])))
        if len(out) > limit:
            txt.append('และอีก %s รายการ' % (len(out) - limit))
        return ' / '.join(txt)

    @api.model
    def _explain(self, c):
        label = self.chain_label(c)
        used = c['deducted'] + c['refunded']
        if c['root'] == NO_SO:
            if abs(c['balance']) < TOLERANCE:
                return 'ok', '', ''
            return ('unmapped',
                    'มีรายการในบัญชี 2133-01 ที่ระบุ SO ไม่ได้ ยอดสุทธิ %s บาท' % _fmt(c['balance']),
                    'ฝ่ายบัญชีตรวจรายการในตารางด้านล่างว่าเป็นเงินประกันของ SO ไหน')
        pname = c['partner'].display_name if c.get('partner') else '-'
        short = c['balance'] < -TOLERANCE or (c['received'] < 0.005 and used > 0.005)
        if (short and c.get('elsewhere_in')) or (c['balance'] > TOLERANCE and c.get('elsewhere_out')):
            others = ', '.join(sorted(set(x['partner'].display_name for x in c['elsewhere_in'] + c['elsewhere_out'])))
            return ('wrong_partner', self._wrong_partner_text(c, pname),
                    'ตรวจว่า %s กับ %s เป็นลูกค้าคนเดียวกันหรือไม่ ถ้าใช่ ให้แก้ชื่อลูกค้าในใบคืน/ใบหักเงินประกัน '
                    'ให้ตรงกับใบแจ้งหนี้ค่าประกัน (INS) และรวมรายชื่อลูกค้าที่ซ้ำกัน' % (pname, others))
        if c['received'] < 0.005 and used > 0.005:
            return ('no_ins',
                    '%s: เงินประกันไม่เคยเข้าระบบ แต่มีการใช้ไป %s บาท\n%s\nใช้ไปแล้ว: %s' % (
                        label, _fmt(used), self._ins_text(c), self.used_text(c)),
                    'ตรวจ statement ธนาคารว่าลูกค้าชำระเงินประกันของ %s จริงหรือไม่ '
                    'ถ้าชำระแล้วให้ออกใบแจ้งหนี้ค่าประกัน (INS) และใบรับชำระใหม่ ถ้าไม่ได้ชำระให้ตามเงินคืนหรือลงรายการปรับปรุง' % c['root'])
        if c['balance'] < -TOLERANCE:
            fn = c['first_negative']
            return ('over',
                    '%s: ใช้เงินประกันเกินยอดที่รับ %s บาท (รับเข้า %s / หัก %s / คืน %s)\nติดลบตั้งแต่เอกสาร %s วันที่ %s' % (
                        label, _fmt(-c['balance']), _fmt(c['received']), _fmt(c['deducted']), _fmt(c['refunded']),
                        fn['move'].name if fn else '-', _d(fn['date']) if fn else '-'),
                    'ตรวจยอดคืน/หักเงินประกันของสายนี้ ถ้าลูกค้ามีเงินประกันจาก SO อื่นที่ตั้งใจโอนมาใช้ ให้ฝ่ายบัญชีลงรายการโอนให้ถูกสาย')
        if c['unpaid_ins']:
            return ('unpaid',
                    '%s: ใบแจ้งหนี้ค่าประกัน %s ยังไม่ได้รับชำระ แต่ยอดเงินประกันนับเข้าระบบแล้ว' % (
                        label, ', '.join(c['unpaid_ins'].mapped('name'))),
                    'ติดตามรับชำระค่าประกัน หรือยกเลิกใบแจ้งหนี้ค่าประกันถ้าลูกค้าไม่ได้วางเงินประกัน')
        return 'ok', '', ''

    # --------------------------------------------------- ข้อความ Error ให้พนักงาน
    @api.model
    def staff_error(self, c, action_label, amount):
        """ข้อความ Error ตอนพนักงานคืน/หักเงินประกัน (None = ผ่าน)
        action_label: 'คืนเงินประกัน' / 'หักเงินประกัน'"""
        label = self.chain_label(c)
        if c['root'] == NO_SO:
            return None
        if c['received'] < 0.005 and c.get('elsewhere_in'):
            got = ' / '.join('%s ในชื่อ %s %s บาท' % (x['move'].name, x['partner'].display_name, _fmt(x['amount']))
                             for x in c['elsewhere_in'])
            pname = c['partner'].display_name if c.get('partner') else '-'
            return ('ไม่สามารถ%sได้: เลือกชื่อลูกค้าผิด\n\n'
                    'เงินประกันของ %s รับเข้าในชื่อลูกค้าอื่น: %s\nแต่ใบนี้เลือกลูกค้า %s\n\n'
                    'สิ่งที่ต้องทำ: เปลี่ยนชื่อลูกค้าในใบนี้ให้ตรงกับใบแจ้งหนี้ค่าประกัน (INS) '
                    'ถ้าเป็นลูกค้าคนเดียวกันแต่มีชื่อซ้ำในระบบ โปรดแจ้งฝ่ายการเงินให้รวมรายชื่อ' % (
                        action_label, label, got, pname))
        if c['received'] < 0.005:
            return ('ไม่สามารถ%sได้: %s ไม่มีเงินประกันเข้าระบบ\n\n%s\n%s\n\n'
                    'สิ่งที่ต้องทำ: แจ้งฝ่ายการเงินตรวจสอบว่าลูกค้าชำระเงินประกันของ %s แล้วหรือยัง '
                    'ถ้าชำระแล้วให้ออกใบแจ้งหนี้ค่าประกัน (INS) และรับชำระให้เรียบร้อยก่อน แล้วจึงทำรายการนี้' % (
                        action_label, label, self._ins_text(c),
                        ('ใช้ไปแล้ว: ' + self.used_text(c)) if (c['deducted'] + c['refunded']) else '',
                        c['root']))
        if amount - c['balance'] > TOLERANCE:
            return ('ไม่สามารถ%sได้: เงินประกันของ %s ไม่พอ\n\n'
                    'รับเข้า %s / ใช้ไปแล้ว %s / คงเหลือ %s บาท\n'
                    'รายการนี้%s %s บาท เกินไป %s บาท\n%s\n\n'
                    'สิ่งที่ต้องทำ: ตรวจยอดให้ถูกต้อง ถ้าต้องการใช้เงินประกันจาก SO อื่นของลูกค้า โปรดติดต่อฝ่ายการเงิน' % (
                        action_label, label, _fmt(c['received']), _fmt(c['deducted'] + c['refunded']),
                        _fmt(c['balance']), action_label, _fmt(amount), _fmt(amount - c['balance']),
                        ('ใช้ไปแล้ว: ' + self.used_text(c)) if (c['deducted'] + c['refunded']) else ''))
        return None
