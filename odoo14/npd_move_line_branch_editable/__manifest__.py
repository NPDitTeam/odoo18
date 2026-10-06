{
    'name': 'NPD Journal Item Branch Editable',
    'version': '18.0.1.0.0',
    'summary': 'สาขา (Branch) ของบรรทัดรายการสมุดรายวัน: ค่าเริ่มต้นตามหัวเอกสาร แก้รายบรรทัดได้',
    'description': """
พอร์ตจาก o14 npd_move_line_branch_editable (pfb1)

o18: สาขาของบรรทัดบัญชี (multi_branch_management_aagam) เป็นช่องแยก ค่าเริ่มต้น
= สาขาของผู้ใช้ จึงไม่ตรงกับหัวเอกสารได้ง่าย และไม่แสดงในแท็บรายการสมุดบัญชี

ตอนนี้: ค่าเริ่มต้นตามหัวเอกสาร (เหมือน o14) แก้รายบรรทัดได้ และแสดงคอลัมน์ Branch
ในแท็บรายการสมุดบัญชีรายวัน — รายงานค่าคอม/งบรายรับ-รายจ่ายรายสาขาใช้สาขาของบรรทัด
ในส่วน JV เช่น ย้ายเงินสมทบประกันสังคมของ JV เงินเดือนสาขาไปสำนักงานใหญ่

ข้อควรรู้: เปลี่ยนสาขาที่หัวเอกสารภายหลัง ทุกบรรทัดจะกลับไปตามหัวเอกสาร
    """,
    'category': 'Accounting',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['account', 'multi_branch_management_aagam'],
    'data': ['views/account_move_views.xml'],
    'installable': True,
    'auto_install': False,
}
