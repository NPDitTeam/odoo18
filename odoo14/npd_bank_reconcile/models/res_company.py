# -*- coding: utf-8 -*-
import logging
from collections import defaultdict

from odoo import Command, models

_logger = logging.getLogger(__name__)

# ฝ่ายบัญชีเคยเปลี่ยนรหัสผังมาแล้ว จึงหาบัญชีจาก "ชื่อ + ประเภท" เสมอ ห้ามผูกรหัส
# เรียงตามลำดับความสำคัญ เจอชื่อแรกก่อนใช้ชื่อนั้น
SUSPENSE_NAMES = ('บัญชีพักธนาคาร', 'บัญชีพักรอกระทบยอดธนาคาร', 'Bank Suspense Account')
SUSPENSE_TYPES = ('asset_current',)
TRANSFER_NAMES = ('เงินโอนระหว่างบัญชี', 'บัญชีพักโอนเงินระหว่างบัญชี', 'Liquidity Transfer')
TRANSFER_TYPES = ('asset_current',)
# (ชื่อปุ่มตัดผลต่าง, ชื่อบัญชีที่หา, ประเภทบัญชี)
# เงินขาด/เกิน ใช้บัญชีค่าใช้จ่าย 'เงินขาด(เกิน)บัญชี' ไม่ใช่บัญชีสินทรัพย์ 'เงินขาด/เกินบัญชี'
WRITEOFF_BUTTONS = [
    ('ค่าธรรมเนียมธนาคาร', ('ค่าธรรมเนียมธนาคาร',), ('expense',)),
    ('ดอกเบี้ยรับเงินฝาก', ('ดอกเบี้ยรับ - เงินฝาก', 'ดอกเบี้ยรับเงินฝาก'), ('income_other', 'income')),
    ('เงินขาด/เกินบัญชี', ('เงินขาด(เกิน)บัญชี',), ('expense',)),
]
BANK_JOURNAL_TYPES = ('bank', 'credit')


def _npd_norm(text):
    return ' '.join((text or '').split())


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _npd_find_account(self, names, types):
        """หาบัญชีของบริษัทนี้จากชื่อ (ไทยหรืออังกฤษ) + ประเภท คืน recordset ว่างถ้าไม่เจอ"""
        self.ensure_one()
        Account = self.env['account.account']
        domain = [
            *Account._check_company_domain(self),
            ('deprecated', '=', False),
            ('account_type', 'in', list(types)),
        ]
        by_name = defaultdict(Account.browse)
        for account in Account.search(domain):
            # ชื่อบัญชีแปลได้ ผังที่ยกมาอาจเก็บไว้แค่ en_US หรือมี th_TH ด้วย ดูทั้งสองภาษา
            for lang in self._npd_name_langs():
                by_name[_npd_norm(account.with_context(lang=lang).name)] |= account
        for name in names:
            found = by_name.get(_npd_norm(name))
            if not found:
                continue
            if len(found) > 1:
                found = found.sorted(lambda a: a.with_company(self).code or '')
                _logger.warning(
                    'บ.%s: บัญชีชื่อ "%s" มี %s บัญชี ใช้รหัสต่ำสุด %s',
                    self.name, name, len(found), found[0].with_company(self).code,
                )
            return found[:1]
        return Account.browse()

    def _npd_name_langs(self):
        # ใช้เฉพาะภาษาที่ติดตั้งอยู่ ส่ง lang ที่ไม่มีเข้า context แล้ว Odoo 18 ยก error
        # (ฐานที่ไม่ได้ลงภาษาไทย เช่นฐานทดสอบ จะติดตั้งโมดูลนี้ไม่ผ่านทั้งโมดูล)
        installed = {code for code, _name in self.env['res.lang'].get_installed()}
        return [lang for lang in ('en_US', 'th_TH') if lang in installed]

    def _npd_find_reconcile_model(self, label):
        RecModel = self.env['account.reconcile.model'].with_context(active_test=False)
        for lang in self._npd_name_langs():
            existing = RecModel.with_context(lang=lang).search(
                [('company_id', '=', self.id), ('name', '=', label)], limit=1,
            )
            if existing:
                return existing
        return RecModel.browse()

    def _npd_setup_bank_reconcile(self):
        """ตั้งค่าเริ่มต้นกระทบยอดธนาคาร กดซ้ำได้: เติมเฉพาะช่องที่ยังว่าง ไม่ทับค่าที่ตั้งไว้
        และไม่สร้างบัญชีในผัง (การเพิ่มบัญชีเป็นงานของฝ่ายบัญชี)

        คืนรายการข้อความภาษาไทยสำหรับรายงานผล
        """
        report = []
        # sudo: ตัวเลือกบริษัทบนแถบเมนูจะซ่อนบัญชี/สมุดของบริษัทที่ไม่ได้ติ๊กไว้
        # ทำให้รายงานว่า "ไม่มีบัญชี" ผิด ๆ (เมธอดนี้เรียกได้จาก hook และ action ของผู้ดูแลระบบเท่านั้น)
        for company in self.sudo():
            prefix = f'บ.{company.name}'
            Journal = self.env['account.journal'].sudo()
            bank_journals = Journal.search([
                ('company_id', '=', company.id),
                ('type', 'in', BANK_JOURNAL_TYPES),
                ('default_account_id', '!=', False),
            ])

            # (a) บัญชีพักธนาคาร: สมุดธนาคารไม่มีบัญชีพัก = สร้างรายการเดินบัญชีไม่ได้เลย
            suspense = company._npd_find_account(SUSPENSE_NAMES, SUSPENSE_TYPES)
            if suspense and not company.account_journal_suspense_account_id:
                company.account_journal_suspense_account_id = suspense
                report.append(f'{prefix}: ตั้งบัญชีพักธนาคารของบริษัท = {suspense.with_company(company).display_name}')
            target_suspense = company.account_journal_suspense_account_id or suspense
            if not suspense:
                report.append(f'{prefix}: ยังไม่มีบัญชีพักธนาคารในผัง')
            # สมุดเช็ค (CHP/CHR/QP/QR) ไม่มีบัญชีเงินฝาก จึงไม่ถูกแตะ
            journals_without_suspense = bank_journals.filtered(lambda j: not j.suspense_account_id)
            if target_suspense and journals_without_suspense:
                journals_without_suspense.write({'suspense_account_id': target_suspense.id})
                report.append(
                    f'{prefix}: ตั้งบัญชีพักธนาคารให้สมุด '
                    f'{", ".join(journals_without_suspense.mapped("code"))}'
                )

            # (b) ให้ปุ่ม "Import (OCA)" ขึ้นบนแดชบอร์ดของสมุดธนาคาร
            undefined_source = bank_journals.filtered(lambda j: j.bank_statements_source == 'undefined')
            if undefined_source:
                undefined_source.write({'bank_statements_source': 'file_import_oca'})

            # (c) เงินโอนระหว่างบัญชีของบริษัทเอง
            transfer = company._npd_find_account(TRANSFER_NAMES, TRANSFER_TYPES)
            if not transfer:
                report.append(f'{prefix}: ยังไม่มีบัญชีเงินโอนระหว่างบัญชีในผัง')
            elif not company.transfer_account_id:
                company.transfer_account_id = transfer
                report.append(f'{prefix}: ตั้งบัญชีเงินโอนระหว่างบัญชี = {transfer.with_company(company).display_name}')
            if transfer and not transfer.reconcile:
                report.append(
                    f'{prefix}: บัญชี {transfer.with_company(company).display_name} ยังไม่ได้ติ๊ก "อนุญาตกระทบยอด"'
                )

            # (d) ปุ่มตัดผลต่างบนหน้ากระทบยอด (ค่าธรรมเนียม/ดอกเบี้ย/เงินขาดเกิน)
            for label, names, types in WRITEOFF_BUTTONS:
                account = company._npd_find_account(names, types)
                if not account:
                    report.append(f'{prefix}: ไม่พบบัญชี "{names[0]}" จึงยังไม่สร้างปุ่ม "{label}"')
                    continue
                if company._npd_find_reconcile_model(label):
                    continue
                self.env['account.reconcile.model'].sudo().create({
                    'name': label,
                    'rule_type': 'writeoff_button',
                    'company_id': company.id,
                    'line_ids': [Command.create({
                        'account_id': account.id,
                        'amount_type': 'percentage',
                        'amount_string': '100',
                        'label': label,
                    })],
                })
                report.append(f'{prefix}: สร้างปุ่มตัดผลต่าง "{label}" -> {account.with_company(company).display_name}')
        return report

    def _npd_setup_bank_reconcile_action(self):
        lines = self._npd_setup_bank_reconcile()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'ตั้งค่ากระทบยอดธนาคาร',
                'message': '\n'.join(lines) or 'ตั้งค่าครบแล้ว ไม่มีอะไรต้องเปลี่ยน',
                'sticky': True,
                'type': 'info',
            },
        }
