# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)

# ผู้ใช้ที่ต้องได้สิทธิ์นี้ตั้งแต่ติดตั้ง — ตามที่ตกลงไว้
# คนอื่นให้ไปติ๊กเพิ่มเองที่หน้าตั้งค่าผู้ใช้
DEFAULT_LOGINS = ['Npd_admin', 'User004']


def post_init_hook(env):
    """ให้สิทธิ์เห็นทุกบริษัทกับผู้ใช้ตั้งต้น

    ทำตอนติดตั้งครั้งเดียว ถ้าภายหลังมีคนเอาสิทธิ์ออก จะไม่ถูกใส่กลับให้เอง
    เพราะการถอดสิทธิ์เป็นการตัดสินใจของผู้ดูแล ไม่ใช่ความผิดพลาด
    """
    users = env['res.users'].sudo().search([('login', 'in', DEFAULT_LOGINS)])
    if not users:
        _logger.warning('[HRMS-ALL-CO] ไม่พบผู้ใช้ %s จึงยังไม่ได้ให้สิทธิ์ใคร',
                        ', '.join(DEFAULT_LOGINS))
        return

    for xmlid in ('group_hrms_all_companies', 'group_show_hrms_app',
                  'group_show_saas_app'):
        group = env.ref('npd_hrms_all_companies.' + xmlid,
                        raise_if_not_found=False)
        if not group:
            continue
        # Odoo รุ่นนี้ใช้ชื่อช่องว่า users ส่วนรุ่นใหม่กว่าเปลี่ยนเป็น user_ids
        # เลือกตามที่มีจริง เพื่อให้ติดตั้งผ่านทั้งสองรุ่น
        field = 'user_ids' if 'user_ids' in group._fields else 'users'
        group.sudo().write({field: [(4, user.id) for user in users]})
        _logger.info('[HRMS-ALL-CO] ให้สิทธิ์ "%s" แก่ %s',
                     group.name, ', '.join(users.mapped('login')))
