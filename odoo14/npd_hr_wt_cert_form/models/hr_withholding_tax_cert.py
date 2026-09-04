from odoo import models, api


class HRWithholdingTaxCert(models.Model):
    _inherit = "hr.withholding.tax.cert"

    def _get_report_base_filename(self):
        self.ensure_one()
        return "HR WT Certificates - %s" % self.display_name

    def _compute_desc_type_other(self, lines, ttype, income_type):
        base_type_other = lines.filtered(
            lambda l: l.wt_cert_income_type in [income_type]
        ).mapped(ttype)
        base_type_other = [x or "" for x in base_type_other]
        desc = ", ".join(base_type_other)
        return desc

    def _group_wt_line(self, lines):
        """รวมยอดรายการเงินได้ตามประเภท — คืนรูป dict เดิมที่เทมเพลตใช้อยู่

        Odoo 18 เปลี่ยน ``read_group`` เป็น ``_read_group`` ที่คืนเป็น tuple
        ไม่ใช่ dict จึงต้องแปลงกลับ ไม่งั้นเทมเพลตที่อ่านด้วยชื่อคีย์จะพัง
        """
        rows = self.env["hr.withholding.tax.cert.line"]._read_group(
            domain=[("id", "in", lines.ids)],
            groupby=["wt_cert_income_type"],
            aggregates=["base:sum", "amount:sum"],
        )
        return [
            {
                "wt_cert_income_type": income_type,
                "base": base_sum or 0.0,
                "amount": amount_sum or 0.0,
            }
            for income_type, base_sum, amount_sum in rows
        ]

    def format_number(self, number):
        return '{:,.2f}'.format(number)

    @staticmethod
    def unit_process(val):
        units = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
        tens = ["", "สิบ", "ยี่สิบ", "สามสิบ", "สี่สิบ", "ห้าสิบ", "หกสิบ", "เจ็ดสิบ", "แปดสิบ", "เก้าสิบ"]
        unit = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]

        length = len(val) > 1
        result = ''

        for index, current in enumerate(map(int, val)):
            if current:
                if index:
                    result = unit[index] + result

                if length and current == 1 and index == 0:
                    result += 'เอ็ด'
                elif index == 1 and current == 2:
                    result = 'ยี่' + result
                elif index != 1 or current != 1:
                    result = units[current] + result

        return result

    @staticmethod
    def thai_num2text(number):
        s_number = str(number)[::-1]
        n_list = [s_number[i:i + 6].rstrip("0") for i in range(0, len(s_number), 6)]
        result = HRWithholdingTaxCert.unit_process(n_list.pop(0))

        for i in n_list:
            result = HRWithholdingTaxCert.unit_process(i) + 'ล้าน' + result

        return result

    @staticmethod
    def amount_to_text_thai(amount):
        """แปลงจำนวนเงินเป็นตัวอักษรไทย

        รับค่าติดลบและศูนย์ได้ ของเดิมส่งเครื่องหมายลบเข้าไปแปลงตรง ๆ
        ทำให้พิมพ์เอกสารไม่ออกทั้งใบเมื่อยอดติดลบ และศูนย์บาทได้คำว่า
        "บาทถ้วน" เฉย ๆ ไม่มีคำว่าศูนย์
        """
        sign = "ลบ" if amount < 0 else ""
        integer_part, decimal_part = "{:.2f}".format(abs(amount)).split(".")
        integer_text = HRWithholdingTaxCert.thai_num2text(int(integer_part)) or "ศูนย์"
        if int(decimal_part) > 0:
            decimal_text = HRWithholdingTaxCert.thai_num2text(int(decimal_part))
            return sign + integer_text + "บาท" + decimal_text + "สตางค์"
        else:
            return sign + integer_text + "บาทถ้วน"

    def amount_to_text_custom(self, amount):
        str_amount = "{:.4f}".format(amount)
        integer_part, decimal_part = str_amount.split(".")
        if len(decimal_part) == 4:
            amount = round(amount, 2)
        return self.amount_to_text_thai(amount)
