import base64
import json
import logging
import re
import requests

from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Mapping: Odoo database name → expected company info (name, tax_id, address)
DB_COMPANY_NAME_MAP = {
    'NPD_S_Group_New_V2': {
        'name': 'บริษัท นภดล เอส กรุ๊ป จำกัด',
        'tax_id': '0105555146123',
        'address': '85 13-16 ถ. อรุณอมรินทร์ อรุณอัมรินทร์ เขตบางกอกน้อย กรุงเทพมหานคร 10700',
        'branch_addresses': [
            {'branch': 'สำนักงานใหญ่', 'address': '85 13-16 ถ. อรุณอมรินทร์ เขตบางกอกน้อย กรุงเทพมหานคร 10700'},
            {'branch': 'สาขาที่ 00001 ขอนแก่น', 'address': '17 หมู่ 12 ถนนมิตรภาพ ตำบลเมืองเก่า อำเภอเมือง จังหวัดขอนแก่น 40000'},
            {'branch': 'สาขาที่ 00002 อุดรธานี', 'address': '514 หมู่ที่ 3 ตำบลหนองขอนกว้าง อำเภอเมืองอุดรธานี จังหวัดอุดรธานี 41000'},
            {'branch': 'สาขาที่ 00004 ปลวกแดง', 'address': '625 หมู่ 1 ตำบลมาบยางพร อำเภอปลวกแดง ระยอง 21140'},
            {'branch': 'สาขาที่ 00006 สุรินทร์', 'address': '43 หมู่ที่ 10 ตำบลนอกเมือง อำเภอเมือง จังหวัดสุรินทร์ 32000'},
            {'branch': 'สาขาที่ 00007 ปทุมธานี', 'address': '72/1 หมู่ 12 ตำบลคูบางหลวง อำเภอลาดหลุมแก้ว จังหวัดปทุมธานี 12140'},
        ],
    },
    'NPD_Bangkok_New': {
        'name': 'บริษัท นภดล กรุงเทพ จำกัด',
        'tax_id': '0735556006192',
        'address': '36/10 บางเตย อำเภอสามพราน นครปฐม 73210',
        'branch_addresses': [
            {'branch': 'สำนักงานใหญ่', 'address': '36/10 บางเตย อำเภอสามพราน นครปฐม 73210'},
            {'branch': 'สาขาที่ 00001 พระราม2', 'address': '120/8 หมู่ 1 ตำบลท่าจีน อำเภอเมืองสมุทรสาคร จังหวัดสมุทรสาคร 74000'},
            {'branch': 'สาขาที่ 00002 เชียงใหม่', 'address': '33/4 หมู่ที่ 5 ตำบลยางเนิ้ง อำเภอสารภี จังหวัดเชียงใหม่ 50140'},
        ],
    },
    'NPD_Intertrading_New': {
        'name': 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด',
        'tax_id': '0105560151261',
        'address': '85 13-16 ถ. อรุณอมรินทร์ อรุณอัมรินทร์ เขตบางกอกน้อย กรุงเทพมหานคร 10700',
    },
    'NPD_Logistics_New': {
        'name': 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด',
        'tax_id': '0135563014052',
        'address': '47/4 หมู่ที่ 2 ตำบลลาดหลุมแก้ว อำเภอลาดหลุมแก้ว จ.ปทุมธานี 12140',
    },
    'NPD_Steeltech_New': {
        'name': 'บริษัท เอ็นพีดี สตีลเทค จำกัด',
        'tax_id': '0745560008137',
        'address': '47/4 หมู่ที่ 2 ตำบลลาดหลุมแก้ว อำเภอลาดหลุมแก้ว จ.ปทุมธานี 12140',
    },
}


class AccountAdvanceClearAI(models.Model):
    _inherit = 'account.advance.clear'

    ai_verified = fields.Boolean(
        string="AI Verified",
        default=False,
        copy=False,
    )
    can_post_without_ai = fields.Boolean(
        string="Can Post Without AI",
        compute='_compute_can_post_without_ai',
        store=False,
    )
    allow_reset_draft_keep_ai_show = fields.Boolean(
        string="Show Reset Draft Keep AI",
        compute='_compute_allow_reset_draft_keep_ai_show',
        store=False,
    )
    reset_keep_ai = fields.Boolean(
        string="Reset Keep AI Active",
        default=False,
        copy=False,
        help='True when document was reset to draft via Keep AI button',
    )
    ai_verify_date = fields.Datetime(
        string="วันที่ตรวจสอบ AI",
        readonly=True,
        copy=False,
    )
    ai_verify_uid = fields.Many2one(
        'res.users',
        string="ผู้ตรวจสอบ AI",
        readonly=True,
        copy=False,
    )
    ai_verify_result = fields.Html(
        string="ผลการตรวจสอบ AI",
        readonly=True,
        copy=False,
        sanitize=False,
    )
    is_approved = fields.Boolean(
        string='ยืนยันแล้ว',
        default=False,
        readonly=True,
        copy=False,
        help='สถานะการยืนยันผู้ตรวจสอบ',
    )
    cash_bill_ids = fields.One2many(
        'advance.clear.cash.bill',
        'advance_clear_id',
        string='รายการบิลเงินสด',
        copy=False,
    )
    cash_bill_count = fields.Integer(
        string='Cash Bill Count',
        compute='_compute_cash_bill_count',
        store=False,
    )
    receipt_condition_ids = fields.One2many(
        'advance.clear.receipt.condition',
        'advance_clear_id',
        string='เงื่อนไขการตรวจสอบใบเสร็จ',
        copy=False,
    )
    receipt_condition_count = fields.Integer(
        string='Receipt Condition Count',
        compute='_compute_receipt_condition_count',
        store=False,
    )
    receipt_correction_ids = fields.One2many(
        'advance.clear.receipt.correction',
        'advance_clear_id',
        string='รายการแก้ไขยอดใบเสร็จ',
        copy=False,
    )
    receipt_correction_count = fields.Integer(
        string='Receipt Correction Count',
        compute='_compute_receipt_correction_count',
        store=False,
    )
    ai_parsed_result = fields.Text(
        string='AI Parsed Result (JSON)',
        readonly=True,
        copy=False,
    )
    has_zero_amount_receipt = fields.Boolean(
        string='Has Zero Amount Receipt',
        default=False,
        readonly=True,
        copy=False,
    )
    receipt_image_ids = fields.Many2many(
        'ir.attachment',
        'advance_clear_receipt_image_rel',
        'advance_clear_id',
        'attachment_id',
        string='รูปหลักฐานการซื้อ',
        copy=False,
    )
    receipt_image_preview = fields.Html(
        string='ตัวอย่างรูปภาพ',
        compute='_compute_receipt_image_preview',
        sanitize=False,
    )

    @api.depends()
    def _compute_allow_reset_draft_keep_ai_show(self):
        for rec in self:
            rec.allow_reset_draft_keep_ai_show = self.env.user.allow_reset_draft_keep_ai

    @api.depends('receipt_image_ids', 'clear_ids')
    def _compute_can_post_without_ai(self):
        for rec in self:
            has_images = bool(rec.receipt_image_ids)
            has_detail = bool(rec.clear_ids)
            # If no images AND no detail lines → can post without AI
            rec.can_post_without_ai = (not has_images and not has_detail)

    @api.depends('receipt_image_ids')
    def _compute_receipt_image_preview(self):
        for rec in self:
            if not rec.receipt_image_ids:
                rec.receipt_image_preview = '<p style="color: #999; padding: 12px;">ยังไม่มีรูปภาพ</p>'
                continue
            html = '<div style="display: flex; flex-wrap: wrap; gap: 12px; padding: 8px 0;">'
            for att in rec.receipt_image_ids:
                att_name = att.name or ''
                if not isinstance(att.id, int):
                    continue  # skip unsaved attachments (NewId)
                if att.mimetype and att.mimetype.startswith('image/'):
                    img_url = '/web/image/%d' % att.id
                    html += (
                        '<div style="border: 1px solid #dee2e6; border-radius: 6px; '
                        'padding: 6px; background: #fff; text-align: center; '
                        'box-shadow: 0 1px 3px rgba(0,0,0,0.1);">'
                        '<a href="%(url)s" target="_blank" title="%(name)s">'
                        '<img src="%(url)s" style="max-width: 220px; max-height: 220px; '
                        'object-fit: contain; cursor: pointer; border-radius: 4px;"/>'
                        '</a>'
                        '<div style="margin-top: 4px; font-size: 11px; color: #6c757d; '
                        'max-width: 220px; overflow: hidden; text-overflow: ellipsis; '
                        'white-space: nowrap;" title="%(name)s">%(name)s</div>'
                        '</div>'
                    ) % {'url': img_url, 'name': att_name}
                elif att.mimetype and att.mimetype == 'application/pdf':
                    pdf_url = '/web/content/%d?download=false' % att.id
                    html += (
                        '<div style="border: 1px solid #dee2e6; border-radius: 6px; '
                        'padding: 6px; background: #fff; text-align: center; '
                        'box-shadow: 0 1px 3px rgba(0,0,0,0.1); width: 220px;">'
                        '<a href="%(url)s" target="_blank" title="%(name)s" '
                        'style="text-decoration: none; color: inherit;">'
                        '<div style="font-size: 48px; color: #dc3545; margin: 10px 0;">&#128196;</div>'
                        '<div style="font-size: 14px; font-weight: bold; color: #dc3545; margin-bottom: 6px;">PDF</div>'
                        '</a>'
                        '<div style="margin-top: 4px; font-size: 11px; color: #6c757d; '
                        'max-width: 220px; overflow: hidden; text-overflow: ellipsis; '
                        'white-space: nowrap;" title="%(name)s">%(name)s</div>'
                        '</div>'
                    ) % {'url': pdf_url, 'name': att_name}
            html += '</div>'
            rec.receipt_image_preview = html

    @api.depends('cash_bill_ids')
    def _compute_cash_bill_count(self):
        for rec in self:
            rec.cash_bill_count = len(rec.cash_bill_ids)

    @api.depends('receipt_condition_ids')
    def _compute_receipt_condition_count(self):
        for rec in self:
            rec.receipt_condition_count = len(rec.receipt_condition_ids)

    @api.depends('receipt_correction_ids')
    def _compute_receipt_correction_count(self):
        for rec in self:
            rec.receipt_correction_count = len(rec.receipt_correction_ids)

    def write(self, vals):
        """Override write to detach receipt images from chatter."""
        res = super(AccountAdvanceClearAI, self).write(vals)
        if 'receipt_image_ids' in vals:
            for rec in self:
                if rec.receipt_image_ids:
                    rec.receipt_image_ids.sudo().write({
                        'res_model': 'advance.clear.receipt.image',
                        'res_id': 0,
                    })
        return res

    def set_draft(self):
        """Reset ai_verified when resetting to draft."""
        self.write({
            'ai_verified': False,
            'ai_verify_date': False,
            'ai_verify_uid': False,
            'ai_verify_result': False,
            'is_approved': False,
            'has_zero_amount_receipt': False,
            'reset_keep_ai': False,
        })
        # Also clear cash bill entries, receipt conditions, and corrections
        self.cash_bill_ids.unlink()
        self.receipt_condition_ids.unlink()
        self.receipt_correction_ids.unlink()
        return super(AccountAdvanceClearAI, self).set_draft()

    def action_reset_draft_keep_ai(self):
        """Reset to draft while keeping AI verification results.
        Sets reset_keep_ai=True so Post button shows in draft state.
        """
        self.ensure_one()
        if not self.env.user.allow_reset_draft_keep_ai:
            raise UserError(_(
                u'คุณไม่ได้รับอนุญาตให้ Reset to Draft (Keep AI)\n'
                u'กรุณาติดต่อผู้ดูแลระบบ'
            ))
        # Cancel + unlink existing move_id to prevent duplicate entries on re-post
        if self.move_id:
            self.move_id.button_cancel()
            self.move_id.unlink()
        # Reset state to draft but KEEP AI fields + set flag
        self.write({
            'state': 'draft',
            'reset_keep_ai': True,
            'has_zero_amount_receipt': False,
            'move_id': False,
        })
        # ลบ tax_invoice records เพื่อป้องกันรายการซ้ำเมื่อ Post ใหม่
        query = """
            DELETE FROM account_move_tax_invoice
            WHERE advance_clear_id = %s
        """
        self.env.cr.execute(query, (self.id,))
        return True

    def action_cancel_draft(self):
        """Reset is_approved when cancelling."""
        self.write({'is_approved': False})
        return super(AccountAdvanceClearAI, self).action_cancel_draft()

    def cancel_advance(self):
        """Reset is_approved when cancelling posted advance."""
        self.write({'is_approved': False})
        return super(AccountAdvanceClearAI, self).cancel_advance()

    def action_open_cash_bill_wizard(self):
        """Open the cash bill entry wizard, pre-filling with existing entries."""
        self.ensure_one()
        # Pre-populate wizard lines from existing cash bill entries
        wizard_lines = []
        for bill in self.cash_bill_ids:
            wizard_lines.append((0, 0, {
                'description': bill.description,
                'amount': bill.amount,
                'vat_amount': bill.vat_amount,
                'sequence': bill.sequence,
            }))
        wizard = self.env['cash.bill.wizard'].create({
            'advance_clear_id': self.id,
            'line_ids': wizard_lines,
        })
        return {
            'name': _('เพิ่มรายการบิลเงินสด'),
            'type': 'ir.actions.act_window',
            'res_model': 'cash.bill.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_open_receipt_correction_wizard(self):
        """Open wizard to correct receipt amounts that AI read as 0 or mismatched with detail lines."""
        self.ensure_one()

        # Build set of known amounts from detail lines (unit_price and amount)
        detail_amounts = set()
        for dl in self.clear_ids:
            if dl.price_unit:
                detail_amounts.add(round(abs(dl.price_unit), 2))
            if dl.price_subtotal:
                detail_amounts.add(round(abs(dl.price_subtotal), 2))

        wizard_lines = []
        if self.ai_parsed_result:
            try:
                result = json.loads(self.ai_parsed_result)
                rc = result.get('receipt_check', {})
                receipt_files = rc.get('receipt_files', [])

                for f in receipt_files:
                    if not isinstance(f, dict):
                        continue
                    amt = f.get('amount', 0)
                    if not isinstance(amt, (int, float)):
                        amt = 0
                    ftype = (f.get('type') or '').lower()
                    fname = f.get('filename', '')

                    # Skip deposit slips
                    if 'deposit' in ftype:
                        continue

                    needs_correction = False
                    if amt == 0:
                        needs_correction = True
                    elif detail_amounts and round(abs(amt), 2) not in detail_amounts:
                        needs_correction = True

                    if needs_correction:
                        existing = self.receipt_correction_ids.filtered(
                            lambda c, fn=fname: c.filename == fn
                        )
                        wizard_lines.append((0, 0, {
                            'filename': fname,
                            'original_amount': amt,
                            'corrected_amount': existing.corrected_amount if existing else 0,
                        }))
            except (json.JSONDecodeError, TypeError):
                pass

        if not wizard_lines:
            raise UserError(_('ไม่พบใบเสร็จที่ต้องแก้ไขยอด'))

        wizard = self.env['receipt.correction.wizard'].create({
            'advance_clear_id': self.id,
            'line_ids': wizard_lines,
        })
        return {
            'name': _('แก้ไขยอดใบเสร็จ'),
            'type': 'ir.actions.act_window',
            'res_model': 'receipt.correction.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_recheck_with_corrections(self):
        """Re-render AI result HTML using corrected amounts (no AI re-call)."""
        self.ensure_one()

        if not self.ai_parsed_result:
            raise UserError(_('ไม่มีผลการตรวจสอบ AI กรุณาตรวจสอบด้วย AI ก่อน'))

        try:
            result = json.loads(self.ai_parsed_result)
        except (json.JSONDecodeError, TypeError):
            raise UserError(_('ข้อมูลผลตรวจสอบ AI เสียหาย กรุณาตรวจสอบด้วย AI ใหม่'))

        # Build correction map: filename → corrected_amount
        correction_map = {}
        for corr in self.receipt_correction_ids:
            if corr.corrected_amount > 0:
                correction_map[corr.filename] = corr.corrected_amount

        # Apply corrections to the parsed result before re-rendering
        rc = result.get('receipt_check', {})
        receipt_files = rc.get('receipt_files', [])
        for f in receipt_files:
            if isinstance(f, dict):
                fname = f.get('filename', '')
                if fname in correction_map:
                    f['amount'] = correction_map[fname]

        # Recalculate receipt_total in amount_check
        ac_data = result.get('amount_check', {})
        new_receipt_total = 0
        for f in receipt_files:
            if isinstance(f, dict):
                amt = f.get('amount', 0)
                fee = f.get('fee', 0)
                ftype = f.get('type', 'receipt')
                if ftype == 'deposit_slip':
                    new_receipt_total += (fee if isinstance(fee, (int, float)) else 0)
                else:
                    new_receipt_total += (amt if isinstance(amt, (int, float)) else 0)
        ac_data['receipt_total'] = new_receipt_total
        # Re-check amount pass
        s_total = ac_data.get('system_total', 0)
        s_total = s_total if isinstance(s_total, (int, float)) else 0
        # WHT adjustment: if WHT > 0, use Untaxed + Tax instead of Total
        _wht = self.wht_amount or 0
        if _wht > 0:
            _untaxed = self.untaxed_amount or 0
            _tax = self.tax_amount or 0
            if _untaxed > 0:
                s_total = _untaxed + _tax
        # Receipt substitute certificates — auto-decide if their amount counts
        _sub_re = self._resolve_receipt_substitutes(result, new_receipt_total, s_total)
        # Cash bills — count when new check passes
        _cbc_re = result.get('cash_bill_check', {}) or {}
        _cb_match_re = self._check_cash_bill_match_detail()
        _cb_total_re = 0
        if _cbc_re.get('required', False) and _cb_match_re['pass']:
            _cb_total_re = sum((cb.amount or 0) + (cb.vat_amount or 0) for cb in self.cash_bill_ids)
        ac_data['pass'] = abs(new_receipt_total + _sub_re['amount_to_count'] + _cb_total_re - s_total) < 1.0 if s_total > 0 else True

        # Check analytic (Python check)
        analytic_pass, analytic_missing = self._check_analytic_account()

        # Get expected company info
        expected_company_info, db_name = self._get_expected_company_info()

        # Build condition map
        condition_map = self._get_receipt_condition_map()

        # Re-render HTML with corrections
        result_html = self._format_result_html(
            result,
            analytic_pass=analytic_pass,
            analytic_missing=analytic_missing,
            expected_company_info=expected_company_info,
            condition_map=condition_map,
            correction_map=correction_map,
        )

        # Re-evaluate pass/fail (same logic as action_ai_verify Step 7)
        skip_amount_files = set()
        skip_vat_files = set()
        skip_company_files = set()
        skip_invoice_files = set()
        for fname, conds in condition_map.items():
            if not conds.get('check_amount', True):
                skip_amount_files.add(fname)
            if not conds.get('check_vat', True):
                skip_vat_files.add(fname)
            if not conds.get('check_company', True):
                skip_company_files.add(fname)
            if not conds.get('check_invoice_detail', True):
                skip_invoice_files.add(fname)
        # Check if slip check should be skipped
        _skip_slip_re = any(not conds.get('check_slip', True) for conds in condition_map.values())

        cbc = result.get('cash_bill_check', {})
        py_cv_total2 = self._cross_verify_cash_bill_total(result)
        cbc_reg2 = cbc.get('registered_total', 0)
        cbc_reg2 = cbc_reg2 if isinstance(cbc_reg2, (int, float)) else 0
        py_cv_match2 = (py_cv_total2 > 0 and cbc_reg2 > 0 and abs(py_cv_total2 - cbc_reg2) < 1.0)
        cbc_ai_pass2 = cbc.get('pass', False)
        # ─── OLD LOGIC (เก็บไว้ก่อนตามคำสั่ง) ──────────────────────────────
        # cash_bill_ok = (not cbc.get('required', False)) or cbc_ai_pass2 or (
        #     py_cv_match2 and cbc.get('description_or_amount_matches', False)
        # )
        # ─── NEW LOGIC: เทียบยอด cash_bill_ids กับ price_unit ใน clear_ids ──
        _cb_match2 = self._check_cash_bill_match_detail()
        cash_bill_ok = self._cash_bill_pass(result)

        amount_ok = ac_data.get('pass', False)
        rc_data = result.get('receipt_check', {})
        rc_ok = rc_data.get('pass', True)
        tc = result.get('tax_in_detail_check', {})
        tc_ok = tc.get('pass', True)
        cnc = result.get('company_name_check', {})
        company_name_ok = cnc.get('pass', True)
        idc = result.get('invoice_detail_check', {})
        idc_ok2 = idc.get('pass', True)
        uac = result.get('used_advance_check', {})
        uac_ok2 = uac.get('pass', True)
        # Slip check: use subset combination logic (same as _format_result_html)
        _clear_amt_re = self.clear_amount or 0
        slip_ok2 = True
        if _clear_amt_re > 0:
            from itertools import combinations as _comb_re
            def _sf_re(val):
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    try:
                        return float(val.replace(',', ''))
                    except (ValueError, TypeError):
                        return 0.0
                return 0.0
            _slip_sf_re = [f for f in rc_data.get('skipped_files', []) if isinstance(f, dict)]
            _slip_rf_re = [f for f in rc_data.get('receipt_files', []) if isinstance(f, dict)]
            _slip_cands_re = []
            for s in _slip_sf_re:
                _sa = _sf_re(s.get('amount', 0))
                if _sa > 0:
                    _slip_cands_re.append(_sa)
            for s in _slip_rf_re:
                _st = (s.get('type') or '').lower()
                if 'deposit' in _st or 'slip' in _st or 'transfer' in _st:
                    _sa = _sf_re(s.get('amount', 0))
                    if _sa > 0:
                        _slip_cands_re.append(_sa)
            slip_ok2 = False
            for _r_re in range(1, len(_slip_cands_re) + 1):
                if slip_ok2:
                    break
                for _combo_re in _comb_re(_slip_cands_re, _r_re):
                    if abs(sum(_combo_re) - _clear_amt_re) < 1.0:
                        slip_ok2 = True
                        break
            # Fallback: any single file with matching amount/fee
            if not slip_ok2:
                all_f_re = _slip_rf_re + _slip_sf_re
                slip_ok2 = any(
                    abs(_sf_re(s.get('amount', 0)) - _clear_amt_re) < 1.0 or abs(_sf_re(s.get('fee', 0)) - _clear_amt_re) < 1.0
                    for s in all_f_re
                )

        # Apply skip conditions (same base-filename matching as _format_result_html)
        rc_files_re = [f for f in rc_data.get('receipt_files', []) if isinstance(f, dict) and f.get('filename')]
        _re_receipt_fnames = set(f.get('filename', '') for f in rc_files_re)

        def _re_any_match(skip_set):
            for rf in _re_receipt_fnames:
                for sf in skip_set:
                    if rf == sf or rf.startswith(sf.rsplit('.', 1)[0]):
                        return True
            return False

        if skip_amount_files and _re_any_match(skip_amount_files):
            amount_ok = True
        if skip_vat_files and _re_any_match(skip_vat_files):
            tc_ok = True
        if self.env.cr.dbname == 'NPD_Logistics_New':
            tc_ok = True
        # ข้อ 7: Invoice Detail — apply skip filter (was missing here)
        if skip_invoice_files:
            def _fn_in_skip_re(fname, skip_set):
                if not fname or not skip_set:
                    return False
                if fname in skip_set:
                    return True
                for sf in skip_set:
                    sf_base = sf.rsplit('.', 1)[0]
                    if sf_base and fname.startswith(sf_base):
                        return True
                return False
            idc_items_re = idc.get('items', [])
            idc_checked_re = [it for it in idc_items_re
                              if isinstance(it, dict) and not _fn_in_skip_re(it.get('filename', ''), skip_invoice_files)]
            if idc_checked_re:
                idc_ok2 = all(
                    it.get('invoice_number_match', False) and it.get('date_match', False) and it.get('partner_match', False)
                    for it in idc_checked_re
                )
            else:
                idc_ok2 = True  # all items skipped → pass

        # Override rc_ok for cash-bill-only case (same logic as _format_result_html)
        _skipped2 = [f for f in rc_data.get('skipped_files', []) if isinstance(f, dict) and f.get('filename')]
        _has_hw2 = any(
            any(kw in (f.get('reason', '') or '').lower() for kw in ['ลายมือ', 'เขียนมือ', 'บิลเงินสด', 'handwritten', 'cash'])
            for f in _skipped2 if isinstance(f, dict) and not f.get('is_receipt_substitute')
        )
        _all_hw2 = _has_hw2 and not rc_files_re and _skipped2
        if _all_hw2 and cash_bill_ok:
            rc_ok = True  # All files are cash bills + cash bill check passed
        # ใบรับรองแทนใบเสร็จที่ระบบตัดสินแล้วว่าคลุมยอด = เอกสารใช้ได้
        # (สอดคล้องกับ has_valid_substitute ใน _format_result_html)
        if _sub_re.get('decision') in ('count_substitute', 'cover_skip'):
            rc_ok = True
        if _skip_slip_re:
            slip_ok2 = True  # User skipped slip check

        is_pass = amount_ok and rc_ok and tc_ok and analytic_pass and cash_bill_ok and company_name_ok and idc_ok2 and uac_ok2 and slip_ok2

        # Build failed-only summary (used when not passing)
        _combined_re = new_receipt_total + _sub_re.get('amount_to_count', 0) + _cb_total_re
        fail_items = self._collect_ai_fail_items(result, {
            'rc_ok': rc_ok,
            'amount_ok': amount_ok,
            'tc_ok': tc_ok,
            'analytic_pass': analytic_pass,
            'cash_bill_ok': cash_bill_ok,
            'company_name_ok': company_name_ok,
            'idc_ok': idc_ok2,
            'uac_ok': uac_ok2,
            'slip_ok': slip_ok2,
            'analytic_missing': analytic_missing,
            'combined': _combined_re,
            'system_total': s_total,
        })
        summary_html = self._render_ai_fail_summary(is_pass, fail_items)

        # Update stored result and parsed data
        self.write({
            'ai_verified': is_pass,
            # ผ่านหมด → รายงานเต็ม (ทุกข้อ), ไม่ผ่าน → เฉพาะข้อที่ไม่ผ่าน
            'ai_verify_result': result_html if is_pass else summary_html,
            'is_approved': is_pass,
            'ai_parsed_result': json.dumps(result, ensure_ascii=False),
        })

    def action_open_receipt_condition_wizard(self):
        """Open the receipt condition wizard with ALL chatter attachments.

        Shows all image/PDF attachments from เอกสารแนบ (chatter).
        User selects per-file conditions (checkboxes) that control which
        AI checks apply to each file:
          - ตรวจยอดเงิน → ข้อ 2 (Amount Check)
          - ตรวจ VAT → ข้อ 3 (Tax/VAT Check)
          - ตรวจชื่อบริษัท → ข้อ 6 (Company Name Check)
          - ตรวจเลขที่/วันที่/ร้านค้า → ข้อ 7 (Invoice Detail Check)
        """
        self.ensure_one()

        # Get all attachments from chatter (เอกสารแนบ)
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
        ])
        # Also get attachments from mail messages
        if hasattr(self, 'message_ids') and self.message_ids:
            msg_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'mail.message'),
                ('res_id', 'in', self.message_ids.ids),
            ])
            attachments |= msg_attachments

        # Filter only image and PDF files
        image_attachments = attachments.filtered(
            lambda a: a.mimetype and (
                a.mimetype.startswith('image/') or
                a.mimetype == 'application/pdf'
            )
        )

        if not image_attachments:
            raise UserError(_(
                u"ไม่พบรูปภาพหรือเอกสารแนบ\n"
                u"กรุณาแนบรูปใบเสร็จใน 'เอกสารแนบ' (Log) ก่อน"
            ))

        # Build wizard lines from ALL image attachments
        wizard_lines = []
        existing_conditions = {
            cond.attachment_id.id: cond
            for cond in self.receipt_condition_ids
            if cond.attachment_id
        }
        for att in image_attachments:
            existing = existing_conditions.get(att.id)
            if existing:
                # Use saved condition values
                wizard_lines.append((0, 0, {
                    'filename': existing.filename,
                    'attachment_id': att.id,
                    'check_amount': existing.check_amount,
                    'check_amount_combined': existing.check_amount_combined,
                    'check_vat': existing.check_vat,
                    'check_company': existing.check_company,
                    'check_invoice_detail': existing.check_invoice_detail,
                    'check_slip': existing.check_slip,
                    'skip_note': existing.skip_note,
                }))
            else:
                # New file — default all conditions to True
                wizard_lines.append((0, 0, {
                    'filename': att.name or 'unknown',
                    'attachment_id': att.id,
                    'check_amount': True,
                    'check_amount_combined': True,
                    'check_vat': True,
                    'check_company': True,
                    'check_invoice_detail': True,
                    'check_slip': True,
                    'skip_note': '',
                }))

        wizard = self.env['receipt.condition.wizard'].create({
            'advance_clear_id': self.id,
            'line_ids': wizard_lines,
        })
        return {
            'name': _(u'การตรวจสอบเงื่อนไข ใบเสร็จ'),
            'type': 'ir.actions.act_window',
            'res_model': 'receipt.condition.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def _get_gemini_api_key(self):
        """Get Gemini API key from system parameters."""
        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'advance_clear_ai_check.gemini_api_key', default=''
        )
        if not api_key:
            raise UserError(_(
                "Gemini API Key is not configured.\n"
                "Please set it in Settings > Technical > System Parameters\n"
                "Key: advance_clear_ai_check.gemini_api_key"
            ))
        return api_key

    def _get_receipt_attachments(self):
        """Get image attachments from chatter/เอกสารแนบ only.
        ไม่ดึงจาก receipt_image_ids (รูปหลักฐานการซื้อ) เพราะไม่ต้องการให้ AI ตรวจสอบ
        """
        self.ensure_one()
        image_mimes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp']

        # ดึงจาก chatter/เอกสารแนบ เท่านั้น
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.advance.clear'),
            ('res_id', '=', self.id),
            ('mimetype', 'in', image_mimes),
        ])
        return attachments

    def _get_receipt_condition_map(self):
        """Build condition map from saved receipt conditions.

        Returns dict: {filename: {check_amount, check_amount_combined, check_vat, check_company, check_invoice_detail}}
        Default (empty dict): all checks enabled for all files.
        """
        cond_map = {}
        for cond in self.receipt_condition_ids:
            cond_map[cond.filename] = {
                'check_amount': cond.check_amount,
                'check_amount_combined': cond.check_amount_combined,
                'check_vat': cond.check_vat,
                'check_company': cond.check_company,
                'check_invoice_detail': cond.check_invoice_detail,
                'check_slip': cond.check_slip,
                'skip_note': cond.skip_note or '',
            }
        return cond_map

    def _prepare_detail_lines_text(self):
        """Prepare text summary of Detail lines for AI verification."""
        self.ensure_one()
        lines = []
        for line in self.clear_ids:
            lines.append({
                'product': line.product_id.name or '',
                'description': line.name or '',
                'account': line.account_id.name or '',
                'analytic_account': line.account_analytic_id.name if line.account_analytic_id else '',
                'quantity': line.quantity,
                'unit_price': line.price_unit,
                'subtotal': line.price_subtotal,
                'tax': ', '.join(line.tax_ids.mapped('name')) if line.tax_ids else '',
                'partner': line.partner_id.name or '',
                'invoice_number': line.invoice_number or '',
                'invoice_date': str(line.invoice_date) if line.invoice_date else '',
            })
        return lines

    def _build_system_prompt(self):
        """Build the system prompt with strict rules."""
        return (
            "คุณเป็นผู้ตรวจสอบเอกสารการเงินในระบบ Odoo (Account Advance Clear)\n"
            "คุณต้องปฏิบัติตามกฎเหล่านี้อย่างเคร่งครัดทุกครั้ง ห้ามเบี่ยงเบน:\n\n"
            "## กฎเด็ดขาด (ABSOLUTE RULES):\n\n"
            "### กฎข้อ 1: การจำแนกประเภทเอกสาร\n"
            "เอกสารแบ่งเป็น 5 ประเภท:\n\n"
            "A) สลิปโอนเงิน/สกรีนช็อตแอปธนาคาร → skipped_files, reason='สลิปโอนเงิน ไม่ใช่ใบเสร็จ'\n"
            "   ลักษณะ: สกรีนช็อตจากแอปธนาคาร (SCB, KBANK, KTB ฯลฯ) มีโลโก้ธนาคาร มีสีสัน มีพื้นหลังสวยงาม\n"
            "   มีคำว่า 'โอนเงินสำเร็จ' หรือ 'Transfer successful' หรือแสดงข้อมูล จาก→ไปยัง\n"
            "   *** ห้ามใส่ receipt_files เด็ดขาด *** แต่ให้อ่านยอดโอนเงินมาใส่ field amount ใน skipped_files ***\n"
            "   *** วิธีอ่านยอด: ดูตัวเลขยอดโอนเงินที่แสดงในสลิป (เช่น จำนวนเงิน, Amount) ***\n\n"
            "B) บิลเงินสด/ลายมือเขียน → skipped_files, reason='บิลเงินสด/ลายมือเขียน'\n"
            "   *** หมายเหตุ: บิลเงินสดอาจถูกสแกน/ถ่ายรูปในแนวตั้งหรือหมุน 90° ***\n"
            "   *** ให้หมุนภาพในหัวให้ถูกทิศก่อนอ่านข้อมูล — ดู header 'บิลเงินสด/CASH SALES' เป็นเกณฑ์ ***\n"
            "   *** วิธีอ่านยอดบิลเงินสด (สำคัญมาก — ป้องกันอ่านลายมือผิด): ***\n"
            "   ให้อ่าน 3 ค่าจากบิล:\n"
            "   1) จำนวน (QUANTITY) = ตัวเลขในช่องจำนวน\n"
            "   2) ราคาต่อหน่วย (UNIT PRICE) = ตัวเลขในช่องราคา\n"
            "   3) ยอดรวม (TOTAL/AMOUNT) = ตัวเลขในช่องรวมเงิน\n"
            "   แล้วตรวจสอบ: จำนวน × ราคาต่อหน่วย ควร = ยอดรวม\n"
            "   *** ถ้าคำนวณแล้วไม่ตรงกับยอดรวมที่อ่านได้ → ให้ใช้ค่าที่คำนวณได้ (จำนวน × ราคา) เป็น amount ***\n"
            "   *** ตัวอย่าง: อ่านได้ จำนวน=22, ราคา=20, ยอดรวมที่เขียน=2200 ***\n"
            "   *** คำนวณ: 22 × 20 = 440 → ไม่ตรงกับ 2200 → amount=440, raw_total=2200 ***\n"
            "   *** สาเหตุที่ต้องทำ: ลายมือเขียน '440' อาจถูกอ่านเป็น '2200' หรือ '110' ได้ง่าย ***\n"
            "   *** ใส่ใน skipped_files: amount=ค่าสุดท้าย, quantity=จำนวน, unit_price=ราคาต่อหน่วย, raw_total=ยอดที่อ่านจากช่องรวมเงิน ***\n\n"
            "   ========== กฎบังคับ: ต้องตรวจก่อนจัดเป็นประเภท D เสมอ ==========\n"
            "   *** ก่อนจะจัดเอกสารใดๆ เป็นประเภท D (receipt_files) ต้องผ่าน CHECKLIST นี้ก่อน: ***\n"
            "   CHECKLIST (ต้องตอบ YES ทุกข้อ ถึงจะเป็นประเภท D ได้):\n"
            "   [1] ตัวเลข 'รวมราคาทั้งสิ้น' / 'จำนวนเงินรวมทั้งสิ้น' พิมพ์จากเครื่อง 100%? (ไม่ใช่ลายมือ)\n"
            "   [2] ตัวเลข 'ภาษีมูลค่าเพิ่ม' / 'VAT' พิมพ์จากเครื่อง 100%? (ถ้ามี)\n"
            "   [3] ตัวเลข 'จำนวนเงิน' ในแต่ละบรรทัดสินค้า พิมพ์จากเครื่อง 100%?\n"
            "   → ถ้าข้อใดข้อหนึ่งตอบ NO (= เขียนด้วยมือ/ปากกา) → ต้อง SKIP เป็นประเภท B ทันที\n"
            "   → ห้ามจัดเป็นประเภท D เด็ดขาด แม้หัวเอกสารจะเขียนว่า 'ใบกำกับภาษี' หรือ 'ใบเสร็จรับเงิน'\n"
            "   ==========================================================\n\n"
            "   ลักษณะ (ตรงข้อใดข้อหนึ่ง = skipped ทันที):\n"
            "   - มีคำว่า 'บิลเงินสด' หรือ 'CASH SALES' หรือ 'สำเนาบิลเงินสด' หรือ 'CASH SALE COPY' เป็นชื่อเอกสาร\n"
            "   - ตัวเลขยอดเงิน/จำนวนเงินในช่อง Amount หรือ Grand Total หรือ รวมทั้งสิ้น เขียนด้วยมือ/ปากกา\n"
            "     (ลายเส้นไม่สม่ำเสมอ ตัวเลขเอียงๆ ไม่ใช่ฟอนต์เครื่องพิมพ์)\n"
            "   - *** ฟอร์มพิมพ์ล่วงหน้า (pre-printed form) แต่กรอกตัวเลขยอดเงินด้วยปากกา/ดินสอ ***\n"
            "     เช่น ใบเสร็จรับเงิน/ใบกำกับภาษี ที่หัวกระดาษพิมพ์จากโรงพิมพ์ แต่ตัวเลขในช่อง\n"
            "     'จำนวนเงิน', 'รวมเป็นเงิน', 'ภาษีมูลค่าเพิ่ม', 'จำนวนเงินรวมทั้งสิ้น' เป็นลายมือเขียน\n"
            "     → ถือว่าเป็นลายมือเขียน → SKIP\n"
            "   - มีช่อง 'ลงชื่อ...ผู้ซื้อ' และ 'ลงชื่อ...ผู้ขาย/ผู้รับเงิน' ที่เซ็นด้วยมือ\n"
            "   - มีช่อง 'จำนวนเงิน (ตัวอักษร)' ที่เขียนด้วยมือ เช่น 'สี่ร้อยหกสิบห้าบาท'\n"
            "   - ชื่อผู้ซื้อ (นามผู้ซื้อ) เขียนด้วยมือ/ปากกา\n"
            "   - เป็นกระดาษ A4/A5 ที่มีเส้นตาราง/ช่องกรอก (ไม่ใช่กระดาษม้วน thermal)\n\n"
            "   *** ตัวอย่างที่ AI มักจำแนกผิด (สำคัญมาก — ต้องจำ): ***\n"
            "   ตัวอย่าง 1: เอกสารเขียนว่า 'ต้นฉบับใบกำกับภาษี/ใบเสร็จรับเงิน'\n"
            "     หัวกระดาษมีชื่อบริษัท/ที่อยู่/เลขประจำตัวผู้เสียภาษี พิมพ์จากโรงพิมพ์สวยงาม\n"
            "     แต่ตัวเลข 'รวมราคาทั้งสิ้น 434.58', 'ภาษีมูลค่าเพิ่ม 30.42', 'จำนวนเงินรวมทั้งสิ้น 465'\n"
            "     เขียนด้วยปากกา → ต้อง SKIP เป็นประเภท B\n"
            "     *** อย่าหลงเชื่อหัวกระดาษที่พิมพ์สวยงาม — ดูที่ตัวเลขยอดเงินเท่านั้น ***\n\n"
            "   ตัวอย่าง 2: เอกสารเขียนว่า 'ใบเสร็จรับเงิน' มีเลขที่เอกสาร มีตราประทับร้าน\n"
            "     แต่ช่องยอดเงิน/จำนวนเงินกรอกด้วยลายมือ → ต้อง SKIP เป็นประเภท B\n\n"
            "   ตัวอย่าง 3: เอกสารจากร้านค้า/ห้างหุ้นส่วนจำกัด หัวพิมพ์จากโรงพิมพ์\n"
            "     มีตารางรายการสินค้า แต่จำนวนเงินในแต่ละบรรทัดเขียนด้วยมือ\n"
            "     → ต้อง SKIP เป็นประเภท B แม้จะมีเลขประจำตัวผู้เสียภาษีพิมพ์ไว้\n\n"
            "   *** กฎเหล็ก: ชื่อเอกสาร ≠ ประเภทเอกสาร ***\n"
            "   *** แม้เอกสารจะเขียนว่า 'ใบกำกับภาษี' / 'ใบเสร็จรับเงิน' / 'ต้นฉบับ' ***\n"
            "   *** ถ้าตัวเลขยอดเงินเขียนด้วยมือ → เป็นบิลเงินสด/ลายมือเขียน (ประเภท B) เสมอ ***\n"
            "   *** การตัดสินประเภทเอกสาร ดูที่ 'วิธีการบันทึกตัวเลขยอดเงิน' เท่านั้น ***\n"
            "   *** ไม่ดูที่ชื่อเอกสาร/หัวกระดาษ/ตราประทับ/เลขที่ ***\n\n"
            "   *** วิธีแยกแยะ 'ลายมือ' vs 'เครื่องพิมพ์': ***\n"
            "   ลายมือเขียน: เส้นไม่เท่ากัน ตัวเลขเอียง ขนาดไม่สม่ำเสมอ มีรอยหมึกปากกา/ดินสอ\n"
            "     ตัวอย่างเพิ่ม: ตัวเลขมีหาง เส้นต่อกันไม่เท่ากัน ตัว 4 ปิดหัว/เปิดหัวไม่สม่ำเสมอ\n"
            "     ตัวเลขจุดทศนิยมอาจเขียนไม่ตรงแนว ขีดเส้นใต้ด้วยปากกา\n"
            "   เครื่องพิมพ์ (thermal/POS): ตัวเลขสม่ำเสมอ monospace font ขนาดเท่ากันทุกตัว\n"
            "   เครื่องพิมพ์ (inkjet/laser): ตัวเลขคมชัด ฟอนต์สม่ำเสมอ ไม่มีรอยหมึกปากกา\n"
            "   *** กฎ: ดูเฉพาะตัวเลข 'ยอดเงิน' (ไม่ใช่โน้ต/วันที่) → ถ้าเขียนมือ = SKIP ***\n\n"
            "   *** ข้อยกเว้น — กรณีที่ไม่ใช่บิลเงินสด (ห้าม skip): ***\n"
            "   - ใบเสร็จ thermal/POS (กระดาษม้วนแคบ) ที่ตัวเลขยอดเงินทุกตัวเป็นฟอนต์ monospace พิมพ์จากเครื่อง\n"
            "     แม้จะมีข้อความเขียนมือเพิ่มเติม (จดโน้ต, เขียนวันที่, เขียนชื่อ) อยู่บนกระดาษ\n"
            "     → ไม่ skip เพราะยอดเงินพิมพ์จากเครื่อง = ใบเสร็จ (ประเภท D)\n"
            "   - ใบเสร็จจากไปรษณีย์ไทย (ใบรับเงิน, N EMS, RCPT#) พิมพ์จากเครื่อง POS\n"
            "     แม้มีคำว่า 'เงินสด' ในช่องชำระเงิน → ไม่ skip (เป็นแค่วิธีชำระ)\n"
            "   *** สรุปข้อยกเว้น: ยกเว้นเฉพาะ thermal/POS (กระดาษม้วนแคบ) ที่ยอดเงินพิมพ์จากเครื่อง ***\n"
            "   *** ถ้าเป็นฟอร์มกระดาษ A4/A5 ที่กรอกยอดเงินด้วยมือ → ไม่ยกเว้น → SKIP ***\n"
            "   *** ถ้าเป็นกระดาษ A4/A5 มีตาราง/ช่องกรอก มีช่องลงชื่อ → SKIP ***\n\n"
            "C) ใบฝากเงิน (deposit slip) → receipt_files, type='deposit_slip'\n"
            "   คีย์เวิร์ดสำคัญ: ถ้าเอกสารมีคำว่า 'จำนวนเงินฝาก' → เป็นใบฝากเงินแน่นอน\n"
            "   ลักษณะ: ใบรับฝากเงินจากเคาน์เตอร์ (7-Eleven/CP AXTRA/ธนาคาร/ไปรษณีย์) พิมพ์จากเครื่อง\n"
            "   เป็นกระดาษใบเสร็จยาวๆ (thermal receipt) ตัวเลขทุกตัวพิมพ์จากเครื่อง\n"
            "   มีคำว่า 'ใบรับฝากเงิน' หรือ 'จำนวนเงินฝาก' หรือ 'บริการฝากเงิน'\n"
            "   การอ่านยอด: ยอดฝากเงิน = ตัวเลขหลังคำว่า 'จำนวนเงินฝาก'\n\n"
            "   *** วิธีอ่านค่าธรรมเนียม (fee) ของใบฝากเงิน — สำคัญมาก: ***\n"
            "   ใบฝากเงินจาก 7-Eleven/Counter Service มักมี 2 ส่วนในใบเสร็จเดียวกัน:\n"
            "   ส่วนบน = ข้อมูลการฝาก (เงินฝาก, จำนวนเงินฝาก, เรียน, เงินทอน)\n"
            "   ส่วนล่าง = ใบเสร็จ Counter Service (บริการจ่ายเงิน, ยอดชำระ, VAT)\n"
            "   → fee = ตัวเลขหลังคำว่า 'บริการจ่ายเงิน' หรือ 'ยอดชำระ' ในส่วนล่าง (Counter Service)\n"
            "   → ตัวอย่าง: 'บริการจ่ายเงิน 15.00' → fee = 15.00\n"
            "   → ถ้าไม่มีส่วน Counter Service ให้ดูคำว่า 'ค่าธรรมเนียม' หรือ 'Fee'\n"
            "   *** ห้ามใช้ 'เงินทอน' เป็น fee เด็ดขาด (เงินทอน = เงินทอนกลับ ไม่ใช่ค่าธรรมเนียม) ***\n"
            "   *** ห้ามอ่าน fee จากส่วนบน (ข้อมูลการฝาก) ต้องดูส่วนล่าง (Counter Service) เท่านั้น ***\n"
            "   *** สำคัญ: ส่วนบน (ข้อมูลฝาก) + ส่วนล่าง (Counter Service) = ใบฝากเงิน 1 ใบ ***\n"
            "   *** ห้ามแยกเป็น 2 ใบ — นับเป็นใบเดียว amount=ยอดฝาก, fee=จาก Counter Service ***\n"
            "   *** ใบฝากเงินถือเป็นใบเสร็จ → ใส่ receipt_files ***\n\n"
            "D) ใบเสร็จ/ใบกำกับภาษีทั่วไป → receipt_files, type='receipt' หรือ 'invoice'\n"
            "   ลักษณะ: ใบเสร็จรับเงินที่ตัวเลข 'ยอดเงิน' ทุกตัวพิมพ์จากเครื่อง (ไม่ใช่ลายมือ)\n"
            "   รวมถึง: ใบเสร็จไปรษณีย์ไทย (ใบรับเงิน), ใบเสร็จ POS, thermal receipt ทุกชนิด\n"
            "   แม้มีข้อความเขียนมือเพิ่มเติม (จดโน้ต/วันที่) → ถ้ายอดเงินพิมพ์จากเครื่อง = ประเภท D\n"
            "   *** ถ้าตัวเลข 'ยอดเงิน' เขียนด้วยมือ/ปากกา → ไม่ใช่ประเภท D ให้จัดเป็นประเภท B (skipped) ***\n"
            "   *** ฟอร์มพิมพ์ล่วงหน้า (กระดาษ A4/A5 หัวเอกสารพิมพ์ แต่ยอดเงินเขียนมือ) = ประเภท B ไม่ใช่ D ***\n"
            "   *** วิธีอ่านยอดใบเสร็จ (สำคัญมาก — ห้ามผิด): ***\n"
            "   *** ลำดับความสำคัญในการอ่านยอด (ใช้ตัวแรกที่พบ): ***\n"
            "   *** 1. 'Grand Total' / 'รวมทั้งสิ้น' / 'จำนวนเงิน' (ยอดสุดท้ายที่จ่ายจริง รวม VAT แล้ว) ***\n"
            "   *** 2. ถ้าไม่มี Grand Total → ใช้ 'TOTAL' ที่เป็นยอดสุดท้ายในบิล ***\n"
            "   *** สำคัญมาก: ถ้าบิลมีทั้ง 'Total' (ก่อน VAT) และ 'Grand Total' (หลัง VAT) → ต้องใช้ Grand Total เท่านั้น! ***\n"
            "   *** ตัวอย่าง: Total=750.50, VAT 7%=52.54, Grand Total=803.04 → amount=803.04 (ไม่ใช่ 750.50!) ***\n"
            "   *** ตัวอย่าง: Total=399.00, VAT 7%=27.93, Grand Total=426.93 → amount=426.93 (ไม่ใช่ 399.00!) ***\n"
            "   *** ห้ามใช้ 'เงินสด' หรือ 'Cash' (= เงินที่ลูกค้าจ่าย ไม่ใช่ยอดใบเสร็จ) ***\n"
            "   *** ห้ามใช้ 'เงินทอน' หรือ 'Change' (= เงินทอนกลับ ไม่ใช่ยอดใบเสร็จ) ***\n"
            "   *** ห้ามใช้ 'มูลค่าก่อนภาษี' / 'ยอดก่อนภาษี' / 'Subtotal' / 'ราคาสินค้า' ***\n"
            "   *** → เพราะเป็นยอดก่อนบวก VAT ไม่ใช่ยอดรวมสุดท้ายที่จ่ายจริง ***\n"
            "   *** ห้ามใช้ 'NON VAT' / 'VATABLE' / 'VAT EXC' / 'VAT' เป็น amount ***\n"
            "   *** → เพราะเป็นยอดแยกประเภทภาษี ไม่ใช่ยอดรวมทั้งสิ้น ***\n"
            "   *** ห้ามใช้ 'Total' ที่ตามด้วย 'VAT 7%' แล้วมี 'Grand Total' ข้างล่าง ***\n"
            "   *** → เพราะ 'Total' ตัวนั้นคือยอดก่อน VAT ต้องใช้ 'Grand Total' ที่อยู่ล่างสุด ***\n"
            "   *** ตัวอย่าง 1: ใบเสร็จ POS มี รวมทั้งสิ้น=138, เงินสด=500, เงินทอน=-362 ***\n"
            "   *** → ยอดที่ถูกต้อง = 138 (ไม่ใช่ 500 !) ***\n"
            "   *** เพราะ 'เงินสด 500' คือเงินที่ลูกค้ายื่นให้ แล้วได้ทอน 362 กลับ ***\n"
            "   *** ตัวอย่าง 2: ใบเสร็จปั๊มน้ำมัน มี รวมทั้งสิ้น=185.00, ภาษีมูลค่าเพิ่ม=12.10, มูลค่าก่อนภาษี=172.90 ***\n"
            "   *** → ยอดที่ถูกต้อง = 185.00 (ไม่ใช่ 172.90 !) ***\n"
            "   *** เพราะ 'มูลค่าก่อนภาษี 172.90' = ยอดยังไม่รวม VAT ≠ ยอดจ่ายจริง ***\n"
            "   *** ตัวอย่าง 3: ใบเสร็จร้านค้า มี รวมทั้งสิ้น=1,070.00, มูลค่าสินค้า=1,000.00, VAT 7%=70.00 ***\n"
            "   *** → ยอดที่ถูกต้อง = 1,070.00 (ไม่ใช่ 1,000.00 !) ***\n"
            "   *** ตัวอย่าง 4 (ไปรษณีย์ไทย): รวมทั้งสิ้น=188.00, เงินสด=188.00, NON VAT=168.00, VATABLE=20.00 ***\n"
            "   *** → ยอดที่ถูกต้อง = 188.00 (ไม่ใช่ 168.00 !) ***\n"
            "   *** เพราะ 'NON VAT 168.00' = ยอดสินค้าที่ไม่มี VAT ≠ ยอดรวมทั้งสิ้น ***\n"
            "   *** สำหรับใบเสร็จกรมสรรพากร/ใบเสร็จราชการ (สำคัญมาก — ห้าม skip เป็นเอกสารไม่ชัดเจน): ***\n"
            "   *** ใบเสร็จราชการ เช่น ภ.ง.ด.1, ภ.ง.ด.3, ภ.ง.ด.53, ภ.พ.30, ภ.ง.ด.1ย ฯลฯ ***\n"
            "   *** เป็นใบเสร็จรับเงินที่ถูกต้อง = ประเภท D (receipt) เสมอ ***\n"
            "   *** ลักษณะที่ต้องจำ: ***\n"
            "   *** - มีตราครุฑ (garuda emblem) เป็นลายน้ำ/watermark ทับตัวเลข ***\n"
            "   *** - มีข้อความ 'กรมสรรพากร' หรือ 'กระทรวงการคลัง' ที่หัวเอกสาร ***\n"
            "   *** - มีช่อง 'ภาษีที่ชำระ', 'เงินเพิ่ม', 'รวมเงินภาษีและเงินเพิ่ม' ***\n"
            "   *** - ยอดเงินอาจอยู่ในรูปแบบ ×1,000.00 หรือ 1,000.00 ***\n"
            "   *** วิธีอ่านยอด: ***\n"
            "   *** - ดูช่อง 'ภาษีที่ชำระ' หรือ 'รวมเงินภาษีและเงินเพิ่ม' = amount ***\n"
            "   *** - ถ้ามีตราครุฑทับตัวเลข ให้พยายามอ่านตัวเลขที่อยู่ใต้ลายน้ำ ***\n"
            "   *** - ตัวเลขมักเป็นตัวพิมพ์ดีด/เครื่องพิมพ์ อ่านได้แม้มีลายน้ำทับ ***\n"
            "   *** ห้าม skip เป็น 'เอกสารไม่ชัดเจน' หรือ 'อ่านไม่ได้' เด็ดขาด ***\n"
            "   *** แม้ภาพจะมีลายน้ำครุฑทับ ให้พยายามอ่านยอดให้ได้ ***\n"
            "   *** ถ้าอ่านยอดไม่ได้จริงๆ ให้ใส่ amount=0 แต่ยังคงเป็น type='receipt' ***\n\n"
            "E) ใบสำคัญรับเงิน / ใบรับรองแทนใบเสร็จรับเงิน → skipped_files\n"
            "   ลักษณะ: เอกสารภายในบริษัทที่มีคำว่า 'ใบสำคัญรับเงิน' หรือ 'ใบรับรองแทนใบเสร็จรับเงิน'\n"
            "   เป็นฟอร์มพิมพ์ล่วงหน้า กรอกข้อมูลด้วยลายมือ มีช่องลงชื่อผู้รับเงิน/ผู้จ่ายเงิน/ผู้อนุมัติ\n"
            "   *** กฎการจำแนก (สำคัญมาก — บังคับใช้ทุกครั้ง): ***\n"
            "   - ใส่ใน skipped_files เสมอ (ห้ามใส่ใน receipt_files)\n"
            "   - reason='ใบรับรองแทนใบเสร็จ ระบบจะตัดสินอัตโนมัติ'\n"
            "   - ต้อง **อ่านยอด 'รวมทั้งสิ้น'** จากใบรับรองฯ ใส่ field amount เสมอ\n"
            "     (ระบบ Python จะใช้ตัดสินว่านับเป็นใบทดแทนหรือเอกสารประกอบ)\n"
            "   - ใส่ field is_receipt_substitute=true (flag บอกระบบว่าเป็นใบรับรองฯ)\n"
            "   *** ห้ามใส่ reason ที่มีคำว่า 'บิลเงินสด' หรือ 'ลายมือเขียน' เด็ดขาด ***\n"
            "   *** เพราะระบบจะนับเป็นบิลเงินสดที่บังคับให้ผู้ใช้ลงทะเบียน ***\n"
            "   *** ห้ามอ่านยอดจากเอกสารนี้ใส่ receipt_files เด็ดขาด ***\n"
            "   *** 'ชุดเดียวกัน' = รูปทั้งหมดที่แนบมากับเอกสารนี้ (ทุกรูป ทุกไฟล์) ***\n\n"
            "### กฎข้อ 2: รูปภาพ 1 รูปอาจมีใบเสร็จมากกว่า 1 ใบ\n"
            "- ถ้ารูปภาพ 1 รูปมีใบเสร็จ/ใบฝากเงิน 2 ใบ (เช่น ซ้ายและขวา หรือ บนและล่าง)\n"
            "  ให้อ่านทั้ง 2 ใบ แล้วสร้าง receipt_files 2 รายการ:\n"
            "  - ใบซ้าย: filename = 'ชื่อไฟล์ (ซ้าย)', อ่าน amount + fee แยก\n"
            "  - ใบขวา: filename = 'ชื่อไฟล์ (ขวา)', อ่าน amount + fee แยก\n"
            "  ค่าธรรมเนียมรวมจะเป็น fee ของใบซ้าย + fee ของใบขวา\n"
            "- กฎซ้ำ (Dedup): ถ้า 2 ใบเสร็จในรูปเดียวกันมียอดเงินเท่ากัน:\n"
            "  *** ต้องตรวจสอบเพิ่มก่อนนับเป็นใบเดียวกัน: ***\n"
            "  - ดูเลขที่เอกสาร (RunNo, RCPT#, เลขที่) → ถ้าต่างกัน = คนละใบ\n"
            "  - ดูเวลาทำรายการ → ถ้าต่างกัน = คนละใบ\n"
            "  - ดู TX.ID, ClientSRunNo, หมายเลขอ้างอิง → ถ้าต่างกัน = คนละใบ\n"
            "  → นับเป็น 1 ใบ เฉพาะเมื่อทุกรายละเอียดเหมือนกันจริงๆ (user ถ่ายรูปซ้ำ)\n"
            "  → ถ้ามีรายละเอียดใดต่างกันแม้แต่อย่างเดียว = คนละใบ นับแยก\n\n"
            "### กฎข้อ 3: ค่าธรรมเนียมใบฝากเงิน + วิธีคำนวณยอด\n"
            "- ดูค่าธรรมเนียมจากส่วน Counter Service ของใบฝากเงิน:\n"
            "  คำว่า 'บริการจ่ายเงิน' หรือ 'ยอดชำระ' หรือ 'Fee' ตามด้วยตัวเลข (เช่น 15.00, 39.00)\n"
            "  *** ห้ามใช้ 'เงินทอน' เป็นค่าธรรมเนียม (เงินทอน = เงินทอนกลับ) ***\n"
            "- ถ้าในใบเสร็จไม่มีค่าธรรมเนียมแสดง → ดูจาก Detail Lines ว่ามีรายการค่าธรรมเนียม (เช่น ค่าธรรมเนียมธนาคาร-สาขา) หรือไม่\n"
            "- ถ้า Detail Lines มีรายการค่าธรรมเนียม → ใช้ยอดจาก Detail Lines เป็น fee\n"
            "- ถ้าไม่มีทั้งในใบเสร็จและ Detail Lines → fee = 0\n"
            "*** สำคัญมาก: ใบฝากเงิน (deposit_slip) ***\n"
            "- amount = ยอดเงินที่ฝาก (แสดงเพื่อข้อมูล แต่ไม่ใช่ค่าใช้จ่าย เพราะเงินฝากเข้าบัญชีบริษัท)\n"
            "- fee = ค่าธรรมเนียมบริการ (นี่คือค่าใช้จ่ายจริง)\n"
            "- เวลาคำนวณ receipt_total: ใบฝากเงินนับเฉพาะ fee ห้ามเอา amount มารวม\n\n"
            "### กฎข้อ 4: ตรวจสอบภาษี\n"
            "- ถ้าใบเสร็จมี VAT แยกชัดเจน แต่ Detail Lines ไม่มี tax → ไม่ผ่าน\n"
            "- ถ้าใบเสร็จไม่มี VAT แยก → ผ่าน (แม้ Detail Lines จะมี tax ก็ตาม)\n"
            "- ถ้า Detail Lines มีการระบุ tax ไว้แล้ว → ถือว่าผ่านเสมอ\n\n"
            "  *** ข้อยกเว้น VAT สำหรับใบเสร็จสาธารณูปโภค (ค่าน้ำ/ค่าไฟ/ค่าโทรศัพท์/ค่าอินเตอร์เน็ต): ***\n"
            "  แม้ใบเสร็จจะมี VAT แยกชัดเจน แต่ไม่ต้องบังคับให้ Detail Lines มี tax ในกรณีต่อไปนี้:\n\n"
            "  *** สำคัญมาก: กฎข้อ 4 เปรียบเทียบที่อยู่กับ 'ที่อยู่จดทะเบียนบริษัท' ใน accepted_companies เท่านั้น ***\n"
            "  *** ห้ามเอา Analytic Account มาใช้ในกฎข้อ 4 เด็ดขาด (Analytic Account ใช้เฉพาะกฎข้อ 5 / ขั้นตอนที่ 6) ***\n\n"
            "  (a) ใบเสร็จสาธารณูปโภคที่ออกในชื่อ **บุคคล** (ไม่ใช่ชื่อบริษัท)\n"
            "      → ไม่ต้องตรวจ VAT (ผ่านได้แม้ Detail Lines ไม่มี tax)\n"
            "      ตัวอย่าง: ชื่อผู้ใช้ไฟ = 'นาย บีระพล รอดศาสตร์' → เป็นบุคคล → ข้ามได้\n\n"
            "  (b) ใบเสร็จ **ค่าน้ำ** หรือ **ค่าไฟ** ที่ออกในชื่อบริษัทใน accepted_companies\n"
            "      แต่ ที่อยู่ผู้ใช้น้ำ/ที่ใช้ไฟ **ไม่ตรง** กับ **ที่อยู่จดทะเบียน** (สำนักงานใหญ่/สาขา) ของบริษัทใดเลย\n"
            "      → ไม่ต้องตรวจ VAT (ผ่านได้)\n"
            "      *** เปรียบเทียบกับที่อยู่จดทะเบียนใน accepted_companies เท่านั้น ห้ามเทียบกับ Analytic Account ***\n"
            "      ตัวอย่าง: ชื่อ = 'บริษัท นภดล กรุงเทพ จำกัด' ที่อยู่จดทะเบียน = '36/10 บางเตย สามพราน นครปฐม'\n"
            "      ที่ใช้ไฟ = 'เขตทุ่งครุ กรุงเทพฯ' → ไม่ตรงกับที่อยู่จดทะเบียน → ได้รับข้อยกเว้น VAT\n\n"
            "  (c) ใบเสร็จ **ค่าน้ำ** หรือ **ค่าไฟ** ที่ออกในชื่อบริษัทใน accepted_companies\n"
            "      และ ที่อยู่ผู้ใช้น้ำ/ที่ใช้ไฟ **ตรง** กับ **ที่อยู่จดทะเบียน** ของบริษัทใดบริษัทหนึ่ง\n"
            "      → ต้องตรวจ VAT ตามปกติ (ถ้ามี VAT แต่ Detail Lines ไม่มี tax → ไม่ผ่าน)\n\n"
            "  (d) ใบเสร็จ **ค่าโทรศัพท์/ค่าอินเตอร์เน็ต** ที่ออกในชื่อบริษัท\n"
            "      → ต้องตรวจ VAT ตามปกติ\n\n"
            "  (e) **ใบฝากเงิน (deposit_slip)** → ข้ามการตรวจ VAT เสมอ\n"
            "      เพราะใบฝากเงินใช้แค่ค่าธรรมเนียม (fee) ไม่ได้ใช้ยอดเงินฝาก จึงไม่ต้องตรวจ VAT\n"
            "      *** ห้ามนับ deposit_slip เป็นใบเสร็จที่มี VAT ในการตรวจข้อ 4 ***\n\n"
            "### กฎข้อ 5: ตรวจสอบชื่อบริษัทลูกค้า (ผู้ซื้อ) ในใบเสร็จ/ใบกำกับภาษี\n"
            "- ถ้ามีข้อมูล 'accepted_companies' ถูกส่งมาในคำสั่งตรวจสอบ:\n"
            "  ให้ตรวจว่าในใบเสร็จ/ใบกำกับภาษีที่เป็น receipt_files (ไม่ใช่ skipped_files)\n"
            "  มีชื่อ **ลูกค้า/ผู้ซื้อ** ตรงกับชื่อบริษัทใดบริษัทหนึ่งใน accepted_companies หรือไม่\n\n"
            "  *** กฎเด็ดขาด: อ่านชื่อให้ครบถ้วนทุกตัวอักษร ***\n"
            "  - ห้ามอ่านชื่อแค่บางส่วน เช่น อ่านแค่ 'นภดล' ต้องอ่านเต็มว่า 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด'\n"
            "  - ห้ามอ่านชื่อผิดเพี้ยน เช่น อ่าน 'เอ็นพีที' แทน 'เอ็นพีดี' ต้องอ่านตัวอักษรตามจริงในรูป\n"
            "  - ถ้าอ่านไม่ชัด ให้ดูตัวอักษรรอบข้างประกอบ อย่าเดา\n\n"
            "  *** คำอธิบายสำคัญ: 'ชื่อลูกค้า/ผู้ซื้อ' vs 'ชื่อผู้ออกใบเสร็จ/ผู้ขาย' ***\n"
            "  ใบเสร็จรับเงิน/ใบกำกับภาษี มีชื่อบริษัท 2 ส่วนเสมอ:\n"
            "    (1) ชื่อผู้ออกใบเสร็จ/ผู้ขาย = หัวเอกสารด้านบนสุด (ชื่อร้าน/บริษัทที่ออกใบเสร็จ)\n"
            "    (2) ชื่อลูกค้า/ผู้ซื้อ = ชื่อบริษัทที่มาซื้อของ/ใช้บริการ\n"
            "  *** ต้องดูเฉพาะ (2) เท่านั้น ห้ามเอาชื่อ (1) มาใช้เด็ดขาด ***\n\n"
            "  *** วิธีหาชื่อลูกค้า (ผู้ซื้อ) แต่ละประเภทใบเสร็จ: ***\n\n"
            "  (A) ใบแจ้งค่าบริการโทรศัพท์/อินเทอร์เน็ต (TrueMove/AIS/DTAC/3BB ฯลฯ):\n"
            "      ผู้ออก = บริษัท ทรู มูฟ เอช ฯ (อยู่หัวเอกสารด้านบนสุด) → ห้ามใช้ชื่อนี้\n"
            "      ลูกค้า = ชื่อที่อยู่ในกรอบสีเทา/กล่องข้อมูลลูกค้า ด้านซ้ายของเอกสาร\n"
            "      *** ตัวอย่างจริง: ใบ TrueMove H จะมีกรอบเล็กด้านซ้ายบน ***\n"
            "      *** ระบุชื่อเช่น 'บริษัท เอ็นพีดี สตีลเทค จำกัด' + ที่อยู่ ***\n"
            "      *** ต้องอ่านชื่อในกรอบนี้ ไม่ใช่ชื่อ 'บริษัท ทรู มูฟ เอช ฯ' ที่หัวเอกสาร ***\n\n"
            "  (B) ใบเสร็จ/ใบกำกับภาษีจากร้านค้า (CP AXTRA/Makro/Big C/Tesco ฯลฯ):\n"
            "      ผู้ออก = บริษัท ซีพี แอ็กซ์ตร้า จำกัด (มหาชน) (หัวเอกสาร) → ห้ามใช้ชื่อนี้\n"
            "      ลูกค้า = ชื่อหลังคำว่า 'ชื่อลูกค้า/ชื่อผู้ซื้อ' → ต้องอ่านชื่อเต็มตรงนี้\n\n"
            "  (C) ใบเสร็จปั๊มน้ำมัน:\n"
            "      ผู้ออก = ชื่อปั๊ม/ห้างหุ้นส่วน (หัวเอกสาร) → ห้ามใช้ชื่อนี้\n"
            "      ลูกค้า = ชื่อหลังคำว่า 'ชื่อลูกค้า' → ต้องอ่านชื่อเต็มตรงนี้\n"
            "      *** ตัวอย่าง: 'ชื่อลูกค้า : บริษัทนภดล อินเตอร์เทรดดิ้ง จำกัด' ***\n"
            "      *** ต้องอ่านเต็ม 'บริษัทนภดล อินเตอร์เทรดดิ้ง จำกัด' ไม่ใช่แค่ 'นภดล' ***\n\n"
            "  (D) ใบรับเงินไปรษณีย์ไทย (thermal POS):\n"
            "      ผู้ออก = บริษัท ไปรษณีย์ไทย จำกัด (หัวเอกสาร) → ห้ามใช้ชื่อนี้\n"
            "      ลูกค้า = ชื่อบริษัทผู้ส่งพัสดุ ซึ่งอยู่ถัดจาก 'เลขประจำตัวผู้เสียภาษีอากร' ส่วนที่สอง\n"
            "      *** ในใบเสร็จไปรษณีย์จะมี 'เลขประจำตัวผู้เสียภาษีอากร' 2 ชุด: ***\n"
            "      *** ชุดที่ 1 (TAX ID ด้านบนสุด) = ของไปรษณีย์ไทย (ผู้ออก) → ห้ามใช้ ***\n"
            "      *** ชุดที่ 2 (อยู่หลัง 'Refer ABB Rcpt#' หรือหลัง 'Refer') = ของลูกค้า/ผู้ส่ง ***\n"
            "      *** ชื่อบริษัทลูกค้าจะอยู่บรรทัดถัดจากเลข TAX ID ชุดที่ 2 ***\n"
            "      *** ตัวอย่าง: 'เลขประจำตัวผู้เสียภาษี 0105560151261' ***\n"
            "      *** บรรทัดถัดไป: 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด' ← นี่คือชื่อลูกค้า ***\n"
            "      *** ต้องอ่านเต็ม 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด' ***\n"
            "      *** ห้ามอ่านแค่ 'นภดล' หรือตัดชื่อ ***\n"
            "      *** ใบเสร็จไปรษณีย์ที่มีชื่อบริษัทผู้ส่ง = 'มีชื่อลูกค้า' (ห้ามบอกว่า 'ไม่ระบุชื่อลูกค้า') ***\n\n"
            "  (E) ใบเสร็จทั่วไปที่ไม่มีชื่อลูกค้าจริงๆ:\n"
            "      ใบเสร็จ thermal/POS จากร้านสะดวกซื้อ/ร้านอาหาร ที่ไม่มีช่องชื่อลูกค้าเลย\n"
            "      → กรณีนี้เท่านั้นที่ถือว่า 'ไม่ระบุชื่อลูกค้า'\n\n"
            "- *** ใบฝากเงิน (deposit_slip) → ไม่ต้องตรวจชื่อบริษัท/เลขภาษี/ที่อยู่ (ข้ามได้) ***\n"
            "- *** ใบเสร็จค่าน้ำประปา/ค่าไฟฟ้า → ข้ามชื่อ/เลขภาษี/ที่อยู่ลูกค้า ใน company_name_check ***\n"
            "  - ข้ามชื่อบริษัท+เลขภาษี+ที่อยู่ลูกค้า ใน company_name_check (ไม่ว่าจะเป็นชื่อบุคคลหรือบริษัท)\n"
            "  - *** ห้ามให้ใบเสร็จค่าน้ำ/ค่าไฟทำให้ company_name_check ไม่ผ่าน เด็ดขาด ***\n"
            "  - *** ห้ามนำใบเสร็จค่าน้ำ/ค่าไฟมาใส่ใน mismatched_files ***\n"
            "  - การตรวจที่อยู่สาธารณูปโภค ระบบจะตรวจจาก Detail Lines โดยอัตโนมัติ (ไม่ต้องตรวจใน AI)\n\n"
            "  *** การตรวจสอบ 3 รายการ (สำหรับใบเสร็จอื่นที่ไม่ใช่ค่าน้ำ/ค่าไฟ): ***\n"
            "  *** สำคัญ: ตรวจกับ accepted_companies ทั้งหมด ไม่ใช่แค่บริษัทเดียว ***\n\n"
            "  (I) ตรวจชื่อบริษัท:\n"
            "  - ผ่าน: ถ้าชื่อลูกค้า/ผู้ซื้อในใบเสร็จตรงกับชื่อบริษัทใดก็ได้ใน accepted_companies\n"
            "    (เปรียบเทียบแบบยืดหยุ่น ไม่ต้องตรง 100%%\n"
            "    เช่น 'บริษัทนภดล อินเตอร์เทรดดิ้ง จำกัด' = 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด' ถือว่าตรง)\n"
            "  - ไม่ผ่าน: ถ้าชื่อบริษัทไม่ตรงกับบริษัทใดเลยใน accepted_companies\n\n"
            "  (II) ตรวจเลขประจำตัวผู้เสียภาษี (Tax ID):\n"
            "  - ดูเลขประจำตัวผู้เสียภาษีของ **ลูกค้า/ผู้ซื้อ** ในใบเสร็จ\n"
            "    *** ห้ามใช้เลขภาษีของผู้ออกใบเสร็จ (ผู้ขาย) ที่อยู่ด้านบนสุด ***\n"
            "    *** เลขภาษีของลูกค้ามักอยู่หลังคำว่า 'เลขประจำตัวผู้เสียภาษี' ของส่วนลูกค้า ***\n"
            "  - ผ่าน: เลขภาษีตรงกับเลขภาษีของบริษัทใดก็ได้ใน accepted_companies\n"
            "    หรือใบเสร็จไม่มีเลขภาษีลูกค้าระบุ\n"
            "  - ไม่ผ่าน: เลขภาษีไม่ตรงกับบริษัทใดเลยใน accepted_companies\n\n"
            "  (III) ตรวจที่อยู่ลูกค้า:\n"
            "  - ดูที่อยู่ของ **ลูกค้า/ผู้ซื้อ** ในใบเสร็จ\n"
            "    *** ห้ามใช้ที่อยู่ของผู้ออกใบเสร็จ (ผู้ขาย) ***\n"
            "  - ผ่าน: ที่อยู่สอดคล้องกับที่อยู่ (สำนักงานใหญ่หรือสาขา) ของบริษัทใดก็ได้ใน accepted_companies\n"
            "    (เปรียบเทียบยืดหยุ่น ดูคำสำคัญ เช่น เลขที่, ถนน, เขต/อำเภอ,\n"
            "    จังหวัด, รหัสไปรษณีย์ ถ้าตรงส่วนใหญ่ถือว่าผ่าน)\n"
            "    หรือใบเสร็จไม่มีที่อยู่ลูกค้าระบุ\n"
            "  - ไม่ผ่าน: ที่อยู่ไม่สอดคล้องกับที่อยู่ใดเลยของทุกบริษัทใน accepted_companies\n\n"
            "  *** สรุปผลรวม: ***\n"
            "  - ใบเสร็จที่ไม่มีข้อมูลลูกค้าเลย → ข้ามได้ (ถือว่าผ่าน)\n"
            "  - ใบเสร็จที่มีข้อมูลลูกค้า → ต้องตรวจทั้ง 3 รายการที่มีข้อมูล\n"
            "  - company_name_check.pass = true เมื่อไม่มีใบเสร็จใดที่ชื่อ/เลขภาษี/ที่อยู่ ไม่ตรง\n"
            "- ถ้าไม่มี accepted_companies → ข้ามการตรวจนี้ (company_name_check.required = false)\n\n"

            "### กฎข้อ 6: ตรวจสอบเลขที่ใบเสร็จ / วันที่ / ชื่อร้านค้า (Invoice Detail Check)\n"
            "- ตรวจเฉพาะไฟล์ที่เป็น **ใบเสร็จ (receipt)** หรือ **ใบกำกับภาษี (invoice)** ใน receipt_files เท่านั้น\n"
            "- *** ห้ามตรวจ: บิลเงินสด, ลายมือเขียน, สลิปโอนเงิน, ใบฝากเงิน (deposit_slip), เอกสารที่ถูก skip ***\n\n"
            "- สำหรับใบเสร็จ/ใบกำกับภาษีแต่ละใบ ให้อ่านข้อมูลจากรูป:\n"
            "  1. **เลขที่ใบเสร็จ/เลขที่เอกสาร** (Invoice Number) - เลขที่พิมพ์อยู่บนใบเสร็จ\n"
            "  2. **วันที่ในใบเสร็จ** (Invoice Date) - วันที่ออกใบเสร็จ\n"
            "     *** รูปแบบวันที่ไทย: DD/MM/พ.ศ. (วัน/เดือน/ปีพุทธศักราช) เช่น 26/01/2569 = 2026-01-26 ***\n"
            "     *** พ.ศ. ลบ 543 = ค.ศ., มกราคม=01, กุมภาพันธ์=02, มีนาคม=03 ***\n"
            "  3. **ชื่อผู้ออกใบเสร็จ/ร้านค้า/ผู้ขาย** (Partner) - ชื่อร้านค้าหรือบริษัทที่ออกใบเสร็จ\n\n"
            "- จากนั้นเปรียบเทียบกับข้อมูลใน **Detail Lines** ที่ User ลงไว้:\n"
            "  - Invoice Number: ตรวจว่า User ลงเลขที่ใบเสร็จถูกต้องตรงกับในรูปหรือไม่\n"
            "  - Invoice Date: ตรวจว่า User ลงวันที่ถูกต้องตรงกับในรูปหรือไม่\n"
            "  - Partner: ตรวจว่า User ลงชื่อร้านค้า/ผู้ขายถูกต้องตรงกับในรูปหรือไม่ (เปรียบเทียบแบบยืดหยุ่น)\n\n"
            "- *** วิธีจับคู่ใบเสร็จกับ Detail Line: ***\n"
            "  ใช้ **ยอดเงิน (amount/subtotal)** เป็นตัวจับคู่หลัก\n"
            "  เช่น ใบเสร็จ 70155.jpg ยอด 3,521.53 → หา Detail Line ที่ subtotal = 3,521.53\n"
            "  ถ้ามีหลาย Line ยอดเท่ากัน ให้ดู invoice_number หรือ partner ประกอบ\n\n"
            "- *** เงื่อนไขผ่าน/ไม่ผ่าน: ***\n"
            "  - ถ้า Detail Line ไม่มีข้อมูล invoice_number / invoice_date / partner (ค่าว่าง) → ถือว่า User ไม่ได้ลง → ไม่ผ่าน\n"
            "  - ถ้า Detail Line มีข้อมูลแล้วตรงกับในรูป → ผ่าน\n"
            "  - ถ้า Detail Line มีข้อมูลแต่ไม่ตรงกับในรูป → ไม่ผ่าน\n"
            "  - invoice_detail_check.pass = true เมื่อใบเสร็จทุกใบที่ตรวจได้ มีข้อมูลครบและตรงกับ Detail Lines\n\n"

            "### กฎข้อ 7: ตรวจสอบที่อยู่สาธารณูปโภค\n"
            "- *** ระบบจะตรวจจาก Detail Lines โดยอัตโนมัติ (Analytic Account vs Partner) ***\n"
            "- *** AI ไม่ต้องตรวจส่วนนี้ ไม่ต้องส่ง utility_address_check ***\n\n"

            "ตอบเป็นภาษาไทยในรูปแบบ JSON เท่านั้น"
        )

    def _build_ai_prompt(self, attachments=None, expected_company_info=None, condition_map=None):
        """Build the prompt for Gemini AI to verify the document."""
        self.ensure_one()
        if condition_map is None:
            condition_map = {}

        detail_lines = self._prepare_detail_lines_text()

        detail_json = json.dumps(detail_lines, ensure_ascii=False, indent=2)

        # Build attachment list text
        att_list_text = ""
        if attachments:
            att_list_text = "## รายชื่อไฟล์แนบทั้งหมด (%d ไฟล์):\n" % len(attachments)
            for idx, att in enumerate(attachments, 1):
                att_list_text += "- รูปที่ %d: %s\n" % (idx, att.name or 'unknown')
            att_list_text += "\n"

        # Build itemized file list from condition_map
        itemized_files = []
        if condition_map:
            for fname, conds in condition_map.items():
                if not conds.get('check_amount_combined', True):
                    itemized_files.append(fname)

        prompt = (
            "## ข้อมูลเอกสารในระบบ:\n"
            "- เลขที่เอกสาร: " + str(self.name or '') + "\n"
            "- วันที่: " + str(self.doc_date or '') + "\n"
            "- พนักงาน: " + str(self.employee_id.name or '') + "\n"
            "- Description: " + str(self.description or 'ไม่มีข้อมูล') + "\n"
            "- จำนวนเงินรวม (Total/Amount): " + str(self.amount or 0) + "\n"
            "- Untaxed Amount: " + str(self.untaxed_amount or 0) + "\n"
            "- Tax Amount: " + str(self.tax_amount or 0) + "\n"
            "- WHT Amount: " + str(self.wht_amount or 0) + "\n"
            "- Advance Amount: " + str(self.advance_amount or 0) + "\n"
            "- Clear Amount: " + str(self.clear_amount or 0) + "\n\n"
            + att_list_text
            + "## รายการ Detail Lines:\n" + detail_json + "\n\n"
        )

        # Add expected company info for company name/tax_id/address check
        if expected_company_info and isinstance(expected_company_info, dict):
            accepted = expected_company_info.get('accepted_companies', [])
            if accepted:
                prompt += u"## บริษัทในกลุ่มที่ยอมรับ (accepted_companies):\n"
                prompt += u"*** ใบเสร็จที่ออกในชื่อบริษัทใดก็ตามในรายการนี้ ถือว่าผ่านทั้งหมด ***\n"
                for idx, comp in enumerate(accepted, 1):
                    prompt += u"\n### บริษัทที่ %d:\n" % idx
                    prompt += u"- ชื่อบริษัท: %s\n" % comp.get('name', '')
                    prompt += u"- เลขภาษี: %s\n" % comp.get('tax_id', '')
                    prompt += u"- ที่อยู่สำนักงานใหญ่: %s\n" % comp.get('address', '')
                    br_addrs = comp.get('branch_addresses', [])
                    if br_addrs:
                        prompt += u"- ที่อยู่สาขา:\n"
                        for br in br_addrs:
                            prompt += u"  * %s: %s\n" % (br.get('branch', ''), br.get('address', ''))
                prompt += (
                    u"\n- ให้ตรวจสอบว่า ชื่อ/เลขภาษี/ที่อยู่ ของลูกค้า (ผู้ซื้อ) ในใบเสร็จ "
                    u"ตรงกับบริษัทใดบริษัทหนึ่งในรายการนี้หรือไม่\n"
                    u"- *** ชื่อ: ตรงกับบริษัทใดก็ได้ในรายการ = ผ่าน ***\n"
                    u"- *** เลขภาษี: ตรงกับเลขภาษีของบริษัทใดก็ได้ในรายการ = ผ่าน ***\n"
                    u"- *** ที่อยู่: ตรงกับที่อยู่ (สำนักงานใหญ่หรือสาขา) ของบริษัทใดก็ได้ = ผ่าน ***\n\n"
                )

        # Add cash bill registration data
        cash_bills = self.cash_bill_ids
        if cash_bills:
            cash_bill_data = []
            for bill in cash_bills:
                bill_total = bill.amount + (bill.vat_amount or 0)
                entry = {
                    'description': bill.description,
                    'amount': bill_total,  # จำนวนเงิน + VAT = ยอดรวมต่อรายการ
                }
                if bill.vat_amount:
                    entry['amount_before_vat'] = bill.amount
                    entry['vat'] = bill.vat_amount
                cash_bill_data.append(entry)
            cash_bill_json = json.dumps(cash_bill_data, ensure_ascii=False, indent=2)
            prompt += (
                u"## รายการบิลเงินสด (Cash Bills) ที่ผู้ใช้ลงทะเบียนไว้ (%d รายการ):\n" % len(cash_bills)
                + cash_bill_json + u"\n\n"
            )
        else:
            prompt += u"## รายการบิลเงินสด: ไม่มี (ผู้ใช้ไม่ได้ลงทะเบียนบิลเงินสดไว้)\n\n"

        prompt += (
            u"## คำสั่งตรวจสอบ:\n\n"
            u"### ขั้นตอนที่ 1: จำแนกประเภทรูปภาพ\n"
            u"สำหรับรูปแต่ละรูป ให้จำแนกเป็น 1 ใน 6 ประเภท:\n"
            u"*** ลำดับการจำแนก: จำแนกประเภท A, B, C, D, E ก่อนทุกรูป → แล้วค่อยจำแนกประเภท F ***\n"
            u"(เพราะ ประเภท F ต้องดูว่ามีเอกสาร B/C/D อยู่ในชุดหรือไม่ จึงต้องจำแนกรูปอื่นก่อน)\n\n"
            u"**ประเภท A: สลิปโอนเงิน/สกรีนช็อตแอปธนาคาร → skipped_files**\n"
            u"  สกรีนช็อตจากแอปธนาคาร (SCB, KBANK, KTB, BBL ฯลฯ) ที่แสดงการโอนเงินสำเร็จ\n"
            u"  มีพื้นหลังสีสัน/กราฟิกสวยงาม มีโลโก้ธนาคาร มีข้อมูล จาก→ไปยัง\n"
            u"  → skipped_files, reason='สลิปโอนเงิน ไม่ใช่ใบเสร็จ'\n"
            u"  *** สำคัญ: ให้อ่านยอดโอนเงินจากสลิปด้วย แล้วใส่ใน field amount ***\n"
            u"  *** ไม่นับรวมใน receipt_total แต่ระบบต้องการยอดเพื่อตรวจสอบข้อ 9 ***\n\n"
            u"**ประเภท B: บิลเงินสด/ลายมือเขียน → skipped_files (กฎสำคัญสูงสุด)**\n"
            u"  *** วิธีอ่านยอด: อ่าน 3 ค่า → จำนวน(QUANTITY) × ราคาต่อหน่วย(UNIT PRICE) = ยอดรวม(TOTAL) ***\n"
            u"  *** ถ้าคำนวณไม่ตรงกับยอดรวมที่อ่านได้ → ใช้ค่าคำนวณ (จำนวน × ราคา) ใส่ field amount ***\n\n"
            u"  ========== CHECKLIST บังคับ: ก่อนจัดเป็นประเภท D ต้องผ่านทุกข้อ ==========\n"
            u"  *** ก่อนจะจัดเอกสารใดๆ เป็นประเภท D (receipt_files) ต้องตอบ YES ทุกข้อ: ***\n"
            u"  [1] ตัวเลข 'รวมราคาทั้งสิ้น' / 'จำนวนเงินรวมทั้งสิ้น' พิมพ์จากเครื่อง 100%? (ไม่ใช่ลายมือ)\n"
            u"  [2] ตัวเลข 'ภาษีมูลค่าเพิ่ม' / 'VAT' พิมพ์จากเครื่อง 100%? (ถ้ามี)\n"
            u"  [3] ตัวเลข 'จำนวนเงิน' ในแต่ละบรรทัดสินค้า พิมพ์จากเครื่อง 100%?\n"
            u"  → ถ้าข้อใดข้อหนึ่งตอบ NO (= เขียนด้วยมือ/ปากกา) → SKIP เป็นประเภท B ทันที\n"
            u"  → ห้ามจัดเป็นประเภท D เด็ดขาด แม้หัวเอกสารจะเขียนว่า 'ใบกำกับภาษี' หรือ 'ใบเสร็จรับเงิน'\n"
            u"  ==================================================================\n\n"
            u"  ตรงข้อใดข้อหนึ่ง = SKIP ทันที:\n"
            u"  - มีคำว่า 'บิลเงินสด' / 'CASH SALES' / 'สำเนาบิลเงินสด' / 'CASH SALE COPY' เป็นชื่อเอกสาร\n"
            u"  - ตัวเลข 'ยอดเงิน' (Amount/Grand Total/รวมทั้งสิ้น/จำนวนเงิน) เขียนด้วยมือ/ปากกา (ไม่ใช่ฟอนต์พิมพ์)\n"
            u"  - *** ฟอร์มพิมพ์ล่วงหน้า (pre-printed form) ที่กรอกตัวเลขยอดเงินด้วยมือ → SKIP ***\n"
            u"    ตัวอย่าง: ใบเสร็จรับเงิน/ใบกำกับภาษี กระดาษ A4/A5 ที่ตัวหัวเอกสาร/ชื่อร้านพิมพ์จากโรงพิมพ์\n"
            u"    แต่ตัวเลขในช่อง 'จำนวนเงิน', 'รวมเป็นเงิน', 'ภาษีมูลค่าเพิ่ม', 'จำนวนเงินรวมทั้งสิ้น'\n"
            u"    เป็นลายมือเขียนด้วยปากกา → ถือว่าเป็นบิลเงินสด/ลายมือเขียน → SKIP\n"
            u"  - มีช่อง 'ลงชื่อ...ผู้ซื้อ' และ 'ลงชื่อ...ผู้ขาย/ผู้รับเงิน' ที่เซ็นด้วยมือ\n"
            u"  - มีช่อง 'จำนวนเงิน (ตัวอักษร)' ที่เขียนด้วยมือ เช่น 'สี่ร้อยหกสิบห้าบาท'\n"
            u"  - ชื่อผู้ซื้อ (นามผู้ซื้อ) เขียนด้วยมือ/ปากกา\n"
            u"  - เป็นกระดาษ A4/A5 ที่มีเส้นตาราง/ช่องกรอก (ไม่ใช่กระดาษม้วน thermal)\n\n"
            u"  *** ตัวอย่างที่ AI มักจำแนกผิด (สำคัญมาก): ***\n"
            u"  ตัวอย่าง 1: เอกสาร 'ต้นฉบับใบกำกับภาษี/ใบเสร็จรับเงิน' หัวสวยงามพิมพ์จากโรงพิมพ์\n"
            u"    แต่ยอด 434.58, VAT 30.42, รวม 465 เขียนด้วยปากกา → ต้อง SKIP เป็น B\n"
            u"  ตัวอย่าง 2: เอกสาร 'ใบเสร็จรับเงิน' มีเลขที่เอกสาร มีตราประทับ\n"
            u"    แต่ช่องยอดเงิน/จำนวนเงินกรอกด้วยลายมือ → ต้อง SKIP เป็น B\n"
            u"  ตัวอย่าง 3: เอกสารจากร้านค้า/ห.จ.ก. หัวพิมพ์จากโรงพิมพ์\n"
            u"    มีตารางรายการสินค้า แต่จำนวนเงินในบรรทัดเขียนด้วยมือ → ต้อง SKIP เป็น B\n\n"
            u"  *** กฎเหล็ก: ชื่อเอกสาร ≠ ประเภทเอกสาร ***\n"
            u"  *** แม้เอกสารเขียนว่า 'ใบกำกับภาษี' / 'ใบเสร็จรับเงิน' / 'ต้นฉบับ' ***\n"
            u"  *** ถ้าตัวเลขยอดเงินเขียนด้วยมือ → เป็นประเภท B เสมอ ***\n"
            u"  *** ตัดสินจาก 'วิธีบันทึกตัวเลขยอดเงิน' ไม่ใช่ชื่อเอกสาร/หัวกระดาษ/ตราประทับ ***\n\n"
            u"  *** วิธีแยก ลายมือ vs เครื่องพิมพ์: ***\n"
            u"  - ลายมือ: เส้นไม่เท่ากัน ตัวเลขเอียง ขนาดไม่สม่ำเสมอ มีรอยหมึกปากกา\n"
            u"    ตัวเลขมีหาง เส้นต่อกันไม่เท่า ตัว 4 ปิดหัว/เปิดหัวไม่สม่ำเสมอ จุดทศนิยมไม่ตรงแนว\n"
            u"  - เครื่องพิมพ์: ตัวเลขสม่ำเสมอ monospace font ขนาดเท่ากัน คมชัด ไม่มีรอยหมึก\n\n"
            u"  *** ข้อยกเว้น (ห้าม skip): เฉพาะ thermal/POS receipt ที่ยอดเงินพิมพ์จากเครื่อง ***\n"
            u"  - ใบเสร็จ thermal (กระดาษม้วนแคบ) / POS ที่ตัวเลขยอดเงินทุกตัวเป็น monospace font\n"
            u"    แม้มีข้อความเขียนมือเพิ่ม (โน้ต, วันที่, ชื่อ) → ไม่ skip เพราะยอดเงินพิมพ์จากเครื่อง\n"
            u"  - มีคำว่า 'เงินสด' ในช่องชำระเงินของใบเสร็จ thermal/POS → ไม่ skip (แค่วิธีชำระ)\n"
            u"  - ใบเสร็จไปรษณีย์ไทย (ใบรับเงิน, N EMS, RCPT#) พิมพ์จาก POS → ไม่ skip\n"
            u"  *** ข้อยกเว้นนี้ใช้เฉพาะ thermal/POS เท่านั้น ***\n"
            u"  *** ฟอร์มกระดาษ A4/A5 ที่กรอกยอดเงินด้วยมือ → ไม่ได้ยกเว้น → SKIP ***\n"
            u"  → skipped_files, reason='บิลเงินสด/ลายมือเขียน ไม่อ่านยอด'\n\n"
            u"**ประเภท C: ใบฝากเงิน (deposit slip) → receipt_files, type='deposit_slip'**\n"
            u"  คีย์เวิร์ดระบุ (ตรงข้อใดข้อหนึ่ง → เป็นใบฝากเงิน):\n"
            u"  - มีคำว่า 'จำนวนเงินฝาก' หรือ 'ใบบันทึกรายการฝากเงิน'\n"
            u"  - มีชื่อ CP AXTRA / ข้าวเบ็ค / 7-Eleven / ไปรษณีย์ / ธนาคาร (SCB, KBANK ฯลฯ)\n"
            u"  - มีคำว่า 'ค่าบริการรับฝากเงิน' หรือ 'บริการจ่ายเงิน'\n"
            u"  วิธีอ่านยอดฝากเงิน: ดูตัวเลขหลังคำว่า 'จำนวนเงินฝาก' นั่นคือ amount\n\n"
            u"  *** กฎเด็ดขาดสำหรับใบฝากเงิน (ห้ามทำผิด): ***\n"
            u"  *** 1. ใบฝากเงิน 1 รูป = 1 รายการเสมอ (ห้ามแยกเป็น (บน)/(ล่าง) เด็ดขาด) ***\n"
            u"  *** 2. type ต้องเป็น 'deposit_slip' เสมอ ห้ามใช้ 'receipt' หรือ 'invoice' ***\n"
            u"  *** 3. ห้ามใช้ 'เงินสด' / 'เงินทอน' / 'ยอดรวม' เป็น amount หรือ fee ***\n"
            u"  *** 4. filename ใช้ชื่อไฟล์เดิม ห้ามเพิ่ม (บน)/(ล่าง) ***\n\n"
            u"  *** วิธีอ่านค่าธรรมเนียม (fee) — สำคัญมาก: ***\n"
            u"  ใบฝากเงิน 7-Eleven/CP AXTRA มี 2 ส่วน: ส่วนบน=ข้อมูลฝากเงิน, ส่วนล่าง=ใบเสร็จ Counter Service\n"
            u"  → ดูส่วนล่าง (Counter Service) หาคำว่า 'บริการจ่ายเงิน' หรือ 'ค่าบริการรับฝากเงิน' หรือ 'ยอดรวม'\n"
            u"  → ตัวเลขถัดจากคำนี้คือ fee (เช่น 'ค่าบริการรับฝากเงิน 15.00' → fee = 15.00)\n"
            u"  → ถ้าไม่มี Counter Service ให้ดูคำว่า 'ค่าธรรมเนียม' หรือ 'Fee'\n"
            u"  *** ห้ามใช้ 'เงินทอน' เป็น fee เด็ดขาด (เงินทอน ≠ ค่าธรรมเนียม) ***\n"
            u"  *** ห้ามอ่าน fee จากส่วนบน (ข้อมูลฝาก) ต้องดูส่วนล่าง (Counter Service) ***\n"
            u"  → receipt_files 1 รายการเดียว: {filename='ชื่อไฟล์เดิม', type='deposit_slip', amount=ยอดฝาก, fee=จาก Counter Service}\n\n"
            u"**ประเภท D: ใบเสร็จ/ใบกำกับภาษีทั่วไป → receipt_files, type='receipt' หรือ 'invoice'**\n"
            u"  *** ก่อนจัดเป็นประเภท D ต้องผ่าน CHECKLIST (ดูประเภท B ด้านบน) ก่อนเสมอ ***\n"
            u"  *** ถ้าตัวเลขยอดเงินข้อใดข้อหนึ่งเขียนด้วยมือ → ต้อง SKIP เป็นประเภท B ทันที ***\n"
            u"  ใบเสร็จที่ตัวเลข 'ยอดเงิน' ทุกตัวพิมพ์จากเครื่อง 100% (ไม่ใช่ลายมือ)\n"
            u"  รวมถึง: ใบเสร็จไปรษณีย์ไทย (ใบรับเงิน), ใบเสร็จ POS, thermal receipt\n"
            u"  แม้มีข้อความเขียนมือเพิ่มเติม (จดโน้ต/วันที่) อยู่บนกระดาษ → ถ้ายอดเงินพิมพ์จากเครื่อง = ประเภท D\n"
            u"  *** ถ้าตัวเลข 'ยอดเงิน' เขียนด้วยมือ → ไม่ใช่ประเภท D ให้จัดเป็นประเภท B (skipped) ***\n"
            u"  *** ฟอร์มพิมพ์ล่วงหน้า (กระดาษ A4/A5 หัวเอกสารพิมพ์ แต่ยอดเงินกรอกด้วยมือ) = ประเภท B ***\n\n"
            u"  *** วิธีอ่านยอดเงินจากใบเสร็จ (สำคัญมาก — อ่านผิดคือบกพร่อง): ***\n"
            u"  *** กฎเหล็ก: ใช้ 'รวมทั้งสิ้น' / 'Grand Total' / 'Total' / 'จำนวนเงิน' เท่านั้น ***\n"
            u"  *** ห้ามใช้ 'เงินสด' / 'Cash' / 'Tender' → เงินที่จ่าย ≠ ยอดใบเสร็จ ***\n"
            u"  *** ห้ามใช้ 'เงินทอน' / 'Change' → เงินทอนกลับ ≠ ยอดใบเสร็จ ***\n"
            u"  *** ห้ามใช้ 'มูลค่าก่อนภาษี' / 'ยอดก่อนภาษี' / 'Subtotal' / 'ราคาสินค้า' / 'มูลค่าสินค้า' ***\n"
            u"  ***   → เพราะเป็นยอดก่อนบวก VAT ไม่ใช่ยอดรวมสุดท้ายที่จ่ายจริง ***\n"
            u"  *** ห้ามใช้ 'NON VAT' / 'VATABLE' / 'VAT EXC' / 'VAT' เป็น amount ***\n"
            u"  ***   → เพราะเป็นยอดแยกประเภทภาษี ไม่ใช่ยอดรวมทั้งสิ้น ***\n"
            u"  ***   ต้องใช้ 'รวมทั้งสิ้น' (= ยอดรวม VAT แล้ว) เสมอ ***\n"
            u"  *** ตัวอย่าง 1: รวมทั้งสิ้น ฿138.00, เงินสด ฿500.00, เงินทอน -฿362.00 ***\n"
            u"  ***   → amount = 138.00 (ไม่ใช่ 500!) ***\n"
            u"  ***   เพราะ 'เงินสด 500' = เงินที่ลูกค้ายื่นจ่าย แล้วได้ทอน 362 กลับ ***\n"
            u"  *** ตัวอย่าง 2: รวมทั้งสิ้น ฿232.00, เงินสด ฿1,002.00, เงินทอน -฿770.00 ***\n"
            u"  ***   → amount = 232.00 (ไม่ใช่ 1,002!) ***\n"
            u"  *** ตัวอย่าง 3 (ปั๊มน้ำมัน): รวมทั้งสิ้น ฿185.00, ภาษี 7% ฿12.10, มูลค่าก่อนภาษี ฿172.90 ***\n"
            u"  ***   → amount = 185.00 (ไม่ใช่ 172.90!) ***\n"
            u"  ***   เพราะ 'มูลค่าก่อนภาษี 172.90' = ยอดยังไม่รวม VAT ***\n"
            u"  *** ตัวอย่าง 4 (ร้านค้า): รวมทั้งสิ้น ฿1,070.00, มูลค่าสินค้า ฿1,000.00, VAT 7% ฿70.00 ***\n"
            u"  ***   → amount = 1,070.00 (ไม่ใช่ 1,000.00!) ***\n"
            u"  *** ตัวอย่าง 5 (ไปรษณีย์ไทย): รวมทั้งสิ้น ฿188.00, เงินสด ฿188.00, NON VAT ฿168.00, VATABLE ฿20.00 ***\n"
            u"  ***   → amount = 188.00 (ไม่ใช่ 168.00!) ***\n"
            u"  ***   เพราะ 'NON VAT 168.00' = ยอดสินค้าที่ไม่มี VAT ≠ ยอดรวมทั้งสิ้น ***\n"
            u"  *** วิธีตรวจสอบ: ถ้ามี 'เงินทอน' ติดลบ → ยอดที่อ่านต้องน้อยกว่า 'เงินสด' ***\n"
            u"  *** ถ้ายอดที่คุณอ่านเท่ากับ 'เงินสด' → คุณอ่านผิด! ให้กลับไปอ่าน 'รวมทั้งสิ้น' ***\n"
            u"  *** ถ้ามีทั้ง 'รวมทั้งสิ้น' และ 'มูลค่าก่อนภาษี' → ใช้ 'รวมทั้งสิ้น' เสมอ ***\n"
            u"  - ถ้ามีตราประทับทับตัวเลข ให้พยายามอ่านตัวเลขที่อยู่หลังคำว่า 'รวมทั้งสิ้น'\n\n"
            u"  *** ใบเสร็จกรมสรรพากร/ใบเสร็จราชการ (ห้าม skip เป็น 'อ่านไม่ได้'): ***\n"
            u"  - เอกสาร ภ.ง.ด.1, ภ.ง.ด.1ย, ภ.ง.ด.3, ภ.ง.ด.53, ภ.พ.30 ฯลฯ\n"
            u"  - มีตราครุฑ (garuda) เป็นลายน้ำทับบนเอกสาร → เป็นเรื่องปกติ ไม่ใช่เอกสารเสียหาย\n"
            u"  - มีข้อความ 'กรมสรรพากร' หรือ 'กระทรวงการคลัง' ที่หัวกระดาษ\n"
            u"  - เป็นใบเสร็จรับเงินถูกต้อง → จัดเป็น type='receipt' เสมอ\n"
            u"  - วิธีอ่านยอด: ดูช่อง 'ภาษีที่ชำระ' หรือ 'รวมเงินภาษีและเงินเพิ่ม'\n"
            u"  - ตัวเลขอาจอยู่ในรูป ×1,000.00 → amount = 1000.00\n"
            u"  - ถ้ามีลายน้ำครุฑทับตัวเลข ให้พยายามอ่านตัวเลขใต้ลายน้ำให้ได้\n"
            u"  *** ห้าม skip เป็น 'เอกสารไม่ชัดเจน/อ่านไม่ได้' เด็ดขาด ***\n"
            u"  *** ถ้าอ่านยอดไม่ชัด ให้ใส่ amount=0 แต่ยังคงต้องเป็น receipt_files type='receipt' ***\n\n"
            u"  → receipt_files, อ่านยอด 'รวมทั้งสิ้น/Total/ภาษีที่ชำระ' เป็น amount, fee = 0\n\n"
            u"**ประเภท E: สำเนาบัตรประชาชน / เอกสารประกอบที่ไม่ใช่ใบเสร็จ → skipped_files**\n"
            u"  ลักษณะ: สำเนาบัตรประชาชน, สำเนาทะเบียนบ้าน, สำเนาหนังสือเดินทาง,\n"
            u"  สำเนาใบขับขี่, สำเนาหนังสือรับรองบริษัท, ภพ.20, รูปถ่ายสินค้า, รูปหน้าจอ\n"
            u"  → skipped_files, reason='เอกสารประกอบ ไม่ใช่ใบเสร็จ'\n"
            u"  *** ห้ามอ่านยอดเงิน ใส่ amount=0 ***\n\n"
            u"**ประเภท F: ใบสำคัญรับเงิน / ใบรับรองแทนใบเสร็จรับเงิน → skipped_files**\n"
            u"  ลักษณะ: เอกสารภายในบริษัทที่มีคำว่า 'ใบสำคัญรับเงิน' หรือ 'ใบรับรองแทนใบเสร็จรับเงิน'\n"
            u"  เป็นฟอร์มพิมพ์ล่วงหน้า กรอกข้อมูลด้วยลายมือ มีช่องลงชื่อผู้รับเงิน/ผู้จ่ายเงิน/ผู้อนุมัติ\n"
            u"  *** กฎเด็ดขาด (ใช้กับทุกใบรับรองฯ ไม่ว่าจะมีเอกสารอื่นหรือไม่): ***\n"
            u"  - ใส่ใน skipped_files เสมอ (ห้ามใส่ใน receipt_files)\n"
            u"  - reason='ใบรับรองแทนใบเสร็จ ระบบจะตัดสินอัตโนมัติ'\n"
            u"  - ต้อง**อ่านยอด 'รวมทั้งสิ้น'** ใส่ field amount เสมอ (ระบบ Python ใช้ตัดสิน)\n"
            u"  - ใส่ field is_receipt_substitute=true (flag บอกระบบ)\n"
            u"  *** ห้ามใส่ reason ที่มีคำว่า 'บิลเงินสด' หรือ 'ลายมือเขียน' เด็ดขาด ***\n"
            u"  *** เพราะระบบจะนับเป็นบิลเงินสด → fail ถ้าผู้ใช้ไม่ลงทะเบียน ***\n"
            u"  *** ห้ามอ่านยอดจากเอกสารนี้ใส่ receipt_files เด็ดขาด ***\n"
            u"  *** ห้ามนับใบรับรองฯ ใน skipped_count ของ cash_bill_check ***\n"
            u"  *** 'ชุดนี้' = รูปภาพทั้งหมดที่แนบมากับเอกสาร Advance Clear นี้ ***\n\n"
            u"### สำคัญ: รูป 1 รูป อาจมีใบเสร็จมากกว่า 1 ใบ\n"
            u"- ตรวจสอบทุกรูปอย่างละเอียดว่ามีใบเสร็จมากกว่า 1 ใบในรูปเดียวกันหรือไม่\n"
            u"- ถ้ารูปมี 2 ใบเสร็จ (ซ้าย+ขวา หรือ บน+ล่าง):\n"
            u"  ให้สร้าง receipt_files 2 รายการจากรูปเดียวกัน:\n"
            u"  ใบที่ 1: filename = 'ชื่อไฟล์ (ซ้าย)' อ่าน amount + fee ของใบซ้าย\n"
            u"  ใบที่ 2: filename = 'ชื่อไฟล์ (ขวา)' อ่าน amount + fee ของใบขวา\n"
            u"- กฎซ้ำ (Dedup): ถ้า 2 ใบในรูปเดียวกันมียอดเงินเท่ากัน:\n"
            u"  *** ต้องตรวจรายละเอียดอื่นก่อน: ***\n"
            u"  - เลขที่เอกสาร (RunNo, RCPT#) → ต่างกัน = คนละใบ\n"
            u"  - เวลาทำรายการ → ต่างกัน = คนละใบ\n"
            u"  - TX.ID, ClientSRunNo, หมายเลขอ้างอิง → ต่างกัน = คนละใบ\n"
            u"  → นับเป็น 1 ใบ เฉพาะเมื่อทุกรายละเอียดเหมือนกัน (ถ่ายรูปซ้ำ)\n"
            u"  → มีรายละเอียดต่างแม้แต่อย่างเดียว = คนละใบ นับแยก\n\n"
            u"### ขั้นตอนที่ 2: ตรวจสอบ Description\n"
            u"- ถ้ามี Description → ตรวจว่ารายการตรงกับ Detail Lines หรือไม่\n"
            u"- ถ้ามีจำนวนเงินใน Description → ตรวจว่าตรงกับ Total และยอดใบเสร็จหรือไม่\n\n"
            u"### ขั้นตอนที่ 3: ตรวจสอบยอดเงิน\n"
            u"สูตรคำนวณ receipt_total (สำคัญมาก):\n"
            u"- ใบเสร็จทั่วไป (type=receipt/invoice): นับ amount\n"
            u"- ใบฝากเงิน (type=deposit_slip): นับเฉพาะ fee เท่านั้น ห้ามนับ amount\n"
            u"  เพราะยอดฝาก (amount) เป็นเงินที่เข้าบัญชีบริษัท ไม่ใช่ค่าใช้จ่าย\n"
            u"  ค่าใช้จ่ายจริงของใบฝากเงิน = fee (ค่าธรรมเนียม) เท่านั้น\n"
            u"- receipt_total = ผลรวม amount ของใบเสร็จทั่วไป + ผลรวม fee ของใบฝากเงินทุกใบ\n"
            u"  *** ห้ามรวมยอดบิลเงินสดใน receipt_total (ระบบจะคำนวณรวมให้เอง) ***\n"
            u"- cash_bill_total = ยอดรวมจากรายการบิลเงินสดที่ผู้ใช้ลงทะเบียน (ถ้า cash_bill_check.pass = true)\n"
            u"- combined_total = receipt_total + cash_bill_total (ถ้าบิลเงินสดผ่าน) หรือ receipt_total (ถ้าไม่มีบิลเงินสด)\n"
            u"- system_total = ถ้า WHT Amount > 0 ให้ใช้ Untaxed Amount + Tax Amount (เพราะ Total หักภาษี ณ ที่จ่ายแล้ว แต่ยอดใบเสร็จยังไม่หัก), ถ้า WHT Amount = 0 ให้ใช้ Total/Amount\n"
            u"- เปรียบเทียบ combined_total กับ system_total\n"
            u"- ใน JSON: receipt_total = ยอดจากใบเสร็จเท่านั้น (ไม่รวมบิลเงินสด)\n"
            u"            cash_bill_total = ยอดจากบิลเงินสดที่ลงทะเบียน (0 ถ้าไม่มีหรือไม่ผ่าน)\n"
            u"            combined_total = receipt_total + cash_bill_total\n"
            u"            matches = true ถ้า combined_total ใกล้เคียง system_total\n\n"
            u"### ขั้นตอนที่ 4: ตรวจสอบภาษีในรายการ Detail\n"
            u"- ถ้าใบเสร็จมี VAT แยกชัดเจน (มีบรรทัด VAT 7%) → ตรวจว่า Detail Lines ระบุ tax หรือยัง\n"
            u"- ถ้า Detail Lines มี tax อยู่แล้ว → ผ่าน\n"
            u"- ถ้าใบเสร็จไม่มี VAT แยก → ผ่านเสมอ\n"
            u"- *** ข้อยกเว้น VAT สำหรับสาธารณูปโภค (ค่าน้ำ/ค่าไฟ/ค่าโทรศัพท์/ค่าอินเตอร์เน็ต): ***\n"
            u"  *** สำคัญ: ขั้นตอนที่ 4 เปรียบเทียบที่อยู่กับ 'ที่อยู่จดทะเบียนบริษัท' ใน accepted_companies เท่านั้น ***\n"
            u"  *** ห้ามเอา Analytic Account มาใช้ในขั้นตอนที่ 4 เด็ดขาด (Analytic Account ใช้เฉพาะขั้นตอนที่ 6) ***\n"
            u"  ถ้าใบเสร็จเป็นสาธารณูปโภค ให้ตรวจเพิ่ม:\n"
            u"  (a) ออกชื่อบุคคล → ข้าม VAT (vat_exempt_utility = true)\n"
            u"  (b) ค่าน้ำ/ค่าไฟ ชื่อบริษัทในกลุ่ม แต่ที่อยู่ผู้ใช้น้ำ/ไฟไม่ตรงกับ **ที่อยู่จดทะเบียนบริษัท** → ข้าม VAT\n"
            u"      (เปรียบเทียบกับที่อยู่จดทะเบียนใน accepted_companies เท่านั้น ห้ามเทียบกับ Analytic Account)\n"
            u"  (c) ค่าน้ำ/ค่าไฟ ชื่อบริษัทในกลุ่ม + ที่อยู่ตรงกับ **ที่อยู่จดทะเบียน** → ต้องมี VAT ปกติ\n"
            u"  (d) ค่าโทรศัพท์/อินเตอร์เน็ต ชื่อบริษัท → ต้องมี VAT ปกติ\n"
            u"  (e) ใบฝากเงิน (deposit_slip) → ข้ามการตรวจ VAT เสมอ (ใช้แค่ค่าธรรมเนียม ไม่ต้องตรวจ VAT)\n"
            u"      *** ห้ามนับ deposit_slip เป็นใบเสร็จที่มี VAT ***\n\n"
            u"### ขั้นตอนที่ 5: ตรวจสอบบิลเงินสด (Cash Bill Cross-Check)\n"
            u"*** สำคัญมาก: ข้อมูล 'รายการลงทะเบียน' คือข้อมูลจากหัวข้อ 'รายการบิลเงินสด (Cash Bills) ที่ผู้ใช้ลงทะเบียนไว้' ***\n"
            u"*** ห้ามใช้ข้อมูลจาก Detail Lines มาตรวจสอบในขั้นตอนนี้เด็ดขาด ***\n"
            u"*** Detail Lines คือรายการบัญชี ไม่ใช่รายการบิลเงินสดที่ลงทะเบียน ***\n\n"
            u"- ถ้ามีไฟล์ที่ถูก skip เพราะเป็น 'บิลเงินสด/ลายมือเขียน':\n"
            u"  1. นับจำนวนบิลเงินสดที่ถูก skip (skipped_count)\n"
            u"  2. ดูจำนวนรายการจากหัวข้อ 'รายการบิลเงินสด (Cash Bills) ที่ผู้ใช้ลงทะเบียนไว้' (registered_count)\n"
            u"     *** ถ้าหัวข้อนี้บอกว่า 'ไม่มี' หรือ registered_count = 0 → fail ทันที ***\n"
            u"     *** ห้ามดูจาก Detail Lines แทน — ต้องมีรายการบิลเงินสดที่ลงทะเบียนจริงเท่านั้น ***\n"
            u"  *** สำคัญ: จำนวนรายการลงทะเบียน อาจไม่เท่ากับจำนวนใบบิล ***\n"
            u"  เพราะผู้ใช้อาจแยก item หลายรายการจากบิล 1 ใบ (เช่น บิล 1 ใบมี 3 รายการ → ลงทะเบียน 3 แถว)\n"
            u"  ดังนั้น ห้ามใช้จำนวนรายการเปรียบเทียบกับจำนวนใบบิล\n"
            u"  3. อ่านยอดจากรูปบิลเงินสด:\n"
            u"     *** สำคัญมาก — ป้องกันอ่านลายมือผิด: ***\n"
            u"     ให้อ่าน 3 ค่าจากบิลแต่ละใบ:\n"
            u"     (1) จำนวน (QUANTITY)\n"
            u"     (2) ราคาต่อหน่วย (UNIT PRICE)\n"
            u"     (3) ยอดรวม (TOTAL/AMOUNT)\n"
            u"     แล้วตรวจสอบ: จำนวน × ราคาต่อหน่วย ควร = ยอดรวม\n"
            u"     *** ถ้าคำนวณไม่ตรง → ใช้ค่าที่คำนวณได้ (จำนวน × ราคา) เป็นยอดจริง ***\n"
            u"     ตัวอย่าง: จำนวน=22, ราคา=20 → 22×20=440 แต่อ่านยอดรวมได้ 2200 → ใช้ 440\n"
            u"  4. เปรียบเทียบ description หรือ amount จาก 'รายการบิลเงินสดที่ลงทะเบียน' กับรูปบิลเงินสด:\n"
            u"     - ดู description ในรายการลงทะเบียน (Cash Bills) แล้วหาว่าสอดคล้องกับรายการในรูปบิลเงินสดหรือไม่\n"
            u"     - หรือดู amount ในรายการลงทะเบียน (Cash Bills) แล้วหาว่าสอดคล้องกับยอดในรูปบิลเงินสดหรือไม่\n"
            u"     - ตรงอย่างใดอย่างหนึ่งก็ถือว่าผ่าน (ไม่ต้องตรงทั้งคู่)\n"
            u"  5. ตรวจยอดรวม: ยอดรวมจาก Cash Bills ที่ลงทะเบียน ควรสอดคล้องกับยอดรวมในรูปบิลเงินสดทุกใบรวมกัน\n"
            u"  6. ถ้า description หรือ amount สอดคล้อง + ยอดรวมสอดคล้อง → pass\n"
            u"  7. ถ้าไม่ตรง → fail พร้อมระบุสิ่งที่ไม่ตรง\n"
            u"- ถ้าไม่มีไฟล์บิลเงินสดถูก skip → cash_bill_check.required = false (ไม่ต้องตรวจ)\n"
            u"- ถ้ามีบิลเงินสดถูก skip แต่ผู้ใช้ไม่ได้ลงทะเบียน (ไม่มี Cash Bills) → fail ทันที\n\n"
            u"=== สำคัญ: สลิปโอนเงินจากแอป ≠ ใบฝากเงิน / บิลเงินสดหรือตัวเลขเขียนมือ = skipped เสมอ ===\n\n"
            u"### ขั้นตอนที่ 6: ตรวจสอบข้อมูลบริษัทลูกค้า (ผู้ซื้อ) ในใบเสร็จ\n"
            u"*** กฎเด็ดขาด: ***\n"
            u"*** 1. 'ข้อมูลลูกค้า' = ข้อมูลของ 'ผู้ซื้อ/ผู้รับบริการ' ไม่ใช่ 'ผู้ออกใบเสร็จ/ผู้ขาย' ***\n"
            u"*** 2. ต้องอ่านชื่อ/เลขภาษี/ที่อยู่ให้ครบถ้วนทุกตัวอักษร ห้ามย่อหรือตัดข้อมูล ***\n"
            u"*** 3. ห้ามอ่านข้อมูลผิดเพี้ยน ต้องอ่านจากรูปให้ถูกต้อง ***\n\n"
            u"- ถ้ามี accepted_companies ในข้อมูลด้านบน:\n"
            u"  1. ดูใบเสร็จ/ใบกำกับภาษีที่เป็น receipt_files (ไม่ต้องดู skipped_files)\n"
            u"  2. หาข้อมูล **ลูกค้า/ผู้ซื้อ** ตามประเภทใบเสร็จ (ดูกฎข้อ 5)\n"
            u"  *** ข้อยกเว้นค่าน้ำ/ค่าไฟ: ข้ามชื่อ/เลขภาษี/ที่อยู่ลูกค้า ใน company_name_check (ไปตรวจในขั้นตอนที่ 8 แทน) ***\n"
            u"  3. ตรวจ 3 รายการ (สำหรับใบเสร็จที่ไม่ใช่ค่าน้ำ/ค่าไฟ):\n"
            u"     (I) ชื่อบริษัท: ตรงกับชื่อบริษัทใดก็ได้ใน accepted_companies (ยืดหยุ่น) = ผ่าน\n"
            u"     (II) เลขภาษี: ตรงกับเลขภาษีของบริษัทใดก็ได้ใน accepted_companies = ผ่าน\n"
            u"     (III) ที่อยู่: ตรงกับที่อยู่ (สำนักงานใหญ่/สาขา) ของบริษัทใดก็ได้ใน accepted_companies = ผ่าน\n"
            u"  4. ใบเสร็จค่าน้ำ/ค่าไฟ → ข้ามชื่อ/เลขภาษี/ที่อยู่ลูกค้า ใน company_name_check (ไปตรวจที่อยู่ในขั้นตอนที่ 8)\n"
            u"  5. ใบเสร็จที่ไม่มีข้อมูลลูกค้าเลย → ข้ามได้\n"
            u"  6. ใบฝากเงิน (deposit_slip) → ข้ามได้\n"
            u"  7. ถ้าใบเสร็จทุกใบไม่มีข้อมูลลูกค้า → ผ่าน\n"
            u"  8. pass ถ้าข้อมูลตรงกับบริษัทใดบริษัทหนึ่ง / fail ถ้าไม่ตรงกับบริษัทใดเลย\n"
            u"  *** ห้ามนำใบเสร็จค่าน้ำ/ค่าไฟมาใส่ใน mismatched_files ***\n"
            u"- ถ้าไม่มี accepted_companies → company_name_check.required = false\n\n"

            u"### ขั้นตอนที่ 7: ตรวจสอบเลขที่ใบเสร็จ / วันที่ / ชื่อร้านค้า\n"
            u"- ตรวจเฉพาะไฟล์ที่เป็น **ใบเสร็จ (receipt)** หรือ **ใบกำกับภาษี (invoice)** เท่านั้น\n"
            u"- *** ห้ามตรวจ: บิลเงินสด, ลายมือเขียน, สลิปโอนเงิน, ใบฝากเงิน (deposit_slip) ***\n\n"
            u"- สำหรับใบเสร็จ/ใบกำกับภาษีแต่ละใบ:\n"
            u"  1. อ่านจากรูป: เลขที่ใบเสร็จ, วันที่ในใบเสร็จ, ชื่อผู้ออกใบเสร็จ/ร้านค้า\n"
            u"  2. จับคู่กับ Detail Line โดยใช้ **ยอดเงิน (subtotal)** เป็นตัวจับคู่\n"
            u"  3. เปรียบเทียบ:\n"
            u"     - Invoice Number ใน Detail Line ตรงกับเลขที่ในรูปหรือไม่\n"
            u"     - Invoice Date ใน Detail Line ตรงกับวันที่ในรูปหรือไม่\n"
            u"     - Partner ใน Detail Line ตรงกับชื่อร้านค้า/ผู้ขายในรูปหรือไม่ (ยืดหยุ่น)\n"
            u"  4. ถ้า Detail Line ไม่มีข้อมูล (ค่าว่าง) → ถือว่า User ไม่ได้ลง → ไม่ผ่านรายการนั้น\n"
            u"  5. ถ้าจับคู่ใบเสร็จกับ Detail Line ไม่ได้ → ข้ามใบนั้น\n\n"

            u"### ขั้นตอนที่ 8: (ข้ามได้ - ระบบตรวจที่อยู่สาธารณูปโภคจาก Detail Lines โดยอัตโนมัติ)\n\n"

            u"## รูปแบบ JSON ที่ต้องตอบ:\n"
            u"{\n"
            u'  "status": "pass หรือ fail",\n'
            u'  "receipt_check": {\n'
            u'    "found": true_or_false,\n'
            u'    "clear": true_or_false,\n'
            u'    "total_from_receipt": ผลรวมยอดเงินจากใบเสร็จทั้งหมดเป็นตัวเลข,\n'
            u'    "items_from_receipt": ["รายการที่อ่านได้จากใบเสร็จ"],\n'
            u'    "receipt_files": [\n'
            u'      {"filename": "ชื่อไฟล์จริง", "amount": ยอดเงินที่อ่านจากใบเสร็จ, "fee": ค่าธรรมเนียม, "type": "deposit_slip หรือ receipt หรือ invoice"}\n'
            u'    ],\n'
            u'    "skipped_files": [\n'
            u'      {"filename": "ชื่อไฟล์จริง", "reason": "เหตุผลที่ข้าม", "amount": ยอดสุดท้าย,\n'
            u'       "quantity": จำนวน_ถ้าเป็นบิลเงินสด_ไม่ใช่ใส่0, "unit_price": ราคาต่อหน่วย_ถ้าเป็นบิลเงินสด_ไม่ใช่ใส่0,\n'
            u'       "raw_total": ยอดรวมที่อ่านได้จากช่องรวมเงิน_ก่อน_cross_verify}\n'
            u'    ],\n'
            u'    "message": "คำอธิบายสั้นๆ"\n'
            u'  },\n'
            u'  "description_check": {\n'
            u'    "has_description": true_or_false,\n'
            u'    "matches_detail": true_or_false,\n'
            u'    "amount_matches": true_or_false,\n'
            u'    "message": "คำอธิบาย"\n'
            u'  },\n'
            u'  "amount_check": {\n'
            u'    "receipt_total": ผลรวม_amount_ใบเสร็จทั่วไป_บวก_fee_ใบฝากเงิน_ไม่รวมบิลเงินสด,\n'
            u'    "cash_bill_total": ยอดรวมบิลเงินสดที่ลงทะเบียน_ใส่0ถ้าไม่มีหรือไม่ผ่าน,\n'
            u'    "combined_total": receipt_total_บวก_cash_bill_total,\n'
            u'    "system_total": ยอด_Total_จากข้อมูลระบบ,\n'
            u'    "matches": true_ถ้า_combined_total_ใกล้เคียง_system_total,\n'
            u'    "message": "คำอธิบาย"\n'
            u'  },\n'
            u'  "tax_in_detail_check": {\n'
            u'    "receipt_has_vat": true_or_false,\n'
            u'    "detail_has_tax": true_or_false,\n'
            u'    "vat_exempt_utility": true_ถ้าเป็นสาธารณูปโภคที่ได้รับข้อยกเว้น_VAT_false_ถ้าไม่ใช่,\n'
            u'    "exempt_reason": "ระบุเหตุผล เช่น ใบเสร็จค่าน้ำออกชื่อบุคคล หรือ ที่อยู่ผู้ใช้น้ำไม่ตรงบริษัท (ถ้า vat_exempt_utility=false ใส่ค่าว่าง)",\n'
            u'    "missing_tax_lines": [{"product": "ชื่อสินค้า/บริการ", "subtotal": ยอดเงิน, "receipt_filename": "ชื่อไฟล์ภาพใบเสร็จที่เกี่ยวข้อง"}],\n'
            u'    "message": "คำอธิบาย"\n'
            u'  },\n'
            u'  "cash_bill_check": {\n'
            u'    "required": true_ถ้ามีบิลเงินสดถูก_skip_false_ถ้าไม่มี,\n'
            u'    "skipped_count": จำนวนบิลเงินสดที่ถูก_skip,\n'
            u'    "registered_count": จำนวนรายการที่ผู้ใช้ลงทะเบียน,\n'
            u'    "registered_total": ยอดรวมจากรายการลงทะเบียนทั้งหมด,\n'
            u'    "bill_total": ยอดรวมจากรูปบิลเงินสดทุกใบ,\n'
            u'    "total_amount_matches": true_ถ้ายอดรวมลงทะเบียนสอดคล้องกับยอดรวมบิลเงินสด,\n'
            u'    "description_or_amount_matches": true_ถ้า_description_หรือ_amount_สอดคล้องกัน,\n'
            u'    "pass": true_or_false,\n'
            u'    "message": "คำอธิบาย"\n'
            u'  },\n'
            u'  "company_name_check": {\n'
            u'    "required": true_ถ้ามี_accepted_companies_false_ถ้าไม่มี,\n'
            u'    "expected_name": "ชื่อบริษัทที่ตรงกัน (จาก accepted_companies)",\n'
            u'    "expected_tax_id": "เลขภาษีที่ตรงกัน",\n'
            u'    "expected_address": "ที่อยู่ที่ตรงกัน",\n'
            u'    "found_names": ["ชื่อบริษัทที่พบในใบเสร็จแต่ละใบ (อ่านให้ครบถ้วน)"],\n'
            u'    "found_tax_ids": ["เลขภาษีที่พบในใบเสร็จแต่ละใบ"],\n'
            u'    "found_addresses": ["ที่อยู่ลูกค้าที่พบในใบเสร็จแต่ละใบ"],\n'
            u'    "name_match": true_ถ้าชื่อตรงกับบริษัทใดก็ได้ใน_accepted_companies,\n'
            u'    "tax_id_match": true_ถ้าเลขภาษีตรงกับบริษัทใดก็ได้_หรือไม่มีเลขภาษีลูกค้า,\n'
            u'    "address_match": true_ถ้าที่อยู่ตรงกับบริษัทใดก็ได้_หรือไม่มีที่อยู่ลูกค้า,\n'
            u'    "mismatched_files": [\n'
            u'      {"filename": "ชื่อไฟล์", "issue": "ระบุสิ่งที่ไม่ตรง เช่น ชื่อไม่ตรง/เลขภาษีไม่ตรง/ที่อยู่ไม่ตรง",\n'
            u'       "found_name": "ชื่อที่พบ", "found_tax_id": "เลขภาษีที่พบ", "found_address": "ที่อยู่ที่พบ"}\n'
            u'    ],\n'
            u'    "pass": true_ถ้า_name_match_และ_tax_id_match_และ_address_match_ทั้งหมดเป็น_true,\n'
            u'    "message": "คำอธิบาย"\n'
            u'  },\n'
            u'  "invoice_detail_check": {\n'
            u'    "items": [\n'
            u'      {\n'
            u'        "filename": "ชื่อไฟล์ใบเสร็จ",\n'
            u'        "receipt_invoice_number": "เลขที่ใบเสร็จที่อ่านจากรูป",\n'
            u'        "receipt_date": "วันที่ในใบเสร็จที่อ่านจากรูป",\n'
            u'        "receipt_partner": "ชื่อร้านค้า/ผู้ขายที่อ่านจากรูป",\n'
            u'        "detail_invoice_number": "เลขที่ใน Detail Line",\n'
            u'        "detail_date": "วันที่ใน Detail Line",\n'
            u'        "detail_partner": "ชื่อ Partner ใน Detail Line",\n'
            u'        "invoice_number_match": true_or_false,\n'
            u'        "date_match": true_or_false,\n'
            u'        "partner_match": true_or_false\n'
            u'      }\n'
            u'    ],\n'
            u'    "pass": true_ถ้าทุกรายการตรงกัน_false_ถ้ามีรายการที่ไม่ตรง,\n'
            u'    "message": "คำอธิบาย"\n'
            u'  },\n'
            u'  "_note_utility": "ระบบตรวจที่อยู่สาธารณูปโภคจาก Detail Lines โดยอัตโนมัติ ไม่ต้องส่ง utility_address_check",\n'
            u'  "summary": "สรุปผลการตรวจสอบทั้งหมดอย่างละเอียด"\n'
            u"}\n\n"
            u"หมายเหตุสำคัญ:\n"
            u"1. ทุก field ตัวเลข (amount, fee, receipt_total, system_total) ต้องเป็นตัวเลขจริงที่อ่านได้จากรูป ห้ามใส่ 0 ถ้าอ่านยอดได้\n"
            u"2. summary ต้องมีข้อความสรุปเสมอ ห้ามเป็นค่าว่าง\n"
            u"3. receipt_total: ใบเสร็จทั่วไปใช้ amount + ใบฝากเงินใช้เฉพาะ fee (ห้ามเอายอดฝากมารวม) + ห้ามรวมบิลเงินสด (ระบบรวมให้)\n"
            u"4. status: ถ้ามีบิลเงินสดถูก skip + ผู้ใช้ลงทะเบียนไว้ + ยอดรวมสอดคล้อง + description หรือ amount ตรง → ส่วนบิลเงินสดถือว่าผ่าน\n"
            u"5. cash_bill_check.required = false ถ้าไม่มีบิลเงินสดถูก skip เลย\n"
            u"6. company_name_check.required = false ถ้าไม่มี accepted_companies\n"
            u"7. invoice_detail_check: ตรวจเฉพาะใบเสร็จ/ใบกำกับภาษี (receipt/invoice) ห้ามตรวจบิลเงินสด/สลิป/ใบฝากเงิน\n"
            u"8. สลิปโอนเงิน (ประเภท A): ใส่ skipped_files แต่ต้องอ่านยอดโอนเงินมาใส่ field amount ด้วย (ระบบใช้ตรวจสอบข้อ 9)\n"
            u"9. บิลเงินสด (ประเภท B): อ่าน จำนวน × ราคาต่อหน่วย = ยอดรวม แล้วใส่ field amount ใน skipped_files + bill_total ใน cash_bill_check\n"
            u"10. ใบรับรองแทนใบเสร็จ (ประเภท F): ใส่ skipped_files พร้อม amount + is_receipt_substitute=true\n"
            u"    *** ห้ามนับใน skipped_count ของ cash_bill_check (ระบบจัดการแยก) ***\n"
            u"    *** reason ต้องไม่มีคำว่า 'บิลเงินสด' หรือ 'ลายมือเขียน' ***\n"
        )

        # Append itemized file instruction at the very end (highest priority position)
        if itemized_files:
            prompt += u"\n## *** สำคัญสุด: อ่านแยกทุก line item ***\n"
            prompt += u"เฉพาะไฟล์: %s\n" % ', '.join(itemized_files)
            prompt += u"ใบเสร็จที่มีมากกว่า 1 รายการ → สร้าง receipt_files แยกทุกรายการ filename='ชื่อไฟล์ (รายการN)' amount=ยอดของรายการนั้น\n"
            prompt += u"ใบเสร็จที่มีแค่ 1 รายการ → อ่านยอดรวมตามปกติ\n"

        return prompt

    def _repair_truncated_json(self, text):
        """Attempt to repair truncated JSON by closing open brackets/braces."""
        # Track open brackets and braces
        stack = []
        in_string = False
        escape_next = False

        for ch in text:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()

        # If we're in the middle of a string, close it
        if in_string:
            text += '"'

        # Remove trailing incomplete key-value (e.g., `"type": "` becomes nothing useful)
        # Try to find a clean cut point - last complete value
        text = text.rstrip()
        # Remove trailing colon or comma with incomplete value
        text = re.sub(r',?\s*"[^"]*":\s*"?[^"{}[\]]*$', '', text)

        # Close remaining open brackets/braces in reverse order
        for bracket in reversed(stack):
            if bracket == '{':
                text += '}'
            elif bracket == '[':
                text += ']'

        return text

    def _call_gemini_api(self, prompt, image_attachments, system_prompt=None):
        """Call Gemini API with images, prompt, and system prompt."""
        api_key = self._get_gemini_api_key()

        # Build parts array with images for Gemini format
        parts = []

        for idx, att in enumerate(image_attachments, 1):
            if att.datas:
                mime_type = att.mimetype or 'image/jpeg'
                image_data = att.datas.decode('utf-8') if isinstance(att.datas, bytes) else att.datas

                # Add filename label before each image
                parts.append({
                    "text": "[รูปที่ %d] ชื่อไฟล์: %s" % (idx, att.name or 'unknown'),
                })
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_data,
                    }
                })

        # Add text prompt
        parts.append({
            "text": prompt,
        })

        # Build Gemini payload
        payload = {
            "contents": [
                {
                    "parts": parts,
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 65536,
                "responseMimeType": "application/json",
                "thinkingConfig": {
                    "thinkingBudget": 24576,
                },
            },
        }

        # Add system instruction for consistent behavior
        if system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": system_prompt}]
            }

        headers = {
            "content-type": "application/json",
        }

        # Gemini uses API key as URL parameter
        url = "%s?key=%s" % (GEMINI_API_URL, api_key)

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            result = response.json()

            _logger.info("=== Gemini RAW response keys: %s", list(result.keys()))

            # Parse Gemini response format
            candidates = result.get('candidates', [])
            if candidates:
                finish_reason = candidates[0].get('finishReason', 'UNKNOWN')
                content = candidates[0].get('content', {})
                parts = content.get('parts', [])
                _logger.info("=== Gemini parts count: %d, finishReason: %s", len(parts), finish_reason)
                if parts:
                    text_result = parts[0].get('text', '')
                    _logger.info("=== Gemini text type: %s, length: %d, first 300 chars: %s",
                                 type(text_result).__name__, len(text_result), repr(text_result[:300]))

                    # If response was truncated (MAX_TOKENS), try to fix incomplete JSON
                    if finish_reason == 'MAX_TOKENS' and text_result:
                        _logger.warning("=== Gemini response TRUNCATED (MAX_TOKENS)! Attempting JSON repair...")
                        text_result = self._repair_truncated_json(text_result)

                    return text_result

            _logger.warning("=== Gemini no candidates found. Full response: %s", json.dumps(result, ensure_ascii=False)[:500])
            return json.dumps({
                "status": "fail",
                "summary": "ไม่สามารถรับผลลัพธ์จาก AI ได้"
            })

        except requests.exceptions.Timeout:
            raise UserError(_("Gemini API request timed out. Please try again."))
        except requests.exceptions.ConnectionError:
            raise UserError(_("Cannot connect to Gemini API. Please check your internet connection."))
        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            try:
                error_detail = e.response.json()
                error_msg = error_detail.get('error', {}).get('message', str(e))
            except Exception:
                pass
            raise UserError(_("Gemini API Error: %s") % error_msg)
        except Exception as e:
            raise UserError(_("Unexpected error calling Gemini API: %s") % str(e))

    def _parse_ai_response(self, response_text):
        """Parse JSON from Gemini AI response."""
        try:
            # If response is already a dict (e.g., Gemini JSON mode), return directly
            if isinstance(response_text, dict):
                _logger.info("=== AI response is already a dict, returning directly")
                return response_text

            text = response_text.strip()
            _logger.info("=== Parsing AI response, length=%d, first 200 chars: %s", len(text), repr(text[:200]))

            # Method 1: Try direct JSON parse first (for responseMimeType=application/json)
            try:
                result = json.loads(text)
                _logger.info("=== Direct JSON parse succeeded")
                return result
            except json.JSONDecodeError:
                pass

            # Method 2: Extract JSON from ```json ... ``` code block using regex
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1).strip()
                result = json.loads(text)
                _logger.info("=== Parsed from ```json block")
                return result

            # Method 3: Extract from ``` ... ``` code block
            code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if code_match:
                text = code_match.group(1).strip()
                result = json.loads(text)
                _logger.info("=== Parsed from ``` block")
                return result

            # Method 4: Find first { and last } to extract JSON object
            first_brace = text.find('{')
            last_brace = text.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                text = text[first_brace:last_brace + 1]
                result = json.loads(text)
                _logger.info("=== Parsed from brace extraction")
                return result

            raise ValueError("No JSON object found in response")

        except (json.JSONDecodeError, IndexError, ValueError) as e:
            _logger.warning("Failed to parse AI response: %s\nResponse type: %s\nResponse: %s",
                            str(e), type(response_text).__name__,
                            str(response_text)[:500] if response_text else "EMPTY")
            return {
                "status": "fail",
                "summary": str(response_text)[:300] if response_text else "ไม่ได้รับผลลัพธ์",
                "receipt_check": {"message": "ไม่สามารถแปลผลลัพธ์จาก AI ได้"},
                "description_check": {"message": ""},
                "amount_check": {"message": ""},
                "tax_in_detail_check": {"message": ""},
            }

    def _check_analytic_account(self):
        """Check that all detail lines have Analytic Account filled.
        Returns (pass, missing_lines) - checked in Python, not by AI."""
        self.ensure_one()
        missing = []
        for line in self.clear_ids:
            if not line.account_analytic_id:
                desc = line.name or line.product_id.name or 'N/A'
                missing.append(desc)
        return (len(missing) == 0, missing)

    def _get_expected_company_info(self):
        """Get the expected company info based on the current database name.
        Returns (company_info_dict, db_name) or (None, db_name) if DB not in mapping.
        company_info_dict includes 'accepted_companies' listing all group companies."""
        db_name = self.env.cr.dbname
        company_info = DB_COMPANY_NAME_MAP.get(db_name, None)
        if company_info:
            # Build accepted_companies list from ALL companies in the group
            accepted = []
            for _key, info in DB_COMPANY_NAME_MAP.items():
                acc_entry = {
                    'name': info.get('name', ''),
                    'tax_id': info.get('tax_id', ''),
                    'address': info.get('address', ''),
                }
                if info.get('branch_addresses'):
                    acc_entry['branch_addresses'] = info['branch_addresses']
                accepted.append(acc_entry)
            company_info = dict(company_info)  # copy to avoid mutating original
            company_info['accepted_companies'] = accepted
        return company_info, db_name

    def _check_utility_analytic_partner(self):
        """Check utility lines: Analytic Account keyword must match Partner name.
        ปิดการตรวจสอบไว้ — ค่าน้ำ/ค่าไฟข้ามการตรวจชื่อบริษัทใน AI อยู่แล้ว (ข้อ 6.1)
        """
        return True, []

    def _get_cash_bill_cross_verify_details(self, result):
        """อ่านข้อมูล quantity, unit_price, raw_total จาก skipped_files ที่เป็นบิลเงินสด
        แล้วคำนวณ cross-verify (quantity × unit_price) เพื่อหายอดที่ถูกต้อง
        Returns: list of dicts [{filename, quantity, unit_price, raw_total, calculated, final_amount}, ...]
        """
        def _sf(val):
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val.replace(',', ''))
                except (ValueError, TypeError):
                    return 0.0
            return 0.0

        details = []
        rc = result.get('receipt_check', {})
        skipped = [f for f in rc.get('skipped_files', []) if isinstance(f, dict)]
        for f in skipped:
            reason = (f.get('reason') or '').lower()
            # เฉพาะบิลเงินสด/ลายมือเขียน
            if not ('บิลเงินสด' in reason or 'ลายมือ' in reason or 'เขียนมือ' in reason
                    or 'cash' in reason or 'handwritten' in reason):
                continue
            qty = _sf(f.get('quantity', 0))
            price = _sf(f.get('unit_price', 0))
            raw = _sf(f.get('raw_total', 0))
            ai_amount = _sf(f.get('amount', 0))
            # Cross-verify: ถ้ามี qty และ price → คำนวณ
            calculated = qty * price if qty > 0 and price > 0 else 0
            # กำหนดยอดสุดท้าย
            if calculated > 0:
                # ใช้ค่าคำนวณเสมอถ้ามี qty × price (ไว้ใจการคำนวณมากกว่า AI อ่านลายมือ)
                final = calculated
            elif ai_amount > 0:
                final = ai_amount
            elif raw > 0:
                final = raw
            else:
                final = 0
            details.append({
                'filename': f.get('filename', '?'),
                'quantity': qty,
                'unit_price': price,
                'raw_total': raw,
                'calculated': calculated,
                'final_amount': final,
            })
        return details

    def _cross_verify_cash_bill_total(self, result):
        """คำนวณยอดรวมบิลเงินสดทั้งหมดจาก cross-verify (quantity × unit_price)
        ถ้า AI อ่านยอดผิด จะถูกแก้ไขด้วยการคำนวณ
        Returns: float (ยอดรวมที่ cross-verify แล้ว, 0 ถ้าไม่มีบิลเงินสด)
        """
        details = self._get_cash_bill_cross_verify_details(result)
        if not details:
            return 0.0
        return sum(d['final_amount'] for d in details)

    def _python_sum_receipt_total(self, result):
        u"""รวมยอด receipt_files แบบ Python (deposit_slip ใช้ fee, ที่เหลือใช้ amount).
        เชื่อถือได้กว่า AI's receipt_total ซึ่งอาจรวมเลขผิดเวลามีใบเสร็จหลายใบ.
        ใช้ร่วมกันใน _format_result_html และ action_ai_verify เพื่อกัน divergence
        ระหว่าง icon ของ Section 2 (display) กับการตัดสิน is_pass/overall_pass.
        """
        files = result.get('receipt_check', {}).get('receipt_files', []) or []
        total = 0.0
        for f in files:
            if not isinstance(f, dict):
                continue
            if (f.get('type') or '') == 'deposit_slip':
                v = f.get('fee', 0)
            else:
                v = f.get('amount', 0)
            if isinstance(v, (int, float)):
                total += v
        return round(total, 2)

    def _check_cash_bill_match_detail(self, tolerance=1.0):
        u"""ตรวจบิลเงินสด (เงื่อนไขใหม่):
        จับคู่ amount ของ cash_bill_ids แต่ละรายการ กับ price_unit ใน clear_ids
        ถ้าทุกรายการ register มี detail line ที่ยอดตรงกัน → ผ่าน
        Returns: {pass, matched, unmatched, message, detail_unused}
        """
        if not self.cash_bill_ids:
            return {
                'pass': True,
                'matched': [],
                'unmatched': [],
                'detail_unused': [],
                'message': u'ไม่มีรายการบิลเงินสดที่ลงทะเบียน',
            }
        # รายการรายละเอียด (clear_ids) ที่ยังว่าง — เก็บ id+price+ชื่อสินค้า
        detail_pool = []
        for line in self.clear_ids:
            price = line.price_unit or 0
            if price > 0:
                pname = (line.product_id.display_name if line.product_id else '') or line.name or ''
                detail_pool.append({'id': line.id, 'price': price, 'product': pname})
        matched = []
        unmatched = []
        used_ids = set()
        for cb in self.cash_bill_ids:
            amt = cb.amount or 0
            if amt <= 0:
                continue
            found = None
            for d in detail_pool:
                if d['id'] in used_ids:
                    continue
                if abs(amt - d['price']) < tolerance:
                    used_ids.add(d['id'])
                    found = d
                    break
            if found:
                matched.append({'cash_bill': cb, 'matched_detail': found})
            else:
                unmatched.append(cb)
        detail_unused = [d for d in detail_pool if d['id'] not in used_ids]
        return {
            'pass': len(unmatched) == 0 and bool(matched),
            'matched': matched,
            'unmatched': unmatched,
            'detail_unused': detail_unused,
            'message': u'ทุกรายการบิลเงินสดที่ลงทะเบียน ตรงกับยอดในรายละเอียด' if not unmatched
                      else u'มีรายการบิลเงินสดที่ลงทะเบียนแต่ไม่ตรงกับยอดในรายละเอียด',
        }

    def _cash_bill_pass(self, result):
        u"""ตัดสินว่าข้อ 5 (บิลเงินสด) ผ่านสำหรับการอนุมัติหรือไม่ — ใช้ร่วมกันทุก path
        เพื่อไม่ให้ popup / รายงานเต็ม / is_pass คำนวณคนละแบบ:
          - AI ไม่พบบิลเงินสด (required=False) → ผ่าน
          - AI พบบิลเงินสด แต่ผู้ใช้ยังไม่ได้ลงทะเบียนเลย → ไม่ผ่าน (ต้องลงทะเบียน)
          - ลงทะเบียนแล้ว → ทุกรายการต้องจับคู่กับยอดใน Detail Lines ได้
        """
        cbc = result.get('cash_bill_check', {}) or {}
        if not cbc.get('required', False):
            return True
        if not self.cash_bill_ids:
            return False
        return self._check_cash_bill_match_detail()['pass']

    def _resolve_receipt_substitutes(self, result, py_receipt_total, py_system_total, tolerance=1.0):
        u"""ตัดสินว่าใบรับรองแทนใบเสร็จ (is_receipt_substitute=true ใน skipped_files)
        ควรนับยอดเข้า combined_total หรือไม่ โดยเปรียบเทียบยอดรวม:
        - ใบเสร็จตรงระบบอยู่แล้ว → ใบรับรองฯ = cover (ไม่นับ)
        - ใบเสร็จ + ใบรับรองฯ ตรงระบบ → ใบรับรองฯ = ใบทดแทน (นับเข้า)
        - ไม่ตรงทั้ง 2 → ambiguous (ไม่นับ + flag warning)
        Returns dict: {substitutes, sub_total, amount_to_count, decision, message}
        """
        rc = result.get('receipt_check', {}) or {}
        skipped = rc.get('skipped_files', []) or []
        substitutes = []
        sub_total = 0.0
        for f in skipped:
            if isinstance(f, dict) and f.get('is_receipt_substitute'):
                amt = f.get('amount', 0)
                if isinstance(amt, (int, float)) and amt > 0:
                    substitutes.append(f)
                    sub_total += amt
        if not substitutes:
            return {
                'substitutes': [],
                'sub_total': 0.0,
                'amount_to_count': 0.0,
                'decision': 'no_substitutes',
                'message': '',
            }
        sub_total = round(sub_total, 2)
        py_receipt_total = py_receipt_total or 0
        py_system_total = py_system_total or 0
        if py_system_total <= 0:
            return {
                'substitutes': substitutes,
                'sub_total': sub_total,
                'amount_to_count': 0.0,
                'decision': 'ambiguous',
                'message': u'ไม่สามารถตัดสินใบรับรองแทนใบเสร็จ เนื่องจากไม่มียอดในระบบให้เปรียบเทียบ',
            }
        diff_without = abs(py_receipt_total - py_system_total)
        diff_with = abs(py_receipt_total + sub_total - py_system_total)
        if diff_without <= tolerance:
            return {
                'substitutes': substitutes,
                'sub_total': sub_total,
                'amount_to_count': 0.0,
                'decision': 'cover_skip',
                'message': u'ใบรับรองแทนใบเสร็จ = เอกสารคลุมยอด (ใบเสร็จตรงกับระบบอยู่แล้ว ไม่นับเพิ่ม)',
            }
        if diff_with <= tolerance:
            return {
                'substitutes': substitutes,
                'sub_total': sub_total,
                'amount_to_count': sub_total,
                'decision': 'count_substitute',
                'message': u'ใบรับรองแทนใบเสร็จ = ใบทดแทน (รวมยอดเข้า combined_total อัตโนมัติ)',
            }
        return {
            'substitutes': substitutes,
            'sub_total': sub_total,
            'amount_to_count': 0.0,
            'decision': 'ambiguous',
            'message': (u'ใบรับรองแทนใบเสร็จ ไม่สามารถตัดสินอัตโนมัติได้ '
                        u'(ใบเสร็จ %.2f, +ใบรับรองฯ %.2f, ระบบ %.2f)'
                        % (py_receipt_total, py_receipt_total + sub_total, py_system_total)),
        }

    def _format_result_html(self, result, analytic_pass=True, analytic_missing=None,
                            expected_company_info=None, condition_map=None,
                            correction_map=None):
        """Format AI verification result as HTML for display in wizard.

        condition_map: dict {filename: {check_amount, check_vat, check_company, check_invoice_detail}}
        If a condition is False for a file, that check is skipped for that file.
        """
        if analytic_missing is None:
            analytic_missing = []
        if condition_map is None:
            condition_map = {}

        # Build skip-sets from condition_map (files that should skip each check)
        skip_amount_files = set()
        skip_vat_files = set()
        skip_company_files = set()
        skip_invoice_files = set()
        skip_slip_check = False
        skip_slip_note = ''
        for fname, conds in condition_map.items():
            if not conds.get('check_amount', True):
                skip_amount_files.add(fname)
            if not conds.get('check_vat', True):
                skip_vat_files.add(fname)
            if not conds.get('check_company', True):
                skip_company_files.add(fname)
            if not conds.get('check_invoice_detail', True):
                skip_invoice_files.add(fname)
            if not conds.get('check_slip', True):
                skip_slip_check = True
                if conds.get('skip_note', ''):
                    skip_slip_note = conds.get('skip_note', '')

        # Auto-skip VAT for NPD_Logistics_New database
        _is_logistics_db = (self.env.cr.dbname == 'NPD_Logistics_New')

        # Determine overall status considering AI result, analytic check, cash bill check, and company name check
        ai_status = result.get('status', 'fail')
        cbc = result.get('cash_bill_check', {})

        # Company name check
        cnc = result.get('company_name_check', {})
        company_name_ok = (not cnc.get('required', False)) or cnc.get('pass', False)

        # Python cross-verify: คำนวณยอดบิลเงินสดจาก qty × unit_price แทน AI อ่าน
        py_cash_bill_total = self._cross_verify_cash_bill_total(result)

        # ถ้า Python cross-verify ได้ยอดที่ตรงกับ registered_total → override cash_bill_ok
        cbc_reg_total = cbc.get('registered_total', 0)
        cbc_reg_total = cbc_reg_total if isinstance(cbc_reg_total, (int, float)) else 0
        py_cv_total_match = (py_cash_bill_total > 0 and cbc_reg_total > 0
                             and abs(py_cash_bill_total - cbc_reg_total) < 1.0)
        cbc_ai_pass = cbc.get('pass', False)
        # ─── OLD LOGIC (เก็บไว้ก่อนตามคำสั่ง) ──────────────────────────────
        # cash_bill_ok: AI pass หรือ Python cross-verify ยอดตรง (+ มี description ตรง)
        # cash_bill_ok = (not cbc.get('required', False)) or cbc_ai_pass or (
        #     py_cv_total_match and cbc.get('description_or_amount_matches', False)
        # )
        # ─── NEW LOGIC: เทียบยอด cash_bill_ids กับ price_unit ใน clear_ids ──
        cb_match_result = self._check_cash_bill_match_detail()
        cash_bill_ok = self._cash_bill_pass(result)

        # Re-evaluate amount check: if cash bill passed, add registered_total to receipt_total
        ac_data = result.get('amount_check', {})
        # ใช้ Python sum (เชื่อถือได้กว่า AI's receipt_total ที่อาจสรุปเลขผิดเวลามีหลายใบ)
        # — สอดคล้องกับ display r_total ใน Section 2 (fallback AI ถ้า Python sum = 0)
        py_receipt_total = self._python_sum_receipt_total(result)
        if py_receipt_total == 0:
            _ai_rt = ac_data.get('receipt_total', 0)
            py_receipt_total = _ai_rt if isinstance(_ai_rt, (int, float)) else 0
        py_system_total = ac_data.get('system_total', 0)
        py_system_total = py_system_total if isinstance(py_system_total, (int, float)) else 0
        # WHT adjustment: if WHT > 0, use Untaxed + Tax instead of Total
        _wht = self.wht_amount or 0
        if _wht > 0:
            _untaxed = self.untaxed_amount or 0
            _tax = self.tax_amount or 0
            if _untaxed > 0:
                py_system_total = _untaxed + _tax
        py_cb_total = 0
        # ใช้ logic ใหม่ (cash_bill_ok) แทน AI's pass/cross-verify
        if cbc.get('required', False) and cash_bill_ok:
            # ถ้า new check ผ่าน ใช้ผลรวม cash_bill_ids ที่ user ลงทะเบียน
            py_cb_total = sum((cb.amount or 0) + (cb.vat_amount or 0) for cb in self.cash_bill_ids)
            if not py_cb_total:
                py_cb_total = cbc_reg_total
        # ใบรับรองแทนใบเสร็จ — ตัดสินอัตโนมัติว่านับเข้า combined ไหม
        sub_resolution = self._resolve_receipt_substitutes(result, py_receipt_total, py_system_total)
        py_sub_total = sub_resolution['amount_to_count']
        py_combined = py_receipt_total + py_cb_total + py_sub_total
        py_amount_ok = abs(py_combined - py_system_total) < 1.0 if py_system_total > 0 else ac_data.get('matches', False)

        # Override AI status: if amount didn't match but now matches with cash bill total → pass
        rc_data = result.get('receipt_check', {})
        dc_data = result.get('description_check', {})
        tc_data = result.get('tax_in_detail_check', {})
        rc_ok = rc_data.get('found', False) and rc_data.get('clear', False)
        dc_ok = dc_data.get('matches_detail', False) or not dc_data.get('has_description', False)
        # Utility address check (Python: Analytic Account vs Partner from Detail Lines)
        uac_ok, uac_items = self._check_utility_analytic_partner()

        # Python fallback for VAT exemption
        ai_vat_exempt = tc_data.get('vat_exempt_utility', False)
        # Check if ALL receipt_files are deposit_slip → exempt from VAT
        rc_files = [f for f in result.get('receipt_check', {}).get('receipt_files', []) if isinstance(f, dict)]
        py_all_deposit = len(rc_files) > 0 and all(
            'deposit' in (f.get('type') or '').lower() for f in rc_files
        )
        vat_exempt_final = ai_vat_exempt or py_all_deposit
        tc_ok = tc_data.get('detail_has_tax', False) or not tc_data.get('receipt_has_vat', False) or vat_exempt_final

        # Invoice detail check (invoice number / date / partner)
        idc_data = result.get('invoice_detail_check', {})
        idc_ok = idc_data.get('pass', True)  # default True if AI didn't return this field
        uac_required = len(uac_items) > 0

        # Transfer slip check (clear_amount vs any receipt file amount)
        clear_amt = self.clear_amount or 0
        slip_check_required = clear_amt > 0
        slip_check_ok = True
        slip_matched_file = None
        slip_all_files = []
        slip_debug_info = []
        def _safe_float(val):
            """Convert string/int/float to float safely"""
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val.replace(',', ''))
                except (ValueError, TypeError):
                    return 0.0
            return 0.0
        if slip_check_required:
            from itertools import combinations
            # Collect ALL files from both receipt_files and skipped_files
            rc_data = result.get('receipt_check', {})
            slip_all_files = [f for f in rc_data.get('receipt_files', []) if isinstance(f, dict)]
            slip_skipped = [f for f in rc_data.get('skipped_files', []) if isinstance(f, dict)]
            slip_check_ok = False
            slip_matched_files = []
            slip_total = 0.0

            # Collect ALL candidate files with amounts
            slip_candidates = []
            for slip in slip_skipped:
                slip_amt = _safe_float(slip.get('amount', 0))
                s_type = (slip.get('type') or '').lower()
                slip_debug_info.append({'file': slip.get('filename', '?'), 'type': s_type, 'amount': slip_amt, 'fee': 0, 'source': 'skipped_files'})
                if slip_amt > 0:
                    slip_candidates.append((slip, slip_amt))
            for slip in slip_all_files:
                s_type = (slip.get('type') or '').lower()
                if 'deposit' in s_type or 'slip' in s_type or 'transfer' in s_type:
                    slip_amt = _safe_float(slip.get('amount', 0))
                    slip_debug_info.append({'file': slip.get('filename', '?'), 'type': s_type, 'amount': slip_amt, 'fee': 0, 'source': 'receipt_files'})
                    if slip_amt > 0:
                        slip_candidates.append((slip, slip_amt))

            # Try all subsets to find combination that sums to Clear Amount (±1 baht)
            for r in range(1, len(slip_candidates) + 1):
                if slip_check_ok:
                    break
                for combo in combinations(slip_candidates, r):
                    combo_total = sum(amt for _, amt in combo)
                    if abs(combo_total - clear_amt) < 1.0:
                        slip_matched_files = [f for f, _ in combo]
                        slip_total = combo_total
                        slip_check_ok = True
                        slip_matched_file = slip_matched_files[0] if len(slip_matched_files) == 1 else None
                        break

        # ── Apply receipt condition overrides (skip checks for unchecked files) ──
        # Get all receipt filenames from AI result for condition matching
        _all_receipt_fnames = set(
            f.get('filename', '') for f in rc_files if isinstance(f, dict) and f.get('filename')
        )

        def _any_receipt_matches_skip(skip_set):
            """Check if any receipt filename matches a skip filename.
            AI filenames may have suffixes like '(ซ้าย)', '(ขวา)', '(ล่าง)' etc.
            Condition map uses original filenames without suffixes.
            """
            for rf in _all_receipt_fnames:
                for sf in skip_set:
                    if rf == sf or rf.startswith(sf.rsplit('.', 1)[0]):
                        return True
            return False

        # ข้อ 2: Amount Check — if any receipt file has check_amount=False → force pass
        if skip_amount_files and _any_receipt_matches_skip(skip_amount_files):
            py_amount_ok = True

        # ข้อ 3: VAT Check — if any receipt file with VAT has check_vat=False → force pass
        if skip_vat_files and _any_receipt_matches_skip(skip_vat_files):
            tc_ok = True
        # Auto-skip VAT for NPD_Logistics_New
        if _is_logistics_db:
            tc_ok = True

        # ข้อ 6: Company Name Check — filter mismatched_files excluding unchecked files
        if skip_company_files:
            cnc_mismatched = cnc.get('mismatched_files', [])
            cnc_filtered = [mf for mf in cnc_mismatched
                            if isinstance(mf, dict) and mf.get('filename', '') not in skip_company_files]
            if not cnc_filtered and cnc_mismatched:
                # All mismatched files were skipped → force pass
                company_name_ok = True

        # ข้อ 7: Invoice Detail Check — filter items excluding unchecked files
        # Use base-name matching: AI may split "X.jpg" into "X.jpg (บนซ้าย)", "(ขวา)" etc.
        def _filename_in_skip_set(fname, skip_set):
            if not fname or not skip_set:
                return False
            if fname in skip_set:
                return True
            for sf in skip_set:
                sf_base = sf.rsplit('.', 1)[0]
                if sf_base and fname.startswith(sf_base):
                    return True
            return False
        if skip_invoice_files:
            idc_items_raw = idc_data.get('items', [])
            idc_checked_items = [it for it in idc_items_raw
                                 if isinstance(it, dict) and not _filename_in_skip_set(it.get('filename', ''), skip_invoice_files)]
            # Re-evaluate: only checked files determine pass/fail
            if idc_checked_items:
                idc_ok = all(
                    it.get('invoice_number_match', False) and it.get('date_match', False) and it.get('partner_match', False)
                    for it in idc_checked_items
                )
            else:
                idc_ok = True  # all files skipped → pass

        # overall_pass is calculated after rc_pass is determined (below)
        # Header placeholder — will be prepended after overall_pass is known
        html = ''

        # 1. Receipt Check
        rc = result.get('receipt_check', {})
        # Filter out empty/invalid receipt files (no filename or no amount)
        receipt_files = [f for f in rc.get('receipt_files', [])
                         if isinstance(f, dict) and f.get('filename')]
        skipped_files = [f for f in rc.get('skipped_files', [])
                         if isinstance(f, dict) and f.get('filename')]

        # Check if any skipped files are handwritten/unclear (need warning)
        has_handwritten = False
        has_unclear = False
        for f in skipped_files:
            if isinstance(f, dict):
                # Receipt substitute certs are handled separately — never count as handwritten cash bill
                if f.get('is_receipt_substitute'):
                    continue
                reason = f.get('reason', '').lower()
                if 'ลายมือ' in reason or 'เขียนมือ' in reason or 'บิลเงินสด' in reason or 'handwritten' in reason or 'cash' in reason.lower():
                    has_handwritten = True
                if 'ไม่ชัด' in reason or 'อ่านไม่ออก' in reason or 'เบลอ' in reason or 'unclear' in reason:
                    # Safeguard: don't flag กรมสรรพากร/government receipts as unclear
                    fn_lower = (f.get('filename', '') or '').lower()
                    reason_combined = reason + ' ' + fn_lower
                    is_govt = any(kw in reason_combined for kw in [
                        'สรรพากร', 'ภ.ง.ด', 'ภ.พ.', 'กระทรวง', 'ราชการ',
                    ])
                    if not is_govt:
                        has_unclear = True

        # If cash bill check passed, handwritten bills are OK (user registered them)
        # ใช้ cash_bill_ok (logic ใหม่ = เทียบ register กับ price_unit) แทน AI's pass
        cash_bill_check_passed = cash_bill_ok if cbc.get('required', False) else False

        # Case: ALL files are handwritten/cash bills AND cash bill check passed
        all_are_handwritten = has_handwritten and not receipt_files and skipped_files
        # Python flags (has_handwritten/has_unclear) cover all the bad cases — AI's
        # `clear` field is dropped because it can be falsely False when substitute certs
        # or slips are present (those are categorized properly via skipped_files reasons).
        # If a printed receipt is genuinely unclear, AI must include 'ไม่ชัด' in its reason
        # (caught by has_unclear).
        # ใบรับรองแทนใบเสร็จ (is_receipt_substitute) ที่ระบบตัดสินแล้วว่าคลุมยอด
        # (count_substitute/cover_skip) ถือเป็นเอกสารประกอบที่ใช้ได้ เทียบเท่าใบเสร็จ
        # แม้ผู้ใช้จะอัปโหลดมาแค่ใบสำคัญรับเงิน ไม่มีใบเสร็จรับเงิน/ใบกำกับภาษี
        has_valid_substitute = sub_resolution.get('decision') in ('count_substitute', 'cover_skip')
        has_any_receipt = bool(receipt_files) or rc.get('found', False) or has_valid_substitute
        if all_are_handwritten and cash_bill_check_passed:
            # No printed receipts at all, only cash bills → pass if cash bill verified
            rc_pass = not has_unclear
        elif has_handwritten and cash_bill_check_passed:
            # Mix of printed receipts and handwritten → check printed ones
            rc_pass = has_any_receipt and not has_unclear
        else:
            rc_pass = has_any_receipt and not has_handwritten and not has_unclear
        # Override slip check if user skipped it via condition
        if skip_slip_check:
            slip_check_ok = True
        # Now calculate overall_pass (after rc_pass is determined)
        overall_pass = py_amount_ok and rc_pass and tc_ok and analytic_pass and cash_bill_ok and company_name_ok and idc_ok and uac_ok and slip_check_ok
        status_color = '#28a745' if overall_pass else '#dc3545'
        status_text = 'ผ่าน' if overall_pass else 'ไม่ผ่าน'

        # Prepend header now that we know overall_pass
        header_html = '<div style="font-family: Segoe UI, sans-serif; padding: 10px;">'
        header_html += '<h2 style="text-align:center; color: %s; border-bottom: 2px solid %s; padding-bottom: 8px;">' % (status_color, status_color)
        header_html += 'ผลการตรวจสอบด้วย AI: %s</h2>' % status_text
        html = header_html + html

        rc_icon = '<span style="color: #28a745;">&#10004;</span>' if rc_pass else '<span style="color: #dc3545;">&#10008;</span>'
        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        html += '<h3>%s 1. ตรวจสอบใบเสร็จ</h3>' % rc_icon
        html += '<p>%s</p>' % rc.get('message', '-')

        # Show warning banner for handwritten — but only if cash bill check did NOT pass
        if has_handwritten and not cash_bill_check_passed:
            html += '<div style="margin: 8px 0; padding: 10px; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">'
            html += '<strong>&#9888; พบบิลเงินสด/ลายมือเขียน — ไม่ผ่านการตรวจสอบ</strong><br/>'
            html += 'กรุณาลงทะเบียนรายการบิลเงินสด (ปุ่ม "เพิ่มรายการบิลเงินสด") หรือขอใบเสร็จตัวจริงที่พิมพ์จากระบบ'
            html += '</div>'
        elif has_handwritten and cash_bill_check_passed:
            html += '<div style="margin: 8px 0; padding: 10px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; color: #155724;">'
            html += '<strong>&#10004; พบบิลเงินสด/ลายมือเขียน — ผ่านการตรวจสอบ</strong><br/>'
            html += 'ผู้ใช้ได้ลงทะเบียนรายการบิลเงินสดไว้แล้ว และข้อมูลตรงกัน'
            html += '</div>'
        if has_unclear:
            html += '<div style="margin: 8px 0; padding: 10px; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; color: #721c24;">'
            html += '<strong>&#9888; พบใบเสร็จไม่ชัดเจน — ไม่ผ่านการตรวจสอบ</strong><br/>'
            html += 'กรุณาสแกนหรือถ่ายภาพใบเสร็จใหม่ให้ชัดเจน แล้วอัปโหลดเข้ามาใหม่ (Reset To Draft > อัปโหลดรูปใหม่ > ตรวจสอบด้วย AI อีกครั้ง)'
            html += '</div>'

        # Show receipt files with amounts and fees (only readable printed receipts)
        type_labels = {
            'deposit_slip': 'ใบฝากเงิน',
            'receipt': 'ใบเสร็จ',
            'invoice': 'ใบกำกับภาษี',
        }
        # Build correction map if not provided
        if correction_map is None:
            correction_map = {}
        if receipt_files:
            html += '<p><strong>ไฟล์ที่เป็นใบเสร็จ (%d รายการ):</strong></p><ul>' % len(receipt_files)
            for f in receipt_files:
                if isinstance(f, dict):
                    fname = f.get('filename', '')
                    amt = f.get('amount', 0)
                    fee = f.get('fee', 0)
                    ftype = f.get('type', 'receipt')
                    type_label = type_labels.get(ftype, ftype)

                    # Check if this receipt has a user correction
                    is_corrected = fname in correction_map
                    display_amt = correction_map[fname] if is_corrected else amt
                    amt_str = '{:,.2f}'.format(display_amt) if isinstance(display_amt, (int, float)) else str(display_amt)

                    if ftype == 'deposit_slip':
                        fee_str = '{:,.2f}'.format(fee) if isinstance(fee, (int, float)) and fee > 0 else '0.00'
                        line_html = '<li>%s — ยอดฝาก %s บาท | ค่าธรรมเนียม <strong>%s บาท</strong>' % (fname, amt_str, fee_str)
                    else:
                        # Check amount=0 (AI can't read)
                        orig_amt = amt if not is_corrected else 0
                        if isinstance(orig_amt, (int, float)) and orig_amt == 0 and not is_corrected:
                            # Show red warning for amount=0
                            line_html = (
                                '<li style="color: #dc3545;">&#9888; %s — '
                                '<strong>ยอด 0.00 บาท</strong> '
                                '<em>(AI อ่านยอดไม่ได้ กรุณากดปุ่ม "แก้ไขยอดใบเสร็จ")</em>'
                            ) % fname
                        elif is_corrected:
                            # Show corrected amount with note
                            line_html = (
                                '<li>%s — <strong>ยอด %s บาท</strong> '
                                '<em style="color: #17a2b8;">(แก้ไขโดยผู้ใช้)</em>'
                            ) % (fname, amt_str)
                        else:
                            line_html = '<li>%s — <strong>ยอด %s บาท</strong>' % (fname, amt_str)
                        if fee and isinstance(fee, (int, float)) and fee > 0:
                            line_html += ' | ค่าธรรมเนียม <strong>%s บาท</strong>' % '{:,.2f}'.format(fee)
                    line_html += ' <em style="color: #6c757d;">(%s)</em></li>' % type_label
                    html += line_html
                else:
                    html += '<li>%s</li>' % f
            html += '</ul>'
        if skipped_files:
            html += '<p><strong style="color: #856404;">ไฟล์ที่ไม่ใช่ใบเสร็จ / ไม่อ่านยอด (%d ไฟล์):</strong></p><ul>' % len(skipped_files)
            for f in skipped_files:
                if isinstance(f, dict):
                    fname = f.get('filename', '')
                    reason = f.get('reason', '')
                    # Substitute certificates: show amount + label
                    if f.get('is_receipt_substitute'):
                        amt_val = f.get('amount', 0)
                        amt_str = '{:,.2f}'.format(amt_val) if isinstance(amt_val, (int, float)) and amt_val > 0 else '0.00'
                        html += (
                            u'<li style="color: #17a2b8;">&#128196; %s — '
                            u'<strong>ยอด %s บาท</strong> '
                            u'<em>(ใบรับรองแทนใบเสร็จ)</em></li>'
                        ) % (fname, amt_str)
                        continue
                    # Highlight handwritten/unclear in red, others in yellow
                    reason_lower = reason.lower() if reason else ''
                    if 'ลายมือ' in reason_lower or 'เขียนมือ' in reason_lower or 'บิลเงินสด' in reason_lower or 'ไม่ชัด' in reason_lower or 'อ่านไม่ออก' in reason_lower:
                        html += '<li style="color: #dc3545;">&#9888; %s — <em>%s</em></li>' % (fname, reason)
                    else:
                        html += '<li style="color: #856404;">%s — <em>%s</em></li>' % (fname, reason)
                else:
                    html += '<li style="color: #856404;">%s</li>' % f
            html += '</ul>'
        html += '</div>'

        # 2. Amount Check (with cash bill total if passed)
        ac = result.get('amount_check', {})
        ac_pass = ac.get('matches', False)

        # If AI didn't include combined_total, calculate it from Python side
        r_total_ai = ac.get('receipt_total', 0)
        cb_total = ac.get('cash_bill_total', 0)
        combined = ac.get('combined_total', 0)
        s_total = ac.get('system_total', 0)

        # Ensure numeric types
        r_total_ai = r_total_ai if isinstance(r_total_ai, (int, float)) else 0
        cb_total = cb_total if isinstance(cb_total, (int, float)) else 0
        combined = combined if isinstance(combined, (int, float)) else 0
        s_total = s_total if isinstance(s_total, (int, float)) else 0

        # Python-calculated receipt_total: sum actual receipt amounts (more accurate than AI's sum)
        _py_receipt_sum = 0.0
        _deposit_slip_labels = {'deposit_slip'}
        for _rf in receipt_files:
            if isinstance(_rf, dict):
                _rf_type = _rf.get('type', 'receipt')
                if _rf_type in _deposit_slip_labels:
                    _fee = _rf.get('fee', 0)
                    if isinstance(_fee, (int, float)):
                        _py_receipt_sum += _fee
                else:
                    _amt = _rf.get('amount', 0)
                    if isinstance(_amt, (int, float)):
                        _py_receipt_sum += _amt
        # Use Python sum if available, fallback to AI's receipt_total
        _py_overrode_r_total = False
        if _py_receipt_sum > 0:
            r_total = round(_py_receipt_sum, 2)
            if abs(r_total - r_total_ai) > 0.01:
                _py_overrode_r_total = True
        else:
            r_total = r_total_ai
        # WHT adjustment: if WHT > 0, use Untaxed + Tax instead of Total
        _wht_display = self.wht_amount or 0
        if _wht_display > 0:
            _untaxed_d = self.untaxed_amount or 0
            _tax_d = self.tax_amount or 0
            if _untaxed_d > 0:
                s_total = _untaxed_d + _tax_d

        # Resolve cash bill total from registered_total when check passed
        # ใช้ cash_bill_ok (logic ใหม่) แทน AI's pass
        if cbc.get('required', False) and cash_bill_ok:
            # ใช้ผลรวม cash_bill_ids ที่ user ลงทะเบียน (มากกว่า AI's registered_total ที่อาจ stale)
            reg_total_val = sum((cb.amount or 0) + (cb.vat_amount or 0) for cb in self.cash_bill_ids)
            if not reg_total_val:
                reg_total_val = cbc.get('registered_total', 0)
            if isinstance(reg_total_val, (int, float)) and reg_total_val > 0:
                cb_total = reg_total_val

        # Receipt substitute certificates — auto-decide if their amount counts
        sub_resolution = self._resolve_receipt_substitutes(result, r_total, s_total)
        sub_total = sub_resolution['amount_to_count']

        # Recompute combined when AI didn't provide it, when Python overrode r_total,
        # or when there are receipt substitutes to add
        if (r_total > 0 or cb_total > 0 or sub_total > 0) and (combined == 0 or _py_overrode_r_total or sub_total > 0):
            combined = round(r_total + cb_total + sub_total, 2)

        # Re-check matches with combined_total
        if combined > 0 and s_total > 0:
            ac_pass = abs(combined - s_total) < 1.0  # tolerance 1 baht

        # Check if amount check was skipped by condition
        amount_skipped = bool(skip_amount_files and _any_receipt_matches_skip(skip_amount_files))
        if amount_skipped:
            ac_pass = True  # forced pass
        ac_icon = '<span style="color: #28a745;">&#10004;</span>' if ac_pass else '<span style="color: #dc3545;">&#10008;</span>'
        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        html += '<h3>%s 2. ตรวจสอบยอดเงิน</h3>' % ac_icon
        if amount_skipped:
            skipped_names = ', '.join(sorted(skip_amount_files))
            html += '<div style="margin: 4px 0; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
            html += u'<strong>&#9196; ข้ามการตรวจยอดเงิน</strong> ตามเงื่อนไขที่กำหนด: %s</div>' % skipped_names

        r_total_str = '{:,.2f}'.format(r_total)
        s_total_str = '{:,.2f}'.format(s_total)
        combined_str = '{:,.2f}'.format(combined)
        html += '<p>ยอดจากใบเสร็จ (รวมจากรายการ): <strong>%s บาท</strong></p>' % r_total_str
        # Show note if Python sum differs from AI's reported total
        if _py_receipt_sum > 0 and abs(_py_receipt_sum - r_total_ai) > 1.0 and r_total_ai > 0:
            html += '<p style="color: #6c757d; font-size: 0.9em;">* AI รายงานยอดรวม {:,.2f} แต่ระบบคำนวณจากรายการได้ {:,.2f} (ใช้ยอดที่ระบบคำนวณ)</p>'.format(r_total_ai, _py_receipt_sum)
        if cb_total > 0:
            cb_total_str = '{:,.2f}'.format(cb_total)
            html += '<p>ยอดจากบิลเงินสด: <strong>%s บาท</strong></p>' % cb_total_str
        # Show substitute certificates
        if sub_resolution['substitutes']:
            sub_total_str = '{:,.2f}'.format(sub_resolution['sub_total'])
            decision = sub_resolution['decision']
            sub_files_str = ', '.join(
                f.get('filename', '') for f in sub_resolution['substitutes'] if isinstance(f, dict)
            )
            if decision == 'count_substitute':
                badge_color = '#28a745'
                badge_text = u'นับเข้ารวม'
            elif decision == 'cover_skip':
                badge_color = '#6c757d'
                badge_text = u'ไม่นับ (เอกสารคลุมยอด)'
            else:
                badge_color = '#dc3545'
                badge_text = u'ไม่ตรงกับระบบ ต้องตรวจสอบเอง'
            html += (
                u'<p>ยอดจากใบรับรองแทนใบเสร็จ (%s): <strong>%s บาท</strong> '
                u'<span style="background:%s; color:#fff; padding:2px 8px; border-radius:3px; font-size:0.85em;">%s</span></p>'
            ) % (sub_files_str, sub_total_str, badge_color, badge_text)
            if sub_resolution.get('message'):
                html += u'<p style="color: #6c757d; font-size: 0.9em;">* %s</p>' % sub_resolution['message']
        if cb_total > 0 or sub_total > 0:
            parts = [u'ใบเสร็จ']
            if cb_total > 0:
                parts.append(u'บิลเงินสด')
            if sub_total > 0:
                parts.append(u'ใบรับรองฯ')
            html += u'<p>ยอดรวมทั้งหมด (%s): <strong>%s บาท</strong></p>' % (' + '.join(parts), combined_str)
        if _wht_display > 0 and (self.untaxed_amount or 0) > 0:
            html += '<p>ยอดในระบบ (Untaxed + Tax): <strong>%s บาท</strong></p>' % s_total_str
            html += '<p style="color: #6c757d; font-size: 0.9em;">* ใช้ Untaxed + Tax แทน Total เนื่องจากมีภาษีหัก ณ ที่จ่าย %.2f บาท</p>' % _wht_display
        else:
            html += '<p>ยอดในระบบ: <strong>%s บาท</strong></p>' % s_total_str
        ac_msg = ac.get('message', '')
        if ac_msg:
            html += '<p>%s</p>' % ac_msg

        # --- Comparison table: AI receipt amounts vs system unit prices ---
        if not ac_pass and receipt_files:
            # Build list of AI amounts (excluding deposit_slip which uses fee)
            ai_amounts = []
            for f in receipt_files:
                if isinstance(f, dict) and f.get('filename'):
                    ftype = f.get('type', 'receipt')
                    if ftype == 'deposit_slip':
                        fee_val = f.get('fee', 0)
                        if isinstance(fee_val, (int, float)) and fee_val > 0:
                            ai_amounts.append({
                                'filename': f.get('filename', ''),
                                'amount': fee_val,
                                'matched': False,
                            })
                    else:
                        amt_val = f.get('amount', 0)
                        if isinstance(amt_val, (int, float)) and amt_val > 0:
                            ai_amounts.append({
                                'filename': f.get('filename', ''),
                                'amount': amt_val,
                                'matched': False,
                            })

            # Build list of system unit prices
            sys_prices = []
            for line in self.clear_ids:
                sys_prices.append({
                    'product': line.product_id.name or line.name or '',
                    'price_unit': line.price_unit or 0,
                    'matched': False,
                })

            # Phase 1: Match 1-to-1 (AI amount ≈ system unit price, within 1 baht)
            for ai_item in ai_amounts:
                for sys_item in sys_prices:
                    if not sys_item['matched'] and abs(ai_item['amount'] - sys_item['price_unit']) < 1.0:
                        ai_item['matched'] = True
                        ai_item['matched_product'] = sys_item['product']
                        ai_item['matched_price'] = sys_item['price_unit']
                        sys_item['matched'] = True
                        sys_item['matched_file'] = ai_item['filename']
                        break

            # Phase 2: Sum matching — for unmatched AI amounts, check if they equal
            # the sum of multiple unmatched system entries (handles receipts with multiple items
            # where AI reads only the total but system has individual entries)
            unmatched_ai_phase1 = [a for a in ai_amounts if not a['matched']]
            unmatched_sys_phase1 = [s for s in sys_prices if not s['matched']]

            if unmatched_ai_phase1 and len(unmatched_sys_phase1) >= 2:
                # Try to find combinations of unmatched system prices that sum to an unmatched AI amount
                from itertools import combinations
                for ai_item in unmatched_ai_phase1:
                    if ai_item['matched']:
                        continue
                    target = ai_item['amount']
                    found_combo = False
                    # Try combinations of 2, 3, 4 unmatched system items
                    still_unmatched_sys = [s for s in sys_prices if not s['matched']]
                    for combo_size in range(2, min(len(still_unmatched_sys) + 1, 5)):
                        if found_combo:
                            break
                        for combo in combinations(enumerate(still_unmatched_sys), combo_size):
                            combo_sum = sum(s['price_unit'] for _, s in combo)
                            if abs(combo_sum - target) < 1.0:
                                # Found a match!
                                ai_item['matched'] = True
                                ai_item['matched_product'] = ' + '.join(s['product'] for _, s in combo)
                                ai_item['matched_price'] = combo_sum
                                ai_item['sum_matched'] = True
                                for _, s in combo:
                                    s['matched'] = True
                                    s['matched_file'] = ai_item['filename']
                                found_combo = True
                                break

            unmatched_ai = [a for a in ai_amounts if not a['matched']]
            unmatched_sys = [s for s in sys_prices if not s['matched']]

            # Show sum-matched info (receipts matched to multiple system entries)
            sum_matched = [a for a in ai_amounts if a.get('sum_matched')]
            if sum_matched:
                html += '<div style="margin-top: 10px; padding: 8px; background: #d4edda; border: 1px solid #28a745; border-radius: 4px;">'
                html += u'<strong style="color: #155724;">&#10004; จับคู่ยอดรวม (ใบเสร็จ 1 ใบ = หลายรายการในระบบ):</strong>'
                html += '<table style="width:100%; border-collapse: collapse; font-size: 0.9em; margin-top: 6px;">'
                html += '<tr style="background: #c3e6cb;">'
                html += u'<th style="border: 1px solid #28a745; padding: 4px 8px; text-align: left;">ไฟล์แนบ</th>'
                html += u'<th style="border: 1px solid #28a745; padding: 4px 8px; text-align: right;">ยอดในใบเสร็จ</th>'
                html += u'<th style="border: 1px solid #28a745; padding: 4px 8px; text-align: left;">รายการในระบบที่รวมกัน</th>'
                html += '</tr>'
                for a in sum_matched:
                    html += '<tr>'
                    html += '<td style="border: 1px solid #28a745; padding: 4px 8px;">%s</td>' % a['filename']
                    html += '<td style="border: 1px solid #28a745; padding: 4px 8px; text-align: right;">%s</td>' % '{:,.2f}'.format(a['amount'])
                    html += '<td style="border: 1px solid #28a745; padding: 4px 8px;">%s = %s</td>' % (a.get('matched_product', ''), '{:,.2f}'.format(a.get('matched_price', 0)))
                    html += '</tr>'
                html += '</table></div>'

            if unmatched_ai or unmatched_sys:
                html += '<div style="margin-top: 10px; padding: 8px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px;">'
                html += u'<strong style="color: #856404;">&#128269; รายการที่ยอดไม่ตรงกัน:</strong>'

                if unmatched_ai:
                    html += u'<p style="margin: 6px 0 2px 0; color: #856404;"><strong>ยอดจากใบเสร็จ (AI อ่าน) ที่ไม่พบในระบบ:</strong></p>'
                    html += '<table style="width:100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 8px;">'
                    html += '<tr style="background: #ffeeba;">'
                    html += u'<th style="border: 1px solid #ffc107; padding: 4px 8px; text-align: left;">ไฟล์แนบ</th>'
                    html += u'<th style="border: 1px solid #ffc107; padding: 4px 8px; text-align: right;">ยอด AI อ่าน</th>'
                    html += '</tr>'
                    for a in unmatched_ai:
                        html += '<tr>'
                        html += '<td style="border: 1px solid #ffc107; padding: 4px 8px;">%s</td>' % a['filename']
                        html += '<td style="border: 1px solid #ffc107; padding: 4px 8px; text-align: right;">%s</td>' % '{:,.2f}'.format(a['amount'])
                        html += '</tr>'
                    html += '</table>'

                if unmatched_sys:
                    html += u'<p style="margin: 6px 0 2px 0; color: #856404;"><strong>ยอดในระบบที่ไม่พบในใบเสร็จ:</strong></p>'
                    html += '<table style="width:100%; border-collapse: collapse; font-size: 0.9em;">'
                    html += '<tr style="background: #ffeeba;">'
                    html += u'<th style="border: 1px solid #ffc107; padding: 4px 8px; text-align: left;">รายการในระบบ</th>'
                    html += u'<th style="border: 1px solid #ffc107; padding: 4px 8px; text-align: right;">Unit Price</th>'
                    html += '</tr>'
                    for s in unmatched_sys:
                        html += '<tr>'
                        html += '<td style="border: 1px solid #ffc107; padding: 4px 8px;">%s</td>' % s['product']
                        html += '<td style="border: 1px solid #ffc107; padding: 4px 8px; text-align: right;">%s</td>' % '{:,.2f}'.format(s['price_unit'])
                        html += '</tr>'
                    html += '</table>'

                diff_val = abs(r_total - s_total) if r_total and s_total else 0
                if diff_val > 0:
                    html += u'<p style="margin-top: 6px; color: #856404;"><strong>ส่วนต่าง: %s บาท</strong></p>' % '{:,.2f}'.format(diff_val)
                html += '</div>'

        html += '</div>'

        # 4. Tax in Detail Check (AI checks if receipt has VAT -> detail lines have tax)
        tc = result.get('tax_in_detail_check', {})
        receipt_has_vat = tc.get('receipt_has_vat', False)
        detail_has_tax = tc.get('detail_has_tax', False)
        vat_exempt = tc.get('vat_exempt_utility', False) or py_all_deposit  # Python fallback
        # Check if VAT check was skipped by condition
        vat_skipped = bool(skip_vat_files and _any_receipt_matches_skip(skip_vat_files))
        vat_skipped_logistics = _is_logistics_db
        if vat_skipped or vat_skipped_logistics:
            tc_pass = True  # forced pass
        else:
            tc_pass = detail_has_tax or not receipt_has_vat or vat_exempt
        tc_icon = '<span style="color: #28a745;">&#10004;</span>' if tc_pass else '<span style="color: #dc3545;">&#10008;</span>'
        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        html += '<h3>%s 3. ตรวจสอบภาษีในรายการ</h3>' % tc_icon
        if vat_skipped_logistics:
            html += '<div style="margin: 4px 0; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
            html += u'<strong>&#9196; ข้ามการตรวจ VAT</strong> (NPD_Logistics_New ไม่ต้องตรวจ VAT)</div>'
        elif vat_skipped:
            skipped_names = ', '.join(sorted(skip_vat_files))
            html += '<div style="margin: 4px 0; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
            html += u'<strong>&#9196; ข้ามการตรวจ VAT</strong> ตามเงื่อนไขที่กำหนด: %s</div>' % skipped_names
        # Show VAT status details
        vat_label = 'มี' if receipt_has_vat else 'ไม่มี'
        tax_label = 'มี' if detail_has_tax else 'ไม่มี'
        html += '<p>ใบเสร็จ %s VAT | Detail Lines %s Tax</p>' % (vat_label, tax_label)
        if vat_exempt:
            exempt_reason = tc.get('exempt_reason', '')
            if not exempt_reason and py_all_deposit:
                exempt_reason = u'ใบฝากเงินทั้งหมด ใช้แค่ค่าธรรมเนียม ไม่ต้องตรวจ VAT'
            html += '<p style="color: #17a2b8;">&#9432; ได้รับข้อยกเว้น VAT: %s</p>' % (exempt_reason or u'ใบเสร็จสาธารณูปโภค')
        tc_msg = tc.get('message', '')
        if tc_msg:
            html += '<p>%s</p>' % tc_msg
        if not tc_pass:
            missing_lines = tc.get('missing_tax_lines', [])
            if missing_lines:
                html += '<p style="color: #dc3545; font-weight: bold;">รายการที่ยังไม่ระบุภาษี:</p>'
                html += '<table style="border-collapse: collapse; width: 100%; margin: 4px 0;">'
                html += '<tr style="background: #f8d7da;">'
                html += '<th style="border: 1px solid #ddd; padding: 4px 8px; text-align: left;">ชื่อรายการ</th>'
                html += '<th style="border: 1px solid #ddd; padding: 4px 8px; text-align: right;">ยอดเงิน</th>'
                html += '<th style="border: 1px solid #ddd; padding: 4px 8px; text-align: left;">ไฟล์แนบ</th>'
                html += '</tr>'
                for ml in missing_lines:
                    if isinstance(ml, dict):
                        name = ml.get('product', '') or ml.get('description', '') or ml.get('line', '') or ml.get('name', '') or '-'
                        subtotal = ml.get('subtotal', ml.get('unit_price', ''))
                        if subtotal not in ('', None):
                            try:
                                subtotal = '{:,.2f}'.format(float(subtotal))
                            except (ValueError, TypeError):
                                subtotal = str(subtotal)
                        else:
                            subtotal = '-'
                        filename = ml.get('receipt_filename', '') or ml.get('invoice_number', '') or '-'
                    else:
                        name = str(ml)
                        subtotal = '-'
                        filename = '-'
                    html += '<tr>'
                    html += '<td style="border: 1px solid #ddd; padding: 4px 8px;">%s</td>' % name
                    html += '<td style="border: 1px solid #ddd; padding: 4px 8px; text-align: right;">%s</td>' % subtotal
                    html += '<td style="border: 1px solid #ddd; padding: 4px 8px;">%s</td>' % filename
                    html += '</tr>'
                html += '</table>'
        html += '</div>'

        # 5. Analytic Account Check (Python check, not AI)
        an_icon = '<span style="color: #28a745;">&#10004;</span>' if analytic_pass else '<span style="color: #dc3545;">&#10008;</span>'
        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        html += '<h3>%s 4. ตรวจสอบ Analytic Account</h3>' % an_icon
        if analytic_pass:
            html += '<p>ทุกรายการระบุ Analytic Account เรียบร้อยแล้ว</p>'
        else:
            html += '<p style="color: #dc3545;">รายการที่ยังไม่ระบุ Analytic Account:</p><ul>'
            for name in analytic_missing:
                html += '<li style="color: #dc3545;">%s</li>' % name
            html += '</ul>'
        html += '</div>'

        # 5. Cash Bill Check (NEW LOGIC: เทียบ cash_bill_ids กับ price_unit ใน clear_ids)
        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        if cbc.get('required', False):
            cb_check = self._check_cash_bill_match_detail()
            cbc_display_pass = cash_bill_ok
            cbc_icon = '<span style="color: #28a745;">&#10004;</span>' if cbc_display_pass else '<span style="color: #dc3545;">&#10008;</span>'
            html += '<h3>%s 5. ตรวจสอบบิลเงินสด</h3>' % cbc_icon

            skip_count = cbc.get('skipped_count', 0)
            reg_count = len(self.cash_bill_ids)
            html += u'<p>บิลเงินสดที่พบในรูป: <strong>%s ใบ</strong></p>' % str(skip_count)
            html += u'<p>รายการที่ผู้ใช้ลงทะเบียน: <strong>%s รายการ</strong></p>' % str(reg_count)

            if not self.cash_bill_ids:
                html += u'<p style="color: #dc3545;">&#10008; ผู้ใช้ยังไม่ได้ลงทะเบียนบิลเงินสด — กรุณากดปุ่ม "เพิ่มรายการบิลเงินสด"</p>'
            else:
                matched = cb_check['matched']
                unmatched = cb_check['unmatched']
                # ตารางเทียบยอด register ↔ detail
                html += u'<div style="margin: 5px 0; padding: 8px; background: #e8f4f8; border-radius: 4px; font-size: 0.9em;">'
                html += u'<strong>&#128270; เทียบยอดบิลเงินสด (ลงทะเบียน) กับ ราคาต่อหน่วยในรายละเอียด:</strong>'
                html += u'<table style="width:100%; border-collapse: collapse; margin-top: 6px;">'
                html += (u'<tr style="background: #d1ecf1;">'
                         u'<th style="border:1px solid #bee5eb; padding:4px 8px; text-align:left;">รายการ (ลงทะเบียน)</th>'
                         u'<th style="border:1px solid #bee5eb; padding:4px 8px; text-align:right;">ยอดที่กรอก</th>'
                         u'<th style="border:1px solid #bee5eb; padding:4px 8px; text-align:left;">รายละเอียด (จับคู่)</th>'
                         u'<th style="border:1px solid #bee5eb; padding:4px 8px; text-align:right;">ราคาต่อหน่วย</th>'
                         u'<th style="border:1px solid #bee5eb; padding:4px 8px; text-align:center;">สถานะ</th></tr>')
                for m in matched:
                    cb = m['cash_bill']
                    md = m['matched_detail']
                    html += u'<tr>'
                    html += u'<td style="border:1px solid #bee5eb; padding:4px 8px;">%s</td>' % (cb.description or '-')
                    html += u'<td style="border:1px solid #bee5eb; padding:4px 8px; text-align:right;">%s</td>' % '{:,.2f}'.format(cb.amount or 0)
                    html += u'<td style="border:1px solid #bee5eb; padding:4px 8px;">%s</td>' % (md.get('product') or '-')
                    html += u'<td style="border:1px solid #bee5eb; padding:4px 8px; text-align:right;">%s</td>' % '{:,.2f}'.format(md.get('price') or 0)
                    html += u'<td style="border:1px solid #bee5eb; padding:4px 8px; text-align:center; color:#28a745;">&#10004;</td>'
                    html += u'</tr>'
                for cb in unmatched:
                    html += u'<tr style="background: #f8d7da;">'
                    html += u'<td style="border:1px solid #f5c6cb; padding:4px 8px;">%s</td>' % (cb.description or '-')
                    html += u'<td style="border:1px solid #f5c6cb; padding:4px 8px; text-align:right;">%s</td>' % '{:,.2f}'.format(cb.amount or 0)
                    html += u'<td style="border:1px solid #f5c6cb; padding:4px 8px;" colspan="2"><em>ไม่พบยอดที่ตรงกันในรายละเอียด</em></td>'
                    html += u'<td style="border:1px solid #f5c6cb; padding:4px 8px; text-align:center; color:#dc3545;">&#10008;</td>'
                    html += u'</tr>'
                html += u'</table>'
                html += u'</div>'
                if cb_check['pass']:
                    html += u'<p style="color: #28a745;">&#10004; %s</p>' % cb_check['message']
                else:
                    html += u'<p style="color: #dc3545;">&#10008; %s</p>' % cb_check['message']

            # ─── OLD LOGIC HTML (เก็บไว้ก่อนตามคำสั่ง) ────────────────────────
            # reg_total = cbc.get('registered_total', 0)
            # bill_total = py_cash_bill_total if py_cash_bill_total > 0 else cbc.get('bill_total', 0)
            # reg_total_str = '{:,.2f}'.format(reg_total) if isinstance(reg_total, (int, float)) else str(reg_total)
            # bill_total_str = '{:,.2f}'.format(bill_total) if isinstance(bill_total, (int, float)) else str(bill_total)
            # html += '<p>ยอดรวมจากรูปบิล (Python ตรวจสอบ): <strong>%s บาท</strong></p>' % bill_total_str
            # html += '<p>ยอดรวมที่ลงทะเบียน: <strong>%s บาท</strong></p>' % reg_total_str
            # cv_details = self._get_cash_bill_cross_verify_details(result)
            # if cv_details:
            #     html += '<div style="margin: 5px 0; padding: 8px; background: #e8f4f8; border-radius: 4px; font-size: 0.9em;">'
            #     html += '<strong>&#128270; การตรวจสอบยอดบิลเงินสด (Cross-Verify):</strong><ul style="margin: 5px 0;">'
            #     for cv in cv_details:
            #         fname = cv.get('filename', '?')
            #         qty = cv.get('quantity', 0)
            #         price = cv.get('unit_price', 0)
            #         raw = cv.get('raw_total', 0)
            #         calc = cv.get('calculated', 0)
            #         final = cv.get('final_amount', 0)
            #         if qty > 0 and price > 0:
            #             if abs(calc - raw) > 0.5 and calc > 0:
            #                 html += '<li style="color: #856404;">%s: จำนวน=%s × หน่วยละ=%s = <strong>%s</strong> (AI อ่านยอดได้ %s → ใช้ค่าคำนวณ)</li>' % (
            #                     fname, '{:,.0f}'.format(qty), '{:,.2f}'.format(price), '{:,.2f}'.format(calc), '{:,.2f}'.format(raw))
            #             else:
            #                 html += '<li style="color: #28a745;">%s: จำนวน=%s × หน่วยละ=%s = <strong>%s</strong> &#10004;</li>' % (
            #                     fname, '{:,.0f}'.format(qty), '{:,.2f}'.format(price), '{:,.2f}'.format(final))
            #         else:
            #             html += '<li>%s: ยอด <strong>%s</strong> บาท (ไม่มีข้อมูลจำนวน/ราคาต่อหน่วย)</li>' % (fname, '{:,.2f}'.format(final))
            #     html += '</ul></div>'
            # py_total_match = abs(bill_total - (reg_total if isinstance(reg_total, (int, float)) else 0)) < 1.0 if bill_total > 0 else cbc.get('total_amount_matches', False)
            # if py_total_match:
            #     html += '<p style="color: #28a745;">&#10004; ยอดรวมสอดคล้อง</p>'
            # else:
            #     html += '<p style="color: #dc3545;">&#10008; ยอดรวมไม่สอดคล้อง</p>'
            # if cbc.get('description_or_amount_matches'):
            #     html += '<p style="color: #28a745;">&#10004; รายการสินค้า/ยอดเงินสอดคล้อง</p>'
            # else:
            #     html += '<p style="color: #dc3545;">&#10008; รายการสินค้า/ยอดเงินไม่สอดคล้อง</p>'
        else:
            cbc_icon = '<span style="color: #28a745;">&#10004;</span>'
            html += '<h3>%s 5. ตรวจสอบบิลเงินสด</h3>' % cbc_icon
            html += '<p>ไม่มีบิลเงินสด</p>'
        html += '</div>'

        # 7. Company Info Check + Utility Address Check (combined)
        cnc_required = cnc.get('required', False)
        cnc_pass = cnc.get('pass', False)
        # Apply condition override for company check
        company_skipped_names = set()
        if skip_company_files and cnc_required and not cnc_pass:
            cnc_mismatched_orig = cnc.get('mismatched_files', [])
            cnc_mismatched_filtered = [mf for mf in cnc_mismatched_orig
                                       if isinstance(mf, dict) and mf.get('filename', '') not in skip_company_files]
            if not cnc_mismatched_filtered and cnc_mismatched_orig:
                cnc_pass = True  # all mismatched files were skipped → force pass
                company_skipped_names = set(mf.get('filename', '') for mf in cnc_mismatched_orig if isinstance(mf, dict)) & skip_company_files
        check7_company_ok = (not cnc_required) or cnc_pass
        check7_utility_ok = uac_ok  # from Python _check_utility_analytic_partner()
        check7_pass = check7_company_ok and check7_utility_ok
        check7_icon = '<span style="color: #28a745;">&#10004;</span>' if check7_pass else '<span style="color: #dc3545;">&#10008;</span>'

        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        html += '<h3>%s 6. ตรวจสอบข้อมูลบริษัทลูกค้า + ที่อยู่สาธารณูปโภค</h3>' % check7_icon
        if company_skipped_names:
            skipped_names = ', '.join(sorted(company_skipped_names))
            html += '<div style="margin: 4px 0; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
            html += u'<strong>&#9196; ข้ามการตรวจชื่อบริษัท</strong> ตามเงื่อนไขที่กำหนด: %s</div>' % skipped_names

        # 7a. Company name/tax_id/address (AI check)
        if cnc_required:
            cnc_msg = cnc.get('message', '')
            if cnc_pass:
                html += '<p style="color: #28a745;">&#10004; %s</p>' % (cnc_msg or 'ข้อมูลบริษัทลูกค้าในใบเสร็จตรงกับบริษัทในกลุ่ม')
            else:
                html += '<p style="color: #dc3545;">&#10008; %s</p>' % (cnc_msg or 'ข้อมูลบริษัทลูกค้าในใบเสร็จไม่ตรง')
                mismatched = cnc.get('mismatched_files', [])
                if mismatched:
                    html += '<ul style="color: #dc3545;">'
                    for mf in mismatched:
                        if isinstance(mf, dict):
                            mf_fname = mf.get('filename', '')
                            issue = mf.get('issue', '')
                            html += '<li><strong>%s</strong> — %s</li>' % (mf_fname, issue)
                        else:
                            html += '<li>%s</li>' % mf
                    html += '</ul>'

        # 7b. Utility address check (Python: Analytic Account vs Partner)
        if uac_required:
            if uac_ok:
                html += '<p style="color: #28a745;">&#10004; Analytic Account ตรงกับ Partner ในรายการค่าน้ำ/ค่าไฟทุกรายการ</p>'
            else:
                html += '<p style="color: #dc3545;">&#10008; Analytic Account ไม่ตรงกับ Partner:</p>'
                html += '<ul style="margin: 4px 0;">'
                for ui in uac_items:
                    if ui.get('match', False):
                        continue  # ผ่าน → ไม่แสดง
                    ui_reason = ui.get('reason', '')
                    html += '<li style="color: #dc3545;">&#10008; %s</li>' % ui_reason
                html += '</ul>'

        if not cnc_required and not uac_required:
            html += '<p>ไม่มีข้อมูลที่ต้องตรวจสอบ (ใบเสร็จค่าน้ำ/ค่าไฟ หรือข้อมูลบริษัท)</p>'

        html += '</div>'

        # 8. Invoice Detail Check (invoice number / date / partner)
        idc = result.get('invoice_detail_check', {})
        idc_items = idc.get('items', [])
        # Apply condition override — separate checked vs skipped items
        # Use base-name matching for split filenames (e.g. "X.jpg (บนซ้าย)")
        idc_checked_items = []
        idc_skipped_items = []
        for item in idc_items:
            if not isinstance(item, dict):
                continue
            fname = item.get('filename', '')
            if _filename_in_skip_set(fname, skip_invoice_files):
                idc_skipped_items.append(item)
            else:
                idc_checked_items.append(item)
        # Recalculate pass from checked items only
        if idc_skipped_items:
            if idc_checked_items:
                idc_pass_val = all(
                    it.get('invoice_number_match', False) and it.get('date_match', False) and it.get('partner_match', False)
                    for it in idc_checked_items
                )
            else:
                idc_pass_val = True  # all items skipped → pass
        else:
            idc_pass_val = idc.get('pass', True)
        idc_icon = '<span style="color: #28a745;">&#10004;</span>' if idc_pass_val else '<span style="color: #dc3545;">&#10008;</span>'
        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        html += '<h3>%s 7. ตรวจสอบเลขที่ใบเสร็จ / วันที่ / ร้านค้า</h3>' % idc_icon
        if idc_skipped_items:
            skipped_names = ', '.join(it.get('filename', '?') for it in idc_skipped_items)
            html += '<div style="margin: 4px 0; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
            html += u'<strong>&#9196; ข้ามการตรวจเลขที่/วันที่/ร้านค้า</strong> ตามเงื่อนไขที่กำหนด: %s</div>' % skipped_names

        if idc_checked_items:
            html += '<p>ตรวจสอบใบเสร็จ/ใบกำกับภาษี (%d ไฟล์):</p>' % len(idc_checked_items)
            html += '<ul style="margin: 4px 0;">'
            for item in idc_checked_items:
                fname = item.get('filename', '')
                inv_match = item.get('invoice_number_match', False)
                dt_match = item.get('date_match', False)
                pt_match = item.get('partner_match', False)
                all_match = inv_match and dt_match and pt_match
                r_inv = item.get('receipt_invoice_number', '') or '-'
                r_dt = item.get('receipt_date', '') or '-'
                r_pt = item.get('receipt_partner', '') or '-'
                if all_match:
                    item_color = '#28a745'
                    html += '<li style="color: %s;"><strong>%s</strong> — เลขที่: %s | วันที่: %s | ร้านค้า: %s</li>' % (item_color, fname, r_inv, r_dt, r_pt)
                else:
                    item_color = '#dc3545'
                    parts = []
                    if not inv_match:
                        d_inv = item.get('detail_invoice_number', '') or '-ว่าง-'
                        parts.append('เลขที่: %s (ระบบ: %s)' % (r_inv, d_inv))
                    if not dt_match:
                        d_dt = item.get('detail_date', '') or '-ว่าง-'
                        parts.append('วันที่: %s (ระบบ: %s)' % (r_dt, d_dt))
                    if not pt_match:
                        d_pt = item.get('detail_partner', '') or '-ว่าง-'
                        parts.append('ร้านค้า: %s (ระบบ: %s)' % (r_pt, d_pt))
                    html += '<li style="color: %s;"><strong>%s</strong> — %s</li>' % (item_color, fname, ' | '.join(parts))
            html += '</ul>'
        elif not idc_skipped_items:
            html += '<p>ไม่มีใบเสร็จ/ใบกำกับภาษีที่ต้องตรวจสอบ</p>'

        idc_msg = idc.get('message', '')
        if idc_msg:
            html += '<p>%s</p>' % idc_msg
        html += '</div>'

        # 9. Transfer Slip Check (clear_amount vs receipt file amount)
        slip_icon = '<span style="color: #28a745;">&#10004;</span>' if (not slip_check_required or slip_check_ok) else '<span style="color: #dc3545;">&#10008;</span>'
        html += '<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">'
        html += '<h3>%s 8. ตรวจสอบสลิปโอนเงิน</h3>' % slip_icon
        if skip_slip_check:
            html += '<div style="margin: 4px 0; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; color: #856404;">'
            html += u'<strong>&#9196; ข้ามการตรวจสลิป</strong> ตามเงื่อนไขที่กำหนด'
            if skip_slip_note:
                html += u'<br/>หมายเหตุ: %s' % skip_slip_note
            html += '</div>'
        elif slip_check_required:
            html += '<p>Clear Amount ในระบบ: <strong>%.2f</strong> บาท</p>' % clear_amt
            if slip_check_ok and slip_matched_files:
                if len(slip_matched_files) == 1:
                    # Single slip matched
                    m_name = slip_matched_files[0].get('filename', '') or 'unknown'
                    m_amt = _safe_float(slip_matched_files[0].get('amount', 0))
                    html += '<p style="color: #28a745;">&#10004; พบสลิป <strong>%s</strong> ยอด %.2f ตรงกับ Clear Amount %.2f</p>' % (m_name, m_amt, clear_amt)
                else:
                    # Multiple slips — show table
                    html += '<p style="color: #28a745;">&#10004; พบสลิปโอนเงิน %d รายการ ยอดรวม %.2f ตรงกับ Clear Amount %.2f</p>' % (len(slip_matched_files), slip_total, clear_amt)
                    html += '<table style="width:100%%; border-collapse: collapse; font-size: 0.9em; margin: 6px 0;">'
                    html += '<tr style="background: #d4edda;"><th style="border: 1px solid #c3e6cb; padding: 4px 8px; text-align: left;">สลิป</th>'
                    html += '<th style="border: 1px solid #c3e6cb; padding: 4px 8px; text-align: right;">ยอดโอน</th></tr>'
                    for sf in slip_matched_files:
                        sf_name = sf.get('filename', '?')
                        sf_amt = _safe_float(sf.get('amount', 0))
                        html += '<tr><td style="border: 1px solid #c3e6cb; padding: 4px 8px;">%s</td>' % sf_name
                        html += '<td style="border: 1px solid #c3e6cb; padding: 4px 8px; text-align: right;">%.2f</td></tr>' % sf_amt
                    html += '<tr style="font-weight: bold;"><td style="border: 1px solid #c3e6cb; padding: 4px 8px;">รวม</td>'
                    html += '<td style="border: 1px solid #c3e6cb; padding: 4px 8px; text-align: right;">%.2f</td></tr>' % slip_total
                    html += '</table>'
            else:
                html += '<p style="color: #dc3545;">ไม่พบสลิปโอนเงินที่ยอดตรงกับ Clear Amount %.2f ในเอกสารแนบ</p>' % clear_amt
                # Debug: show all files AI returned so we can troubleshoot
                if slip_all_files or slip_debug_info:
                    html += '<details style="margin-top: 5px;"><summary style="cursor:pointer; color:#6c757d;">&#9660; Debug: ข้อมูลที่ AI ส่งกลับ</summary>'
                    html += '<ul style="font-size: 0.85em; color: #6c757d;">'
                    for sf in slip_all_files:
                        sf_name = sf.get('filename', '?')
                        sf_type = sf.get('type', '?')
                        sf_amt = sf.get('amount', 'N/A')
                        sf_fee = sf.get('fee', 'N/A')
                        html += '<li>[receipt_files] %s — type: %s, amount: %s, fee: %s</li>' % (sf_name, sf_type, sf_amt, sf_fee)
                    for di in slip_debug_info:
                        if di.get('source') == 'skipped_files':
                            html += '<li>[skipped_files] %s — type: %s, amount: %s, fee: %s</li>' % (di['file'], di['type'], di['amount'], di['fee'])
                    html += '</ul></details>'
        else:
            html += '<p>ไม่มียอด Clear Amount (ไม่ต้องตรวจสลิป)</p>'
        html += '</div>'

        html += '</div>'

        return html

    # ──────────────────────────────────────────────────────────────────
    #  Failed-only summary for the AI verify popup
    #  (the full report is still saved to ai_verify_result / shown at the
    #   bottom of the document — this is only what the user must FIX)
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _fmt_baht(val):
        try:
            return '{:,.2f}'.format(float(val))
        except (ValueError, TypeError):
            return str(val)

    def _collect_ai_fail_items(self, result, flags):
        """Build a list of failed checks with a plain-language reason and fix.

        flags is a dict carrying the pass/fail booleans already computed in
        action_ai_verify plus a few values used to craft the messages:
          rc_ok, amount_ok, tc_ok, analytic_pass, cash_bill_ok,
          company_name_ok, idc_ok, uac_ok, slip_ok,
          analytic_missing (list), combined (float), system_total (float)
        """
        items = []
        fmt = self._fmt_baht

        # 1. ใบเสร็จ
        if not flags.get('rc_ok', True):
            rc = result.get('receipt_check', {}) or {}
            skipped = [f for f in rc.get('skipped_files', []) if isinstance(f, dict)]
            receipt_files = [f for f in rc.get('receipt_files', []) if isinstance(f, dict) and f.get('filename')]
            has_unclear = any(
                any(kw in (f.get('reason', '') or '').lower()
                    for kw in ['ไม่ชัด', 'อ่านไม่ออก', 'เบลอ', 'unclear'])
                for f in skipped if not f.get('is_receipt_substitute')
            )
            has_hw = any(
                any(kw in (f.get('reason', '') or '').lower()
                    for kw in ['ลายมือ', 'เขียนมือ', 'บิลเงินสด', 'handwritten', 'cash'])
                for f in skipped if not f.get('is_receipt_substitute')
            )
            if not receipt_files and not rc.get('found', False) and not has_hw:
                reason = u'ไม่พบไฟล์ใบเสร็จที่อ่านได้ในเอกสารแนบ'
                fix = u'อัปโหลดรูปใบเสร็จ/ใบกำกับภาษีที่ชัดเจนในเอกสารแนบ แล้วกด "ตรวจสอบด้วย AI" อีกครั้ง'
            elif has_unclear:
                reason = u'ใบเสร็จบางใบไม่ชัดเจน ระบบอ่านข้อมูลไม่ออก'
                fix = u'ถ่าย/สแกนใบเสร็จใหม่ให้ชัด แล้ว Reset to Draft > อัปโหลดรูปใหม่ > ตรวจสอบด้วย AI อีกครั้ง'
            elif has_hw:
                reason = u'พบบิลเขียนมือ/บิลเงินสด ที่ยังไม่ได้ลงทะเบียนเข้าระบบ'
                fix = u'กดปุ่ม "เพิ่มรายการบิลเงินสด" เพื่อลงทะเบียนบิล หรือขอใบเสร็จที่พิมพ์จากระบบมาแนบแทน'
            else:
                reason = u'ใบเสร็จไม่ผ่านการตรวจสอบความถูกต้อง'
                fix = u'ตรวจสอบไฟล์ใบเสร็จที่แนบให้ครบและชัดเจน แล้วตรวจสอบด้วย AI อีกครั้ง'
            items.append({'title': u'1. ใบเสร็จ', 'reason': reason, 'fix': fix})

        # 2. ยอดเงิน
        if not flags.get('amount_ok', True):
            c = flags.get('combined', 0) or 0
            s = flags.get('system_total', 0) or 0
            diff = abs(s - c)
            reason = (u'ยอดรวมจากใบเสร็จ %s บาท ไม่ตรงกับยอดในระบบ %s บาท (ต่างกัน %s บาท)'
                      % (fmt(c), fmt(s), fmt(diff)))
            fix = (u'ตรวจสอบว่าแนบใบเสร็จครบทุกใบ และยอดในรายการ (Detail Lines) ถูกต้อง '
                   u'หากมีบิลเงินสดที่ยังไม่ได้ลงทะเบียน ให้กด "เพิ่มรายการบิลเงินสด"')
            items.append({'title': u'2. ยอดเงินไม่ตรง', 'reason': reason, 'fix': fix})

        # 3. ภาษีในรายการ (VAT)
        if not flags.get('tc_ok', True):
            reason = u'ใบเสร็จมี VAT แต่ในรายการ (Detail Lines) ยังไม่ได้ระบุภาษี (Tax)'
            fix = u'เปิดแต่ละบรรทัดใน Detail Lines แล้วเลือกภาษี (Tax) ให้ตรงกับ VAT ในใบเสร็จ'
            items.append({'title': u'3. ภาษี (VAT) ไม่ครบ', 'reason': reason, 'fix': fix})

        # 4. Analytic Account
        if not flags.get('analytic_pass', True):
            missing = [m for m in (flags.get('analytic_missing') or []) if m]
            if missing:
                reason = u'มีรายการที่ยังไม่ได้ระบุ Analytic Account: %s' % u', '.join(missing)
            else:
                reason = u'มีรายการที่ยังไม่ได้ระบุ Analytic Account'
            fix = u'เปิดแต่ละบรรทัดใน Detail Lines แล้วเลือก Analytic Account ให้ครบทุกรายการ'
            items.append({'title': u'4. ยังไม่ได้เลือก Analytic Account', 'reason': reason, 'fix': fix})

        # 5. บิลเงินสด
        if not flags.get('cash_bill_ok', True):
            if not self.cash_bill_ids:
                reason = u'ระบบพบบิลเงินสด/บิลเขียนมือในเอกสารแนบ แต่ผู้ใช้ยังไม่ได้ลงทะเบียนเข้าระบบ'
                fix = u'กดปุ่ม "เพิ่มรายการบิลเงินสด" เพื่อลงทะเบียนบิลเงินสดให้ครบทุกใบ'
            else:
                reason = u'ยอดบิลเงินสดที่ลงทะเบียนไว้ ไม่ตรงกับราคาต่อหน่วยในรายการ (Detail Lines)'
                fix = u'ตรวจสอบยอดในรายการบิลเงินสดที่ลงทะเบียน ให้ตรงกับยอดในรายการ Detail Lines'
            items.append({'title': u'5. บิลเงินสดไม่ตรง', 'reason': reason, 'fix': fix})

        # 6. ข้อมูลบริษัทลูกค้า (ผู้ซื้อ)
        if not flags.get('company_name_ok', True):
            cnc = result.get('company_name_check', {}) or {}
            mm = [m.get('filename', '') for m in cnc.get('mismatched_files', []) if isinstance(m, dict)]
            mm = [m for m in mm if m]
            reason = u'ชื่อ / เลขภาษี / ที่อยู่ ของบริษัทในใบเสร็จ ไม่ตรงกับบริษัทที่ระบบยอมรับ'
            if mm:
                reason += u' (ไฟล์: %s)' % u', '.join(mm)
            fix = u'ขอใบเสร็จที่ออกในชื่อ/เลขภาษี/ที่อยู่บริษัทให้ถูกต้อง แล้วอัปโหลดมาตรวจสอบใหม่'
            items.append({'title': u'6. ข้อมูลบริษัทในใบเสร็จไม่ตรง', 'reason': reason, 'fix': fix})

        # 7. เลขที่ใบเสร็จ / วันที่ / ร้านค้า
        if not flags.get('idc_ok', True):
            idc = result.get('invoice_detail_check', {}) or {}
            rows = []
            for it in idc.get('items', []):
                if not isinstance(it, dict):
                    continue
                inv_m = it.get('invoice_number_match', False)
                dt_m = it.get('date_match', False)
                pt_m = it.get('partner_match', False)
                if inv_m and dt_m and pt_m:
                    continue
                fname = it.get('filename', '') or u'?'
                diffs = []
                if not inv_m:
                    diffs.append((u'เลขที่ใบเสร็จ',
                                  it.get('receipt_invoice_number', '') or u'(อ่านไม่พบ)',
                                  it.get('detail_invoice_number', '') or u'(ยังไม่กรอก)'))
                if not dt_m:
                    diffs.append((u'วันที่',
                                  it.get('receipt_date', '') or u'(อ่านไม่พบ)',
                                  it.get('detail_date', '') or u'(ยังไม่กรอก)'))
                if not pt_m:
                    diffs.append((u'ชื่อร้านค้า',
                                  it.get('receipt_partner', '') or u'(อ่านไม่พบ)',
                                  it.get('detail_partner', '') or u'(ยังไม่กรอก)'))
                rows.append((fname, diffs))
            if rows:
                reason = u'AI อ่านข้อมูลจากใบเสร็จได้ไม่ตรงกับที่กรอกในรายการ Detail:'
                for fname, diffs in rows:
                    reason += u'<div style="margin-top:6px;"><strong>&#128196; %s</strong>' % fname
                    reason += u'<table style="border-collapse:collapse; margin:4px 0; font-size:0.95em; background:#fff;">'
                    reason += (u'<tr style="background:#f1f1f1;">'
                               u'<th style="border:1px solid #ddd; padding:3px 8px; text-align:left;">หัวข้อ</th>'
                               u'<th style="border:1px solid #ddd; padding:3px 8px; text-align:left;">AI อ่านจากรูป</th>'
                               u'<th style="border:1px solid #ddd; padding:3px 8px; text-align:left;">ที่กรอกในระบบ</th></tr>')
                    for label, ai_val, sys_val in diffs:
                        reason += (u'<tr>'
                                   u'<td style="border:1px solid #ddd; padding:3px 8px;">%s</td>'
                                   u'<td style="border:1px solid #ddd; padding:3px 8px; color:#155724; font-weight:bold;">%s</td>'
                                   u'<td style="border:1px solid #ddd; padding:3px 8px; color:#721c24;">%s</td></tr>'
                                   % (label, ai_val, sys_val))
                    reason += u'</table></div>'
                fix = u'แก้ไขรายการใน Detail ให้ตรงกับค่าที่ AI อ่านได้จากใบเสร็จ (คอลัมน์ "AI อ่านจากรูป") แล้วตรวจสอบอีกครั้ง'
            else:
                reason = u'เลขที่ใบเสร็จ / วันที่ / ชื่อร้านค้า ในรายการ Detail ไม่ตรงกับใบเสร็จ หรือยังไม่ได้กรอก'
                fix = u'กรอกเลขที่ใบเสร็จ วันที่ และชื่อร้านค้าในรายการ Detail ให้ตรงกับใบเสร็จจริง'
            items.append({'title': u'7. เลขที่/วันที่/ร้านค้า ไม่ตรง', 'reason': reason, 'fix': fix})

        # 8. ที่อยู่สาธารณูปโภค (ค่าน้ำ/ค่าไฟ)
        if not flags.get('uac_ok', True):
            reason = u'ที่อยู่ในใบเสร็จค่าน้ำ/ค่าไฟ ไม่สอดคล้องกับ Analytic Account (สาขา) ที่เลือก'
            fix = u'เลือก Analytic Account (สาขา) ให้ตรงกับที่อยู่ในใบเสร็จค่าสาธารณูปโภค'
            items.append({'title': u'8. ที่อยู่สาธารณูปโภคไม่ตรงสาขา', 'reason': reason, 'fix': fix})

        # 9. สลิปโอนเงิน
        if not flags.get('slip_ok', True):
            reason = (u'ไม่พบสลิปโอนเงินที่มียอด (รวมกัน) ตรงกับยอดเคลียร์ (Clear Amount) %s บาท'
                      % fmt(self.clear_amount or 0))
            fix = u'แนบสลิปโอนเงินที่ยอดรวมตรงกับ Clear Amount หรือตรวจสอบยอด Clear Amount ให้ถูกต้อง'
            items.append({'title': u'9. สลิปโอนเงินไม่ตรงยอด', 'reason': reason, 'fix': fix})

        return items

    def _render_ai_fail_summary(self, overall_pass, fail_items):
        """Render the compact failed-only popup HTML."""
        if overall_pass or not fail_items:
            return (
                u'<div style="font-family: Segoe UI, sans-serif; padding: 24px; text-align:center;">'
                u'<div style="font-size:52px; color:#28a745; line-height:1;">&#10004;</div>'
                u'<h2 style="color:#28a745; margin:12px 0 6px;">ผ่านการตรวจสอบทั้งหมด</h2>'
                u'<p style="color:#155724; margin:0;">เอกสารถูกต้องครบถ้วน พร้อมสำหรับการอนุมัติ</p>'
                u'</div>'
            )
        n = len(fail_items)
        html = u'<div style="font-family: Segoe UI, sans-serif; padding: 6px 4px;">'
        html += (u'<h2 style="text-align:center; color:#dc3545; border-bottom:2px solid #dc3545; '
                 u'padding-bottom:8px; margin:0 0 4px;">ไม่ผ่านการตรวจสอบ &mdash; พบ %d รายการที่ต้องแก้ไข</h2>' % n)
        html += (u'<p style="text-align:center; color:#6c757d; margin:6px 0 14px;">'
                 u'กรุณาแก้ไขรายการด้านล่าง แล้วกด "ตรวจสอบด้วย AI" อีกครั้ง</p>')
        for it in fail_items:
            html += (u'<div style="margin:10px 0; border:1px solid #f5c6cb; border-left:5px solid #dc3545; '
                     u'border-radius:6px; background:#fff5f5; padding:12px 14px;">')
            html += (u'<div style="font-size:15px; font-weight:bold; color:#721c24;">'
                     u'<span style="color:#dc3545;">&#10008;</span> %s</div>' % it['title'])
            html += (u'<div style="margin-top:8px; color:#333; line-height:1.5;">'
                     u'<span style="font-weight:bold; color:#dc3545;">ทำไมไม่ผ่าน:</span> %s</div>' % it['reason'])
            html += (u'<div style="margin-top:8px; color:#0c5460; background:#e7f6f8; border-radius:4px; '
                     u'padding:8px 10px; line-height:1.5;">'
                     u'<span style="font-weight:bold;">&#128161; วิธีแก้:</span> %s</div>' % it['fix'])
            html += u'</div>'
        html += u'</div>'
        return html

    def action_ai_verify(self):
        """Main action: verify document with AI and show popup."""
        self.ensure_one()

        # Step 1: Get receipt attachments
        attachments = self._get_receipt_attachments()
        if not attachments:
            raise UserError(_(
                "ไม่พบเอกสารแนบที่เป็นรูปภาพ\n"
                "กรุณาอัพโหลดรูปใบเสร็จในส่วน Log/Chatter ก่อนทำการตรวจสอบ"
            ))

        # Step 2: Check Analytic Account (Python check, not AI)
        analytic_pass, analytic_missing = self._check_analytic_account()

        # Step 2.5: Get expected company info based on current DB
        expected_company_info, db_name = self._get_expected_company_info()
        _logger.info("=== DB name: %s, Expected company info: %s", db_name,
                     expected_company_info.get('name', 'N/A') if expected_company_info else 'NOT MAPPED')

        # Step 2.7: Build receipt condition map (user-defined per-file check overrides)
        condition_map = self._get_receipt_condition_map()
        _logger.info("=== Receipt condition map: %d entries", len(condition_map))

        # Step 3: Build prompts (system prompt for rules + user prompt for data)
        system_prompt = self._build_system_prompt()
        prompt = self._build_ai_prompt(attachments=attachments, expected_company_info=expected_company_info,
                                       condition_map=condition_map)

        # Step 4: Call Gemini API with system prompt for consistent behavior
        ai_response = self._call_gemini_api(prompt, attachments, system_prompt=system_prompt)

        # Step 5: Parse response
        result = self._parse_ai_response(ai_response)

        # Debug: log parsed result
        _logger.info("=== Parsed result keys: %s", list(result.keys()) if isinstance(result, dict) else "NOT A DICT")
        _logger.info("=== amount_check: %s", result.get('amount_check', 'MISSING'))
        _logger.info("=== tax_in_detail_check: %s", result.get('tax_in_detail_check', 'MISSING'))
        _logger.info("=== receipt_files count: %d", len(result.get('receipt_check', {}).get('receipt_files', [])))
        _logger.info("=== summary: %s", result.get('summary', 'MISSING'))

        # Step 6: Format HTML result (include analytic check, company info, and conditions)
        result_html = self._format_result_html(
            result,
            analytic_pass=analytic_pass,
            analytic_missing=analytic_missing,
            expected_company_info=expected_company_info,
            condition_map=condition_map,
        )

        # Step 7: Update ai_verified status and save result history
        # Build skip-sets from condition_map (same logic as _format_result_html)
        skip_amount_files = set()
        skip_vat_files = set()
        skip_company_files = set()
        skip_invoice_files = set()
        for fname, conds in condition_map.items():
            if not conds.get('check_amount', True):
                skip_amount_files.add(fname)
            if not conds.get('check_vat', True):
                skip_vat_files.add(fname)
            if not conds.get('check_company', True):
                skip_company_files.add(fname)
            if not conds.get('check_invoice_detail', True):
                skip_invoice_files.add(fname)

        # Re-evaluate with combined total (receipt + cash bill if passed)
        cbc = result.get('cash_bill_check', {})
        # Python cross-verify for cash bill total
        py_cv_total2 = self._cross_verify_cash_bill_total(result)
        cbc_reg2 = cbc.get('registered_total', 0)
        cbc_reg2 = cbc_reg2 if isinstance(cbc_reg2, (int, float)) else 0
        py_cv_match2 = (py_cv_total2 > 0 and cbc_reg2 > 0 and abs(py_cv_total2 - cbc_reg2) < 1.0)
        cbc_ai_pass2 = cbc.get('pass', False)
        # ─── OLD LOGIC (เก็บไว้ก่อนตามคำสั่ง) ──────────────────────────────
        # cash_bill_ok = (not cbc.get('required', False)) or cbc_ai_pass2 or (
        #     py_cv_match2 and cbc.get('description_or_amount_matches', False)
        # )
        # ─── NEW LOGIC: เทียบยอด cash_bill_ids กับ price_unit ใน clear_ids ──
        _cb_match3 = self._check_cash_bill_match_detail()
        cash_bill_ok = self._cash_bill_pass(result)
        ac_data = result.get('amount_check', {})
        # ใช้ Python sum (เชื่อถือได้กว่า AI's receipt_total) — สอดคล้องกับ display Section 2
        r_total = self._python_sum_receipt_total(result)
        if r_total == 0:
            _ai_rt3 = ac_data.get('receipt_total', 0)
            r_total = _ai_rt3 if isinstance(_ai_rt3, (int, float)) else 0
        s_total = ac_data.get('system_total', 0)
        s_total = s_total if isinstance(s_total, (int, float)) else 0
        # WHT adjustment: if WHT > 0, use Untaxed + Tax instead of Total
        _wht3 = self.wht_amount or 0
        if _wht3 > 0:
            _untaxed3 = self.untaxed_amount or 0
            _tax3 = self.tax_amount or 0
            if _untaxed3 > 0:
                s_total = _untaxed3 + _tax3
        cb_total = 0
        # ใช้ cash_bill_ok (logic ใหม่) แทน AI's pass/cross-verify
        if cbc.get('required', False) and cash_bill_ok:
            cb_total = sum((cb.amount or 0) + (cb.vat_amount or 0) for cb in self.cash_bill_ids)
            if not cb_total:
                cb_total = cbc_reg2
        # ใบรับรองแทนใบเสร็จ — ตัดสินอัตโนมัติว่านับเข้า combined ไหม
        sub_resolution3 = self._resolve_receipt_substitutes(result, r_total, s_total)
        sub_total3 = sub_resolution3['amount_to_count']
        combined = r_total + cb_total + sub_total3
        amount_ok = abs(combined - s_total) < 1.0 if s_total > 0 else ac_data.get('matches', False)

        rc_data = result.get('receipt_check', {})
        dc_data = result.get('description_check', {})
        tc_data = result.get('tax_in_detail_check', {})
        cnc_data = result.get('company_name_check', {})
        rc_ok = rc_data.get('found', False) and rc_data.get('clear', False)
        dc_ok = dc_data.get('matches_detail', False) or not dc_data.get('has_description', False)
        # Utility address check (Python: Analytic Account vs Partner)
        uac_ok2, _uac_items2 = self._check_utility_analytic_partner()

        # Python fallback for VAT exemption: deposit slip exempt
        rc_files2 = [f for f in result.get('receipt_check', {}).get('receipt_files', []) if isinstance(f, dict)]
        py_all_deposit2 = len(rc_files2) > 0 and all(
            'deposit' in (f.get('type') or '').lower() for f in rc_files2
        )
        tc_ok = tc_data.get('detail_has_tax', False) or not tc_data.get('receipt_has_vat', False) or tc_data.get('vat_exempt_utility', False) or py_all_deposit2
        company_name_ok = (not cnc_data.get('required', False)) or cnc_data.get('pass', False)
        idc_data2 = result.get('invoice_detail_check', {})
        idc_ok2 = idc_data2.get('pass', True)

        # Transfer slip check (clear_amount vs deposit slip amount)
        clear_amt2 = self.clear_amount or 0
        slip_ok2 = True
        def _sf2(val):
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val.replace(',', ''))
                except (ValueError, TypeError):
                    return 0.0
            return 0.0
        if clear_amt2 > 0:
            from itertools import combinations as _comb2
            rc_d2 = result.get('receipt_check', {})
            slip_rf2 = [f for f in rc_d2.get('receipt_files', []) if isinstance(f, dict)]
            slip_sf2 = [f for f in rc_d2.get('skipped_files', []) if isinstance(f, dict)]
            # Collect all candidate amounts (skipped + deposit_slip types)
            _slip_cands2 = []
            for s in slip_sf2:
                _sa2 = _sf2(s.get('amount', 0))
                if _sa2 > 0:
                    _slip_cands2.append(_sa2)
            for s in slip_rf2:
                _st2 = (s.get('type') or '').lower()
                if 'deposit' in _st2 or 'slip' in _st2 or 'transfer' in _st2:
                    _sa2 = _sf2(s.get('amount', 0))
                    if _sa2 > 0:
                        _slip_cands2.append(_sa2)
            # Try all subsets to find combination matching Clear Amount
            for _r2 in range(1, len(_slip_cands2) + 1):
                if slip_ok2 is False:
                    for _combo2 in _comb2(_slip_cands2, _r2):
                        if abs(sum(_combo2) - clear_amt2) < 1.0:
                            slip_ok2 = True
                            break
                else:
                    break
            # Fallback: also check any single file (receipt or skipped) with matching amount/fee
            if not slip_ok2:
                all_f2 = slip_rf2 + slip_sf2
                slip_ok2 = any(
                    abs(_sf2(s.get('amount', 0)) - clear_amt2) < 1.0 or abs(_sf2(s.get('fee', 0)) - clear_amt2) < 1.0
                    for s in all_f2
                )

        # ── Apply receipt condition overrides (same logic as _format_result_html) ──
        _all_receipt_fnames2 = set(
            f.get('filename', '') for f in rc_files2 if isinstance(f, dict) and f.get('filename')
        )

        def _any_receipt_matches_skip2(skip_set):
            for rf in _all_receipt_fnames2:
                for sf in skip_set:
                    if rf == sf or rf.startswith(sf.rsplit('.', 1)[0]):
                        return True
            return False

        # ข้อ 2: Amount — skip if any receipt file unchecked
        if skip_amount_files and _any_receipt_matches_skip2(skip_amount_files):
            amount_ok = True
        # ข้อ 3: VAT — skip if any receipt file unchecked
        if skip_vat_files and _any_receipt_matches_skip2(skip_vat_files):
            tc_ok = True
        if self.env.cr.dbname == 'NPD_Logistics_New':
            tc_ok = True
        # ข้อ 6: Company — filter mismatched files
        if skip_company_files:
            cnc_mm = cnc_data.get('mismatched_files', [])
            cnc_mm_filtered = [mf for mf in cnc_mm
                               if isinstance(mf, dict) and mf.get('filename', '') not in skip_company_files]
            if not cnc_mm_filtered and cnc_mm:
                company_name_ok = True
        # ข้อ 7: Invoice Detail — filter items (use base-name matching for split files)
        def _fn_in_skip2(fname, skip_set):
            if not fname or not skip_set:
                return False
            if fname in skip_set:
                return True
            for sf in skip_set:
                sf_base = sf.rsplit('.', 1)[0]
                if sf_base and fname.startswith(sf_base):
                    return True
            return False
        if skip_invoice_files:
            idc_items_raw2 = idc_data2.get('items', [])
            idc_checked2 = [it for it in idc_items_raw2
                            if isinstance(it, dict) and not _fn_in_skip2(it.get('filename', ''), skip_invoice_files)]
            if idc_checked2:
                idc_ok2 = all(
                    it.get('invoice_number_match', False) and it.get('date_match', False) and it.get('partner_match', False)
                    for it in idc_checked2
                )
            else:
                idc_ok2 = True

        # Override rc_ok for cash-bill-only case
        _skipped3 = [f for f in rc_data.get('skipped_files', []) if isinstance(f, dict) and f.get('filename')]
        _has_hw3 = any(
            any(kw in (f.get('reason', '') or '').lower() for kw in ['ลายมือ', 'เขียนมือ', 'บิลเงินสด', 'handwritten', 'cash'])
            for f in _skipped3 if isinstance(f, dict)
        )
        _rc_files3 = [f for f in rc_data.get('receipt_files', []) if isinstance(f, dict) and f.get('filename')]
        _all_hw3 = _has_hw3 and not _rc_files3 and _skipped3
        if _all_hw3 and cash_bill_ok:
            rc_ok = True
        # ใบรับรองแทนใบเสร็จที่ระบบตัดสินแล้วว่าคลุมยอด = เอกสารใช้ได้
        # (สอดคล้องกับ has_valid_substitute ใน _format_result_html / is_pass อีก path)
        if sub_resolution3.get('decision') in ('count_substitute', 'cover_skip'):
            rc_ok = True
        # Override slip check if user skipped it
        _skip_slip3 = any(not conds.get('check_slip', True) for conds in condition_map.values())
        if _skip_slip3:
            slip_ok2 = True

        is_pass = amount_ok and rc_ok and tc_ok and analytic_pass and cash_bill_ok and company_name_ok and idc_ok2 and uac_ok2 and slip_ok2

        # Build the failed-only popup summary (full report still saved below)
        fail_items = self._collect_ai_fail_items(result, {
            'rc_ok': rc_ok,
            'amount_ok': amount_ok,
            'tc_ok': tc_ok,
            'analytic_pass': analytic_pass,
            'cash_bill_ok': cash_bill_ok,
            'company_name_ok': company_name_ok,
            'idc_ok': idc_ok2,
            'uac_ok': uac_ok2,
            'slip_ok': slip_ok2,
            'analytic_missing': analytic_missing,
            'combined': combined,
            'system_total': s_total,
        })
        summary_html = self._render_ai_fail_summary(is_pass, fail_items)

        # Check if any receipt has amount = 0 or mismatched with detail lines
        _has_zero = False
        _has_mismatch = False

        # Build set of known amounts from detail lines (unit_price and amount/price_subtotal)
        _detail_amounts = set()
        for _dl in self.clear_ids:
            if _dl.price_unit:
                _detail_amounts.add(round(abs(_dl.price_unit), 2))
            if _dl.price_subtotal:
                _detail_amounts.add(round(abs(_dl.price_subtotal), 2))

        for _f in rc_files2:
            if not isinstance(_f, dict):
                continue
            _amt = _f.get('amount')
            _ftype = (_f.get('type') or '').lower()
            # Skip deposit slips — they match by fee, not amount
            if 'deposit' in _ftype:
                continue
            if _amt is not None and isinstance(_amt, (int, float)):
                if _amt == 0:
                    _has_zero = True
                elif _detail_amounts and round(abs(_amt), 2) not in _detail_amounts:
                    _has_mismatch = True

        self.write({
            'ai_verified': is_pass,
            'ai_verify_date': fields.Datetime.now(),
            'ai_verify_uid': self.env.uid,
            # ผ่านหมด → รายงานเต็ม (ทุกข้อ), ไม่ผ่าน → เฉพาะข้อที่ไม่ผ่าน
            'ai_verify_result': result_html if is_pass else summary_html,
            'is_approved': is_pass,
            'ai_parsed_result': json.dumps(result, ensure_ascii=False),
            'has_zero_amount_receipt': _has_zero or _has_mismatch,
        })
        # Clear old corrections when re-running AI verify
        self.receipt_correction_ids.unlink()

        # Step 8: Open wizard popup with results
        wizard = self.env['ai.verify.wizard'].create({
            'advance_clear_id': self.id,
            'result_html': summary_html,
            'is_pass': is_pass,
            'raw_response': ai_response[:5000] if ai_response else '',
        })

        return {
            'name': _('ผลการตรวจสอบด้วย AI'),
            'type': 'ir.actions.act_window',
            'res_model': 'ai.verify.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
