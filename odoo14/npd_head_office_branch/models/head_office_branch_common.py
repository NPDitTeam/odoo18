# -*- coding: utf-8 -*-
"""นิยามกลางของโมดูล กำหนดค่าสาขา -> สาขาสำนักงานใหญ่

ทั้ง 3 เมนูใช้ฟิลด์ชื่อเดียวกัน (HO_FIELD) และใช้ตัวช่วยคำนวณตัวเดียวกัน
เพื่อให้ค่าที่ได้จากการคำนวณตอนกรอกฟอร์ม กับตอนปรับใช้ย้อนหลัง ตรงกันเสมอ
"""

from collections import OrderedDict

# ชื่อฟิลด์ใหม่ที่เพิ่มให้ทั้ง 3 โมเดล
HO_FIELD = 'head_office_branch_id'

# แฟล็กบอกว่าผู้ใช้แก้ HO_FIELD เอง (มีเฉพาะโมเดลที่เปิดให้แก้เองได้)
# ปุ่มปรับใช้ย้อนหลังจะข้ามเอกสารที่ติ๊กไว้
HO_MANUAL_FIELD = 'head_office_branch_manual'

# ประเภทเอกสารของบิลผู้ขาย (เมนู "บิล")
BILL_MOVE_TYPES = ['in_invoice', 'in_refund']

# domain ของเมนู "การรับ" -> เฉพาะ check_type_show_selection = False
# (เขียนแบบ OR เอง เพราะค่าในฐานข้อมูลมีทั้ง NULL และ 'false')
VOUCHER_DOMAIN = [
    '|',
    ('check_type_show_selection', '=', False),
    ('check_type_show_selection', '=', 'false'),
]

# key -> ข้อมูลของแต่ละเมนูที่รองรับ
#   model    : โมเดลของเมนูนั้น
#   config   : ชื่อฟิลด์บนหน้ากำหนดค่า ที่เก็บ "สาขาที่ระบุ" ของเมนูนั้น
#   label    : ชื่อเมนูที่ใช้แสดงผล
#   domain   : ขอบเขตเอกสารของเมนูนั้น (ใช้ตอนปรับใช้ย้อนหลัง)
#   applicable : callable(record) -> bool เงื่อนไขเพิ่มเติมของแต่ละเมนู
#                ถ้าไม่ผ่านเงื่อนไข จะปล่อยฟิลด์ว่างไว้ (None = ใช้ทุกใบ)
DOC_TYPES = OrderedDict([
    ('bill', {
        'model': 'account.move',
        'config': 'bill_branch_ids',
        'label': 'บิลผู้ขาย',
        'domain': [('move_type', 'in', BILL_MOVE_TYPES)],
        'applicable': lambda move: move.move_type in BILL_MOVE_TYPES,
    }),
    ('advance_clear', {
        'model': 'account.advance.clear',
        'config': 'advance_clear_branch_ids',
        'label': 'Avance Clear',
        'domain': [],
        'applicable': None,
    }),
    ('voucher', {
        'model': 'account.voucher',
        'config': 'voucher_branch_ids',
        'label': 'การรับ',
        'domain': VOUCHER_DOMAIN,
        'applicable': lambda voucher: voucher.check_type_show_selection != 'true',
    }),
])

DOC_TYPE_SELECTION = [(key, val['label']) for key, val in DOC_TYPES.items()]


def resolve_head_office_branches(records, doc_type):
    """สาขาที่ระบบควรเติมให้แต่ละใบ (ยังไม่เขียนลงฟิลด์)

    :param records: recordset ของเมนูใดเมนูหนึ่งใน DOC_TYPES
    :param doc_type: key ใน DOC_TYPES
    :return: list ของ (record, res.branch) เรียงตาม ``records``
    """
    Config = records.env['npd.head.office.branch.config']
    empty = records.env['res.branch']
    applicable = DOC_TYPES[doc_type]['applicable']
    has_company = 'company_id' in records._fields
    configs = {}
    result = []
    for record in records:
        if applicable is not None and not applicable(record):
            result.append((record, empty))
            continue
        company = (record.company_id if has_company else False) or record.env.company
        if company.id not in configs:
            configs[company.id] = Config._get_config(company)
        result.append((record, configs[company.id]._resolve_branch(doc_type, record.branch_id)))
    return result


def compute_head_office_branch(records, doc_type):
    """เติมค่าฟิลด์ 'สาขาสำนักงานใหญ่' ให้ ``records``"""
    for record, branch in resolve_head_office_branches(records, doc_type):
        record[HO_FIELD] = branch
