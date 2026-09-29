# -*- coding: utf-8 -*-


def post_init_hook(env):
    """ใบสั่งขายที่มีอยู่ก่อนติดตั้งและเข้าเงื่อนไขต้องอนุมัติ ให้ถือว่าอนุมัติแล้ว
    (ไม่มีผู้อนุมัติจริง — หน้าจอแสดง "ใบที่มีก่อนเปิดใช้ระบบอนุมัติ")

    Odoo 17 เปลี่ยนลายเซ็น hook จาก (cr, registry) เป็น (env) ตัวเดียว
    """
    percent = env['sale.order']._ship_min_percent()
    env.cr.execute("""
        UPDATE sale_order
           SET ship_approval_state = 'approved',
               ship_approved_date = (now() at time zone 'UTC'),
               ship_approval_note = 'อนุมัติอัตโนมัติ: ใบที่มีก่อนเปิดใช้ระบบอนุมัติค่าขนส่ง'
         WHERE use_special_delivery_zero
            OR (COALESCE(shipping_cost_m, 0) > 0
                AND ROUND(shipping_cost_m::numeric, 2)
                    < ROUND((COALESCE(shipping_cost, 0) * %s / 100.0)::numeric, 2))
    """, (percent,))
