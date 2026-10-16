# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class NpdPayrollMonthlySummary(models.Model):
    """รายงานสรุปรายได้ต่อเดือน — อ่านจากหน้าทำเงินเดือนตรง ๆ (ไม่เก็บข้อมูลซ้ำ)

    นับเฉพาะเดือนที่มีรอบทำเงินเดือน (ไม่ใช่ร่าง/ยกเลิก) เหมือน o14
    — รอบที่ยกจาก o14 เป็นของทั้งเครือ แต่ฝั่ง 18 ผูกได้บริษัทเดียว จึงไม่เทียบบริษัทของรอบ
    บริษัท = บริษัทที่จ่ายในเดือนนั้นจากแถว ภ.ง.ด.1 (สลิปที่ยกจาก o14 ใช้สังกัดปัจจุบันของพนักงาน
    ซึ่งผิดสำหรับคนที่ย้ายบริษัท ส.ค. 2569) ไม่มีแถวค่อยใช้บริษัทของสลิป
    """
    _name = 'npd.payroll.monthly.summary'
    _description = 'รายงานสรุปรายได้ต่อเดือน'
    _auto = False
    _order = 'year desc, month desc, company_id, employee_code'

    payroll_id = fields.Many2one('payroll.salary', string='สลิป', readonly=True)
    employee_id = fields.Many2one('employee.salary', string='พนักงาน', readonly=True)
    employee_code = fields.Char(string='รหัสพนักงาน', readonly=True)
    taxid = fields.Char(string='เลขผู้เสียภาษี', readonly=True)
    employee_name = fields.Char(string='ชื่อ-สกุล', readonly=True)
    company_id = fields.Many2one('res.company', string='บริษัท', readonly=True)
    branch_id = fields.Many2one('res.branch', string='สาขา', readonly=True)
    year = fields.Char(string='ปี', readonly=True)
    month = fields.Integer(string='เดือน', readonly=True, aggregator=False)
    period = fields.Char(string='งวด', readonly=True)
    # ตามแบบที่ HR กำหนด (ตัวอย่างเดือน 9/2569)
    net_income = fields.Float(string='รายได้ (รวมรายรับทั้งหมด)', readonly=True)
    tax_monthly = fields.Float(string='ภงด.1', readonly=True,
                               help='ภาษีหัก ณ ที่จ่ายในสลิปเดือนนั้น (ยอดเดียวกับรายงาน ภ.ง.ด.1)')
    sso_wage = fields.Float(string='ประกันสังคม (ฐานค่าจ้าง)', readonly=True,
                            help='เงินเดือน + เงินประจำตำแหน่ง + ค่าประสบการณ์ + ค่าวิชาชีพ + ค่าครองชีพ')
    sso_total = fields.Float(string='ยื่นประกันสังคม', readonly=True,
                             help='เงินสมทบประกันสังคมที่หักในสลิป')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT p.id AS id,
                       p.id AS payroll_id,
                       e.id AS employee_id,
                       e.employee_code AS employee_code,
                       regexp_replace(COALESCE(NULLIF(e.id_card_number, ''), e.passport_number, ''),
                                      '[^0-9A-Za-z]', '', 'g') AS taxid,
                       TRIM(CONCAT_WS(' ', e.prefix_th, e.firstname, e.lastname)) AS employee_name,
                       COALESCE(lc.company_id, p.company_id) AS company_id,
                       e.branch_id AS branch_id,
                       p.year AS year,
                       p.month AS month,
                       CONCAT(p.year, '/', LPAD(p.month::text, 2, '0')) AS period,
                       COALESCE(p.total_gross, 0) AS net_income,
                       COALESCE(p.tax_monthly, 0) AS tax_monthly,
                       COALESCE(p.base_salary, 0) + COALESCE(p.income_position_allowance, 0)
                         + COALESCE(p.income_experience_allowance, 0)
                         + COALESCE(p.income_professional_allowance, 0)
                         + COALESCE(p.income_cost_of_living, 0) AS sso_wage,
                       COALESCE(p.sso_total, 0) AS sso_total
                  FROM payroll_salary p
                  JOIN employee_salary e ON e.id = p.employee_id
                  LEFT JOIN LATERAL (
                        SELECT l.company_id FROM pnd1_line l
                         WHERE l.payroll_id = p.id AND l.source_type = 'system'
                         ORDER BY l.id LIMIT 1) lc ON TRUE
                 WHERE EXISTS (SELECT 1 FROM payroll_period pp
                                WHERE pp.year::text = p.year AND pp.month = p.month
                                  AND COALESCE(pp.state, '') NOT IN ('draft', 'cancelled'))
            )
        """ % self._table)
