# -*- coding: utf-8 -*-
"""สร้างหมวดสินทรัพย์ตาม o14 ให้ทุกบริษัท พร้อมรหัสหมวดและร้อยละค่าเสื่อม

o14 แยกฐานละบริษัท ข้อมูลหมวด (data/o14_asset_profiles.csv) ส่งออกมาจาก
production ของ o14 ทั้ง 5 ฐาน (รวม npd_code/npd_depre_rate ที่ tools/setup_profiles.py
ของ o14 ตั้งไว้)

ผังบัญชีบน o18 ไม่ได้ยกมาตรง ๆ รหัสเดียวกันบางบริษัทเป็นคนละบัญชี
(เช่น บ.กรุงเทพ 1410-07 o14 = คอมพิวเตอร์ แต่ o18 = ทรัพย์สินเพื่อให้เช่า)
จึงจับคู่บัญชีตามลำดับความมั่นใจ และไม่เดาเกินนี้:
    1. รหัสเดียวกัน + ชื่อเดียวกัน
    2. ชื่อเดียวกันมีบัญชีเดียว (มีหลายบัญชีให้เลือกตัวที่อยู่หมวดรหัสเดียวกับ o14
       เช่น 5340 -> 53xx ไม่ใช่ 5160)
    3. รหัสเดียวกัน + ชื่อเป็นส่วนหนึ่งของกันและกัน ("อาคาร" -> "ส/ทสนง.-อาคาร")
หมวดที่หาบัญชีไม่ครบ หรือบัญชีค่าใช้จ่ายซ้ำกับค่าเสื่อมสะสม (o14 ตั้งผิดไว้) จะข้าม
และบอกเหตุผลในผลลัพธ์ ให้ฝ่ายบัญชีตั้งเอง
"""
import csv
import logging
import re

from odoo import api, models
from odoo.tools import file_path

_logger = logging.getLogger(__name__)

PROFILE_CSV = 'npd_asset_depreciation/data/o14_asset_profiles.csv'


def _norm(text):
    return re.sub(r'\s+', '', text or '')


class AccountAssetProfileSeed(models.Model):
    _inherit = 'account.asset.profile'

    @api.model
    def _npd_resolve_account(self, company, code, name):
        """(บัญชี, วิธีที่จับคู่ได้) -- หาไม่เจอคืน (บัญชีว่าง, เหตุผล)"""
        # ชื่อบัญชีเป็นฟิลด์แปลภาษา อ่าน/ค้นด้วยภาษาไทย (ไม่มีไทยจะตกไปใช้อังกฤษเอง)
        Account = self.env['account.account'].sudo().with_company(company).with_context(lang='th_TH')
        domain = [('company_ids', 'in', company.ids), ('deprecated', '=', False)]
        target = _norm(name)

        same_code = Account.search(domain + [('code', '=', code)], limit=1)
        if same_code and _norm(same_code.name) == target:
            return same_code, 'code+name'

        by_name = Account.search(domain + [('name', 'ilike', name.strip())]).filtered(
            lambda a: _norm(a.name) == target)
        if len(by_name) > 1:
            family = by_name.filtered(lambda a: (a.code or '')[:3] == code[:3])
            if len(family) != 1:
                family = by_name.filtered(lambda a: (a.code or '')[:2] == code[:2])
            by_name = family
        if len(by_name) == 1:
            return by_name, 'name'

        if same_code:
            other = _norm(same_code.name)
            if target and other and (target in other or other in target):
                return same_code, 'code~name'
        return Account.browse(), 'ไม่มีบัญชี %s %s' % (code, name)

    @api.model
    def _npd_seed_asset_profiles(self):
        """สร้างหมวดที่ยังไม่มี + เติมรหัสหมวด/ร้อยละให้หมวดที่มีอยู่แล้ว (ชื่อตรงกับ o14)

        รันซ้ำได้ ไม่สร้างซ้ำ ไม่เขียนทับรหัสหมวด/ร้อยละที่ผู้ใช้แก้ไว้แล้ว
        คืน list ข้อความสรุป
        """
        with open(file_path(PROFILE_CSV), encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        companies = self.env['res.company'].sudo().search([])
        summary = []
        for company in companies:
            company_rows = [r for r in rows if _norm(r['company_name']) == _norm(company.name)]
            if not company_rows:
                continue
            Profile = self.sudo().with_company(company).with_context(active_test=False)
            journal = self.env['account.journal'].sudo().search(
                [('company_id', '=', company.id), ('code', '=', 'FA')], limit=1)
            created, updated, skipped = [], [], []
            for row in company_rows:
                rate = float(row['npd_depre_rate'] or 0.0)
                profile = Profile.search(
                    [('name', '=', row['name']), ('company_id', '=', company.id)], limit=1)
                if profile:
                    vals = {}
                    if not profile.npd_code and row['npd_code']:
                        vals['npd_code'] = row['npd_code']
                    if not profile.npd_depre_rate and rate:
                        vals['npd_depre_rate'] = rate
                    if vals:
                        profile.write(vals)
                        updated.append(row['name'])
                    continue
                if not journal:
                    skipped.append('%s [ไม่มีสมุดรายวัน FA]' % row['name'])
                    continue

                accounts, notes, problems = {}, [], []
                for field, prefix in (
                    ('account_asset_id', 'asset'),
                    ('account_depreciation_id', 'depreciation'),
                    ('account_expense_depreciation_id', 'expense'),
                ):
                    account, how = self._npd_resolve_account(
                        company, row['%s_code' % prefix], row['%s_account_name' % prefix])
                    if not account:
                        problems.append(how)
                        continue
                    accounts[field] = account
                    if how != 'code+name':
                        notes.append('%s->%s' % (row['%s_code' % prefix], account.code))
                if not problems and accounts['account_expense_depreciation_id'] \
                        == accounts['account_depreciation_id']:
                    problems.append('บัญชีค่าใช้จ่ายซ้ำกับค่าเสื่อมสะสม (o14 ตั้งไว้แบบนี้)')
                if problems:
                    skipped.append('%s [%s]' % (row['name'], '; '.join(problems)))
                    continue

                Profile.create({
                    'name': row['name'],
                    'company_id': company.id,
                    'journal_id': journal.id,
                    'account_asset_id': accounts['account_asset_id'].id,
                    'account_depreciation_id': accounts['account_depreciation_id'].id,
                    'account_expense_depreciation_id': accounts['account_expense_depreciation_id'].id,
                    'method': row['method'],
                    'method_number': int(row['method_number']),
                    'method_period': row['method_period'],
                    'method_time': row['method_time'],
                    'prorata': row['prorata'] == '1',
                    'open_asset': row['open_asset'] == '1',
                    'days_calc': row['days_calc'] == '1',
                    'active': row['active'] == '1',
                    'npd_code': row['npd_code'] or False,
                    'npd_depre_rate': rate,
                })
                created.append(row['name'] + (' (%s)' % ', '.join(notes) if notes else ''))

            lines = ['[%s] สร้าง %s หมวด: %s' % (company.name, len(created), ', '.join(created) or '-')]
            if updated:
                lines.append('[%s] เติมรหัสหมวด/ร้อยละ %s หมวด' % (company.name, len(updated)))
            lines += ['[%s] ข้าม %s' % (company.name, s) for s in skipped]
            for line in lines:
                _logger.info('npd_asset_depreciation: %s', line)
            summary += lines
        return summary
