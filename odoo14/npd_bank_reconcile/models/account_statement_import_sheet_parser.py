# -*- coding: utf-8 -*-
import datetime as dt
import hashlib
import logging
import re
from collections import Counter

from odoo import api, models

from .npd_xlsx_reader import read_xlsx

_logger = logging.getLogger(__name__)

# ปี พ.ศ. 4 หลัก (2400-2699) ที่ไม่ติดกับตัวเลขอื่น เช่น 02/10/2569 หรือ 2569-10-02
# ไม่แตะ 'YYYYMMDD' ติดกัน และปี 2 หลัก (69) เพราะเดาไม่ได้ว่าเป็น พ.ศ. หรือ ค.ศ.
_BE_YEAR_RE = re.compile(r'(?<!\d)(2[4-6]\d{2})(?!\d)')
_BE_OFFSET = 543


def _npd_be_to_ce(value):
    """แปลงปี พ.ศ. เป็น ค.ศ. ทั้งแบบข้อความและ datetime"""
    if isinstance(value, str):
        return _BE_YEAR_RE.sub(lambda m: str(int(m.group(1)) - _BE_OFFSET), value)
    if isinstance(value, dt.datetime) and value.year >= 2400:
        try:
            return value.replace(year=value.year - _BE_OFFSET)
        except ValueError:
            # 29 ก.พ. ของปีที่ ค.ศ. ไม่ใช่ปีอธิกสุรทิน ปล่อยไว้ให้ OCA แจ้ง error เอง
            return value
    return value


def _npd_is_newest_first(lines):
    """ไฟล์ธนาคารไทยหลายเจ้าเรียงใหม่→เก่า

    OCA เรียงตามวันที่แบบ stable แล้วเอาบรรทัดแรกไปคิดยอดยกมา ถ้าไฟล์เรียงกลับด้าน
    ยอดยกมา/ยอดยกไปของใบจะผิด และลำดับรายการในวันเดียวกันจะกลับหัว
    """
    first, last = lines[0]['timestamp'], lines[-1]['timestamp']
    try:
        if first > last:
            return True
        if first < last:
            return False
    except TypeError:
        return False
    # ทั้งไฟล์อยู่วันเดียวกัน (มีแต่วันที่ไม่มีเวลา) ดูจากยอดคงเหลือแทน
    if any(line.get('balance') is None for line in lines):
        return False
    asc = desc = 0
    for prev, cur in zip(lines, lines[1:]):
        if abs(prev['balance'] + cur['amount'] - cur['balance']) < 0.005:
            asc += 1
        if abs(cur['balance'] + prev['amount'] - prev['balance']) < 0.005:
            desc += 1
    return desc > asc


def _npd_sha1(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


class AccountStatementImportSheetParser(models.TransientModel):
    _inherit = 'account.statement.import.sheet.parser'

    def _get_data_parsers(self):
        # ลอง openpyxl ก่อน xlrd: xlrd 2.0.1 (Python 3.12) อ่าน .xlsx ไม่ได้แล้ว
        return [self._npd_parse_data_openpyxl] + super()._get_data_parsers()

    def _npd_parse_data_openpyxl(self, mapping, data_file):
        result = read_xlsx(data_file)
        if result is None and data_file and data_file[:2] == b'PK':
            _logger.debug('openpyxl อ่านไฟล์ไม่ได้ ส่งต่อให้ตัวอ่านถัดไป')
        return result

    def _get_values_from_column(self, values, columns, column_name):
        value = super()._get_values_from_column(values, columns, column_name)
        if column_name == 'timestamp_column':
            # ต้องแปลงก่อน OCA เรียก strptime: 29/02/2567 ไม่มีจริงในปี ค.ศ. 2567
            value = _npd_be_to_ce(value)
        return value

    def _parse_lines(self, mapping, data_file, currency_code):
        lines = super()._parse_lines(mapping, data_file, currency_code)
        if len(lines) > 1 and _npd_is_newest_first(lines):
            lines.reverse()
        return lines

    @api.model
    def _convert_line_to_transactions(self, line):
        res = super()._convert_line_to_transactions(line)
        balance = line.get('balance')
        if balance is None:
            return res
        # ไฟล์ธนาคารไทยไม่มีรหัสธุรกรรม OCA จึงกันนำเข้าซ้ำไม่ได้
        # ใช้ วันเวลา+ยอด+ยอดคงเหลือ+รายละเอียด แทน ยอดคงเหลือทำให้รายการหน้าตาเหมือนกัน
        # ในวันเดียวกันยังได้รหัสต่างกัน
        timestamp = line['timestamp']
        ts_text = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
        description = str(line.get('description') or '').strip()
        key = f"{ts_text}|{float(line['amount']):.2f}|{float(balance):.2f}|{description}"
        unique_id = 'npd-' + _npd_sha1(key)[:24]
        for transaction in res:
            if not transaction.get('unique_import_id'):
                transaction['unique_import_id'] = unique_id
        return res

    @api.model
    def parse(self, data_file, mapping, filename):
        res = super().parse(data_file, mapping, filename)
        _currency_code, _account_number, statements = res
        seen_balance_ids = Counter()
        seen_fallback_keys = Counter()
        for statement in statements:
            for transaction in statement.get('transactions', []):
                unique_id = transaction.get('unique_import_id')
                if unique_id:
                    if unique_id.startswith('npd-'):
                        # รายการซ้ำเป๊ะในไฟล์เดียว (เช่นยอด 0 สองบรรทัด) จะชน SQL UNIQUE
                        # แล้วทั้งไฟล์ล้ม เติมเลขลำดับให้ตัวที่สองเป็นต้นไป
                        seen_balance_ids[unique_id] += 1
                        if seen_balance_ids[unique_id] > 1:
                            transaction['unique_import_id'] = (
                                f"{unique_id}-{seen_balance_ids[unique_id]}"
                            )
                    continue
                # ไม่มีคอลัมน์ยอดคงเหลือ: ใช้ วันที่+ยอด+รายละเอียด + ลำดับที่ซ้ำในไฟล์
                # รายการเหมือนกันสองตัวในวันเดียวจึงยังนำเข้าครบทั้งคู่
                key = (
                    f"{transaction.get('date')}|{transaction.get('amount')}|"
                    f"{transaction.get('payment_ref') or ''}"
                )
                seen_fallback_keys[key] += 1
                transaction['unique_import_id'] = (
                    f"npd-{_npd_sha1(key)[:20]}-{seen_fallback_keys[key]}"
                )
        return res
