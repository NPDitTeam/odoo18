# -*- coding: utf-8 -*-
"""ปรับสินค้าเงินประกันให้ตรงกับที่ใช้อยู่ใน Odoo 14

1. เปลี่ยนชื่อเป็น "เงินประกันค่าเช่า" (ของเดิมตั้งไว้ว่า "ค่าประกันสินค้า")
2. ผูกบัญชี 2133-01 เงินประกันการเช่า/สินค้า ให้ทุกบริษัทที่มีบัญชีนี้

เงินประกันเป็น "หนี้สิน" ไม่ใช่รายได้ ถ้าไม่ผูกบัญชีไว้ Odoo จะไปหยิบ
บัญชีรายได้จากประเภทสินค้าแทน ซึ่งทำให้งบผิด

ใช้ ORM ไม่ใช่ SQL ตรง ๆ เพราะ property_account_income_id เป็น company-dependent
ที่ Odoo 17+ เก็บเป็น JSONB รูปแบบภายใน ไม่ควรไปเขียนเอง
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

DEPOSIT_ACCOUNT_CODE = '2133-01'
DEPOSIT_ACCOUNT_NAME = 'เงินประกันการเช่า/สินค้า'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    product = env.ref(
        'pfb_npd_all_customs.product_product_insurance_deposit',
        raise_if_not_found=False,
    )
    if not product:
        _logger.info("ไม่พบสินค้าเงินประกันของโมดูล ข้ามการปรับ")
        return

    # 1. เปลี่ยนชื่อ (data file เป็น noupdate จึงไม่เขียนทับให้เอง)
    if product.name == 'ค่าประกันสินค้า':
        product.name = 'เงินประกันค่าเช่า'
        _logger.info("เปลี่ยนชื่อสินค้าเงินประกันเป็น 'เงินประกันค่าเช่า'")

    # 2. ผูกบัญชีเงินประกันรายบริษัท
    linked = []
    skipped = []
    for company in env['res.company'].search([]):
        product_in_company = product.with_company(company)
        if product_in_company.property_account_income_id:
            continue  # ตั้งไว้แล้ว ไม่ทับ

        # ต้องเช็คทั้งรหัสและชื่อ: บางบริษัทใช้รหัส 2133-01 กับบัญชีคนละตัว
        # (สตีลเทค 2133-01 = "รายได้รับล่วงหน้า-ค่าสินค้า") ถ้าจับแค่รหัสจะผูกผิดบัญชี
        account = env['account.account'].with_company(company).search([
            ('code', '=', DEPOSIT_ACCOUNT_CODE),
            ('name', '=', DEPOSIT_ACCOUNT_NAME),
            ('deprecated', '=', False),
        ], limit=1)
        if not account:
            skipped.append(company.display_name)
            continue

        product_in_company.property_account_income_id = account
        linked.append('%s -> %s' % (company.display_name, account.display_name))

    for line in linked:
        _logger.info("ผูกบัญชีเงินประกัน: %s", line)
    if skipped:
        _logger.warning(
            "ไม่พบบัญชี %s ในบริษัท %s "
            "ใบแจ้งหนี้รับเงินประกันของบริษัทนี้จะใช้บัญชีรายได้ตามประเภทสินค้าแทน "
            "ต้องไปตั้งบัญชีที่สินค้าเอง",
            DEPOSIT_ACCOUNT_CODE, ', '.join(skipped),
        )
