# -*- coding: utf-8 -*-
"""จ่ายค่าปรับหายตามศาล — ปรับจำนวนสินค้าให้เท่ายอดงวดที่ศาลสั่ง

ลูกค้าเป็นหนี้แล้วไม่จ่าย เรื่องถึงศาล ศาลสั่งให้ผ่อนเป็นงวด งวดละไม่เท่ากัน
บัญชีออกใบทีละงวดอยู่แล้ว โดยกรอกยอดค้างเต็มมาทั้งใบ แล้วไล่ทำส่วนลดรายบรรทัด
เองจนเหลือเท่ายอดงวดนั้น ซึ่งกินเวลาและพลาดง่าย

ปุ่มนี้แทนงานมือตรงนั้น: ระบุยอดงวด แล้วระบบเลือกจำนวนเต็มของแต่ละสินค้าให้
ยอดรวมใกล้ยอดที่ศาลสั่งที่สุดโดย "ห้ามต่ำกว่า" เศษที่เกินค่อยทำส่วนลดต่อ
ซึ่งเหลือน้อยมากแล้ว บัญชีจึงลงสินทรัพย์ได้ตรงทั้งราคาและจำนวนในแต่ละรอบ

ตัวเดียวกับฝั่ง Odoo 14 (baankheaw_debt_payment) แต่ที่นั่นเงื่อนไขการแสดงปุ่ม
ดูประเภทหนี้บ้านเขียวด้วย ส่วนที่นี่ยังไม่มีโมดูลนั้น จึงดูแค่ประเภทสินค้า
"""
from odoo import models, fields, api
from odoo.exceptions import UserError

LOST_REASON_NAME = 'สินค้าหาย'
# กันไม่ให้ตารางความเป็นไปได้ระเบิด ถ้าเกินนี้ใช้วิธีประมาณแทน
_MAX_STATES = 300000


def solve_quantities(prices, max_qty, target):
    """เลือกจำนวนเต็มของแต่ละรายการ ให้ยอดรวมน้อยที่สุดที่ยังไม่ต่ำกว่า target

    คืน (list จำนวนที่เลือก, ยอดรวมที่ได้) หรือ (None, 0.0) ถ้าของไม่พอ

    ทำงานเป็นสตางค์ทั้งหมดเพื่อไม่ให้ทศนิยมลอย แล้วไล่สะสมยอดที่เป็นไปได้
    ตัดทิ้งยอดที่เกิน target ไปมากกว่าราคาต่อหน่วยที่แพงที่สุด เพราะยอดแบบนั้น
    ถอดของออกหนึ่งชิ้นก็ยังไม่ต่ำกว่า target อยู่ดี จึงไม่มีทางเป็นคำตอบที่ดีที่สุด
    """
    n = len(prices)
    if not n:
        return None, 0.0
    cents = [int(round(p * 100)) for p in prices]
    goal = int(round(target * 100))
    if goal <= 0:
        return [0] * n, 0.0
    ceiling = goal + max(cents)

    reachable = {0: (0,) * n}
    for i, (price, limit) in enumerate(zip(cents, max_qty)):
        if price <= 0 or limit <= 0:
            continue
        grown = dict(reachable)
        for total, picked in reachable.items():
            running = total
            for taken in range(1, int(limit) + 1):
                running += price
                if running > ceiling:
                    break
                if running not in grown:
                    vector = list(picked)
                    vector[i] = taken
                    grown[running] = tuple(vector)
        reachable = grown
        if len(reachable) > _MAX_STATES:
            return _solve_greedy(cents, max_qty, goal)

    hits = [total for total in reachable if total >= goal]
    if not hits:
        return None, 0.0
    best = min(hits)
    return list(reachable[best]), best / 100.0


def _solve_greedy(cents, max_qty, goal):
    """ทางเลือกสำรองเมื่อรายการเยอะเกินจะไล่ครบ — หยิบของแพงก่อนแล้วเติมให้ถึง"""
    order = sorted(range(len(cents)), key=lambda i: -cents[i])
    picked = [0] * len(cents)
    total = 0
    for i in order:
        if cents[i] <= 0 or max_qty[i] <= 0 or total >= goal:
            continue
        need = goal - total
        take = min(int(max_qty[i]), need // cents[i])
        picked[i] = take
        total += take * cents[i]
    if total < goal:
        candidates = [i for i in range(len(cents))
                      if cents[i] > 0 and picked[i] < max_qty[i]]
        if not candidates:
            return None, 0.0
        cheapest = min(candidates, key=lambda i: cents[i])
        picked[cheapest] += 1
        total += cents[cheapest]
    if total < goal:
        return None, 0.0
    return picked, total / 100.0


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ไม่เก็บลงฐาน (store=False) ตั้งใจ — account_move มีหลายแสนแถว ถ้าเก็บค่า
    # ตอนอัปเดตโมดูลจะถูกบังคับคำนวณใหม่ทั้งตารางและล็อกตารางนาน
    lost_court_is_lost_reason = fields.Boolean(
        string='ประเภทสินค้าเป็นสินค้าหาย', compute='_compute_lost_court_is_lost_reason',
        help='ใช้ควบคุมการแสดงปุ่มจ่ายค่าปรับหายตามศาล')

    lost_court_installment_no = fields.Integer(
        string='งวดที่ (ตามคำสั่งศาล)', copy=False, readonly=True)
    lost_court_amount = fields.Float(
        string='ยอดตามคำสั่งศาล (งวดนี้)', digits=(16, 2), copy=False, readonly=True,
        help='ยอดที่ศาลสั่งสำหรับงวดนี้ ส่วนที่ใบนี้เกินมาคือเศษที่บัญชีต้องทำส่วนลด')
    lost_court_diff = fields.Float(
        string='เศษที่ต้องทำส่วนลด', digits=(16, 2),
        compute='_compute_lost_court_diff')

    @api.depends('reason_code_id', 'reason_code_id.name')
    def _compute_lost_court_is_lost_reason(self):
        for move in self:
            move.lost_court_is_lost_reason = (
                move.reason_code_id.name or '').strip() == LOST_REASON_NAME

    @api.depends('lost_court_amount', 'invoice_line_ids.price_unit',
                 'invoice_line_ids.quantity')
    def _compute_lost_court_diff(self):
        for move in self:
            if not move.lost_court_amount:
                move.lost_court_diff = 0.0
                continue
            gross = sum(line.price_unit * line.quantity
                        for line in move.invoice_line_ids)
            move.lost_court_diff = gross - move.lost_court_amount

    # ------------------------------------------------------------------
    def lost_court_lines(self):
        """บรรทัดสินค้าที่เอามาคิดจำนวน — เอาเฉพาะที่มีราคาและจำนวนจริง"""
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
            and l.price_unit > 0 and l.quantity > 0).sorted(
                key=lambda l: (l.sequence, l.id))

    def action_open_lost_court_wizard(self):
        """ปุ่ม 'จ่ายค่าปรับหายตามศาล'"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(
                'ใบนี้ยืนยันแล้ว จึงแก้จำนวนสินค้าไม่ได้\n'
                'ถ้าต้องการแบ่งงวดตามคำสั่งศาล ให้กลับไปเป็นร่างก่อน '
                'หรือออกใบลดหนี้ใบนี้แล้วเริ่มจากใบร่างใหม่')
        if not self.lost_court_lines():
            raise UserError('ใบนี้ไม่มีบรรทัดสินค้าที่มีราคาและจำนวน จึงแบ่งงวดไม่ได้')
        return {
            'name': 'จ่ายค่าปรับหายตามศาล',
            'type': 'ir.actions.act_window',
            'res_model': 'npd.lost.court.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }
