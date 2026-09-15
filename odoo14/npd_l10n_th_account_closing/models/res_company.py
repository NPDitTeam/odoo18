import csv
import logging
import re
from datetime import date

from dateutil.rrule import MONTHLY, YEARLY

from odoo import Command, fields, models
from odoo.tools import file_path

_logger = logging.getLogger(__name__)

WHT_RATES = (1.0, 2.0, 3.0, 5.0)
# ภาษีที่เราหักผู้ขาย: (รหัสบัญชีค้างจ่าย, แบบ ภ.ง.ด., ชื่อ) รหัสเดียวกันทั้ง 5 บริษัท
WHT_PAYABLE = (
    ("2132-02", "pnd3", "หัก ณ ที่จ่าย ภ.ง.ด.3"),
    ("2132-03", "pnd53", "หัก ณ ที่จ่าย ภ.ง.ด.53"),
)
# ข้อ 5 มาตรา 3 เตรส (ค่าจ้างทำของ/บริการ/ขนส่ง/โฆษณา/ค่าเช่า) ตรงกับอัตรา 1/2/3/5%
# o14 ใช้ข้อ 6 แล้วพิมพ์ระบุเองทุกใบ ถ้าใช้ข้อ 6 ไฟล์ยื่นกรมสรรพากรจะได้คำว่า "อื่นๆ (ระบุ)"
WHT_INCOME_TYPE = "5"
# ภาษีที่ลูกค้าหักเรา: ผังบัญชีแต่ละบริษัทใช้รหัสไม่เหมือนกัน ไล่ตามลำดับ
# แล้วเอาตัวแรกที่ชื่อบอกว่าเป็นภาษีถูกหัก (1510-02 ของ ส.กรุ๊ป คือภาษีจ่ายล่วงหน้า)
WHT_PREPAID_CODES = ("1510-02", "1151-02", "152000")
WHT_PREPAID_LABEL = "ถูกหัก ณ ที่จ่าย"

THAI_MONTHS = "['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']"
DATE_RANGE_TYPES = (
    # (ชื่อ, หน่วย, สร้างล่วงหน้ากี่หน่วย, นิพจน์ชื่อช่วง)
    ("ปีบัญชี", YEARLY, 1, "'ปี %s' % (date_start.year + 543)"),
    ("รายเดือน", MONTHLY, 12, THAI_MONTHS + "[date_start.month - 1] + ' ' + str(date_start.year + 543)"),
)

MIS_REPORTS = (
    ("l10n_th_mis_report.mis_report_bs", "งบแสดงฐานะการเงิน"),
    ("l10n_th_mis_report.mis_report_pl", "งบกำไรขาดทุน"),
)

ASSET_PROFILE_CSV = "npd_l10n_th_account_closing/data/o14_asset_profiles.csv"


def _norm(text):
    return re.sub(r"\s+", "", text or "")


class ResCompany(models.Model):
    _inherit = "res.company"

    def _npd_setup_thai_closing(self):
        """ตั้งค่าบัญชีไทยสำหรับปิดงบให้ทุกบริษัท รันซ้ำได้ ของที่มีอยู่แล้วจะข้าม

        คืนค่ารายการข้อความสรุปต่อบริษัท (ใช้ตรวจตอนติดตั้ง/รันซ้ำจาก shell)
        """
        steps = (
            ("สมุดรายวันภาษีเกณฑ์เงินสด", "_npd_setup_cash_basis_journal"),
            ("ภาษีหัก ณ ที่จ่าย", "_npd_setup_withholding_taxes"),
            ("ช่วงวันที่", "_npd_setup_date_ranges"),
            ("กลุ่มสินทรัพย์", "_npd_setup_asset_profiles"),
            ("รายงาน MIS", "_npd_setup_mis_instances"),
        )
        summary = []
        for company in self.sudo():
            # ฟิลด์ company_dependent (เช่น account.asset_profile_id) ต้องเขียนในบริบทบริษัทนั้น
            company = company.with_company(company)
            for label, method in steps:
                try:
                    with self.env.cr.savepoint():
                        notes = getattr(company, method)()
                except Exception as e:
                    notes = ["ผิดพลาด: %s" % e]
                    _logger.exception("Thai closing setup %s / %s failed", company.name, label)
                for note in notes:
                    line = "[%s] %s: %s" % (company.name, label, note)
                    summary.append(line)
                    _logger.info(line)
        return summary

    def _npd_account_by_code(self, code):
        self.ensure_one()
        return self.env["account.account"].with_company(self).search(
            [("code", "=", code), ("company_ids", "in", self.ids)], limit=1
        )

    def _npd_setup_cash_basis_journal(self):
        """o14 ใช้ CABA (สมุดรายวันกลับรายการภาษี) เป็นสมุดภาษีเกณฑ์เงินสด

        o18 ชี้ไปที่สมุด "ภาษีเกณฑ์เงินสด" ที่ถูกเก็บถาวร รายการโอนภาษีขาย
        ยังไม่ถึงกำหนดจึงโพสต์ไม่ได้
        """
        self.ensure_one()
        current = self.tax_cash_basis_journal_id
        if current and current.active:
            return ["ใช้ %s อยู่แล้ว" % current.name]
        journal = self.env["account.journal"].search(
            [("company_id", "=", self.id), ("code", "=", "CABA"), ("type", "=", "general")],
            limit=1,
        )
        if not journal:
            return ["ไม่พบสมุดรายวัน CABA ข้าม"]
        self.tax_cash_basis_journal_id = journal
        return ["เปลี่ยนเป็น %s (เดิม %s ถูกเก็บถาวร)" % (journal.name, current.name or "-")]

    def _npd_setup_withholding_taxes(self):
        self.ensure_one()
        WhtTax = self.env["account.withholding.tax"]
        notes = []

        def ensure(name, account, vals):
            if WhtTax.search_count([("name", "=", name), ("company_id", "=", self.id)]):
                return False
            if not account.wht_account:
                account.wht_account = True
            WhtTax.create(dict(vals, name=name, account_id=account.id, company_id=self.id))
            return True

        for code, form, label in WHT_PAYABLE:
            account = self._npd_account_by_code(code)
            if not account:
                notes.append("ไม่มีบัญชี %s ข้าม %s" % (code, label))
                continue
            created = [
                rate for rate in WHT_RATES
                if ensure("%s %g%%" % (label, rate), account, {
                    "amount": rate,
                    "income_tax_form": form,
                    "wht_cert_income_type": WHT_INCOME_TYPE,
                })
            ]
            notes.append("%s บัญชี %s สร้าง %s" % (label, code, ", ".join("%g%%" % r for r in created) or "ครบแล้ว"))

        prepaid = self.env["account.account"]
        for code in WHT_PREPAID_CODES:
            account = self._npd_account_by_code(code)
            names = account.with_context(lang="th_TH").name, account.with_context(lang="en_US").name
            if account and (any(WHT_PREPAID_LABEL.replace(" ", "") in _norm(n) for n in names)
                            or "withholding" in (names[1] or "").lower()):
                prepaid = account
                break
        if not prepaid:
            notes.append("ไม่พบบัญชีภาษีถูกหัก ณ ที่จ่าย ข้าม")
            return notes
        created = [
            rate for rate in WHT_RATES
            if ensure("ภาษีถูกหัก ณ ที่จ่าย %g%%" % rate, prepaid, {"amount": rate})
        ]
        notes.append("ภาษีถูกหัก ณ ที่จ่าย บัญชี %s %s สร้าง %s" % (
            prepaid.code, prepaid.name, ", ".join("%g%%" % r for r in created) or "ครบแล้ว"))
        return notes

    def _npd_setup_date_ranges(self):
        """ประเภทช่วงวันที่ต่อบริษัท ตั้ง autogeneration ให้ cron รายวันของ date_range
        สร้างปี/เดือนถัดไปเอง ไม่ต้องมาเพิ่มทุกปี"""
        self.ensure_one()
        DateRangeType = self.env["date.range.type"]
        start = date(fields.Date.context_today(self).year, 1, 1)
        first_move = self.env["account.move"].search(
            [("company_id", "=", self.id)], order="date asc", limit=1
        )
        if first_move and first_move.date < start:
            start = date(first_move.date.year, 1, 1)
        notes = []
        for name, unit, ahead, name_expr in DATE_RANGE_TYPES:
            dr_type = DateRangeType.search([("name", "=", name), ("company_id", "=", self.id)], limit=1)
            if not dr_type:
                dr_type = DateRangeType.create({
                    "name": name,
                    "company_id": self.id,
                    "allow_overlap": False,
                    "name_expr": name_expr,
                    "duration_count": 1,
                    "unit_of_time": str(unit),
                    "autogeneration_date_start": start,
                    "autogeneration_count": ahead,
                    "autogeneration_unit": str(unit),
                })
            before = len(dr_type.date_range_ids)
            wizard = self.env["date.range.generator"].new({"type_id": dr_type.id})
            if wizard.date_end:
                wizard.action_apply(batch=True)
            ranges = dr_type.date_range_ids.sorted("date_start")
            notes.append("%s %s ช่วง (%s ถึง %s) เพิ่มใหม่ %s" % (
                name, len(ranges), ranges[:1].name, ranges[-1:].name, len(ranges) - before))
        return notes

    def _npd_setup_asset_profiles(self):
        """กลุ่มสินทรัพย์ตาม o14 จับคู่บัญชีด้วยรหัส และต้องชื่อบัญชีตรงกันด้วย
        กันผังบัญชีที่รหัสเดียวกันแต่คนละความหมาย ที่ไม่ตรงข้ามไว้ให้ฝ่ายบัญชีตั้งเอง"""
        self.ensure_one()
        with open(file_path(ASSET_PROFILE_CSV), encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if _norm(r["company_name"]) == _norm(self.name)]
        if not rows:
            return ["ไม่มีข้อมูลจาก o14"]
        journal = self.env["account.journal"].search(
            [("company_id", "=", self.id), ("code", "=", "FA")], limit=1
        )
        if not journal:
            return ["ไม่พบสมุดรายวันสินทรัพย์ (FA) ข้าม"]
        Profile = self.env["account.asset.profile"].with_context(active_test=False)
        created, skipped = [], []
        for row in rows:
            if Profile.search_count([("name", "=", row["name"]), ("company_id", "=", self.id)]):
                continue
            accounts, problems = {}, []
            for field, prefix in (
                ("account_asset_id", "asset"),
                ("account_depreciation_id", "depreciation"),
                ("account_expense_depreciation_id", "expense"),
            ):
                code, o14_name = row["%s_code" % prefix], row["%s_account_name" % prefix]
                account = self._npd_account_by_code(code)
                if not account:
                    problems.append("ไม่มี %s" % code)
                elif _norm(account.with_context(lang="th_TH").name) != _norm(o14_name):
                    problems.append("%s ชื่อไม่ตรง (o18: %s / o14: %s)" % (
                        code, account.with_context(lang="th_TH").name, o14_name))
                accounts[field] = account.id
            if problems:
                skipped.append("%s [%s]" % (row["name"], "; ".join(problems)))
                continue
            Profile.create(dict(
                accounts,
                name=row["name"],
                company_id=self.id,
                journal_id=journal.id,
                method=row["method"],
                method_number=int(row["method_number"]),
                method_period=row["method_period"],
                method_time=row["method_time"],
                prorata=row["prorata"] == "1",
                open_asset=row["open_asset"] == "1",
                days_calc=row["days_calc"] == "1",
                active=row["active"] == "1",
            ))
            created.append(row["name"])
        notes = ["สร้าง %s กลุ่ม: %s" % (len(created), ", ".join(created) or "-")]
        notes += ["ข้าม %s" % s for s in skipped]
        return notes

    def _npd_setup_mis_instances(self):
        self.ensure_one()
        Instance = self.env["mis.report.instance"]
        notes = []
        for xmlid, label in MIS_REPORTS:
            report = self.env.ref(xmlid, raise_if_not_found=False)
            if not report:
                notes.append("ไม่พบแม่แบบ %s" % xmlid)
                continue
            if Instance.search_count([("report_id", "=", report.id), ("company_id", "=", self.id)]):
                notes.append("%s มีอยู่แล้ว" % label)
                continue
            Instance.create({
                "name": "%s - %s" % (label, self.name),
                "report_id": report.id,
                "company_id": self.id,
                "target_move": "posted",
                "period_ids": [
                    Command.create({"name": "ปีนี้", "mode": "relative", "type": "y",
                                    "offset": 0, "duration": 1, "sequence": 10}),
                    Command.create({"name": "ปีก่อน", "mode": "relative", "type": "y",
                                    "offset": -1, "duration": 1, "sequence": 20}),
                ],
            })
            notes.append("สร้าง %s" % label)
        return notes
