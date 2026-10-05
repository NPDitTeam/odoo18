# -*- coding: utf-8 -*-
"""ค่าคงที่ของการลงบัญชีเงินเดือน

ชื่อบรรทัดต้องตรงกับที่ ``npd_hrms_payroll`` สร้าง (``_income_items`` / ``_build_lines``)
ทุกตัวอักษร เพราะเอนจินผูกบัญชีจากชื่อบรรทัดในสลิป ไม่ได้ผูกจากชื่อฟิลด์
"""

# บรรทัดที่ระบบเงินเดือนสร้างเอง — "สร้างค่าเริ่มต้น" จะสร้างแถวผังให้ครบทุกตัว
# แม้หาบัญชีไม่เจอ เพื่อให้ฝ่ายบัญชีเห็นว่ายังเหลืออะไรต้องเลือก
KNOWN_LINES = {
    'income': [
        'เงินเดือน',
        'ค่าล่วงเวลา/โอที',
        'ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์',
        'ค่าล่วงเวลา',
        'เงินค่าครองชีพ',
        'เงินประจำตำแหน่ง',
        'เงินค่าประสบการณ์',
        'เงินค่าวิชาชีพ',
        'เบี้ยเลี้ยง นอกสถานที่',
        'ค่าอาหาร',
        'ค่าเดินทาง',
        'อินเซนทีฟ',
        'ค่าคอมมิชชั่น',
        'รายได้อื่นๆ',
    ],
    'deduction': [
        'กองทุนสำรองเลี้ยงชีพ (ตามอัตรา)',
        'กองทุนสำรองเลี้ยงชีพ',
        'เบิกเงินล่วงหน้า',
        'เงินกู้',
        'หักเงินสงเคราะห์ลูกจ้าง',
        'กยศ',
        'หักเงินอื่นๆ',
        'หักสาย',
        'หักลากิจ',
        'หักขาดงาน',
        'หักพักงาน',
        'ประกันสังคม',
        'ภาษีหัก ณ ที่จ่าย',
    ],
}

# บรรทัดรวมที่ข้างในมีหลายเรื่องปนกัน (เงินประกัน/คืนเงินประกัน/โบนัส/ค่าเที่ยว)
# (ประเภท, ชื่อบรรทัด) -> (ฟิลด์ยอดรวมบนสลิป, [ฟิลด์ย่อยที่แยกบัญชีได้])
# แยกได้เฉพาะสลิปที่ยอดบรรทัดตรงกับฟิลด์ยอดรวม — สลิปที่ซิงก์มาจาก o14
# ยอดบรรทัดไม่ตรงกับฟิลด์ (ค่าคอม/รายได้อื่นอยู่แต่ในบรรทัด) ถ้าฝืนแยกจะได้ยอดผิด
SPLIT_KEYS = {
    ('deduction', 'หักเงินอื่นๆ'): (
        'expense_other',
        ['expense_deposit_regular_total', 'expense_deposit_extra_total']),
    ('income', 'รายได้อื่นๆ'): (
        'income_other',
        ['income_deposit_refund_total', 'income_bonus', 'income_missed_payment',
         'other_income_total', 'actor_content_total', 'income_manual_request']),
    ('income', 'ค่าเดินทาง'): (
        'income_transport',
        ['income_transport_trip', 'income_transport_allowance']),
}

# ฟิลด์ย่อย -> (ประเภท, ชื่อบรรทัดแม่)
SPLIT_KEY_PARENT = {
    key: parent
    for parent, (_total, keys) in SPLIT_KEYS.items()
    for key in keys
}

# บัญชีที่ "หักลดค่าใช้จ่ายเงินเดือน" เครดิตเข้าได้ ต้องเป็นบัญชีค่าใช้จ่ายเท่านั้น
EXPENSE_TYPES = ('expense', 'expense_direct_cost')
LIABILITY_TYPES = ('liability_current',)
ASSET_TYPES = ('asset_current',)

SALARY_LINE = 'เงินเดือน'
EMPLOYER_SSO_LINE = 'ประกันสังคม'
DEFAULT_JOURNAL_NAME = 'สมุดรายวันทั่วไป'

LINE_TYPE_SELECTION = [
    ('income', 'รายได้'),
    ('deduction', 'รายการหัก'),
    ('employer', 'นายจ้างสมทบ'),
]
LINE_TYPE_LABELS = dict(LINE_TYPE_SELECTION)

# ค่าเริ่มต้นของแถวผัง: None = ผังใหม่ไม่มีบัญชีที่ใช่ ให้ฝ่ายบัญชีเลือกเอง
# review=True = ชื่อตรงแต่ความหมายอาจไม่ตรงทุกบริษัท ให้ตรวจทาน
# ห้ามใส่รหัสบัญชี ฝ่ายบัญชีเปลี่ยนรหัสไปแล้วครั้งหนึ่ง และรหัสของแต่ละผังไม่ตรงกัน
DEFAULT_CANDIDATES = {
    ('income', 'เงินเดือน'): {'names': ('เงินเดือน',), 'types': EXPENSE_TYPES},
    ('income', 'เงินค่าครองชีพ'): {'names': ('เงินเดือน',), 'types': EXPENSE_TYPES},
    ('income', 'เงินประจำตำแหน่ง'): {'names': ('เงินเดือน',), 'types': EXPENSE_TYPES},
    ('income', 'เงินค่าประสบการณ์'): {'names': ('เงินเดือน',), 'types': EXPENSE_TYPES},
    ('income', 'เงินค่าวิชาชีพ'): {'names': ('เงินเดือน',), 'types': EXPENSE_TYPES},
    ('income', 'ค่าล่วงเวลา/โอที'): {'names': ('ค่าล่วงเวลา',), 'types': EXPENSE_TYPES},
    ('income', 'ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์'): {
        'names': ('ค่าล่วงเวลา',), 'types': EXPENSE_TYPES},
    ('income', 'ค่าล่วงเวลา'): {'names': ('ค่าล่วงเวลา',), 'types': EXPENSE_TYPES},
    ('income', 'ค่าคอมมิชชั่น'): {
        'names': ('ค่านายหน้าและค่าคอมมิชชั่น',), 'types': EXPENSE_TYPES},
    ('income', 'อินเซนทีฟ'): {
        'names': ('โบนัสและผลตอบแทนพิเศษ',), 'types': EXPENSE_TYPES, 'review': True},
    # มีเฉพาะผังขนส่ง บริษัทอื่นจะว่างไว้ให้เลือกเอง
    ('income', 'เบี้ยเลี้ยง นอกสถานที่'): {
        'names': ('ค่าเบี้ยเลี้ยงและค่าใช้จ่ายเดินทางพนักงานขนส่ง',),
        'types': EXPENSE_TYPES, 'review': True},
    ('income', 'ค่าเดินทาง'): {
        'names': ('ค่าเบี้ยเลี้ยงและค่าใช้จ่ายเดินทางพนักงานขนส่ง',),
        'types': EXPENSE_TYPES, 'review': True},
    ('income', 'ค่าอาหาร'): None,
    ('income', 'รายได้อื่นๆ'): None,

    ('deduction', 'ภาษีหัก ณ ที่จ่าย'): {
        'names': ('ภาษีหัก ณ ที่จ่ายค้างจ่าย - ภ.ง.ด.1',), 'types': LIABILITY_TYPES},
    ('deduction', 'ประกันสังคม'): {
        'names': ('เงินสมทบกองทุนประกันสังคมรอนำส่ง',), 'types': LIABILITY_TYPES},
    ('deduction', 'กยศ'): {
        'names': ('เงินกู้ยืม กยศ. รอนำส่ง',), 'types': LIABILITY_TYPES},
    ('deduction', 'หักเงินสงเคราะห์ลูกจ้าง'): {
        'names': ('เงินสะสมกองทุนสงเคราะห์ลูกจ้างรอนำส่ง',), 'types': LIABILITY_TYPES},
    ('deduction', 'เบิกเงินล่วงหน้า'): {
        'names': ('ลูกหนี้ - พนักงาน',), 'types': ASSET_TYPES},
    ('deduction', 'เงินกู้'): {'names': ('ลูกหนี้ - พนักงาน',), 'types': ASSET_TYPES},
    # หักสาย/ลา/ขาด/พักงาน คือเงินเดือนที่ไม่ได้จ่ายจริง ต้องลดค่าใช้จ่ายเงินเดือน
    # ไม่ใช่ตั้งหนี้สิน (บรรทัด "เงินเดือน" เป็นยอดก่อนหักพวกนี้)
    ('deduction', 'หักสาย'): {'reduce_expense': True},
    ('deduction', 'หักลากิจ'): {'reduce_expense': True},
    ('deduction', 'หักขาดงาน'): {'reduce_expense': True},
    ('deduction', 'หักพักงาน'): {'reduce_expense': True},
    # ผังใหม่ไม่มีบัญชีกองทุนสำรองเลี้ยงชีพค้างจ่าย
    ('deduction', 'กองทุนสำรองเลี้ยงชีพ (ตามอัตรา)'): None,
    ('deduction', 'กองทุนสำรองเลี้ยงชีพ'): None,
    ('deduction', 'หักเงินอื่นๆ'): None,

    # แถวแยกจากบรรทัดรวม
    ('deduction', 'expense_deposit_regular_total'): {
        'names': ('เงินประกันการทำงานของพนักงาน',), 'types': LIABILITY_TYPES},
    # คืนเงินประกัน = เดบิตหนี้สินเงินประกันตัวเดียวกัน (ลดหนี้ ไม่ใช่ค่าใช้จ่าย)
    ('income', 'income_deposit_refund_total'): {
        'names': ('เงินประกันการทำงานของพนักงาน',), 'types': LIABILITY_TYPES},
    ('income', 'income_bonus'): {
        'names': ('โบนัสและผลตอบแทนพิเศษ',), 'types': EXPENSE_TYPES},
    # Work Permit เป็นการเรียกเก็บคืนค่าใช้จ่ายของบริษัท ไม่คืนพนักงาน ให้บัญชีเลือกเอง
    ('deduction', 'expense_deposit_extra_total'): None,
}

# แถวแยกที่สร้างให้ตอนกดค่าเริ่มต้น (ตัวอื่นฝ่ายบัญชีเพิ่มเองเมื่อจำเป็น)
DEFAULT_SPLIT_ROWS = [
    ('deduction', 'expense_deposit_regular_total'),
    ('deduction', 'expense_deposit_extra_total'),
    ('income', 'income_deposit_refund_total'),
    ('income', 'income_bonus'),
]

CONFIG_DEFAULTS = {
    'payable_account_id': {
        'names': ('เงินเดือนค้างจ่าย',), 'types': LIABILITY_TYPES},
    'employer_sso_expense_account_id': {
        'names': ('เงินสมทบกองทุนประกันสังคม',), 'types': EXPENSE_TYPES},
    'employer_sso_payable_account_id': {
        'names': ('เงินสมทบกองทุนประกันสังคมรอนำส่ง',), 'types': LIABILITY_TYPES},
}

# สถานะในตารางผลการสร้างค่าเริ่มต้น
STATUS_FOUND = 'ตรงชื่อ'
STATUS_REVIEW = 'ตรงชื่อ-ควรตรวจทาน'
STATUS_MISSING = 'ไม่พบในผัง'
STATUS_DUPLICATE = 'ชื่อซ้ำ'
STATUS_KEEP = 'มีอยู่แล้วไม่แตะ'
STATUS_MANUAL = 'ต้องเลือกเอง'
STATUS_REDUCE = 'หักลดค่าใช้จ่ายเงินเดือน'
