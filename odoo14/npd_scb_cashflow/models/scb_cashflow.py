# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# แท็บ (ธนาคาร) ที่จะดึงจากสเปรดชีตเดียวกัน
#   code  = ค่าเก็บในฟิลด์ source (ใช้กรองเมนู)
#   sheet = ชื่อแท็บจริงในสเปรดชีต
#   name  = ชื่อที่แสดง
BANK_SHEETS = [
    {'code': 'scb', 'sheet': 'SCB', 'name': 'SCB'},
    {'code': 'kbank', 'sheet': 'Kbank', 'name': 'Kbank'},
    {'code': 'ktb', 'sheet': 'กรุงไทย', 'name': 'กรุงไทย'},
]
BANK_CODES = [b['code'] for b in BANK_SHEETS]


class ScbCashflow(models.Model):
    _name = 'npd.scb.cashflow'
    _description = 'กระแสเงินสดธนาคาร (จาก Google Sheet)'
    _order = 'date desc, account_no, key'
    _rec_name = 'key'

    source = fields.Selection(
        selection=[(b['code'], b['name']) for b in BANK_SHEETS],
        string='ธนาคาร (แท็บ)', index=True,
        help='แท็บต้นทางในสเปรดชีตที่แถวนี้ถูกดึงมา')
    key = fields.Char('คีย์', index=True, required=True)
    bank = fields.Char('ธนาคาร')
    account_no = fields.Char('เลขบัญชี', index=True)
    account_name = fields.Char('ชื่อบัญชี')
    date = fields.Date('วันที่')
    num_transactions = fields.Integer('จำนวนรายการ')
    money_in = fields.Monetary('เงินเข้า', currency_field='currency_id')
    money_out = fields.Monetary('เงินออก', currency_field='currency_id')
    net_flow = fields.Monetary('กระแสสุทธิ', currency_field='currency_id')
    balance_eod = fields.Monetary('ยอดคงเหลือสิ้นวัน', currency_field='currency_id')
    updated_at = fields.Char('อัปเดตเมื่อ (จากชีต)')
    currency_id = fields.Many2one(
        'res.currency', string='สกุลเงิน',
        default=lambda self: self.env.company.currency_id.id)

    _sql_constraints = [
        ('key_source_uniq', 'unique(source, key)', 'คีย์ (Key) ต้องไม่ซ้ำกันภายในธนาคารเดียวกัน'),
    ]

    # ------------------------------------------------------------------
    # ตัวช่วยแปลงค่า
    # ------------------------------------------------------------------
    @staticmethod
    def _to_float(val):
        if val in (None, ''):
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().replace(',', '').replace('฿', '').replace(' ', '')
        if s in ('', '-'):
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _to_int(self, val):
        return int(round(self._to_float(val)))

    @staticmethod
    def _parse_date(val):
        if val in (None, ''):
            return False
        s = str(val).strip()
        for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return False

    @api.model
    def _row_to_vals(self, row):
        """แปลง 1 แถวจากชีต (list) -> dict ของฟิลด์ (ยังไม่ใส่ source)"""
        def cell(i):
            return row[i] if i < len(row) else ''

        key = str(cell(0)).strip()
        if not key:
            return {}
        return {
            'key': key,
            'bank': str(cell(1)).strip(),
            'account_no': str(cell(2)).strip(),
            'account_name': str(cell(3)).strip(),
            'date': self._parse_date(cell(4)),
            'num_transactions': self._to_int(cell(5)),
            'money_in': self._to_float(cell(6)),
            'money_out': self._to_float(cell(7)),
            'net_flow': self._to_float(cell(8)),
            'balance_eod': self._to_float(cell(9)),
            'updated_at': str(cell(10)).strip(),
        }

    # ------------------------------------------------------------------
    # ดึงข้อมูลจาก Google Sheet (วนอ่านทุกแท็บ/ธนาคาร)
    # ------------------------------------------------------------------
    @api.model
    def _sync_from_sheet(self):
        """อ่านข้อมูลทุกแท็บใน BANK_SHEETS แล้ว upsert เข้าโมเดล -> คืนจำนวนแถวรวม"""
        Config = self.env['npd.scb.cashflow.config'].sudo()
        config = Config._get_config()
        service = Config._get_sheets_service(config)

        Model = self.sudo()
        # ลบแถวที่ไม่ได้อยู่ในธนาคารที่รู้จัก (เช่น ข้อมูลเก่าที่ยังไม่มี source)
        Model.search(['|', ('source', '=', False), ('source', 'not in', BANK_CODES)]).unlink()

        data_range = config.data_range or 'A2:K'
        total = 0
        errors = []
        for bank in BANK_SHEETS:
            try:
                rng = "'%s'!%s" % (bank['sheet'], data_range)
                rows = service.get_values(config.spreadsheet_id, rng)
            except Exception as e:
                errors.append("%s: %s" % (bank['name'], e))
                _logger.exception("Bank cashflow: sync failed for tab %s", bank['sheet'])
                continue

            existing = {r.key: r for r in Model.search([('source', '=', bank['code'])]) if r.key}
            incoming = set()
            for row in rows:
                vals = self._row_to_vals(row)
                if not vals.get('key'):
                    continue
                vals['source'] = bank['code']
                key = vals['key']
                incoming.add(key)
                rec = existing.get(key)
                if rec:
                    rec.write(vals)
                else:
                    # ชีตมีคีย์ซ้ำในแท็บเดียวกันได้ ต้องจำแถวที่เพิ่งสร้าง ไม่งั้น DB ใหม่ชน unique
                    existing[key] = Model.create(vals)
                total += 1

            # ลบแถวเก่าของธนาคารนี้ที่ไม่มีในชีตแล้ว (เฉพาะเมื่อดึงมาได้จริง)
            if incoming:
                stale = Model.search([
                    ('source', '=', bank['code']),
                    ('key', 'not in', list(incoming)),
                ])
                if stale:
                    stale.unlink()

        config.sudo().write({
            'last_sync': fields.Datetime.now(),
            'last_error': '\n'.join(errors) or False,
        })
        _logger.info("Bank cashflow: synced %s rows (errors: %s)", total, len(errors))

        if errors and total == 0:
            raise UserError(_("ดึงข้อมูลไม่สำเร็จ:\n%s") % '\n'.join(errors))
        return total

    @api.model
    def action_refresh_from_sheet(self):
        """เรียกจากปุ่มในเมนู Action ของตาราง (ดึงทุกธนาคาร)"""
        count = self._sync_from_sheet()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('กระแสเงินสดธนาคาร'),
                'message': _('ดึงข้อมูลสำเร็จ %s แถว (ทุกธนาคาร).') % count,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    @api.model
    def action_open_month_summary(self):
        """เปิด popup สรุปกระแสเงินสดเดือนปัจจุบัน (ตามบริษัท) ของธนาคารที่กำลังดูอยู่"""
        source = self.env.context.get('default_source')
        bank_map = {'scb': 'SCB', 'kbank': 'Kbank', 'ktb': 'กรุงไทย'}
        bank_label = bank_map.get(source, 'ทุกธนาคาร')
        view = self.env.ref('npd_scb_cashflow.view_npd_cashflow_summary_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('กระแสเงินสด เดือนปัจจุบัน — %s') % bank_label,
            'res_model': 'npd.scb.cashflow.summary.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': dict(self.env.context, default_source=source, summary_source=source),
        }

    @api.model
    def _cron_refresh(self):
        """เรียกจาก Scheduled Action"""
        config = self.env['npd.scb.cashflow.config'].sudo()._get_config()
        if not config.auto_sync:
            return
        try:
            self._sync_from_sheet()
        except Exception as e:
            _logger.error("Bank cashflow: cron sync failed: %s", e)
