# -*- coding: utf-8 -*-
"""ตัวอ่าน .xlsx ด้วย openpyxl ที่หน้าตาเหมือน xlrd

ทำไมต้องมี: Odoo 18 บน Python 3.12 ล็อก xlrd ไว้ที่ 2.0.1 ซึ่งอ่านได้แค่ .xls
ตัวอ่านไฟล์ของ OCA (account_statement_import_sheet_file) ลอง xlrd ก่อนแล้วตกไป CSV
ไฟล์ .xlsx ของธนาคารจึงพังทุกไฟล์ ไฟล์นี้ห่อผลจาก openpyxl ให้ตัวอ่านของ OCA
ใช้ต่อได้โดยไม่ต้องแก้โค้ด OCA (OCA เรียกแค่ nrows, row_len, row_values,
cell_value, cell_type และ book.datemode)

แยกเป็นไฟล์ไม่พึ่ง odoo เพื่อให้ทดสอบกับไฟล์ตัวอย่างได้โดยไม่ต้องมีฐานข้อมูล
"""
import datetime as dt
import io
import zipfile
from decimal import Decimal

try:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException
except ImportError:  # pragma: no cover - openpyxl เป็น requirement ของ Odoo 18 อยู่แล้ว
    openpyxl = None
    InvalidFileException = ValueError

# ค่าเดียวกับ xlrd.XL_CELL_TEXT ตอบเป็นข้อความเสมอ เพราะวันที่จาก openpyxl
# เป็น datetime อยู่แล้ว ถ้าตอบ XL_CELL_DATE (3) OCA จะเอาไปแปลงซ้ำด้วย
# xldate_as_datetime แล้วพัง
XL_CELL_TEXT = 1

_OPENPYXL_ERRORS = (zipfile.BadZipFile, KeyError, ValueError, OSError, InvalidFileException)


def normalize_cell(value):
    """แปลงค่าจาก openpyxl ให้เหมือนที่ xlrd คืน"""
    if value is None:
        return ''
    # bool เป็นลูกของ int ต้องเช็กก่อน
    if isinstance(value, bool):
        return str(value)
    # _parse_decimal ของ OCA รับแค่ float/Decimal นอกนั้นส่งเข้า re.sub
    # int ดิบ (เช่น 1525) จึงทำให้ TypeError ต้องแปลงเป็น float เหมือน xlrd
    if isinstance(value, (int, Decimal)):
        return float(value)
    if isinstance(value, float):
        return value
    # datetime เป็นลูกของ date ต้องเช็กก่อน
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    if isinstance(value, dt.time):
        return value.strftime('%H:%M:%S')
    return str(value)


def _trim_row(row):
    cells = [normalize_cell(v) for v in row]
    # openpyxl โหมด read_only เติมช่องว่างจนถึงคอลัมน์สุดท้ายตาม dimension ของไฟล์
    while cells and cells[-1] == '':
        cells.pop()
    return cells


class NpdXlsxBook:
    """แทน xlrd.Book OCA ใช้แค่ datemode (ใช้ตอนเจอ XL_CELL_DATE ซึ่งเราไม่ส่ง)"""

    datemode = 0


class NpdXlsxSheet:
    """แทน xlrd.Sheet เฉพาะเมธอดที่ตัวอ่านของ OCA เรียก"""

    def __init__(self, rows):
        self._rows = rows
        self.nrows = len(rows)

    def row_len(self, rowx):
        return len(self._rows[rowx])

    def row_values(self, rowx):
        return list(self._rows[rowx])

    def cell_value(self, rowx, colx):
        return self._rows[rowx][colx]

    def cell_type(self, rowx, colx):
        return XL_CELL_TEXT


def read_xlsx(data_file):
    """คืน (book, sheet) ของชีตแรก หรือ None ถ้าไม่ใช่ไฟล์ .xlsx

    คืน None เพื่อให้ตัวอ่านถัดไปของ OCA (xlrd สำหรับ .xls แล้ว CSV) ได้ลองต่อ
    """
    if openpyxl is None or not data_file or data_file[:2] != b'PK':
        return None
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data_file), read_only=True, data_only=True)
    except _OPENPYXL_ERRORS:
        return None
    try:
        sheets = workbook.worksheets
        rows = [_trim_row(r) for r in sheets[0].iter_rows(values_only=True)] if sheets else []
    except _OPENPYXL_ERRORS:
        return None
    finally:
        workbook.close()
    # ตัดแถวว่างท้ายชีตที่ openpyxl เติมตาม dimension ของไฟล์ ให้ nrows เท่ากับ xlrd
    # ไม่งั้น "จำนวนบรรทัดท้ายไฟล์ที่ข้าม" จะนับผิดแล้วไปข้ามรายการจริงแทนแถวยอดรวม
    while rows and not rows[-1]:
        rows.pop()
    return NpdXlsxBook(), NpdXlsxSheet(rows)
