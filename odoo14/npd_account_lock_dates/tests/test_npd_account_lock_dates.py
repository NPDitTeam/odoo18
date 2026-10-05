# -*- coding: utf-8 -*-
from datetime import date

from freezegun import freeze_time

from odoo import SUPERUSER_ID, Command, fields
from odoo.exceptions import AccessError, RedirectWarning, UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.models.company import LOCK_DATE_FIELDS
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

LOCK_GROUP = 'npd_account_lock_dates.group_npd_lock_manager'
# 2 ต.ค. 2569 เวลาไทย 10:00 -> สิ้นเดือนที่แล้ว = 30 ก.ย.
NOW = '2026-10-02 03:00:00'
END_SEP = date(2026, 9, 30)
END_AUG = date(2026, 8, 31)


@tagged('post_install', '-at_install')
class TestNpdAccountLockDates(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.company_data['company']
        cls.company_b = cls.setup_other_company()['company']
        # ผู้ใช้หลักของคลาสทดสอบเป็นผู้ดูแลบัญชีธรรมดา สร้างผู้ใช้ต้องใช้ sudo
        su_env = cls.env(su=True)
        both = [Command.set([cls.company_a.id, cls.company_b.id])]
        cls.lock_user = new_test_user(
            su_env, login='npd_lock_mgr', groups='base.group_user,' + LOCK_GROUP,
            company_id=cls.company_a.id, company_ids=both, tz=False,
        )
        cls.plain_mgr = new_test_user(
            su_env, login='npd_plain_mgr', groups='base.group_user,account.group_account_manager',
            company_id=cls.company_a.id, company_ids=both,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _wizard(self, user=None, companies=None, **vals):
        companies = companies or self.company_a
        return (
            self.env['npd.account.lock.wizard']
            .with_user(user or self.lock_user)
            .with_context(allowed_company_ids=companies.ids)
            .create(vals)
        )

    def _logs(self, company=None):
        return self.env['npd.account.lock.log'].sudo().search(
            [('company_id', '=', (company or self.company_a).id)]
        )

    def _invoice(self, invoice_date, post=True):
        return self.init_invoice(
            'out_invoice', invoice_date=fields.Date.from_string(invoice_date), amounts=[100.0], post=post,
        )

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------
    def test_01_group_implies_manager(self):
        self.assertTrue(self.lock_user.has_group('account.group_account_manager'))
        self.assertTrue(self.lock_user.has_group(LOCK_GROUP))
        self.assertFalse(self.plain_mgr.has_group(LOCK_GROUP))

    def test_02_defaults_snapshot_company(self):
        self.company_a.sudo().sale_lock_date = date(2026, 6, 30)
        wiz = self._wizard()
        self.assertEqual(wiz.company_id, self.company_a)
        for fname in LOCK_DATE_FIELDS:
            self.assertEqual(wiz['orig_' + fname], self.company_a[fname], fname)
            self.assertEqual(wiz['new_' + fname], self.company_a[fname], fname)
        self.assertEqual(wiz.orig_sale_lock_date, date(2026, 6, 30))
        self.assertFalse(wiz.has_unlock)
        self.assertFalse(wiz.hard_lock_changed)

    def test_03_fill_last_month_thai_time(self):
        self.assertFalse(self.lock_user.tz)
        with freeze_time('2026-10-02 01:00:00'):
            wiz = self._wizard()
            action = wiz.action_fill_last_month()
            self.assertEqual(wiz.new_fiscalyear_lock_date, END_SEP)
            self.assertEqual(wiz.new_tax_lock_date, END_SEP)
            self.assertFalse(wiz.new_sale_lock_date)
            self.assertFalse(wiz.new_purchase_lock_date)
            self.assertFalse(wiz.new_hard_lock_date)
            self.assertEqual(action['type'], 'ir.actions.act_window')
            self.assertEqual(action['res_model'], 'npd.account.lock.wizard')
            self.assertEqual(action['res_id'], wiz.id)
            self.assertEqual(action['target'], 'new')
            # ยังไม่บันทึกเข้าบริษัทจนกว่าจะกดบันทึก
            self.assertFalse(self.company_a.fiscalyear_lock_date)
        # 30 ก.ย. 18:00 UTC = 1 ต.ค. 01:00 เวลาไทย: ถ้าใช้ UTC จะได้ 31 ส.ค. (ผิดเดือน)
        with freeze_time('2026-09-30 18:00:00'):
            wiz = self._wizard()
            wiz.action_fill_last_month()
            self.assertEqual(wiz.new_fiscalyear_lock_date, END_SEP)
            self.assertEqual(wiz.new_tax_lock_date, END_SEP)

    @freeze_time(NOW)
    def test_04_apply_and_log(self):
        wiz = self._wizard()
        wiz.action_fill_last_month()
        result = wiz.action_apply()
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(result['params']['type'], 'success')
        self.assertEqual(result['params']['next'], {'type': 'ir.actions.act_window_close'})
        self.assertEqual(self.company_a.fiscalyear_lock_date, END_SEP)
        self.assertEqual(self.company_a.tax_lock_date, END_SEP)
        self.assertFalse(self.company_a.sale_lock_date)
        self.assertRecordValues(self._logs().sorted('field_name'), [
            {'field_name': 'fiscalyear_lock_date', 'user_id': self.lock_user.id, 'source': 'wizard',
             'direction': 'lock', 'old_date': False, 'new_date': END_SEP},
            {'field_name': 'tax_lock_date', 'user_id': self.lock_user.id, 'source': 'wizard',
             'direction': 'lock', 'old_date': False, 'new_date': END_SEP},
        ])

    @freeze_time(NOW)
    def test_05_access_rights(self):
        Wizard = self.env['npd.account.lock.wizard']
        with self.assertRaises(AccessError):
            Wizard.with_user(self.plain_mgr).create({})
        with self.assertRaises(AccessError):
            self.env['npd.account.lock.log'].with_user(self.plain_mgr).search([])
        with self.assertRaises(AccessError):
            self.env['npd.account.lock.status'].with_user(self.plain_mgr).search([])

        # เรียก action_apply ผ่าน RPC ตรง ๆ โดยไม่มีกลุ่ม ต้องโดนกันฝั่งเซิร์ฟเวอร์
        wiz = Wizard.sudo().create({'company_id': self.company_a.id, 'new_sale_lock_date': END_AUG})
        with self.assertRaises(AccessError):
            wiz.with_user(self.plain_mgr).with_context(allowed_company_ids=self.company_a.ids).action_apply()
        self.assertFalse(self.company_a.sale_lock_date)

        # ประวัติแก้/ลบไม่ได้แม้เป็นผู้ปิดงวด
        self.company_a.sudo().sale_lock_date = END_AUG
        log = self._logs()
        self.assertEqual(len(log), 1)
        with self.assertRaises(AccessError):
            log.with_user(self.lock_user).write({'note': 'แก้ประวัติ'})
        with self.assertRaises(AccessError):
            log.with_user(self.lock_user).unlink()
        with self.assertRaises(AccessError):
            self.env['npd.account.lock.log'].with_user(self.lock_user).create({
                'company_id': self.company_a.id, 'user_id': self.lock_user.id,
                'field_name': 'fiscalyear_lock_date', 'direction': 'lock',
            })

    @freeze_time(NOW)
    def test_06_hard_lock(self):
        wiz = self._wizard(new_hard_lock_date=END_AUG)
        self.assertTrue(wiz.hard_lock_changed)
        with self.assertRaises(UserError):
            wiz.action_apply()  # ยังไม่ติ๊กยืนยัน
        wiz.hard_lock_confirm = True
        with self.assertRaises(UserError):
            wiz.action_apply()  # ไม่มีเหตุผล
        self.assertFalse(self.company_a.hard_lock_date)

        wiz.note = 'ส่งงบการเงินและยื่นภาษีแล้ว'
        wiz.action_apply()
        self.assertEqual(self.company_a.hard_lock_date, END_AUG)
        self.assertRecordValues(self._logs(), [{
            'field_name': 'hard_lock_date', 'direction': 'lock', 'source': 'wizard',
            'old_date': False, 'new_date': END_AUG, 'note': 'ส่งงบการเงินและยื่นภาษีแล้ว',
        }])

        # ล้างทิ้งหรือถอยหลังไม่ได้ แม้ติ๊กยืนยันและกรอกเหตุผลแล้ว
        for bad_value in (False, date(2026, 7, 31)):
            wiz = self._wizard(new_hard_lock_date=bad_value, hard_lock_confirm=True, note='ลองถอย')
            with self.assertRaises(UserError):
                wiz.action_apply()
            self.assertEqual(self.company_a.hard_lock_date, END_AUG)
        self.assertEqual(len(self._logs()), 1)

    @freeze_time(NOW)
    def test_07_core_gate_draft_moves(self):
        draft = self._invoice('2026-08-15', post=False)
        self.assertEqual(draft.state, 'draft')
        self.assertEqual(draft.date, date(2026, 8, 15))
        log_count = len(self._logs())

        wiz = self._wizard(new_hard_lock_date=END_AUG, hard_lock_confirm=True, note='ล็อกถาวร')
        self.assertEqual(wiz.draft_move_count, 1)
        # ตัวตรวจของ Odoo ยังทำงาน: มีเอกสารร่างในช่วง ล็อกถาวรไม่ได้ และไม่มีแถวประวัติ
        with self.assertRaises(RedirectWarning):
            wiz.action_apply()
        self.env.invalidate_all()
        self.assertFalse(self.company_a.hard_lock_date)
        self.assertEqual(len(self._logs()), log_count)

    @freeze_time(NOW)
    def test_08_unlock_needs_reason(self):
        self.company_a.sudo().fiscalyear_lock_date = END_SEP

        wiz = self._wizard(new_fiscalyear_lock_date=END_AUG)
        self.assertTrue(wiz.has_unlock)
        with self.assertRaises(UserError):
            wiz.action_apply()
        self.assertEqual(self.company_a.fiscalyear_lock_date, END_SEP)

        wiz.note = 'ปลดล็อกเพื่อแก้ใบแจ้งหนี้ ก.ย.'
        wiz.action_apply()
        self.assertEqual(self.company_a.fiscalyear_lock_date, END_AUG)
        self.assertRecordValues(self._logs()[0], [{
            'field_name': 'fiscalyear_lock_date', 'direction': 'unlock', 'source': 'wizard',
            'old_date': END_SEP, 'new_date': END_AUG, 'note': 'ปลดล็อกเพื่อแก้ใบแจ้งหนี้ ก.ย.',
        }])

        # ล้างค่าทิ้ง = ปลดล็อกเหมือนกัน
        wiz = self._wizard(new_fiscalyear_lock_date=False)
        self.assertTrue(wiz.has_unlock)
        with self.assertRaises(UserError):
            wiz.action_apply()
        wiz.note = 'ยกเลิกปิดงวดชั่วคราว'
        wiz.action_apply()
        self.assertFalse(self.company_a.fiscalyear_lock_date)
        self.assertRecordValues(self._logs()[0], [{
            'field_name': 'fiscalyear_lock_date', 'direction': 'unlock',
            'old_date': END_AUG, 'new_date': False, 'note': 'ยกเลิกปิดงวดชั่วคราว',
        }])

    @freeze_time(NOW)
    def test_09_upper_limit_end_of_last_month(self):
        wiz = self._wizard(new_fiscalyear_lock_date=date(2026, 10, 1))
        with self.assertRaises(UserError):
            wiz.action_apply()
        self.assertFalse(self.company_a.fiscalyear_lock_date)
        self.assertFalse(self._logs())

    @freeze_time(NOW)
    def test_10_stale_screen(self):
        wiz = self._wizard()
        self.assertFalse(wiz.orig_fiscalyear_lock_date)
        # คนอื่น (หรือ AI-IT) ล็อกไปแล้วระหว่างที่หน้าจอนี้เปิดค้าง
        self.company_a.sudo().write({'fiscalyear_lock_date': '2026-08-31'})
        wiz.new_fiscalyear_lock_date = END_SEP
        with self.assertRaises(UserError):
            wiz.action_apply()
        self.assertEqual(self.company_a.fiscalyear_lock_date, END_AUG)

    @freeze_time(NOW)
    def test_11_company_must_be_in_switcher(self):
        wiz = self._wizard(company_id=self.company_b.id, new_fiscalyear_lock_date=END_SEP)
        with self.assertRaises(UserError):
            wiz.action_apply()
        self.assertFalse(self.company_b.sudo().fiscalyear_lock_date)

    def test_12_log_from_other_sources(self):
        company = self.company_a.sudo()
        company.write({'sale_lock_date': '2026-09-30'})
        self.assertRecordValues(self._logs(), [{
            'field_name': 'sale_lock_date', 'source': 'other', 'direction': 'lock',
            'user_id': self.env.user.id, 'old_date': False, 'new_date': END_SEP, 'note': False,
        }])
        # เขียนค่าเดิมซ้ำ / เขียนฟิลด์อื่น ไม่เกิดแถวขยะ
        company.write({'sale_lock_date': '2026-09-30'})
        company.write({'name': 'บริษัททดสอบ'})
        self.assertEqual(len(self._logs()), 1)

    @freeze_time(NOW)
    def test_13_status_overview(self):
        company_a, company_b = self.company_a, self.company_b
        company_a.sudo().write({'fiscalyear_lock_date': '2026-08-31'})
        wiz = self._wizard(new_hard_lock_date=date(2026, 7, 31), hard_lock_confirm=True, note='ล็อกถาวรปีก่อน')
        wiz.action_apply()
        company_b.sudo().write({'tax_lock_date': '2026-09-30'})

        # เลือกบริษัท A อย่างเดียวที่มุมขวาบน แต่หน้าสถานะต้องเห็นทุกบริษัทที่มีสิทธิ์
        rows = (
            self.env['npd.account.lock.status']
            .with_user(self.lock_user)
            .with_context(allowed_company_ids=company_a.ids)
            .search([])
        )
        self.assertEqual(set(rows.company_id.ids), {company_a.id, company_b.id})

        row_a = rows.filtered(lambda r: r.company_id == company_a)
        self.assertRecordValues(row_a, [{
            'fiscalyear_lock_date': END_AUG, 'tax_lock_date': False, 'sale_lock_date': False,
            'purchase_lock_date': False, 'hard_lock_date': date(2026, 7, 31),
            'effective_lock_date': END_AUG,
        }])
        last_a = self._logs(company_a)[0]
        self.assertEqual(row_a.last_change_user_id, self.lock_user)
        self.assertEqual(row_a.last_change_user_id, last_a.user_id)
        self.assertEqual(row_a.last_change_date, last_a.change_datetime)

        row_b = rows.filtered(lambda r: r.company_id == company_b)
        self.assertRecordValues(row_b, [{
            'fiscalyear_lock_date': False, 'tax_lock_date': END_SEP, 'hard_lock_date': False,
            'effective_lock_date': False, 'active_exception_count': 0,
        }])
        self.assertEqual(row_b.last_change_user_id, self.env.user)

        # กดเปิดแถวบริษัทที่ไม่ได้ติ๊ก: ฟอร์มขอ display_name ทุกครั้ง ต้องไม่ติดกฎ res.company
        # ล้าง cache ก่อน ไม่งั้นชื่อบริษัท B ที่อ่านด้วย sudo ไว้แล้วจะบังปัญหา
        self.env.invalidate_all()
        data = row_b.web_read({'display_name': {}, 'company_id': {'fields': {'display_name': {}}}})
        self.assertEqual(data[0]['display_name'], company_b.sudo().display_name)
        self.assertEqual(data[0]['company_id']['display_name'], company_b.sudo().display_name)

    @freeze_time(NOW)
    def test_14_core_redates_instead_of_refusing(self):
        """บันทึกพฤติกรรมของ Odoo ที่ต้องบอกฝ่ายบัญชี: ล็อกแล้วไม่ได้ห้ามผ่านรายการ แต่ย้ายวันที่บัญชี"""
        posted_before_lock = self._invoice('2026-09-10')
        self.assertEqual(posted_before_lock.state, 'posted')
        self.company_a.sudo().fiscalyear_lock_date = END_SEP

        late = self._invoice('2026-09-15')
        self.assertEqual(late.invoice_date, date(2026, 9, 15))
        self.assertEqual(late.date, date(2026, 10, 2))

        with self.assertRaises(UserError):
            posted_before_lock.button_draft()
        self.env.invalidate_all()
        self.assertEqual(posted_before_lock.state, 'posted')

    def test_15_menus_only_for_lock_group(self):
        menu_ids = {
            self.env.ref('npd_account_lock_dates.' + xmlid).id
            for xmlid in ('menu_npd_account_lock_wizard', 'menu_npd_account_lock_status', 'menu_npd_account_lock_log')
        }
        Menu = self.env['ir.ui.menu']
        self.assertLessEqual(menu_ids, Menu.with_user(self.lock_user)._visible_menu_ids())
        self.assertFalse(menu_ids & Menu.with_user(self.plain_mgr)._visible_menu_ids())

    @freeze_time(NOW)
    def test_16_unlock_needs_group_from_any_path(self):
        """AI-IT "ถอยกลับ" / สคริปต์ที่เขียนบริษัทผ่าน sudo: ถอยวันล็อกได้เฉพาะกลุ่มผู้ปิดงวด หรือ OdooBot"""
        as_mgr = self.company_a.with_user(self.plain_mgr).sudo()
        as_mgr.write({'fiscalyear_lock_date': END_SEP})  # ล็อกไปข้างหน้าจากช่องทางอื่นยังทำได้
        self.assertEqual(self.company_a.fiscalyear_lock_date, END_SEP)
        for bad_value in (END_AUG, False):
            with self.assertRaises(AccessError):
                as_mgr.write({'fiscalyear_lock_date': bad_value})
            self.assertEqual(self.company_a.fiscalyear_lock_date, END_SEP)

        # ผู้ปิดงวดถอยได้แม้ไม่ผ่านหน้าจอ แต่ประวัติขึ้นเป็นช่องทางอื่น
        self.company_a.with_user(self.lock_user).sudo().write({'fiscalyear_lock_date': END_AUG})
        # OdooBot (สคริปต์ shell / งานตั้งเวลา) ถอยได้
        self.company_a.with_user(SUPERUSER_ID).write({'fiscalyear_lock_date': False})
        self.assertFalse(self.company_a.fiscalyear_lock_date)
        self.assertRecordValues(self._logs(), [
            {'user_id': SUPERUSER_ID, 'direction': 'unlock', 'source': 'other',
             'old_date': END_AUG, 'new_date': False},
            {'user_id': self.lock_user.id, 'direction': 'unlock', 'source': 'other',
             'old_date': END_SEP, 'new_date': END_AUG},
            {'user_id': self.plain_mgr.id, 'direction': 'lock', 'source': 'other',
             'old_date': False, 'new_date': END_SEP},
        ])

    def test_17_forged_wizard_context_is_not_trusted(self):
        """ใส่ context ว่ามาจากหน้าจอเองผ่าน RPC ไม่ได้ทำให้ประวัติขึ้นว่าผ่านหน้าจอ"""
        self.company_a.sudo().with_context(
            npd_lock_source='wizard', npd_lock_note='อ้างว่ามาจากหน้าจอ',
        ).write({'purchase_lock_date': '2026-09-30'})
        self.assertRecordValues(self._logs(), [{
            'field_name': 'purchase_lock_date', 'source': 'other', 'note': 'อ้างว่ามาจากหน้าจอ',
        }])

    @freeze_time(NOW)
    def test_18_lock_exception_guarded_and_logged(self):
        """ข้อยกเว้นการล็อกของ Odoo ปลดล็อกได้โดยไม่แตะวันล็อกบริษัท ต้องโดนกติกาเดียวกัน"""
        self.company_a.sudo().fiscalyear_lock_date = END_SEP
        LockException = self.env['account.lock_exception'].with_context(
            allowed_company_ids=self.company_a.ids,
        )
        vals = {
            'company_id': self.company_a.id,
            'user_id': False,
            'fiscalyear_lock_date': date(2026, 7, 31),
            'reason': 'แก้ใบแจ้งหนี้ ก.ค.',
        }
        # ACL ของ Odoo ให้ผู้ดูแลบัญชีทุกคนสร้างได้ ต้องโดนกัน
        with self.assertRaises(AccessError):
            LockException.with_user(self.plain_mgr).create(dict(vals))
        with self.assertRaises(UserError):
            LockException.with_user(self.lock_user).create(dict(vals, reason=' '))

        log_count = len(self._logs())
        exception = LockException.with_user(self.lock_user).create(dict(vals))
        self.assertEqual(exception.state, 'active')
        self.assertEqual(len(self._logs()), log_count + 1)
        last = self._logs()[0]
        self.assertRecordValues(last, [{
            'source': 'exception', 'field_name': 'fiscalyear_lock_date', 'direction': 'unlock',
            'old_date': END_SEP, 'new_date': date(2026, 7, 31), 'user_id': self.lock_user.id,
        }])
        self.assertIn('แก้ใบแจ้งหนี้ ก.ค.', last.note)

        Status = self.env['npd.account.lock.status'].with_user(self.lock_user).with_context(
            allowed_company_ids=self.company_a.ids,
        )
        self.assertEqual(Status.search([('company_id', '=', self.company_a.id)]).active_exception_count, 1)

        # บริษัทเปลี่ยนวันล็อก -> Odoo คัดลอกข้อยกเว้นใหม่ (_recreate) ต้องไม่ติดตัวกันและไม่เกิดแถวประวัติซ้ำ
        self._wizard(new_fiscalyear_lock_date=END_AUG, note='ถอยเพื่อแก้เอกสาร ส.ค.').action_apply()
        self.assertEqual(self.company_a.fiscalyear_lock_date, END_AUG)
        self.assertEqual(len(self._logs()), log_count + 2)
        self.assertEqual(self._logs()[0].source, 'wizard')
        exceptions = self.env['account.lock_exception'].sudo().with_context(active_test=False).search(
            [('company_id', '=', self.company_a.id)],
        )
        self.assertEqual(len(exceptions), 2)
        self.assertEqual(exceptions.filtered('active').company_lock_date, END_AUG)
        self.env.invalidate_all()
        self.assertEqual(Status.search([('company_id', '=', self.company_a.id)]).active_exception_count, 1)
