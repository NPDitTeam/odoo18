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
import calendar
import logging
import re
from datetime import date

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
    def _normalize_pay_date(self, value):
        """วันที่ที่พิมพ์ปี พ.ศ. ลงช่องวันที่ของ Excel (เช่น 2569-01-28) → ปี ค.ศ.

        ถ้าไม่แปลง ระบบจะมองเป็นปีอนาคต เรียงลำดับและกรองตามปีผิดทั้งรายงาน
        """
        d = fields.Date.to_date(value)
        if not d or d.year < 2500:
            return value
        year = d.year - 543
        return date(year, d.month, min(d.day, calendar.monthrange(year, d.month)[1]))

    @api.model
    def _normalize_taxid(self, taxid):
        """เลขบัตรสำหรับจับคู่: เอาเฉพาะตัวเลขแล้วตัด 0 นำหน้า

        Excel ตัด 00 หน้าเลขบัตรต่างด้าวทิ้งเมื่อช่องนั้นเป็นตัวเลข
        """
        return re.sub(r'\D', '', taxid or '').lstrip('0')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('pay_date'):
                vals['pay_date'] = self._normalize_pay_date(vals['pay_date'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('pay_date'):
            vals['pay_date'] = self._normalize_pay_date(vals['pay_date'])
        return super().write(vals)

    @api.model
    def _system_pay_date(self, payroll):
        """วันที่ของแถวรายงาน — ใช้วันจ่ายของสลิปถ้าตรงเดือน/ปีของสลิปนั้น

        สลิปที่ทำนอกรอบมักติดวันจ่าย default เป็นเดือนที่กดสร้าง ถ้าใช้ตามนั้น
        ยอดจะไปโผล่ผิดเดือน จึงถอยไปใช้วันที่ 28 ของเดือนสลิปแทน
        """
        pay = payroll.payment_date
        try:
            year, month = int(payroll.year), int(payroll.month)
        except (TypeError, ValueError):
            return pay
        if pay and pay.year == year and pay.month == month:
            return pay
        return date(year, month, min(28, calendar.monthrange(year, month)[1]))

    @api.model
    def _prepare_system_vals(self, payroll, company):
        emp = payroll.employee_id
        prefix = dict(emp._fields['prefix_th'].selection).get(
            emp.prefix_th, '') if emp.prefix_th else ''
        full_name = ('%s%s %s' % (prefix, emp.firstname or '',
                                  emp.lastname or '')).strip()
        return {
            'company_id': company.id,
            'id_card_number': emp.id_card_number or '',
            'full_name': full_name,
            'pay_date': self._system_pay_date(payroll),
            # ฝ่ายบัญชี: เงินได้ใน ภ.ง.ด.1 = รายรับ (รวมรายได้ก่อนหักรายการหัก)
            'income': payroll.total_gross or 0.0,
            'tax': payroll.tax_monthly or 0.0,
            'source_type': 'system',
            'employee_id': emp.id,
            'payroll_id': payroll.id,
            'period_id': payroll.period_id.id or False,
        }

    @api.model
    def _managed_months(self):
        """เดือนที่ทำเงินเดือนด้วยระบบแล้ว — เดือนก่อนหน้านั้นยึดข้อมูลที่นำเข้าจาก excel

        สลิปที่ทำไว้ตอนทดลองระบบก่อนเริ่มใช้จริงจะได้ไม่ไปทับตัวเลขที่ยื่นภาษีไปแล้ว
        """
        return {
            (p.year, p.month)
            for p in self.env['payroll.period'].search(
                [('state', 'not in', ('draft', 'cancelled'))])
        }

    @api.model
    def _sync_payrolls(self, payrolls, months=None):
        """ทำให้แถว ภ.ง.ด.1 (system) ตรงกับสลิปที่ส่งมา

        * มีแถวอยู่แล้ว → อัปเดตเงินได้/ภาษี โดยคงบริษัทเดิมของเดือนนั้น
        * ยังไม่มีแถว → สร้างให้ (บริษัท = สังกัดปัจจุบัน) แล้วลบแถว excel ที่ซ้ำ

        คืนค่า dict จำนวนที่อัปเดต/สร้าง/ลบ
        """
        result = {'updated': 0, 'created': 0, 'excel_removed': 0}
        if months is None:
            months = self._managed_months()
        payrolls = payrolls.filtered(
            lambda p: p.employee_id and (p.year, p.month) in months)
        if not payrolls:
            return result

        line_by_payroll = {}
        for line in self.search([('source_type', '=', 'system'),
                                 ('payroll_id', 'in', payrolls.ids)]):
            line_by_payroll.setdefault(line.payroll_id.id, line)

        new_vals = []
        for payroll in payrolls:
            income = payroll.total_gross or 0.0
            tax = payroll.tax_monthly or 0.0
            line = line_by_payroll.get(payroll.id)
            if line:
                if (abs((line.income or 0.0) - income) > 0.005
                        or abs((line.tax or 0.0) - tax) > 0.005):
                    line.write({'income': income, 'tax': tax})
                    result['updated'] += 1
            else:
                company = payroll.employee_id.company_id or payroll.company_id
                if company:
                    new_vals.append(self._prepare_system_vals(payroll, company))

        if new_vals:
            created = self.create(new_vals)
            result['created'] = len(created)
            result['excel_removed'] = self._remove_excel_overlaps(created)
        return result

    @api.model
    def _sync_payrolls_safe(self, payrolls):
        """เรียกตอนบันทึกสลิป — รายงานล้มต้องไม่ทำให้บันทึกเงินเดือนล้มตาม"""
        try:
            with self.env.cr.savepoint():
                self._sync_payrolls(payrolls)
        except Exception:
            _logger.exception('[PND1] อัปเดตรายงานตอนบันทึกสลิปไม่สำเร็จ')

    @api.model
    def reconcile_system_lines(self):
        """ตามเก็บสลิปที่แก้หลังอนุมัติ หรือทำนอกรอบ ให้รายงานตรงเสมอ

        รอบถูกดึงเข้ารายงานตอนอนุมัติครั้งเดียว ถ้ามีการแก้ยอดทีหลังหรือเพิ่มสลิป
        นอกรอบ รายงานจะค้างเป็นยอดเก่าโดยไม่มีใครรู้
        """
        result = {'updated': 0, 'created': 0, 'excel_removed': 0}
        months = self._managed_months()
        if not months:
            return result
        domain = ['|'] * (len(months) - 1)
        for year, month in sorted(months):
            domain += ['&', ('year', '=', year), ('month', '=', month)]
        payrolls = self.env['payroll.salary'].search(domain)
        result = self._sync_payrolls(payrolls, months)
        if any(result.values()):
            _logger.info('[PND1] ตามเก็บ: อัปเดต %(updated)d สร้าง %(created)d '
                         'ลบแถว excel ที่ซ้ำ %(excel_removed)d', result)
        return result

    @api.model
    def _remove_excel_overlaps(self, system_lines):
        """ลบแถว excel ที่ซ้ำกับแถวระบบ (คนเดียวกัน บริษัทเดียวกัน เดือนเดียวกัน)"""
        to_remove = self.browse()
        for line in system_lines:
            taxid = self._normalize_taxid(line.id_card_number)
            if not line.pay_date or not taxid:
                continue
            year, month = line.pay_date.year, line.pay_date.month
            last_day = calendar.monthrange(year, month)[1]
            candidates = self.search([
                ('source_type', '=', 'excel'),
                ('company_id', '=', line.company_id.id),
                '|',
                '&', ('pay_date', '>=', date(year, month, 1)),
                     ('pay_date', '<=', date(year, month, last_day)),
                '&', ('pay_date', '>=', date(year + 543, month, 1)),
                     ('pay_date', '<=', date(year + 543, month, last_day)),
            ])
            to_remove |= candidates.filtered(
                lambda l: self._normalize_taxid(l.id_card_number) == taxid)
        count = len(to_remove)
        to_remove.unlink()
        return count

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
            # จำบริษัทเดิมของแต่ละสลิปไว้ก่อนลบ — พนักงานที่ย้ายบริษัทภายหลัง
            # ต้องไม่ถูกย้ายยอดของเดือนเก่าตามไปด้วย ไม่งั้น 50 ทวิ ของทั้งสองบริษัทผิด
            existing = self.search([
                ('period_id', '=', prd.id),
                ('source_type', '=', 'system'),
            ])
            company_by_payroll = {
                line.payroll_id.id: line.company_id
                for line in existing if line.payroll_id
            }
            existing.unlink()

            vals_list = []
            skipped = []
            for payroll in prd.salary_ids:
                emp = payroll.employee_id
                if not emp:
                    continue
                company = (company_by_payroll.get(payroll.id)
                           or emp.company_id or payroll.company_id)
                if not company:
                    # บริษัทเป็นช่องบังคับ — ไม่มีแล้วแถวนี้จะไม่โผล่ในรายงานของใครเลย
                    skipped.append(emp.display_name)
                    continue
                vals = self._prepare_system_vals(payroll, company)
                vals['period_id'] = prd.id
                vals_list.append(vals)
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
