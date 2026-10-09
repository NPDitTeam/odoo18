from odoo import _, fields, models
from odoo.exceptions import UserError

# เอกสารที่ยกเลิกด้วยการกลับรายการ: โมเดล -> ชื่อที่แสดงในข้อความ
SOURCE_MODELS = {
    'account.payment': 'ใบรับ/จ่ายชำระ',
    'account.voucher': 'ใบสำคัญ',
    'account.advance.clear': 'Advance Clear',
    'cash.payment': 'รับชำระเงินสด',
    'refund.payment': 'โอนคืนเงินลูกค้า',
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _npd_source_documents(self):
        """เอกสารต้นทางที่ใช้รายการบัญชีนี้เป็นรายการหลัก (move_id ตรงกัน)"""
        docs = []
        for model, label in SOURCE_MODELS.items():
            if model not in self.env or 'move_id' not in self.env[model]._fields:
                continue
            for rec in self.env[model].sudo().search([('move_id', 'in', self.ids)]):
                docs.append((label, rec.display_name))
        return docs

    def _npd_check_not_source_move(self):
        if self.env.context.get('npd_allow_draft'):
            return
        posted = self.filtered(lambda m: m.state == 'posted')
        docs = posted._npd_source_documents() if posted else []
        if docs:
            label, name = docs[0]
            raise UserError(_(
                'รายการบัญชีนี้เป็นของ%(label)s %(name)s\n'
                'รีเซตเป็นฉบับร่าง/ยกเลิกที่หน้ารายการบัญชีไม่ได้ เพราะจะทำให้เลขรายการบัญชีข้าม\n'
                'ให้กด "ยกเลิก" ที่เอกสารต้นทาง ระบบจะกลับขาบัญชีให้',
                label=label, name=name))

    def button_draft(self):
        self._npd_check_not_source_move()
        return super().button_draft()

    def button_cancel(self):
        self._npd_check_not_source_move()
        return super().button_cancel()

    def _npd_reversal_date(self):
        """ยกเลิกเดือนเดียวกับเอกสาร -> วันที่เดิม, ข้ามเดือนหรือวันที่เดิมถูกล็อก -> วันนี้"""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if (self.date.year, self.date.month) != (today.year, today.month):
            return today
        try:
            lock = self.company_id._get_user_fiscal_lock_date(self.journal_id)
        except Exception:
            lock = False
        if lock and self.date <= lock:
            return today
        return self.date

    def _npd_copy_tax_invoice_info(self, reversal):
        """คัดลอกเลข/วันที่ใบกำกับภาษีจากรายการเดิมไปแถวใบกำกับของรายการกลับขา (จับคู่ตามภาษี)"""
        self.ensure_one()
        if 'tax_invoice_ids' not in self._fields:
            return
        src = {}
        for ti in self.tax_invoice_ids:
            src.setdefault(ti.tax_line_id.id, []).append(ti)
        for ti in reversal.tax_invoice_ids:
            pool = src.get(ti.tax_line_id.id) or []
            orig = pool.pop(0) if pool else False
            vals = {}
            if not ti.tax_invoice_number:
                vals['tax_invoice_number'] = (orig and orig.tax_invoice_number) or '/'
            if not ti.tax_invoice_date:
                vals['tax_invoice_date'] = (orig and orig.tax_invoice_date) or reversal.date
            if vals:
                ti.write(vals)

    def _npd_cancel_by_reverse(self, reason=None):
        """ยกเลิกรายการบัญชีด้วยการกลับรายการ (ไม่ลบ ไม่รีเซต เลขเดิมคงอยู่)

        - ลงบัญชีแล้ว: สร้างรายการกลับขาในสมุดเดียวกัน ลงบัญชี และกระทบยอดคู่กับรายการเดิม
        - ยังเป็นร่าง: เปลี่ยนเป็นยกเลิก (เลขเดิมคงอยู่)
        """
        posted = self.filtered(lambda m: m.state == 'posted' and not m.reversal_move_ids)
        reversals = self.browse()
        if posted:
            defaults = [{
                'date': m._npd_reversal_date(),
                'ref': _('ยกเลิก %s%s') % (m.name, (': %s' % reason) if reason else ''),
            } for m in posted]
            ctx = dict(npd_allow_draft=True, skip_invoice_sync=True)
            reversals = posted.with_context(**ctx)._reverse_moves(defaults, cancel=False)
            for move, rev in zip(posted, reversals):
                # แถวใบกำกับภาษีของรายการกลับขาไม่มีเลข/วันที่ -> account_payment_invoice ไม่ยอมโพสต์ (เงียบ)
                # ใช้เลข/วันที่เดียวกับใบเดิม เพราะกลับรายการใบกำกับใบเดิม
                move._npd_copy_tax_invoice_info(rev)
            reversals.with_context(**ctx).action_post()
            not_posted = reversals.filtered(lambda r: r.state != 'posted')
            if not_posted:
                raise UserError(_('กลับรายการบัญชีไม่สำเร็จ (%s) กรุณาตรวจเลขที่/วันที่ใบกำกับภาษี')
                                % ', '.join(not_posted.reversed_entry_id.mapped('name')))
            for move, rev in zip(posted, reversals):
                # กระทบยอดคู่กับรายการเดิม แบบเดียวกับ _reverse_moves(cancel=True)
                groups = {}
                for line in (move.line_ids | rev.line_ids).filtered(lambda l: not l.reconciled):
                    groups.setdefault((line.account_id, line.currency_id), self.env['account.move.line'])
                    groups[(line.account_id, line.currency_id)] |= line
                for (account, _cur), lines in groups.items():
                    if account.reconcile or account.account_type in ('asset_cash', 'liability_credit_card'):
                        lines.with_context(move_reverse_cancel=True).reconcile()
                move.message_post(body=_('ยกเลิกด้วยการกลับรายการ: %s') % rev._get_html_link())
        drafts = self.filtered(lambda m: m.state == 'draft')
        if drafts:
            drafts.with_context(npd_allow_draft=True).button_cancel()
        return reversals
