"""
แก้ไฟล์ .jrxml หลัง save ผ่าน Jaspersoft Studio 6.21 ก่อน deploy ลง JasperServer
รัน:  python fix_jrxml.py
จะแก้ทุกไฟล์ .jrxml ในโฟลเดอร์ report/ :
  1) textAdjust="StretchHeight" -> isStretchWithOverflow="true"  (อื่น ๆ ลบทิ้ง)
     เพราะ JasperServer ที่ bundle มาไม่รองรับ attribute textAdjust
  2) <property name="ODOO_RELATIONS"><![CDATA[...]]></property>
     -> <property name="ODOO_RELATIONS" value="..."/>
     เพราะรูปแบบ CDATA ทำให้ one2many (บรรทัดสินค้า) วนแค่แถวแรก
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(HERE, "report")


def fix(path):
    s = open(path, encoding="utf-8").read()
    orig = s
    s = s.replace(' textAdjust="StretchHeight"', ' isStretchWithOverflow="true"')
    s = re.sub(r'\s+textAdjust="[^"]*"', '', s)
    s = re.sub(r'(isStretchWithOverflow="true")(\s+isStretchWithOverflow="true")+',
               r'\1', s)
    s = re.sub(
        r'<property name="ODOO_RELATIONS">\s*<!\[CDATA\[(.*?)\]\]>\s*</property>',
        r'<property name="ODOO_RELATIONS" value="\1"/>', s, flags=re.DOTALL)
    if s != orig:
        open(path, "w", encoding="utf-8").write(s)
        print("fixed:", os.path.basename(path))
    else:
        print("ok   :", os.path.basename(path))


if __name__ == "__main__":
    for name in os.listdir(REPORT_DIR):
        if name.endswith(".jrxml"):
            fix(os.path.join(REPORT_DIR, name))
