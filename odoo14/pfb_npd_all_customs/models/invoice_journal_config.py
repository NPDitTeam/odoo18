# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# กรณีการออกใบแจ้งหนี้ที่ตั้งสมุดรายวันเริ่มต้นได้
USAGES = [
    ('so_sale', 'ใบแจ้งหนี้ - ใบเสนอราคาประเภท Sales'),
    ('so_rent', 'ใบแจ้งหนี้ - ใบเสนอราคาประเภท Rent'),
    ('insurance', 'ใบแจ้งหนี้รับเงินประกัน'),
    ('penalty_lost', 'ใบแจ้งหนี้ค่าปรับหาย'),
    ('penalty_damaged', 'ใบแจ้งหนี้ค่าปรับชำรุด'),
    ('credit_note', 'ใบลดหนี้'),
    ('voucher_sale', 'ใบสำคัญรับ (Voucher ฝั่งรับเงิน)'),
    ('voucher_purchase', 'ใบสำคัญจ่าย / คืนเงินประกัน (Voucher ฝั่งจ่ายเงิน)'),
]

# ประเภทสมุดรายวันที่เลือกได้ของแต่ละกรณี
# ใบสำคัญรับ/จ่ายใช้สมุดรายวันประเภท receivable/payable ที่โมดูล
# account_journal_sequences เพิ่มเข้ามา ไม่ใช่ประเภท sale
USAGE_JOURNAL_TYPES = {
    'voucher_sale': ['receivable'],
    'voucher_purchase': ['payable'],
}
DEFAULT_JOURNAL_TYPES = ['sale']

# สมุดรายวันฝั่งรับ/จ่ายเงินมีสองกลุ่ม แยกกันเด็ดขาดเพราะ Odoo 18 บังคับไว้คนละแบบ
#
# 1) เอกสารใบสำคัญ (account.voucher) - โมเดลของเราเอง ไม่มีข้อจำกัด
#    ใช้ประเภท receivable/payable ที่โมดูล account_journal_sequences เพิ่มเข้ามา
#    (สมุดรายวันรับชำระ*, จ่ายชำระ)
VOUCHER_JOURNAL_TYPES = ['receivable', 'payable']
#
# 2) การรับชำระจริง (account.payment)
#    เปิดให้เลือกได้ทั้ง receivable/payable และ bank/cash/credit ตามที่ผู้ใช้ต้องการ
#    ให้ค่าเริ่มต้นเหมือน Odoo 14
#
#    ข้อควรรู้: Odoo 18 ฮาร์ดโค้ดใน account.payment._compute_available_journal_ids
#    และ domain ของฟอร์มไว้ว่ารับเฉพาะ bank/cash/credit อีกทั้ง
#    account.journal._compute_available_payment_method_ids ตั้ง
#    available_payment_method_ids = False ให้ทุกเล่มที่ไม่ใช่ bank/cash/credit
#    => สมุดรายวัน receivable/payable ตั้ง payment_method_line ไม่ได้เลย
#    หน้ารับชำระของ Odoo จึงเลือกเล่มพวกนี้ไม่ได้ และโพสต์ไม่ผ่าน
PAYMENT_JOURNAL_TYPES = ['receivable', 'payable', 'bank', 'cash', 'credit']

# สมุดรายวันรับชำระเริ่มต้นของแต่ละกรณี ใช้เมื่อยังไม่ได้ตั้งค่าในเมนู
USAGE_PAYMENT_FALLBACK_NAMES = {
    'so_sale': ['สมุดรายวันรับชำระ'],
    'so_rent': ['สมุดรายวันรับชำระ'],
    'insurance': ['สมุดรายวันรับชำระค่าประกัน'],
    'penalty_lost': ['สมุดรายวันรับชำระค่าปรับหาย'],
    'penalty_damaged': ['สมุดรายวันรับชำระค่าปรับชำรุด'],
    'credit_note': ['สมุดรายวันรับชำระลดหนี้'],
}

# ชื่อสมุดรายวันที่ใช้เดาให้อัตโนมัติ เมื่อยังไม่ได้ตั้งค่าในเมนู
# ไล่ตามลำดับ ชื่อแรกที่มีอยู่จริงในบริษัทนั้นเป็นตัวชนะ
# ทำให้บริษัทที่ยังไม่มีเล่มแบบ (สาขา) ตกไปใช้เล่มปกติแทน ไม่ใช่หลุดไปเล่มอื่น
USAGE_FALLBACK_NAMES = {
    'so_sale': ['สมุดรายวันการขาย(สาขา)', 'สมุดรายวันการขาย'],
    'so_rent': ['สมุดรายวันเช่า(สาขา)', 'สมุดรายวันเช่า'],
    'insurance': ['สมุดรายวันค่าประกัน'],
    'penalty_lost': ['สมุดรายวันค่าปรับหาย'],
    'penalty_damaged': ['สมุดรายวันค่าปรับชำรุด'],
    'credit_note': ['สมุดรายวันลดหนี้การขาย', 'สมุดรายวันลดหนี้ขาย'],
    'voucher_sale': ['สมุดรายวันรับชำระ'],
    'voucher_purchase': ['สมุดรายวันจ่ายชำระ'],
}


class NpdInvoiceJournalConfig(models.Model):
    _name = 'npd.invoice.journal.config'
    _description = 'สมุดรายวันเริ่มต้นตอนออกใบแจ้งหนี้'
    _order = 'company_id, usage'
    _rec_name = 'usage'

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.company,
    )
    usage = fields.Selection(
        USAGES, string='กรณีการออกใบแจ้งหนี้', required=True, index=True,
    )
    allowed_journal_ids = fields.Many2many(
        'account.journal', 'npd_journal_config_allowed_rel',
        compute='_compute_allowed_journal_ids',
    )
    journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวัน', required=True, check_company=True,
        domain="[('id', 'in', allowed_journal_ids)]",
        help="สมุดรายวันที่จะถูกใส่ให้อัตโนมัติตอนสร้างเอกสารของกรณีนี้",
    )
    allowed_payment_journal_ids = fields.Many2many(
        'account.journal', 'npd_journal_config_allowed_payment_rel',
        compute='_compute_allowed_journal_ids',
    )
    payment_journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันรับชำระ (ใบสำคัญ)', check_company=True,
        domain="[('id', 'in', allowed_payment_journal_ids)]",
        help="สมุดรายวันของเอกสารใบสำคัญ (account.voucher) "
             "เมื่อใบแจ้งหนี้ที่กำลังรับชำระอยู่ในสมุดรายวันด้านซ้าย\n"
             "เลือกได้เฉพาะประเภท รับชำระ/จ่ายชำระ (receivable/payable)",
    )
    allowed_payment_bank_journal_ids = fields.Many2many(
        'account.journal', 'npd_journal_config_allowed_bank_rel',
        compute='_compute_allowed_journal_ids',
    )
    payment_bank_journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันรับเงิน (Payment)', check_company=True,
        domain="[('id', 'in', allowed_payment_bank_journal_ids)]",
        help="สมุดรายวันที่จะถูกเลือกให้อัตโนมัติในหน้ารับชำระเงิน (account.payment)\n"
             "Odoo 18 อนุญาตเฉพาะประเภท ธนาคาร/เงินสด/เครดิต เท่านั้น\n"
             "เว้นว่างได้ ถ้าเว้นไว้ระบบจะใช้สมุดรายวันเริ่มต้นของ Odoo",
    )
    allowed_income_account_ids = fields.Many2many(
        'account.account', 'npd_journal_config_allowed_income_rel',
        compute='_compute_allowed_journal_ids',
    )
    income_account_id = fields.Many2one(
        'account.account', string='บัญชีรายได้', check_company=True,
        domain="[('id', 'in', allowed_income_account_ids)]",
        help="บัญชีที่จะใส่ให้บรรทัดใบแจ้งหนี้ของกรณีนี้\n"
             "Odoo 18 ให้บัญชีของสินค้า/ประเภทสินค้าชนะบัญชีเริ่มต้นของสมุดรายวัน "
             "ตั้งตรงนี้เพื่อบังคับให้ได้บัญชีเดียวกับ Odoo 14 แน่นอน\n"
             "เว้นว่าง = ปล่อยให้ Odoo เลือกเองตามปกติ",
    )
    product_id = fields.Many2one(
        'product.product', string='สินค้าเงินประกัน',
        domain="['&', ('type', '=', 'service'),"
               " '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="สินค้าที่ใช้เป็นบรรทัดในใบแจ้งหนี้รับเงินประกัน\n"
             "ใช้เฉพาะกรณี 'ใบแจ้งหนี้รับเงินประกัน' เท่านั้น",
    )
    note = fields.Char(string='หมายเหตุ')

    _sql_constraints = [(
        'uniq_company_usage',
        'unique(company_id, usage)',
        'ตั้งค่าสมุดรายวันซ้ำกันไม่ได้ — หนึ่งบริษัทตั้งได้กรณีละหนึ่งเล่มเท่านั้น',
    )]

    @api.depends('usage', 'company_id')
    def _compute_allowed_journal_ids(self):
        Journal = self.env['account.journal']
        for config in self:
            if not config.company_id:
                config.allowed_journal_ids = Journal
                config.allowed_payment_journal_ids = Journal
                config.allowed_payment_bank_journal_ids = Journal
                config.allowed_income_account_ids = self.env['account.account']
                continue
            config.allowed_income_account_ids = self.env['account.account'].search([
                ('company_ids', 'in', config.company_id.id),
                ('deprecated', '=', False),
                ('account_type', 'not in', ('asset_receivable', 'liability_payable')),
            ])
            company_journals = Journal.search([
                ('company_id', '=', config.company_id.id),
            ])
            allowed_types = USAGE_JOURNAL_TYPES.get(
                config.usage, DEFAULT_JOURNAL_TYPES)
            config.allowed_journal_ids = company_journals.filtered(
                lambda j: j.type in allowed_types)
            config.allowed_payment_journal_ids = company_journals.filtered(
                lambda j: j.type in VOUCHER_JOURNAL_TYPES)
            config.allowed_payment_bank_journal_ids = company_journals.filtered(
                lambda j: j.type in PAYMENT_JOURNAL_TYPES)

    @api.constrains('company_id', 'journal_id', 'payment_journal_id',
                    'payment_bank_journal_id')
    def _check_journal_company(self):
        for config in self:
            journals = (config.journal_id | config.payment_journal_id
                        | config.payment_bank_journal_id)
            for journal in journals:
                if journal.company_id != config.company_id:
                    raise ValidationError(_(
                        "สมุดรายวัน %(journal)s เป็นของบริษัท %(jcompany)s "
                        "ไม่ตรงกับบริษัท %(company)s ที่ตั้งค่าไว้",
                        journal=journal.display_name,
                        jcompany=journal.company_id.display_name,
                        company=config.company_id.display_name,
                    ))

    @api.constrains('company_id', 'product_id')
    def _check_product_company(self):
        for config in self:
            product_company = config.product_id.company_id
            if product_company and product_company != config.company_id:
                raise ValidationError(_(
                    "สินค้า %(product)s เป็นของบริษัท %(pcompany)s "
                    "ไม่ตรงกับบริษัท %(company)s ที่ตั้งค่าไว้",
                    product=config.product_id.display_name,
                    pcompany=product_company.display_name,
                    company=config.company_id.display_name,
                ))

    @api.onchange('company_id', 'usage')
    def _onchange_company_id(self):
        # เปลี่ยนบริษัทหรือกรณี แล้วสมุดรายวันเดิมเลือกไม่ได้อีก ให้ล้างทิ้ง
        if self.journal_id and self.journal_id not in self.allowed_journal_ids:
            self.journal_id = False
        if self.payment_journal_id \
                and self.payment_journal_id not in self.allowed_payment_journal_ids:
            self.payment_journal_id = False
        if self.payment_bank_journal_id \
                and self.payment_bank_journal_id not in self.allowed_payment_bank_journal_ids:
            self.payment_bank_journal_id = False
        if self.product_id.company_id and self.product_id.company_id != self.company_id:
            self.product_id = False

    # -------------------------------------------------------------------------
    # API สำหรับโมดูลอื่นเรียกใช้
    # -------------------------------------------------------------------------

    @api.model
    def _get_journal(self, company, usage):
        """คืนสมุดรายวันเริ่มต้นของบริษัท ``company`` สำหรับกรณี ``usage``

        ลำดับการหา
          1. ค่าที่ตั้งไว้ในเมนู "สมุดรายวันออกใบแจ้งหนี้"
          2. เดาจากชื่อสมุดรายวันตาม ``USAGE_FALLBACK_NAMES`` (เผื่อยังไม่ได้ตั้งค่า)

        :return: ``account.journal`` recordset ว่างถ้าหาไม่เจอ
        """
        Journal = self.env['account.journal']
        if not company or not usage:
            return Journal

        # sudo: พนักงานขายทั่วไปต้องอ่านค่าตั้งค่านี้ได้ แต่ไม่ควรมีสิทธิ์แก้
        config = self.sudo().search([
            ('company_id', '=', company.id),
            ('usage', '=', usage),
        ], limit=1)
        if config.journal_id:
            return Journal.browse(config.journal_id.id)

        for name in USAGE_FALLBACK_NAMES.get(usage, []):
            # ต้องล็อก company_id เสมอ: ทุกบริษัทในฐานข้อมูลนี้มีสมุดรายวันชื่อ
            # ซ้ำกัน ถ้าไม่ล็อกแล้วผู้ใช้เปิดหลายบริษัทพร้อมกัน จะคว้าเล่มของ
            # บริษัทอื่นมา แล้วไปตายที่ _check_company ตอนสร้างใบแจ้งหนี้
            # sudo() เพื่อไม่ให้ record rule รายสาขาบังสมุดรายวันจนหาไม่เจอ
            journal = Journal.sudo().search([
                ('name', '=', name),
                ('type', 'in', USAGE_JOURNAL_TYPES.get(usage, DEFAULT_JOURNAL_TYPES)),
                ('company_id', '=', company.id),
            ], limit=1)
            if journal:
                return Journal.browse(journal.id)

        _logger.warning(
            "ยังไม่ได้ตั้งสมุดรายวันกรณี '%s' ของบริษัท %s และหาจากชื่อ %s ไม่เจอ",
            usage, company.display_name, USAGE_FALLBACK_NAMES.get(usage, []),
        )
        return Journal

    @api.model
    def _resolve_journal_by_invoice_journal(self, company, invoice_journals, field_name):
        """หาสมุดรายวันปลายทางจากสมุดรายวันของใบแจ้งหนี้

        ใบแจ้งหนี้ต้องถูกนำมาชำระเสมอ ฝั่งรับชำระจึงอิงสมุดรายวันของใบแจ้งหนี้
        เป็นตัวตั้ง แล้วมาดูว่าแถวนั้นผูกสมุดรายวันตัวไหนไว้ในคอลัมน์ ``field_name``

        :param company: ``res.company`` ของรายการรับชำระ
        :param invoice_journals: ``account.journal`` ของใบแจ้งหนี้ที่กำลังจะชำระ
                                 (ชำระหลายใบพร้อมกันได้ เล่มแรกที่ผูกไว้ชนะ)
        :return: ``account.journal`` recordset ว่างถ้ายังไม่ได้ผูกไว้
        """
        Journal = self.env['account.journal']
        if not company or not invoice_journals:
            return Journal

        # sudo: พนักงานที่รับชำระต้องอ่านค่าตั้งค่านี้ได้ แต่ไม่ควรมีสิทธิ์แก้
        configs = self.sudo().search([
            ('company_id', '=', company.id),
            ('journal_id', 'in', invoice_journals.ids),
            (field_name, '!=', False),
        ])
        # สมุดรายวันใบแจ้งหนี้เล่มเดียวอาจถูกใช้หลายกรณี (เช่นทั้ง Sales และ Rent
        # ชี้เล่มเดียวกัน) ใช้ setdefault ให้แถวแรกตาม _order ชนะเสมอ
        # ผลลัพธ์จะได้คงที่ ไม่แกว่งตามลำดับที่ DB คืนมา
        by_journal = {}
        for config in configs:
            by_journal.setdefault(config.journal_id.id, config[field_name].id)

        # ไล่ตามลำดับใบแจ้งหนี้ที่ส่งเข้ามา ไม่ใช่ลำดับใน DB
        for journal in invoice_journals:
            target_id = by_journal.get(journal.id)
            if target_id:
                return Journal.browse(target_id)
        return Journal

    @api.model
    def _get_payment_journal(self, company, invoice_journals):
        """สมุดรายวันสำหรับ ``account.payment`` (ธนาคาร/เงินสด/เครดิต)

        ห้ามคืนสมุดรายวันประเภท receivable/payable เด็ดขาด เพราะ Odoo 18
        ไม่ยอมให้ account.payment ใช้ และไม่มี payment_method_line ให้เลย
        """
        return self._resolve_journal_by_invoice_journal(
            company, invoice_journals, 'payment_bank_journal_id')

    @api.model
    def _get_voucher_journal(self, company, invoice_journals):
        """สมุดรายวันสำหรับเอกสารใบสำคัญ ``account.voucher`` (รับชำระ/จ่ายชำระ)"""
        return self._resolve_journal_by_invoice_journal(
            company, invoice_journals, 'payment_journal_id')

    @api.model
    def _get_income_account(self, company, usage):
        """คืนบัญชีรายได้ที่ตั้งไว้สำหรับกรณี ``usage``

        :return: ``account.account`` recordset ว่างถ้าไม่ได้ตั้งไว้
                 (ปล่อยให้ Odoo เลือกบัญชีเองตามปกติ)
        """
        Account = self.env['account.account']
        if not company or not usage:
            return Account
        config = self.sudo().search([
            ('company_id', '=', company.id),
            ('usage', '=', usage),
        ], limit=1)
        return Account.browse(config.income_account_id.id) if config.income_account_id else Account

    @api.model
    def _get_insurance_product(self, company):
        """คืนสินค้าที่ใช้เป็นบรรทัดในใบแจ้งหนี้รับเงินประกันของบริษัท ``company``

        ลำดับการหา
          1. ค่าที่ตั้งไว้ในเมนู "สมุดรายวันออกใบแจ้งหนี้" (แยกตามบริษัทได้)
          2. พารามิเตอร์ ``sale.deposit_default_npd_id`` ในหน้าตั้งค่าการขาย
             (ของเดิม เป็นค่ากลางค่าเดียวใช้ร่วมกันทุกบริษัท)

        :return: ``product.product`` recordset ว่างถ้าหาไม่เจอ
        """
        Product = self.env['product.product']
        if company:
            config = self.sudo().search([
                ('company_id', '=', company.id),
                ('usage', '=', 'insurance'),
            ], limit=1)
            if config.product_id:
                return Product.browse(config.product_id.id)

        param = self.env['ir.config_parameter'].sudo().get_param('sale.deposit_default_npd_id')
        if param:
            product = Product.sudo().browse(int(param)).exists()
            if product and product.active:
                return Product.browse(product.id)

        return Product
