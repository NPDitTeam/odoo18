# -*- coding: utf-8 -*-
"""รายงาน ภ.ง.ด.1 — ภาษีหัก ณ ที่จ่ายรายเดือน แยกตามบริษัท

ข้อมูลมี 2 แหล่ง (``source_type``)
  * ``excel``  ผู้ใช้นำเข้า/กรอกเอง (แก้ไขได้)
  * ``system`` ดึงจากรอบทำเงินเดือน (แก้ไขไม่ได้ ระบบสร้างให้)

ต่างจาก Odoo 14 ตรงที่ **บริษัทเป็น Many2one ไม่ใช่ตัวเลือกข้อความ**
ของเดิมเก็บชื่อบริษัทเป็นสตริงตายตัว 5 รายการในโค้ด ซึ่งเพิ่มบริษัทใหม่ไม่ได้
และใช้กับระบบที่ปล่อยเช่าให้ลูกค้าไม่ได้เลย เพราะชื่อบริษัทของเราไปติดอยู่ในโค้ด

โมเดลนี้เป็นฐานของหนังสือรับรองหัก ณ ที่จ่าย (50 ทวิ) ซึ่งดึงยอดเงินได้และภาษี
ทั้งปีจากที่นี่
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class Pnd1Line(models.Model):
    _name = 'pnd1.line'
    _description = 'รายงาน ภ.ง.ด.1'
    _order = 'pay_date desc, id desc'

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True,
        default=lambda self: self.env.company)
    id_card_number = fields.Char(string='เลขบัตรประจำตัวประชาชน', index=True)
    full_name = fields.Char(string='ชื่อ-นามสกุล')
    pay_date = fields.Date(string='วัน/เดือน/ปี')
    income = fields.Float(string='จำนวนเงินได้')
    tax = fields.Float(string='ภาษีที่ต้องหัก')
    source_type = fields.Selection([
        ('excel', 'เข้าผ่าน excel'),
        ('system', 'ดึงจากในระบบ'),
    ], string='ประเภทการลงข้อมูล', default='excel', required=True, index=True)

    # ── ความเชื่อมโยงกับระบบ (เฉพาะ source_type='system') ──
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', ondelete='set null')
    payroll_id = fields.Many2one(
        'payroll.salary', string='รายการเงินเดือน', ondelete='cascade')
    period_id = fields.Many2one(
        'payroll.period', string='รอบทำเงินเดือน', ondelete='cascade')

    @api.model
    def sync_from_period(self, period):
        """สร้าง/อัปเดตบรรทัด ภ.ง.ด.1 ประเภท 'system' จากสลิปในรอบนี้

        ลบบรรทัด system เดิมของรอบทิ้งก่อนแล้วสร้างใหม่ เพื่อไม่ให้มีข้อมูลค้าง
        เมื่อคำนวณรอบซ้ำ — และไม่ยุ่งกับบรรทัดที่นำเข้าจาก excel

        คืนค่า: จำนวนบรรทัดที่สร้าง
        """
        period = period or self
        created = 0
        for prd in period:
            self.search([
                ('period_id', '=', prd.id),
                ('source_type', '=', 'system'),
            ]).unlink()

            vals_list = []
            skipped = []
            for payroll in prd.salary_ids:
                emp = payroll.employee_id
                if not emp:
                    continue
                company = emp.company_id or payroll.company_id
                if not company:
                    # บริษัทเป็นช่องบังคับ — ไม่มีแล้วแถวนี้จะไม่โผล่ในรายงานของใครเลย
                    skipped.append(emp.display_name)
                    continue
                prefix = dict(emp._fields['prefix_th'].selection).get(
                    emp.prefix_th, '') if emp.prefix_th else ''
                full_name = ('%s%s %s' % (prefix, emp.firstname or '',
                                          emp.lastname or '')).strip()
                vals_list.append({
                    'company_id': company.id,
                    'id_card_number': emp.id_card_number or '',
                    'full_name': full_name,
                    'pay_date': payroll.payment_date,
                    'income': payroll.net_salary or 0.0,
                    'tax': payroll.tax_monthly or 0.0,
                    'source_type': 'system',
                    'employee_id': emp.id,
                    'payroll_id': payroll.id,
                    'period_id': prd.id,
                })
            if vals_list:
                self.create(vals_list)
                created += len(vals_list)
            if skipped:
                _logger.warning('[PND1] ข้ามพนักงานที่ไม่มีบริษัท %d คน: %s',
                                len(skipped), ', '.join(skipped))
            _logger.info('[PND1] รอบ %s สร้าง %d บรรทัด',
                         prd.display_name, len(vals_list))
        self._apply_system_names_to_excel()
        return created

    @api.model
    def _apply_system_names_to_excel(self):
        """ใช้ชื่อจากระบบแทนชื่อที่พิมพ์เองในแถว excel เมื่อเลขบัตรตรงกัน

        ชื่อที่นำเข้าจาก excel เป็นข้อความพิมพ์เอง รูปแบบมักไม่ตรงกับในระบบ
        ถ้าปล่อยไว้ หนังสือรับรองหัก ณ ที่จ่ายจะพิมพ์ชื่อไม่ตรงกับทะเบียนพนักงาน

        ใช้ SQL เพราะแถว excel มักมีหลักหมื่นแถวต่อปี การวนแก้ทีละแถวผ่าน ORM
        ช้าเกินจะใช้งานจริง
        """
        self.env['pnd1.line'].flush_model(
            ['source_type', 'id_card_number', 'full_name'])
        self.env.cr.execute("""
            UPDATE pnd1_line AS e
               SET full_name = s.full_name
              FROM (
                    SELECT DISTINCT ON (btrim(id_card_number))
                           btrim(id_card_number) AS id_card,
                           full_name
                      FROM pnd1_line
                     WHERE source_type = 'system'
                       AND btrim(COALESCE(id_card_number, '')) <> ''
                       AND btrim(COALESCE(full_name, '')) <> ''
                     ORDER BY btrim(id_card_number), id DESC
                   ) AS s
             WHERE e.source_type = 'excel'
               AND btrim(COALESCE(e.id_card_number, '')) = s.id_card
               AND COALESCE(e.full_name, '') <> s.full_name
        """)
        updated = self.env.cr.rowcount
        if updated:
            self.env['pnd1.line'].invalidate_model(['full_name'])
            _logger.info('[PND1] เติมชื่อจากระบบให้แถว excel %d บรรทัด', updated)
        return updated

    @api.model
    def get_year_totals(self, id_card_number, year, company=None):
        """รวมเงินได้และภาษีทั้งปีของเลขบัตรนี้ — ใช้โดยหนังสือรับรอง 50 ทวิ

        รับปีเป็น ค.ศ. หรือ พ.ศ. ก็ได้ และค้นครอบทั้งสองแบบ เพราะแถวที่นำเข้าจาก
        excel บางชุดเก็บ ``pay_date`` เป็น พ.ศ.

        คืนค่า (เงินได้รวม, ภาษีรวม)
        """
        card = (id_card_number or '').strip()
        if not card:
            return 0.0, 0.0
        try:
            y = int(year)
        except (TypeError, ValueError):
            return 0.0, 0.0
        y = y - 543 if y >= 2500 else y

        domain = [('id_card_number', '=', card)]
        if company:
            domain.append(('company_id', '=', company.id))
        yb = y + 543
        domain += [
            '|',
            '&', ('pay_date', '>=', '%04d-01-01' % y),
                 ('pay_date', '<=', '%04d-12-31' % y),
            '&', ('pay_date', '>=', '%04d-01-01' % yb),
                 ('pay_date', '<=', '%04d-12-31' % yb),
        ]
        lines = self.sudo().search(domain)
        return sum(lines.mapped('income')), sum(lines.mapped('tax'))
