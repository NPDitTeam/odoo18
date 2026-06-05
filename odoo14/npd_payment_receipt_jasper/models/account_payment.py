import base64
import logging

from odoo import models, fields, api, tools

_logger = logging.getLogger(__name__)
_logger.warning('[jasper_rcp] account_payment.py loaded (version with payment_method_one_id support)')

THAI_MONTHS_SHORT = {
    1: 'ม.ค.', 2: 'ก.พ.', 3: 'มี.ค.', 4: 'เม.ย.',
    5: 'พ.ค.', 6: 'มิ.ย.', 7: 'ก.ค.', 8: 'ส.ค.',
    9: 'ก.ย.', 10: 'ต.ค.', 11: 'พ.ย.', 12: 'ธ.ค.',
}

SIGNATURE_RESOURCE_PATH = (
    'npd_payment_receipt_jasper/static/img/Signature.png'
)

BANK_NAME_MAP = [
    ('SCB', 'ธนาคารไทยพาณิชย์'),
    ('KBANK', 'ธนาคารกสิกรไทย'),
    ('BBL', 'ธนาคารกรุงเทพ'),
    ('KTB', 'ธนาคารกรุงไทย'),
    ('BAY', 'ธนาคารกรุงศรีอยุธยา'),
]


def _format_thai_date_short(dt):
    if not dt:
        return ''
    day = dt.strftime('%d')
    month = THAI_MONTHS_SHORT.get(dt.month, '')
    year_short = str(dt.year + 543)[-2:]
    return '{} {} {}'.format(day, month, year_short)


def _join_address(*parts):
    return ' '.join(p for p in parts if p)


def _bank_name_from_code(code):
    if not code:
        return ''
    up = code.upper()
    for key, thai_name in BANK_NAME_MAP:
        if key in up:
            return thai_name
    return ''


def _safe_get(obj, attr, default=None):
    if not obj:
        return default
    try:
        val = getattr(obj, attr, default)
    except Exception:
        return default
    if val is False or val is None:
        return default
    return val


def _format_cheque_info(cheque):
    bank = _safe_get(cheque, 'bank_id', False)
    bank_name = _safe_get(bank, 'name', '') or ''
    branch_name = _safe_get(bank, 'branch_name', '') or ''
    cheque_no = _safe_get(cheque, 'name', '') or ''
    return 'ธนาคาร: {} สาขา: {} เลขที่เช็ค: {}'.format(
        bank_name, branch_name, cheque_no,
    )


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    note = fields.Text(string='หมายเหตุ')

    jasper_baht_text = fields.Char(
        string='Baht Text',
        compute='_compute_jasper_baht_text',
    )
    jasper_date_thai = fields.Char(
        string='Date (Thai short)',
        compute='_compute_jasper_date_thai',
    )
    jasper_partner_full_address = fields.Char(
        string='Partner Full Address',
        compute='_compute_jasper_partner_full_address',
    )
    jasper_rcp_partner_vat = fields.Char(
        string='Partner VAT Display',
        compute='_compute_jasper_rcp_partner_vat',
    )
    jasper_company_name_display = fields.Char(
        string='Company Name Display',
        compute='_compute_jasper_company_name_display',
    )
    jasper_company_logo = fields.Binary(
        string='Company Logo (branch company)',
        compute='_compute_jasper_company_branch_info',
    )
    jasper_company_vat = fields.Char(
        string='Company VAT (branch company)',
        compute='_compute_jasper_company_branch_info',
    )
    jasper_branch_address = fields.Char(
        string='Branch Address',
        compute='_compute_jasper_branch_address',
    )
    jasper_amount_untaxed = fields.Float(
        string='Amount Untaxed',
        compute='_compute_jasper_rcp_amounts',
    )
    jasper_wht_amount = fields.Float(
        string='WHT Amount (1%)',
        compute='_compute_jasper_rcp_amounts',
    )
    jasper_net_amount = fields.Float(
        string='Net Amount (after WHT)',
        compute='_compute_jasper_rcp_amounts',
    )
    jasper_is_cash = fields.Char(
        string='Is Cash (X/"")',
        compute='_compute_jasper_rcp_payment_flags',
    )
    jasper_is_bank = fields.Char(
        string='Is Bank Transfer (X/"")',
        compute='_compute_jasper_rcp_payment_flags',
    )
    jasper_is_cheque = fields.Char(
        string='Is Cheque (X/"")',
        compute='_compute_jasper_rcp_payment_flags',
    )
    jasper_is_other = fields.Char(
        string='Is Other (X/"")',
        compute='_compute_jasper_rcp_payment_flags',
    )
    jasper_bank_info = fields.Char(
        string='Bank Info',
        compute='_compute_jasper_rcp_method_info',
    )
    jasper_cheque_info = fields.Char(
        string='Cheque Info',
        compute='_compute_jasper_rcp_method_info',
    )
    jasper_other_info = fields.Char(
        string='Other Method Info',
        compute='_compute_jasper_rcp_method_info',
    )
    jasper_signature = fields.Binary(
        string='Signature Image',
        compute='_compute_jasper_signature',
    )

    @api.depends('amount')
    def _compute_jasper_baht_text(self):
        try:
            from bahttext import bahttext
        except ImportError:
            bahttext = None
        for rec in self:
            amount = rec.amount or 0.0
            if bahttext:
                rec.jasper_baht_text = bahttext(amount)
            else:
                rec.jasper_baht_text = '{:,.2f}'.format(amount)

    @api.depends('date')
    def _compute_jasper_date_thai(self):
        for rec in self:
            rec.jasper_date_thai = _format_thai_date_short(rec.date)

    @api.depends(
        'partner_id.street', 'partner_id.street2',
        'partner_id.city', 'partner_id.state_id',
        'partner_id.zip',
    )
    def _compute_jasper_partner_full_address(self):
        for rec in self:
            p = rec.partner_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_partner_full_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('partner_id.vat')
    def _compute_jasper_rcp_partner_vat(self):
        for rec in self:
            rec.jasper_rcp_partner_vat = rec.partner_id.vat or ''

    @api.depends_context('company', 'allowed_company_ids')
    def _compute_jasper_company_name_display(self):
        for rec in self:
            # ใช้บริษัทที่ active ใน switcher (ไม่ใช่ company_id ที่เก็บใน payment)
            name = rec.env.company.name or ''
            # กัน "(สำนักงานใหญ่)" ซ้ำ ถ้าชื่อบริษัทมีอยู่แล้ว
            if name and '(สำนักงานใหญ่)' not in name:
                name = '{} (สำนักงานใหญ่)'.format(name)
            rec.jasper_company_name_display = name

    @api.depends_context('company', 'allowed_company_ids')
    def _compute_jasper_company_branch_info(self):
        for rec in self:
            company = rec.env.company
            rec.jasper_company_logo = company.logo
            rec.jasper_company_vat = company.vat or ''

    @api.depends(
        'branch_id', 'branch_id.street', 'branch_id.street2',
        'branch_id.city', 'branch_id.state_id', 'branch_id.zip',
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_branch_address(self):
        for rec in self:
            branch = rec.branch_id
            if branch:
                state_name = branch.state_id.name if branch.state_id else ''
                addr = _join_address(
                    branch.street, branch.street2, branch.city,
                    state_name, branch.zip,
                )
                if addr:
                    rec.jasper_branch_address = addr
                    continue
            c = rec.company_id
            state_name = c.state_id.name if c.state_id else ''
            rec.jasper_branch_address = _join_address(
                c.street, c.street2, c.city, state_name, c.zip,
            )

    @api.depends('amount', 'partner_id.company_type')
    def _compute_jasper_rcp_amounts(self):
        for rec in self:
            rec.jasper_amount_untaxed = 0.0
            rec.jasper_wht_amount = 0.0
            rec.jasper_net_amount = 0.0
            amt = rec.amount or 0.0
            if not amt:
                continue
            untaxed = amt / 1.07
            is_company = False
            try:
                partner = rec.partner_id
                if partner:
                    is_company = partner.company_type == 'company'
            except Exception as e:
                _logger.warning('Partner company_type check failed: %s', e)
            wht = (untaxed * 0.01) if is_company else 0.0
            rec.jasper_amount_untaxed = untaxed
            rec.jasper_wht_amount = wht
            rec.jasper_net_amount = amt - wht

    @api.depends(
        'is_payment_multi', 'paid_ids.payment_method_type',
        'payment_method_one_id', 'cheque_id', 'journal_id.type',
    )
    def _compute_jasper_rcp_payment_flags(self):
        print('[jasper_rcp][PRINT] _compute_jasper_rcp_payment_flags CALLED for', self)
        for rec in self:
            is_cash = False
            is_bank = False
            is_cheque = False
            is_other = False
            # read raw values defensively
            is_multi = False
            try:
                is_multi = bool(rec.is_payment_multi)
            except Exception:
                pass
            p1_type = ''
            try:
                p1 = rec.payment_method_one_id
                if p1:
                    p1_type = p1.type or ''
            except Exception as e:
                _logger.warning('Cannot read payment_method_one_id.type: %s', e)
            has_cheque = False
            try:
                has_cheque = bool(rec.cheque_id)
            except Exception:
                pass
            j_type = ''
            try:
                if rec.journal_id:
                    j_type = rec.journal_id.type or ''
            except Exception:
                pass
            # decide
            if is_multi:
                for p in rec.paid_ids:
                    t = ''
                    try:
                        t = p.payment_method_type or ''
                    except Exception:
                        pass
                    if t == 'cash':
                        is_cash = True
                    elif t == 'bank':
                        is_bank = True
                    elif t == 'cheque':
                        is_cheque = True
                    elif t == 'other':
                        is_other = True
            elif p1_type:
                if p1_type == 'cash':
                    is_cash = True
                elif p1_type == 'bank':
                    is_bank = True
                elif p1_type == 'cheque':
                    is_cheque = True
                else:
                    is_other = True
            elif has_cheque:
                is_cheque = True
            elif j_type == 'cash':
                is_cash = True
            elif j_type == 'bank':
                is_bank = True
            else:
                is_other = True
            _logger.warning(
                '[jasper_rcp] flags for %s: cash=%s bank=%s cheque=%s other=%s '
                '(is_multi=%s p1_type=%r has_cheque=%s j_type=%r)',
                rec, is_cash, is_bank, is_cheque, is_other,
                is_multi, p1_type, has_cheque, j_type,
            )
            rec.jasper_is_cash = '\u2713' if is_cash else ''
            rec.jasper_is_bank = '\u2713' if is_bank else ''
            rec.jasper_is_cheque = '\u2713' if is_cheque else ''
            rec.jasper_is_other = '\u2713' if is_other else ''

    @api.depends(
        'is_payment_multi', 'paid_ids',
        'payment_method_one_id', 'cheque_id',
        'journal_id', 'company_id',
    )
    def _compute_jasper_rcp_method_info(self):
        for rec in self:
            company_name = rec.company_id.name or ''
            bank_info = ''
            cheque_info = ''
            other_info = ''
            if _safe_get(rec, 'is_payment_multi', False):
                # Multi payment: iterate paid_ids
                bank_parts = []
                cheque_parts = []
                other_parts = []
                seen_accounts = set()
                for p in rec.paid_ids:
                    t = _safe_get(p, 'payment_method_type', '') or ''
                    if t == 'bank':
                        # Build bank info: company + bank name + account number
                        line_journal = _safe_get(p, 'journal_id', False)
                        bank = _safe_get(line_journal, 'bank_id', False)
                        bank_name = _safe_get(bank, 'name', '') or ''
                        if not bank_name and line_journal:
                            bank_name = _bank_name_from_code(
                                _safe_get(line_journal, 'code', '')
                                or _safe_get(line_journal, 'name', '')
                            )
                        bank_acc = _safe_get(p, 'bank_account_id', False) or (
                            _safe_get(line_journal, 'bank_account_id', False)
                        )
                        acc_number = _safe_get(bank_acc, 'acc_number', '') or ''
                        acc_id = _safe_get(bank_acc, 'id', 0) or 0
                        key = (acc_id, bank_name)
                        if key not in seen_accounts:
                            seen_accounts.add(key)
                            parts = [x for x in [
                                company_name, bank_name,
                                'เลขที่บัญชี ' + acc_number if acc_number else '',
                            ] if x]
                            if parts:
                                bank_parts.append(' '.join(parts))
                    elif t == 'cheque':
                        cheque = _safe_get(p, 'cheque_id', False)
                        if cheque:
                            cheque_parts.append(_format_cheque_info(cheque))
                        else:
                            cheque_no = _safe_get(p, 'cheque_number', '') or ''
                            if cheque_no:
                                cheque_parts.append('เลขที่เช็ค: ' + cheque_no)
                    elif t == 'other':
                        j = _safe_get(p, 'journal_id', False)
                        name = _safe_get(j, 'name', '') or ''
                        if name:
                            other_parts.append(name)
                bank_info = ' / '.join(bank_parts)
                cheque_info = ' / '.join(cheque_parts)
                other_info = ' / '.join(other_parts)
            else:
                # Single payment: prefer payment_method_one_id (Odoo 14 style)
                p1 = _safe_get(rec, 'payment_method_one_id', False)
                t = _safe_get(p1, 'type', '') or '' if p1 else ''
                if t == 'bank':
                    # payment_method_one_id.name is like "SCB 1071", "KBANK 6512"
                    method_label = _safe_get(p1, 'name', '') or ''
                    bank_name = _bank_name_from_code(method_label)
                    acc = _safe_get(p1, 'account_id', False)
                    acc_number = _safe_get(acc, 'name', '') or ''
                    acc_number = acc_number[-13:] if acc_number else ''
                    parts = [x for x in [
                        company_name,
                        bank_name or method_label,
                        'เลขที่บัญชี ' + acc_number if acc_number else '',
                    ] if x]
                    bank_info = ' '.join(parts)
                elif t == 'cheque':
                    cheque = _safe_get(rec, 'cheque_id', False)
                    if cheque:
                        cheque_info = _format_cheque_info(cheque)
                    else:
                        cheque_info = _safe_get(p1, 'name', '') or ''
                elif t == 'other':
                    other_info = _safe_get(p1, 'name', '') or ''
                elif t == 'cash':
                    pass  # no text needed for cash
                else:
                    # Fallback when payment_method_one_id not set
                    cheque = _safe_get(rec, 'cheque_id', False)
                    if cheque:
                        cheque_info = _format_cheque_info(cheque)
                    else:
                        journal = rec.journal_id
                        if journal:
                            j_type = _safe_get(journal, 'type', '') or ''
                            if j_type == 'bank':
                                bank = _safe_get(journal, 'bank_id', False)
                                bank_name = _safe_get(bank, 'name', '') or ''
                                if not bank_name:
                                    bank_name = _bank_name_from_code(
                                        _safe_get(journal, 'code', '')
                                        or _safe_get(journal, 'name', '')
                                    )
                                bank_acc = _safe_get(journal, 'bank_account_id', False)
                                acc_number = _safe_get(bank_acc, 'acc_number', '') or ''
                                parts = [x for x in [
                                    company_name, bank_name,
                                    'เลขที่บัญชี ' + acc_number if acc_number else '',
                                ] if x]
                                bank_info = ' '.join(parts)
                            elif j_type not in ('bank', 'cash'):
                                other_info = _safe_get(journal, 'name', '') or ''
            _logger.warning(
                '[jasper_rcp] method_info for %s: bank=%r cheque=%r other=%r',
                rec, bank_info, cheque_info, other_info,
            )
            rec.jasper_bank_info = bank_info
            rec.jasper_cheque_info = cheque_info
            rec.jasper_other_info = other_info

    def _compute_jasper_signature(self):
        signature_b64 = False
        try:
            with tools.file_open(SIGNATURE_RESOURCE_PATH, 'rb') as f:
                signature_b64 = base64.b64encode(f.read())
        except Exception as e:
            _logger.warning('Could not load signature image: %s', e)
        for rec in self:
            rec.jasper_signature = signature_b64
