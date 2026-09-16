# -*- coding: utf-8 -*-
"""ตอนติดตั้ง: ใส่ผู้ใช้ที่ได้รับสิทธิ์ดูเมนูตรวจทุจริตให้เลย

ผู้ใช้ระบุ 16 ก.ย. 2569 ว่าให้เปิดสิทธิ์ให้ Npd_admin กับ User004 ก่อน
คนอื่นจะไปติ๊กเพิ่มเองที่ ตั้งค่า > ผู้ใช้ > แท็บสิทธิ์
"""
import logging

_logger = logging.getLogger(__name__)

DEFAULT_LOGINS = ('Npd_admin', 'User004')


def post_init_hook(env):
    group = env.ref('npd_transport_fraud_check.group_transport_fraud_viewer',
                    raise_if_not_found=False)
    if not group:
        return
    users = env['res.users'].sudo().search([('login', 'in', list(DEFAULT_LOGINS))])
    if users:
        group.sudo().write({'users': [(4, user.id) for user in users]})
        _logger.info('ตรวจทุจริตการจัดส่ง: เปิดสิทธิ์ดูเมนูให้ %s', users.mapped('login'))
    missing = set(DEFAULT_LOGINS) - set(users.mapped('login'))
    if missing:
        _logger.warning('ตรวจทุจริตการจัดส่ง: ไม่พบผู้ใช้ %s จึงยังไม่ได้เปิดสิทธิ์ให้', missing)
