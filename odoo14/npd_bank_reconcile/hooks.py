# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    # ตั้งค่าที่หาได้จากผังทันทีที่ติดตั้ง ที่ยังขาด (เช่นบัญชีพักธนาคาร) จะขึ้นใน log
    # ให้ฝ่ายบัญชีเพิ่มในผังแล้วกด ตั้งค่า > ธนาคาร > ตั้งค่าเริ่มต้นกระทบยอดธนาคาร ซ้ำ
    for line in env['res.company'].search([])._npd_setup_bank_reconcile():
        _logger.info('npd_bank_reconcile: %s', line)
