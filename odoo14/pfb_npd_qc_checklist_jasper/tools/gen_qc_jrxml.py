# -*- coding: utf-8 -*-
"""สร้าง qc_checklist.jrxml ทั้งไฟล์

หลักที่ยึด:
  * ความสูงกล่องข้อความ >= 1.4 * ขนาดฟอนต์ ต่อ 1 บรรทัด
    (JasperReports ตัดข้อความทิ้งทั้งบรรทัดถ้าไม่พอ ไม่ใช่แสดงครึ่งเดียว)
  * ลายเซ็น + คำแนะนำ อยู่ใน lastPageFooter จึงถูกตรึงที่ท้ายกระดาษหน้าสุดท้าย
  * ตารางสินค้าเพิ่มเติมวาดกรอบทีละแถว แถวว่างยุบด้วย isRemoveLineWhenBlank
"""
SLOTS = 10          # ต้องตรงกับ QC_EXTRA_SLOTS ใน models/vehicle_booking.py
W = 565
FS, FS_TITLE = 13, 15
TH = 20             # ความสูงมาตรฐานของข้อความ 1 บรรทัดที่ขนาด 13

# ความกว้างคอลัมน์ตาราง QC (รวมต้องเท่ากับ W)
C_ITEM, C_QTY, C_PASS, C_FAIL, C_NOTE = 145, 55, 145, 145, 75
assert C_ITEM + C_QTY + C_PASS + C_FAIL + C_NOTE == W

FLD = "$F{Extra_Items-jasper_qc_extra_items}"
ARR = FLD + r'.split("\\|\\|", -1)'

_uid = [0]


def uid(prefix):
    _uid[0] += 1
    return "c1a2b3c4-%s-0000-0000-%012x" % (prefix, _uid[0])


class Band:
    def __init__(self, prefix):
        self.rows, self.prefix = [], prefix

    def _el(self, kind, x, y, w, h, style, extra_re, body, print_when=None):
        self.rows.append('\t\t\t<%s>' % kind)
        head = ('\t\t\t\t<reportElement style="%s"%s x="%d" y="%d" width="%d" height="%d" uuid="%s"'
                % (style, extra_re, x, y, w, h, uid(self.prefix)))
        if print_when:
            self.rows.append(head + '>')
            self.rows.append('\t\t\t\t\t<printWhenExpression><![CDATA[%s]]></printWhenExpression>'
                             % print_when)
            self.rows.append('\t\t\t\t</reportElement>')
        else:
            self.rows.append(head + '/>')
        self.rows.extend(body)
        self.rows.append('\t\t\t</%s>' % kind)

    def text(self, x, y, w, h, txt, size=FS, bold=False, align="Left",
             valign="Middle", box=None, float_=False, stretch=False,
             print_when=None):
        extra = ' positionType="Float"' if float_ else ''
        body = []
        if box:
            body.append('\t\t\t\t' + box)
        body.append('\t\t\t\t<textElement textAlignment="%s" verticalAlignment="%s">'
                    % (align, valign))
        body.append('\t\t\t\t\t<font fontName="Sarabun" size="%d"%s/>'
                    % (size, ' isBold="true"' if bold else ''))
        body.append('\t\t\t\t</textElement>')
        body.append('\t\t\t\t<text><![CDATA[%s]]></text>' % txt)
        kind = 'staticText'
        if stretch:
            self.rows.append('\t\t\t<staticText isStretchWithOverflow="true">')
            self.rows.append(
                '\t\t\t\t<reportElement style="%s"%s x="%d" y="%d" width="%d" height="%d" uuid="%s"/>'
                % ('Thai', extra, x, y, w, h, uid(self.prefix)))
            self.rows.extend(body)
            self.rows.append('\t\t\t</staticText>')
            return
        self._el(kind, x, y, w, h, 'ThaiBold' if bold else 'Thai', extra, body, print_when)

    def field(self, x, y, w, h, expr, size=FS, bold=False, align="Left",
              valign="Middle", box=None, float_=False, remove_blank=False,
              stretch=False, eval_time=None):
        extra = ''
        if float_:
            extra += ' positionType="Float"'
        if remove_blank:
            extra += ' isRemoveLineWhenBlank="true"'
        body = []
        if box:
            body.append('\t\t\t\t' + box)
        body.append('\t\t\t\t<textElement textAlignment="%s" verticalAlignment="%s">'
                    % (align, valign))
        body.append('\t\t\t\t\t<font fontName="Sarabun" size="%d"%s/>'
                    % (size, ' isBold="true"' if bold else ''))
        body.append('\t\t\t\t</textElement>')
        body.append('\t\t\t\t<textFieldExpression><![CDATA[%s]]></textFieldExpression>' % expr)
        attrs = ' isBlankWhenNull="true"'
        if stretch:
            attrs = ' isStretchWithOverflow="true"' + attrs
        if eval_time:
            attrs += ' evaluationTime="%s"' % eval_time
        self.rows.append('\t\t\t<textField%s>' % attrs)
        self.rows.append(
            '\t\t\t\t<reportElement style="%s"%s x="%d" y="%d" width="%d" height="%d" uuid="%s"/>'
            % ('ThaiBold' if bold else 'Thai', extra, x, y, w, h, uid(self.prefix)))
        self.rows.extend(body)
        self.rows.append('\t\t\t</textField>')

    def rect(self, x, y, w, h):
        self.rows.append('\t\t\t<rectangle>')
        self.rows.append('\t\t\t\t<reportElement positionType="Float" x="%d" y="%d" width="%d" height="%d" uuid="%s"/>'
                         % (x, y, w, h, uid(self.prefix)))
        self.rows.append('\t\t\t\t<graphicElement><pen lineWidth="0.75"/></graphicElement>')
        self.rows.append('\t\t\t</rectangle>')

    def line(self, y, width=1.0, style=None, x=0, w=W, float_=False):
        pen = '<pen lineWidth="%s"%s/>' % (width, ' lineStyle="%s"' % style if style else '')
        self.rows.append('\t\t\t<line>')
        self.rows.append('\t\t\t\t<reportElement%s x="%d" y="%d" width="%d" height="1" uuid="%s"/>'
                         % (' positionType="Float"' if float_ else '', x, y, w, uid(self.prefix)))
        self.rows.append('\t\t\t\t<graphicElement>%s</graphicElement>' % pen)
        self.rows.append('\t\t\t</line>')

    def render(self, tag, height, split=True):
        sp = ' splitType="Stretch"' if split else ''
        return ('\t<%s>\n\t\t<band height="%d"%s>\n%s\n\t\t</band>\n\t</%s>'
                % (tag, height, sp, "\n".join(self.rows), tag))


CELL = '<box leftPadding="4" rightPadding="3"><pen lineWidth="0.75"/></box>'
CELL_C = '<box leftPadding="2" rightPadding="2"><pen lineWidth="0.75"/></box>'
DOT = '<box><bottomPen lineWidth="1.0" lineStyle="Dotted"/></box>'

# ============================================================ pageHeader
ph = Band('0001')
ph.text(0, 0, W, 26, 'ใบส่ง/รับ/ตรวจคุณภาพสินค้า (QC Checklist)',
        size=FS_TITLE, bold=True, align="Center")
ph.text(0, 28, 300, TH, 'ข้อมูลเบื้องต้น (General Info)', bold=True)

ph.text(0, 50, 105, TH, 'ชื่อโครงการ/ลูกค้า:')
ph.field(105, 50, 200, TH, '$F{Partner_Name-partner_id}', box=DOT)
ph.text(313, 50, 35, TH, 'วันที่:')
ph.field(348, 50, 90, TH, '$F{Delivery_Date-jasper_qc_delivery_date}', align="Center", box=DOT)
ph.text(442, 50, 38, TH, 'เวลา:')
ph.field(480, 50, 85, TH,
         '$F{Delivery_Time-jasper_qc_delivery_time} != null && !$F{Delivery_Time-jasper_qc_delivery_time}.isEmpty()'
         ' ? $F{Delivery_Time-jasper_qc_delivery_time} + " น." : ""', align="Center", box=DOT)

ph.text(0, 72, 105, TH, 'ทะเบียนรถขนส่ง:')
ph.field(105, 72, 200, TH, '$F{License_Plate-license_plate_name}', box=DOT)
ph.text(313, 72, 85, TH, 'เที่ยวส่งเลขที่:')
ph.field(398, 72, 167, TH, '$F{Booking_Reference-name}',
         bold=True, align="Center", box=DOT)
ph.line(95)
PAGE_HEADER = ph.render('pageHeader', 98)

# ============================================================ columnHeader
HDR_H = 96
ch = Band('0002')
ch.text(0, 0, 300, TH, 'รายการตรวจสอบ (QC Criteria)', bold=True)
x = 0
for w, label in [
        (C_ITEM, 'รายการสินค้า (Items)'),
        (C_QTY, 'จำนวน (ส่ง/รับ)'),
        (C_PASS, 'ผ่าน (Pass): จำนวนครบ, สภาพสมบูรณ์, ใช้งานได้ทันที => "อนุมัติโหลดขึ้นรถได้"'),
        (C_FAIL, 'ไม่ผ่าน (Fail): พบชิ้นส่วนบิดงอ, แตก, ร้าว, หลวม หรือจำนวนไม่ตรงตามใบส่งนี้ => "STOP โหลดสินค้าทันที"'),
        # "สนิม/บิดงอ/แตก/หลวม" ไม่มีช่องว่างให้ Jasper ตัดบรรทัด ถ้าปล่อยไว้
        # จะโดนตัดกลางคำเป็น "...แตก/ห" + "ลวม)" จึงกำหนดจุดขึ้นบรรทัดเอง
        (C_NOTE, 'หมายเหตุ\n(สภาพสินค้า\nสนิม/บิดงอ/\nแตก/หลวม)')]:
    ch.text(x, 22, w, HDR_H, label, bold=True, align="Center", box=CELL_C)
    x += w
COLUMN_HEADER = ch.render('columnHeader', 22 + HDR_H)

# ============================================================ detail
ROW_H = 22
dt = Band('0003')
dt.field(0, 0, C_ITEM, ROW_H,
         '$V{rowNumber} + ". " + ($F{Line_Product-jasper_qc_product_name} != null'
         ' ? $F{Line_Product-jasper_qc_product_name} : "")',
         box=CELL, stretch=True)
dt.field(C_ITEM, 0, C_QTY, ROW_H, '$F{Line_Quantity-jasper_qc_quantity}',
         align="Center", box=CELL_C)
x = C_ITEM + C_QTY
for w in (C_PASS, C_FAIL, C_NOTE):          # ช่องว่างให้ติ๊กด้วยมือ
    dt.text(x, 0, w, ROW_H, '', box=CELL_C)
    x += w
DETAIL = dt.render('detail', ROW_H)
# ให้กรอบทุกช่องยืดเท่าแถวที่สูงที่สุด
DETAIL = DETAIL.replace('<reportElement style="Thai" x=', '<reportElement style="Thai" stretchType="ContainerHeight" x=')

# ============================================================ pageFooter
pf = Band('0004')
pf.field(0, 3, 300, 16,
         '$F{Print_DateTime-jasper_qc_print_datetime} != null'
         ' ? "พิมพ์เมื่อ " + $F{Print_DateTime-jasper_qc_print_datetime} : ""', size=10)
pf.field(405, 3, 100, 16, '"หน้า " + $V{PAGE_NUMBER} + " / "', size=10, align="Right")
pf.field(505, 3, 60, 16, '"" + $V{PAGE_NUMBER}', size=10, eval_time="Report")
PAGE_FOOTER = pf.render('pageFooter', 22, split=False)

# ============================================================ lastPageFooter
ADVICE = ('ให้นำใบส่ง/รับสินค้านี้ กลับมามอบ ผจก.สาขา - ความศักดิ์สิทธิ์ของลายเซ็น '
          'พร้อมชื่อผู้บรรจงชัดเจน ย้ำทีมงานว่าลายเซ็นที่อยู่ในใบนี้คือ "ความรับผิดชอบ" '
          'ถ้าส่งของเสียไปถึงหน้างาน แล้วในใบนี้ไม่มีลายเซ็น หรือเซ็นแบบผ่านๆ '
          'คนที่ต้องรับผิดชอบ ให้ Coaching ตาม SOP อีกครั้งทันที\n'
          'หมายเหตุ: หากเป็นงานใหญ่ แนะนำให้แนบ "รูปถ่ายของที่โหลดขึ้นรถ" '
          'ส่ง Line ลูกค้า / ผจก.สาขา จะเป็นหลักฐานมัดตัวที่ดีที่สุดครับ')

lf = Band('0006')
lf.line(2)
# เส้นประลายเซ็นทั้งสองเส้น ใช้ x/ความกว้างเดียวกัน และชิดขอบขวาของหน้า
SIG_W = 200
SIG_X = W - SIG_W
lf.text(0, 10, SIG_X, TH, 'ลงชื่อผู้ปฏิบัติงาน (ผู้ตรวจ QC):')
lf.text(SIG_X, 10, SIG_W, TH, '', box=DOT)
lf.text(0, 38, SIG_X, TH, 'ลงชื่อผู้จัดการสาขา/หัวหน้าคลัง (อนุมัติปล่อยรถ):')
lf.text(SIG_X, 38, SIG_W, TH, '', box=DOT)
lf.text(0, 66, 120, TH, 'คำแนะนำ :', bold=True)
lf.text(0, 88, W, 124, ADVICE, valign="Top")   # 6 บรรทัด x 17.6 = 106 px
lf.field(0, 216, 300, 16,
         '$F{Print_DateTime-jasper_qc_print_datetime} != null'
         ' ? "พิมพ์เมื่อ " + $F{Print_DateTime-jasper_qc_print_datetime} : ""', size=10)
lf.field(405, 216, 100, 16, '"หน้า " + $V{PAGE_NUMBER} + " / "', size=10, align="Right")
lf.field(505, 216, 60, 16, '"" + $V{PAGE_NUMBER}', size=10, eval_time="Report")
LAST_PAGE_FOOTER = lf.render('lastPageFooter', 236, split=False)

# ============================================================ summary
sm = Band('0005')
y = 6
sm.text(0, y, 300, TH, 'รายการสินค้าที่ลูกค้าต้องการเพิ่ม', bold=True, float_=True)
y += 22
sm.text(0, y, W - 170, TH, 'รายการสินค้า', bold=True, box=CELL, float_=True)
sm.text(W - 170, y, 170, TH, 'จำนวน', bold=True, align="Center", box=CELL_C, float_=True)
y += TH

for i in range(SLOTS):
    guard = '%s != null && %s.length > %d' % (FLD, ARR, i)
    has_row = '%s && !%s[%d].isEmpty()' % (guard, ARR, i)
    # ช่องชื่อสินค้า: ยุบแถวทิ้งเมื่อไม่มีข้อมูล
    sm.field(0, y, W - 170, TH, '%s ? %s[%d] : ""' % (guard, ARR, i),
             box=CELL, float_=True, remove_blank=True)
    # ช่องจำนวน: ต้องเป็น staticText + printWhenExpression ไม่ใช่ textField ที่คืนค่าว่าง
    # เพราะ JasperReports ถือว่า textField ที่มีแต่ช่องว่าง = blank แล้วไม่วาดกรอบให้
    # ทำให้คอลัมน์จำนวนไม่มีเส้นแบ่งแถว
    sm.text(W - 170, y, 170, TH, '', align="Center", box=CELL_C, float_=True,
            print_when=has_row)
    y += TH

y += 4
sm.field(0, y, W, TH, '$F{Extra_More-jasper_qc_extra_more}', float_=True, remove_blank=True)
y += 24

sm.text(0, y, 300, TH, 'สรุปการตรวจสอบ (Audit Summary)', bold=True, float_=True)
y += 24
for label in ['จำนวนถูกต้องตรงตาม BOM (ใบส่งของ)',
              'สภาพพร้อมใช้งาน 100% (สะอาด, ไม่ชำรุด, อุปกรณ์ไม่หลวม)',
              'เอกสาร (ใบส่งของ/แผนที่/เบอร์ติดต่อ) พร้อมส่ง']:
    sm.rect(2, y + 4, 13, 13)
    sm.text(22, y, W - 22, TH, label, float_=True)
    y += 22

y += 6
sm.text(0, y, W, TH, '**บันทึกเพิ่มเติม (กรณีพบปัญหาหรือเปลี่ยนอุปกรณ์):', bold=True, float_=True)
y += 24
sm.line(y, 1.0, 'Dotted', float_=True)      # เส้นประเดียว
y += 8
SUMMARY = sm.render('summary', y)

# ============================================================ ประกอบไฟล์
FIELDS = [
    ('Booking_Reference-name', 'Booking_Reference-name'),
    ('Partner_Name-partner_id', 'Customer-partner_id/Name-name'),
    ('Delivery_Date-jasper_qc_delivery_date', 'Delivery_Date-jasper_qc_delivery_date'),
    ('Delivery_Time-jasper_qc_delivery_time', 'Delivery_Time-jasper_qc_delivery_time'),
    ('License_Plate-license_plate_name', 'License_Plate-license_plate_name'),
    ('Extra_Items-jasper_qc_extra_items', 'Extra_Items-jasper_qc_extra_items'),
    ('Extra_More-jasper_qc_extra_more', 'Extra_More-jasper_qc_extra_more'),
    ('Print_DateTime-jasper_qc_print_datetime', 'Print_DateTime-jasper_qc_print_datetime'),
    ('Line_Product-jasper_qc_product_name',
     'Order_Lines-order_line_ids/Product-jasper_qc_product_name'),
    ('Line_Quantity-jasper_qc_quantity',
     'Order_Lines-order_line_ids/Quantity-jasper_qc_quantity'),
]
field_xml = "\n".join(
    '\t<field name="%s" class="java.lang.String">\n'
    '\t\t<fieldDescription><![CDATA[%s]]></fieldDescription>\n\t</field>' % f
    for f in FIELDS)

doc = '''<?xml version="1.0" encoding="UTF-8"?>
<!-- ใบส่ง/รับ/ตรวจคุณภาพสินค้า (QC Checklist) - vehicle.booking
     ไฟล์นี้สร้างด้วย scratchpad/gen_qc_jrxml.py (SLOTS=%d)
     ระวัง: ความสูงของกล่องข้อความต้อง >= 1.4 เท่าของขนาดฟอนต์ต่อบรรทัด
            มิฉะนั้น JasperReports จะไม่พิมพ์ข้อความนั้นเลย -->
<jasperReport xmlns="http://jasperreports.sourceforge.net/jasperreports" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://jasperreports.sourceforge.net/jasperreports http://jasperreports.sourceforge.net/xsd/jasperreport.xsd" name="qc_checklist" pageWidth="595" pageHeight="842" columnWidth="%d" leftMargin="15" rightMargin="15" topMargin="10" bottomMargin="10" isSummaryWithPageHeaderAndFooter="true" uuid="c1a2b3c4-d5e6-7890-abcd-222222222222">
\t<property name="com.jaspersoft.studio.data.defaultdataadapter" value="Odoo Jasper"/>
\t<property name="ODOO_RELATIONS" value="['order_line_ids']"/>
\t<property name="com.jaspersoft.studio.unit." value="pixel"/>
\t<property name="net.sf.jasperreports.default.font.name" value="Sarabun"/>
\t<style name="Thai" isDefault="true" fontName="Sarabun" fontSize="%d" pdfFontName="THSarabunNewBold.ttf" pdfEncoding="Identity-H" isPdfEmbedded="true"/>
\t<style name="ThaiBold" fontName="Sarabun" fontSize="%d" isBold="true" pdfFontName="THSarabunNewBold.ttf" pdfEncoding="Identity-H" isPdfEmbedded="true"/>
\t<queryString language="xPath">
\t\t<![CDATA[/data/record]]>
\t</queryString>
%s
\t<variable name="rowNumber" class="java.lang.Integer" calculation="Count">
\t\t<variableExpression><![CDATA[Boolean.TRUE]]></variableExpression>
\t\t<initialValueExpression><![CDATA[0]]></initialValueExpression>
\t</variable>
\t<background>
\t\t<band splitType="Stretch"/>
\t</background>
%s
%s
%s
%s
%s
%s
</jasperReport>
''' % (SLOTS, W, FS, FS, field_xml, PAGE_HEADER, COLUMN_HEADER, DETAIL,
       PAGE_FOOTER, LAST_PAGE_FOOTER, SUMMARY)

OUT = (r"C:\Program Files\Odoo 18.0.20251009\server\odoo\odoo_custom\odoo14"
       r"\pfb_npd_qc_checklist_jasper\report\qc_checklist.jrxml")
open(OUT, "w", encoding="utf-8").write(doc)

print("เขียน qc_checklist.jrxml แล้ว")
print("  pageHeader 98 | columnHeader %d | detail %d | pageFooter 22"
      % (22 + HDR_H, ROW_H))
print("  lastPageFooter 236 | summary %d | ตารางเพิ่มเติม %d แถว" % (y, SLOTS))
