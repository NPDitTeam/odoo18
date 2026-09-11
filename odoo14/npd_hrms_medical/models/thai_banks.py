# -*- coding: utf-8 -*-
"""รายชื่อธนาคารไทย — ชุดเดียวกับที่แอปใช้ (ส่งให้แอปผ่าน /manual_time/medical_info)

รหัสต้องตรงกับ BANK_SELECTION ของ employee.salary (npd_hrms_base) เพื่อให้ดึงบัญชี
ที่ผูกไว้กับพนักงานมาเติมให้อัตโนมัติได้

    code  : รหัสธนาคาร (เก็บลง DB)
    name  : ชื่อเต็ม ใช้โชว์ใน dropdown ของแอป
    short : ชื่อย่อ ใช้ประกอบหมายเหตุอัตโนมัติ เช่น "ธ.ไทยพาณิชย์"
"""

THAI_BANKS = [
    {'code': 'KBANK', 'name': 'ธนาคารกสิกรไทย', 'short': 'ธ.กสิกรไทย'},
    {'code': 'BBL', 'name': 'ธนาคารกรุงเทพ', 'short': 'ธ.กรุงเทพ'},
    {'code': 'KTB', 'name': 'ธนาคารกรุงไทย', 'short': 'ธ.กรุงไทย'},
    {'code': 'SCB', 'name': 'ธนาคารไทยพาณิชย์', 'short': 'ธ.ไทยพาณิชย์'},
    {'code': 'BAY', 'name': 'ธนาคารกรุงศรีอยุธยา', 'short': 'ธ.กรุงศรีอยุธยา'},
    {'code': 'TTB', 'name': 'ธนาคารทหารไทยธนชาต', 'short': 'ธ.ทหารไทยธนชาต'},
    {'code': 'GSB', 'name': 'ธนาคารออมสิน', 'short': 'ธ.ออมสิน'},
    {'code': 'UOB', 'name': 'ธนาคารยูโอบี', 'short': 'ธ.ยูโอบี'},
    {'code': 'CIMBT', 'name': 'ธนาคารซีไอเอ็มบีไทย', 'short': 'ธ.ซีไอเอ็มบีไทย'},
    {'code': 'KKP', 'name': 'ธนาคารเกียรตินาคินภัทร', 'short': 'ธ.เกียรตินาคินภัทร'},
    {'code': 'LHBANK', 'name': 'ธนาคารแลนด์ แอนด์ เฮ้าส์', 'short': 'ธ.แลนด์ แอนด์ เฮ้าส์'},
    {'code': 'TISCO', 'name': 'ธนาคารทิสโก้', 'short': 'ธ.ทิสโก้'},
    {'code': 'BAAC', 'name': 'ธนาคารเพื่อการเกษตรและสหกรณ์การเกษตร', 'short': 'ธ.ก.ส.'},
    {'code': 'GHB', 'name': 'ธนาคารอาคารสงเคราะห์', 'short': 'ธอส.'},
    {'code': 'ISBT', 'name': 'ธนาคารอิสลามแห่งประเทศไทย', 'short': 'ธ.อิสลาม'},
    {'code': 'PROMPTPAY', 'name': 'พร้อมเพย์ (PromptPay)', 'short': 'พร้อมเพย์'},
]

BANK_SHORT_BY_CODE = {bank['code']: bank['short'] for bank in THAI_BANKS}


def bank_short_name(code):
    """ชื่อย่อธนาคารสำหรับหมายเหตุ — ไม่รู้จักรหัสก็คืนรหัสเดิม"""
    if not code:
        return ''
    return BANK_SHORT_BY_CODE.get(code, code)
