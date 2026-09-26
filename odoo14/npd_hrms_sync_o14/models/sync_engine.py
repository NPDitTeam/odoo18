# -*- coding: utf-8 -*-
"""ตัวดึงข้อมูลจริงจาก Odoo 14 มาลง Odoo 18

วิธีทำงานโดยสรุป
----------------
1. ถามฝั่ง 14 ว่าโมเดลนี้มีช่องอะไรบ้าง แล้วเทียบกับช่องของฝั่ง 18
   เอาเฉพาะช่องที่มีทั้งสองฝั่ง ชนิดตรงกัน และเขียนได้จริง
   ทำแบบนี้แทนการไล่เขียนชื่อช่องทีละตัว เพราะสองฝั่งมีร่วมกันเป็นร้อยช่อง
   (พนักงานตรงกัน 77 ช่อง สลิปตรงกัน 106 ช่อง) เขียนมือมีแต่จะตกหล่น
2. ช่องที่เหลือซึ่งสองฝั่งเก็บคนละแบบ ให้ตัวแปลงเฉพาะของแต่ละหัวข้อจัดการ
   เช่น บริษัทที่ฝั่ง 14 เป็นข้อความแต่ฝั่ง 18 เป็นการอ้างถึงบริษัทจริง
3. หาว่าแถวนี้เคยยกมาแล้วหรือยัง ด้วยตารางจับคู่ก่อน ถ้าไม่มีค่อยหา
   ด้วยกุญแจธรรมชาติ ถ้ายังไม่มีอีกจึงสร้างใหม่
4. จดการจับคู่ไว้ พร้อมวันที่แก้ไขล่าสุดของฝั่ง 14 รอบถัดไปจะได้ข้ามแถว
   ที่ไม่ได้ขยับ

ทิศทางเดียว ไม่มีจุดไหนในไฟล์นี้เขียนกลับไปฝั่ง 14
"""
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .sync_spec import (SYNC_SPECS, GLOBAL_SKIP_FIELDS, MODEL_RENAMES,
                        FIELD_RENAMES, spec_o18_model)

_logger = logging.getLogger(__name__)


class SkipRow(Exception):
    """แถวนี้ยกมาไม่ได้ด้วยเหตุที่คาดไว้แล้ว ไม่ใช่ความผิดพลาด

    เช่นสาขาที่ฝั่ง 18 ยังไม่ได้เปิด ซึ่งคนต้องไปเปิดเองก่อน
    นับเป็น "ข้าม" พร้อมบอกว่าเป็นของอะไร จะได้ไปจัดการถูกจุด
    ต่างจากความผิดพลาดจริงที่ต้องไปดูว่าโค้ดหรือข้อมูลมีปัญหา
    """


# ฝั่ง 14 เก็บเวลาเข้าออกงานเป็นข้อความเวลาไทย ฝั่ง 18 เก็บเป็นวันเวลาแบบ UTC
# ตามมาตรฐาน Odoo จึงต้องลบออกเจ็ดชั่วโมงตอนยกมา
THAI_UTC_OFFSET = timedelta(hours=7)

# ฝั่ง 14 แยกประเภทงวดจ่ายเงินประกันไว้ห้าแบบ ฝั่ง 18 ตั้งใจเหลือสองแบบ
# เพราะสูตรคืนเงินสนใจแค่ว่า "เป็นเงินประกันที่ต้องคืน" หรือ
# "หักไปเป็นค่าธรรมเนียมแล้วไม่ต้องคืน" ค่าที่ไม่มีในฝั่ง 18 จึงยุบมาเป็น
# work_permit ทั้งหมด ยอดเงินยกมาครบ เสียแค่ป้ายประเภทย่อย
DEPOSIT_PAYMENT_TYPES = {
    'regular': 'regular',
    'work_permit_fee': 'work_permit',
    'visa_fee': 'work_permit',
    'document_service': 'work_permit',
    'other': 'work_permit',
}


class HrmsSyncEngine(models.AbstractModel):
    _name = 'npd.hrms.sync.engine'
    _description = 'ตัวดึงข้อมูล HR จาก Odoo 14'

    # ==================================================================
    # ตัวหลัก
    # ==================================================================
    @api.model
    def run_sync(self, config, incremental=True, only_models=None):
        """ดึงข้อมูลตามรายการใน SYNC_SPECS แล้วคืนใบบันทึกผล

        incremental=True จะข้ามแถวที่วันที่แก้ไขฝั่ง 14 ไม่ขยับตั้งแต่รอบก่อน
        only_models ใส่ชื่อโมเดลฝั่ง 14 ไว้เพื่อดึงเฉพาะบางหัวข้อ
        """
        config.ensure_one()
        log = self.env['npd.hrms.sync.log'].create({
            'config_id': config.id,
            'mode': 'incremental' if incremental else 'full',
            'state': 'running',
        })
        # ทำให้ผลรอบนี้เห็นได้ทันทีแม้รอบยังไม่จบ จะได้ตามดูระหว่างทางได้
        self.env.cr.commit()

        totals = {'fetched': 0, 'created': 0, 'updated': 0,
                  'skipped': 0, 'error': 0}
        failures = []

        for spec in sorted(SYNC_SPECS, key=lambda s: s['seq']):
            if only_models and spec['o14_model'] not in only_models:
                continue
            line = self.env['npd.hrms.sync.log.line'].create({
                'log_id': log.id,
                'sequence': spec['seq'],
                'name': spec['name'],
                'o14_model': spec['o14_model'],
                'o18_model': spec_o18_model(spec),
            })
            # commit ใบบันทึกก่อนเริ่มทำงาน ไม่งั้นถ้าหัวข้อนี้พลาดแล้วต้อง rollback
            # ใบบันทึกจะหายไปพร้อมกัน แล้วจะไม่มีใครรู้ว่าหัวข้อนี้พลาดเพราะอะไร
            self.env.cr.commit()
            try:
                result = self._sync_one(config, spec, incremental)
                line.write(dict(result, state=(
                    'partial' if result.get('error_count') else 'done')))
                for key in totals:
                    totals[key] += result.get(
                        {'created': 'created_count', 'updated': 'updated_count',
                         'skipped': 'skipped_count', 'error': 'error_count'}
                        .get(key, key), 0)
                if result.get('message'):
                    failures.append('%s: %s' % (spec['name'], result['message']))
            except Exception as error:
                # หัวข้อหนึ่งพังไม่ควรทำให้ทั้งรอบหยุด ที่เหลือต้องได้ไปต่อ
                self.env.cr.rollback()
                _logger.exception('[HRMS-SYNC] หัวข้อ %s ล้มเหลว', spec['name'])
                line.write({'state': 'failed', 'message': str(error)})
                failures.append('%s: %s' % (spec['name'], error))
                totals['error'] += 1
            self.env.cr.commit()

        state = 'done'
        if failures and totals['created'] + totals['updated']:
            state = 'partial'
        elif failures:
            state = 'failed'

        log.write({
            'date_end': fields.Datetime.now(),
            'state': state,
            'fetched': totals['fetched'],
            'created_count': totals['created'],
            'updated_count': totals['updated'],
            'skipped_count': totals['skipped'],
            'error_count': totals['error'],
            'note': '\n'.join(failures) if failures else 'สำเร็จทุกหัวข้อ',
        })
        config.sudo().write({'last_sync': fields.Datetime.now()})
        self.env.cr.commit()

        # สลิปที่เพิ่งยกมาใหม่ทำให้รายงานเงินเดือนที่ออกไว้ล้าสมัยทันที
        # รีเฟรชให้เองทุกรอบ จะได้ไม่มีใครเปิดรายงานแล้วเห็นตัวเลขของเมื่อวาน
        # โดยไม่รู้ว่าข้อมูลขยับไปแล้ว
        try:
            self._refresh_payroll_reports()
        except Exception as error:
            _logger.warning('[HRMS-SYNC] รีเฟรชรายงานเงินเดือนไม่สำเร็จ (ข้ามไป): %s',
                            error)
        return log

    def _refresh_payroll_reports(self):
        """สร้างและรีเฟรชรายงานเงินเดือนให้ครบทุกงวดที่มีสลิป

        ทำหลังซิงก์จบ เพราะตัวเลขในรายงานคัดลอกมาจากสลิป ถ้าสลิปเปลี่ยน
        รายงานต้องเปลี่ยนตาม งวดไหนยังไม่เคยออกรายงานก็สร้างให้เลย
        """
        if 'payroll.report' not in self.env:
            return
        companies = self.env['res.company'].sudo().search([]).ids
        Report = self.env['payroll.report'].sudo().with_context(
            allowed_company_ids=companies)
        Slip = self.env['payroll.salary'].sudo().with_context(
            allowed_company_ids=companies)

        periods = sorted({(row['year'], row['month'])
                          for row in Slip.search_read([], ['year', 'month'])
                          if row.get('year') and row.get('month')})
        for year, month in periods:
            report = Report.search([('month', '=', month), ('year', '=', year),
                                    ('company_id', '=', False)], limit=1)
            if not report:
                report = Report.create({'month': month, 'year': year})
            report.action_refresh_lines()
            self.env.cr.commit()
        _logger.info('[HRMS-SYNC] รีเฟรชรายงานเงินเดือนแล้ว %s งวด', len(periods))

    @staticmethod
    def _clean_name(raw):
        """ล้างชื่อให้เทียบกันได้จริง

        ชื่อในทะเบียนถูกพิมพ์/วางมาจากหลายที่ จึงมีอักขระที่มองไม่เห็นติดมาด้วย
        เช่นรหัส 1322 มี zero-width space คั่นกลาง ทำให้เทียบตัวต่อตัวไม่ตรง
        ทั้งที่คนอ่านเห็นเป็นชื่อเดียวกัน (การลงเวลา 167 แถวตกไปเพราะเรื่องนี้)
        """
        text = raw or ''
        text = ''.join(ch for ch in text
                       if not (0x200b <= ord(ch) <= 0x200f
                               or ord(ch) in (0xfeff, 0x00ad)))
        return ' '.join(text.replace(' ', ' ').split())

    def _employee_name_index(self):
        """ดัชนี "ชื่อ นามสกุล" -> id พนักงาน สำหรับจับคู่แถวที่ไม่มีลิงก์

        ฝั่ง 14 มีแถวลงเวลาสองหมื่นกว่าแถวที่บันทึกชื่อคนไว้แต่ไม่ได้ผูกกับ
        ทะเบียนพนักงาน (ช่องพนักงานว่าง เหลือแต่ชื่อที่พิมพ์ไว้) ถ้าไม่จับคู่ให้
        ข้อมูลลงเวลาจะหายไปหนึ่งในสาม

        ชื่อที่ตรงกับพนักงานมากกว่าหนึ่งคนจะถูกตัดออกจากดัชนี เพราะเดาไม่ได้ว่า
        เป็นใคร และการลงเวลาไปผิดคนแย่กว่าการไม่มีข้อมูลแถวนั้น
        """
        index, clashes = {}, set()
        for employee in self._writable('employee.salary').search_read(
                [], ['firstname', 'lastname']):
            first = self._clean_name(employee.get('firstname'))
            last = self._clean_name(employee.get('lastname'))
            name = self._clean_name('%s %s' % (first, last))
            if not name:
                continue
            keys = {name}
            # ทะเบียนบางรายกรอกชื่อซ้ำลงทั้งช่องชื่อและช่องนามสกุล
            # (เช่น "Hlaing Myo Tun Hlaing Myo Tun") แต่ตอนลงเวลาบันทึกชื่อ
            # ไว้ชุดเดียว จึงเก็บชื่อชุดเดียวไว้เป็นคีย์สำรองด้วย
            if first and first == last:
                keys.add(first)
            for key in keys:
                if key in index and index[key] != employee['id']:
                    clashes.add(key)
                index[key] = employee['id']
        for name in clashes:
            index.pop(name, None)

        # เติมคีย์แบบไม่สนตัวพิมพ์ใหญ่เล็กและไม่สนช่องว่างไว้ด้วย
        # ชื่อพม่าที่เขียนเป็นภาษาไทยเว้นวรรคไม่เหมือนกันบ่อย เช่นทะเบียนเป็น
        # "เอมินอู" แต่ตอนลงเวลาพิมพ์ "เอ มิน อู" ซึ่งคนอ่านรู้ว่าคนเดียวกัน
        # ชื่อที่พับแล้วชนกันเองให้ตัดทิ้ง ตามหลักเดิมคือเดาไม่ได้ก็อย่าเดา
        folded, folded_clashes = {}, set()
        for name, employee_id in index.items():
            for key in (name.casefold(), name.replace(' ', '').casefold()):
                if key in folded and folded[key] != employee_id:
                    folded_clashes.add(key)
                folded[key] = employee_id
        for key in folded_clashes:
            folded.pop(key, None)
        for key, employee_id in folded.items():
            index.setdefault(key, employee_id)

        # ชื่อพ้องที่คนยืนยันเองมาทีหลังและทับของที่เดาอัตโนมัติได้
        # เพราะเป็นคำตอบจากคนที่รู้จริง ไม่ใช่การเดาจากตัวสะกด
        # (รวมถึงชื่อที่ระบบตัดทิ้งเพราะซ้ำกันหลายคน ก็ชี้ตัวได้ที่นี่)
        index.update(self.env['npd.hrms.sync.name.alias'].as_index())
        return index

    def _writable(self, model_name):
        """recordset ที่มองเห็นและเขียนได้ทุกบริษัท

        ฝั่ง 18 มีกฎว่าแต่ละคนเห็นเฉพาะข้อมูลของบริษัทที่ตัวเองเปิดใช้งานอยู่
        กฎนี้มีผลกับการค้นหาด้วย ไม่ใช่แค่หน้าจอ ถ้าไม่เปิดให้ครบทุกบริษัท
        การค้นของเดิมจะไม่เจอทั้งที่มีอยู่ แล้วระบบจะสร้างซ้ำขึ้นมาอีกแถว
        (เคยเกิดกับสิทธิ์ลาวันเสาร์ ได้สาขาละสองแถว คนละบริษัทกัน)

        sudo() อย่างเดียวไม่พอ เพราะรายการบริษัทที่เปิดอยู่มาจาก context
        ไม่ได้มาจากสิทธิ์ของผู้ใช้
        """
        companies = self.env['res.company'].sudo().search([]).ids
        return self.env[model_name].sudo().with_context(
            tracking_disable=True, mail_create_nolog=True, mail_notrack=True,
            npd_hrms_sync=True, allowed_company_ids=companies,
            # ฝั่ง 18 คำนวณสลิปใหม่ทุกครั้งที่สร้าง ซึ่งจะไปดึงค่าคอมจากแหล่งข้อมูล
            # ของฝั่ง 18 เอง (ที่ยังไม่มีข้อมูล) มาเขียนทับค่าที่ยกมาให้เป็นศูนย์
            # สลิปเก่าคือยอดที่จ่ายไปแล้ว ต้องเก็บตามที่ฝั่ง 14 บันทึกไว้เท่านั้น
            skip_payroll_recalculate=True,
            # ใบลาก็เช่นกัน การคิดวันหักใหม่จะให้ผลต่างจากที่หักไปแล้วจริง
            skip_leave_deduction=True,
            # ไม่ต้องให้สร้างข้อมูล ภ.ง.ด.1 ใหม่ระหว่างยกข้อมูล เดี๋ยวซ้ำกับของเดิม
            skip_pnd1_sync=True)

    # ==================================================================
    # ซิงก์หัวข้อเดียว
    # ==================================================================
    def _sync_one(self, config, spec, incremental):
        o14_model = spec['o14_model']
        o18_model = spec_o18_model(spec)
        # หัวข้อที่สองฝั่งเก็บคนละรูปแบบจนเทียบช่องต่อช่องไม่ได้ มีตัวจัดการของตัวเอง
        if spec.get('handler'):
            return getattr(self, spec['handler'])(config, spec, incremental)
        if o18_model not in self.env:
            return {'fetched': 0, 'created_count': 0, 'updated_count': 0,
                    'skipped_count': 0, 'error_count': 0,
                    'message': 'ฝั่ง 18 ยังไม่มีโมเดล %s จึงข้ามหัวข้อนี้' % o18_model}

        field_plan = self._build_field_plan(config, spec)
        # หัวข้อที่ฝั่ง 14 บันทึกชื่อคนไว้ด้วย ให้เตรียมดัชนีชื่อไว้จับคู่สำรอง
        spec['_name_index'] = (self._employee_name_index()
                               if 'username' in field_plan['read'] else {})
        known = self.env['npd.hrms.sync.map'].known_write_dates(o14_model) \
            if incremental else {}

        domain = self._build_domain(config, spec, incremental)
        counters = {'fetched': 0, 'created_count': 0, 'updated_count': 0,
                    'skipped_count': 0, 'error_count': 0}
        errors, skipped, warnings = [], [], []

        read_fields = sorted(set(field_plan['read']) | {'write_date'})
        for rows in config.search_read_batched(o14_model, domain, read_fields):
            counters['fetched'] += len(rows)
            for row in rows:
                if incremental and self._unchanged(row, known):
                    counters['skipped_count'] += 1
                    continue
                try:
                    # savepoint ต่อแถว — แถวที่พลาดถูกถอนคืนเฉพาะตัวเอง
                    # ถ้า rollback ทั้งก้อน แถวก่อนหน้าที่ทำสำเร็จแล้วจะหายไปด้วย
                    with self.env.cr.savepoint():
                        created = self._apply_row(config, spec, field_plan, row,
                                                  warnings)
                    counters['created_count' if created else 'updated_count'] += 1
                except SkipRow as reason:
                    counters['skipped_count'] += 1
                    if len(skipped) < 30:
                        skipped.append(str(reason))
                except Exception as error:
                    counters['error_count'] += 1
                    if len(errors) < 20:
                        errors.append('id %s: %s' % (row.get('id'), error))
            # commit ทีละชุด ถ้ารอบยาวแล้วหลุดกลางทาง ของที่ทำไปแล้วจะไม่หาย
            self.env.cr.commit()

        if spec.get('sync_deletes'):
            self._remove_deleted(config, spec, domain, counters, warnings)

        notes = []
        if skipped:
            notes.append('ยังไม่มีในฝั่ง 18 จึงข้ามไป (ต้องไปสร้างเองก่อน): '
                         + ', '.join(skipped))
        if warnings:
            notes.append('ยกมาแล้วแต่ต้องให้คนตามแก้: ' + '; '.join(warnings[:40]))
        if errors:
            notes.append('\n'.join(errors))
        if notes:
            counters['message'] = '\n'.join(notes)
        return counters

    # สัดส่วนสูงสุดที่ยอมให้ลบในรอบเดียว — เกินกว่านี้ถือว่าผิดปกติ ไม่ลบ
    MAX_DELETE_RATIO = 0.30

    def _remove_deleted(self, config, spec, domain, counters, warnings):
        """ลบระเบียนฝั่ง 18 ที่ต้นทางฝั่ง 14 ลบไปแล้ว

        ตัวซิงก์ยกข้อมูลมาทางเดียว เดิมจึงไม่เคยลบตาม ใบที่ถูกลบฝั่ง 14
        จะค้างฝั่ง 18 ตลอดไปแล้วทำให้ยอดในรายงานเกินจริงโดยไม่มีใครรู้
        (เคยค้างจริงสองใบ ใบหนึ่งเป็นบัญชีสาธิตยอด 30,110 บาท)

        เทียบเฉพาะขอบเขตเดียวกับที่เพิ่งดึงมา ไม่ใช่ทั้งตาราง ไม่งั้นงวดเก่า
        ที่อยู่นอกขอบเขตจะถูกเข้าใจผิดว่าถูกลบแล้วโดนลบตามไปด้วย

        ลบเฉพาะใบที่ตัวซิงก์เป็นคนสร้าง (มีในตารางจับคู่) ใบที่คนฝั่ง 18
        สร้างเองไม่ถูกแตะ
        """
        o14_model = spec['o14_model']
        Target = self._writable(spec_o18_model(spec))
        Map = self.env['npd.hrms.sync.map'].sudo()

        scope = Target.search(domain)
        if not scope:
            return 0
        links = Map.search([('o14_model', '=', o14_model),
                            ('res_id', 'in', scope.ids)])
        if not links:
            return 0

        alive = set(config.execute_kw(o14_model, 'search', [domain]))
        if not alive:
            # ฝั่ง 14 ตอบว่าไม่มีอะไรเลยทั้งที่ฝั่ง 18 มีอยู่ — น่าจะดึงไม่สำเร็จ
            # มากกว่าจะเป็นการลบจริง อย่าเพิ่งลบ รอรอบหน้า
            warnings.append('ข้ามการลบตามต้นทาง เพราะฝั่ง 14 ไม่คืนรายการใด '
                            'ทั้งที่ฝั่ง 18 มี %d ใบในขอบเขตนี้' % len(links))
            return 0

        doomed = links.filtered(lambda link: link.o14_id not in alive)
        if not doomed:
            return 0
        if len(doomed) > max(1, int(len(links) * self.MAX_DELETE_RATIO)):
            warnings.append('ข้ามการลบตามต้นทาง เพราะจะต้องลบถึง %d จาก %d ใบ '
                            'ซึ่งมากผิดปกติ ให้คนตรวจก่อน'
                            % (len(doomed), len(links)))
            return 0

        removed = 0
        for link in doomed:
            record = Target.browse(link.res_id).exists()
            label = link.res_id
            try:
                with self.env.cr.savepoint():
                    if record:
                        label = '%s งวด %s/%s' % (
                            getattr(record, 'employee_code', '') or link.res_id,
                            getattr(record, 'month', ''),
                            getattr(record, 'year', ''))
                        record.unlink()
                    link.unlink()
                removed += 1
                warnings.append('ลบตามต้นทาง: %s (ฝั่ง 14 ลบไปแล้ว)' % label)
            except Exception as error:
                counters['error_count'] += 1
                warnings.append('ลบตามต้นทางไม่สำเร็จ %s: %s'
                                % (label, str(error)[:120]))
        if removed:
            self.env.cr.commit()
            _logger.info('[HRMS-SYNC] %s: ลบตามต้นทาง %d ใบ', spec['name'], removed)
        counters['removed_count'] = removed
        return removed

    @staticmethod
    def _unchanged(row, known):
        """แถวนี้เคยยกมาแล้วและฝั่ง 14 ไม่ได้แก้อะไรอีกใช่ไหม"""
        previous = known.get(row.get('id'))
        if not previous:
            return False
        current = row.get('write_date')
        if not current:
            return False
        if isinstance(previous, str):
            return previous[:19] == str(current)[:19]
        return fields.Datetime.to_string(previous)[:19] == str(current)[:19]

    def _build_domain(self, config, spec, incremental=False):
        """เงื่อนไขการดึง — ตัดช่วงวันที่ถ้าหัวข้อนี้มีช่องวันที่

        หัวข้อที่ทำเครื่องหมาย recent_only ไว้ (ลงเวลา ใบลา ใบขอเวลาย้อนหลัง)
        จะอ่านเฉพาะรายการที่ถูกแก้ไขในช่วงไม่กี่วันล่าสุดเมื่อเป็นรอบประจำวัน
        เพราะรายการเก่าที่ผ่านรอบทำเงินเดือนไปแล้วไม่มีใครแก้อีก

        ใช้ "วันที่แก้ไขล่าสุด" เป็นตัวตัด ไม่ใช่วันที่ของรายการ เพราะใบลา
        ที่ยื่นไว้นานแล้วอาจเพิ่งถูกอนุมัติเมื่อวาน ซึ่งต้องยกมาด้วย
        ถ้าตัดด้วยวันที่ลา ใบนั้นจะหลุดไปเงียบ ๆ
        """
        domain = list(spec.get('domain') or [])

        if incremental and spec.get('recent_only') and config.recent_days > 0:
            cutoff = fields.Datetime.now() - timedelta(days=config.recent_days)
            domain.append(('write_date', '>=',
                           fields.Datetime.to_string(cutoff)))

        # สลิปเงินเดือนไม่ได้ดูวันที่แก้ไข แต่ดู "งวด" ของสลิปแทน
        # งวดที่ปิดจ่ายไปแล้วถือว่าจบ ไม่ต้องกวาดซ้ำทุกคืน รอบแรกดึงครบไปแล้ว
        if incremental and spec.get('current_period_only'):
            periods = self._recent_payroll_periods(config)
            if periods:
                domain.extend(self._periods_domain(periods))

        date_field = spec.get('date_field')
        if date_field and config.sync_from_date:
            domain.append((date_field, '>=', str(config.sync_from_date)))
        return domain

    @staticmethod
    def _recent_payroll_periods(config):
        """งวดเงินเดือนที่รอบประจำวันยังต้องตามดู

        งวดเงินเดือนไม่ตรงกับเดือนปฏิทิน รอบตัดคือ 25 ถึง 24 ดังนั้นตั้งแต่
        วันที่ 25 เป็นต้นไปถือว่าเข้างวดของเดือนถัดไปแล้ว
        """
        months = max(int(config.payroll_recent_months or 1), 1)
        today = fields.Date.context_today(config)
        month, year = today.month, today.year
        if today.day >= 25:
            month, year = (1, year + 1) if month == 12 else (month + 1, year)
        periods = []
        for _step in range(months):
            periods.append((month, year))
            month, year = (12, year - 1) if month == 1 else (month - 1, year)
        return periods

    @staticmethod
    def _periods_domain(periods):
        """โดเมน OR ของคู่ (เดือน, ปี) — ฝั่ง 14 เก็บสองช่องนี้เป็นข้อความ"""
        parts = ['|'] * (len(periods) - 1)
        for month, year in periods:
            parts += ['&', ('month', '=', str(month)), ('year', '=', str(year))]
        return parts

    # ==================================================================
    # หาว่าช่องไหนยกได้ตรง ๆ บ้าง
    # ==================================================================
    def _build_field_plan(self, config, spec):
        """เทียบช่องสองฝั่ง แล้วคืนว่าต้องอ่านอะไรและเขียนอะไร

        คืน dict
          read   : ช่องที่ต้องขอจากฝั่ง 14 (รวมช่องที่ตัวแปลงต้องใช้)
          direct : ช่องที่คัดลอกค่าได้ตรง ๆ
          m2o    : {ช่อง: โมเดลปลายทางฝั่ง 18} ต้องแปลงเลขข้ามฐาน
        """
        o14_model = spec['o14_model']
        o18_model = spec_o18_model(spec)
        remote = config.remote_fields(o14_model)
        local = self.env[o18_model]._fields

        limit_to = set(spec.get('fields') or [])
        extra_skip = set(spec.get('skip_fields') or [])
        renames = FIELD_RENAMES.get(o14_model, {})
        wanted_binaries = set(spec.get('binary_fields') or [])

        direct, m2o = [], {}
        for name, meta in remote.items():
            if name in GLOBAL_SKIP_FIELDS or name in extra_skip:
                continue
            if limit_to and name not in limit_to:
                continue
            if not meta.get('store'):
                continue
            if meta['type'] in ('one2many', 'many2many'):
                # ลูกจัดการแยกต่างหาก
                continue
            if meta['type'] == 'binary' and name not in wanted_binaries:
                # ไฟล์แนบไม่ยกมาโดยปริยาย เพราะไฟล์ใหญ่และทำให้รอบซิงก์ช้ามาก
                # ยกเฉพาะตัวที่หัวข้อนั้นระบุไว้ว่าจำเป็น เช่นรูปพนักงาน
                continue
            # ช่องเดียวกันแต่คนละชื่อ ต้องรู้ว่าชื่อฝั่ง 18 คืออะไรก่อนจะเทียบชนิด
            local_name = renames.get(name, name)
            local_field = local.get(local_name)
            if local_field is None or not local_field.store:
                continue
            if local_field.compute and not local_field.inverse:
                # ช่องที่ฝั่ง 18 คำนวณเอง เขียนทับไม่ได้และไม่ควรทับ
                continue
            if local_field.type != meta['type']:
                # ชนิดไม่ตรง ปล่อยให้ตัวแปลงของหัวข้อนั้นจัดการเอง
                continue
            if local_field.type == 'many2one':
                target = MODEL_RENAMES.get(meta.get('relation'), meta.get('relation'))
                if local_field.comodel_name != target:
                    continue
                m2o[name] = (local_name, target)
            else:
                direct.append((name, local_name))

        # สิ่งที่ขอจากฝั่ง 14 ต้องเป็นชื่อช่องของฝั่ง 14 ไม่ใช่ชื่อที่แมปแล้ว
        read = {remote_name for remote_name, _local_name in direct} | set(m2o)
        read |= set(spec.get('read_extra') or [])
        # ตัวแปลงเกือบทุกตัวต้องใช้ช่องพวกนี้ ขอมาเผื่อไว้เสมอถ้าฝั่ง 14 มี
        for helper in ('company', 'branch', 'employee_id', 'employee_code',
                       'checked_at', 'date_requested', 'user_id', 'username',
                       'leave_type', 'reason_type', 'approved_by', 'state'):
            if helper in remote:
                read.add(helper)
        return {'read': sorted(read), 'direct': direct, 'm2o': m2o}

    # ==================================================================
    # เขียนลงฝั่ง 18
    # ==================================================================
    def _apply_row(self, config, spec, field_plan, row, warnings=None):
        """ยกหนึ่งแถว — คืน True ถ้าสร้างใหม่ False ถ้าแก้ของเดิม"""
        o14_model = spec['o14_model']
        o18_model = spec_o18_model(spec)
        warnings = warnings if warnings is not None else []
        Target = self._writable(o18_model)

        values = self._row_to_values(spec, field_plan, row)
        transform = spec.get('transform')
        if transform:
            values = getattr(self, transform)(config, spec, row, values, warnings)
        if values is None:
            raise UserError(_('ตัวแปลงของหัวข้อนี้ตีกลับแถว id %s') % row.get('id'))

        record = self._find_target(spec, row, values, Target)
        if record:
            record.write(values)
            created = False
        else:
            if not spec.get('create', True):
                raise SkipRow(self._natural_key_text(spec, values))
            record = Target.create(values)
            created = True

        self.env['npd.hrms.sync.map'].remember(
            o14_model, row['id'], record,
            natural_key=self._natural_key_text(spec, values),
            o14_write_date=row.get('write_date'))

        if spec.get('children'):
            self._sync_children(config, spec, row, record)
        return created

    def _row_to_values(self, spec, field_plan, row):
        """แปลงแถวดิบจากฝั่ง 14 เป็นค่าที่เขียนลงฝั่ง 18 ได้"""
        values = {}
        for remote_name, local_name in field_plan['direct']:
            value = row.get(remote_name)
            values[local_name] = False if value is None else value
        Map = self.env['npd.hrms.sync.map']
        o18_model = spec_o18_model(spec)
        local = self.env[o18_model]._fields if o18_model in self.env else {}
        for remote_name, (local_name, target_model) in field_plan['m2o'].items():
            raw = row.get(remote_name)
            if not raw:
                values[local_name] = False
                continue
            remote_id = raw[0] if isinstance(raw, (list, tuple)) else raw
            source_model = self._source_model_for(target_model)
            resolved = Map.lookup(source_model, remote_id)
            if not resolved:
                field = local.get(local_name)
                if field is not None and field.required:
                    # ของที่ถูกอ้างถึงยังไม่ได้ยกมา (อาจติดปัญหาในหัวข้อของมันเอง)
                    # เขียนต่อไปจะได้แถวที่ชี้ไปที่ว่าง ซึ่งผิดกว่าการข้ามไว้ก่อน
                    # รอบถัดไปพอต้นทางถูกยกมาแล้ว แถวนี้จะตามมาเอง
                    raise SkipRow('%s ของฝั่ง 14 id %s ยังไม่ได้ยกมา'
                                  % (remote_name, remote_id))
            values[local_name] = resolved or False
        return values

    @staticmethod
    def _source_model_for(o18_model):
        """ย้อนจากชื่อโมเดลฝั่ง 18 กลับไปชื่อฝั่ง 14 เพื่อค้นตารางจับคู่"""
        for o14, o18 in MODEL_RENAMES.items():
            if o18 == o18_model:
                return o14
        return o18_model

    def _find_target(self, spec, row, values, Target):
        """หาว่าแถวนี้มีของเดิมอยู่แล้วไหม — ดูตารางจับคู่ก่อน แล้วค่อยดูกุญแจ"""
        mapped_id = self.env['npd.hrms.sync.map'].lookup(spec['o14_model'], row['id'])
        if mapped_id:
            existing = Target.browse(mapped_id).exists()
            if existing:
                return existing

        keys = spec.get('key') or []
        if not keys:
            return Target.browse()
        domain = []
        for key in keys:
            if key not in values:
                # กุญแจไม่อยู่ในค่าที่แปลงได้ แปลว่าแปลงไม่สำเร็จ อย่าเดามั่ว
                return Target.browse()
            domain.append((key, '=', values[key] or False))
        candidate = Target.search(domain, limit=1)
        if not candidate:
            return candidate

        # แถวที่กุญแจชี้มา ถูกระเบียนอื่นของฝั่ง 14 จองไว้แล้วหรือยัง
        #
        # กุญแจของบางหัวข้อไม่ได้แยกระเบียนได้จริง เช่นขอลงเวลาย้อนหลังใช้
        # (พนักงาน, วันที่ทำงาน, เหตุผล) แต่คนหนึ่งยื่นซ้ำวันเดียวกันเหตุผล
        # เดียวกันได้หลายใบ (ยื่นเข้า-ออกคนละใบ หรือโดนตีกลับแล้วยื่นใหม่)
        # ถ้าปล่อยให้จับคู่ตามกุญแจอย่างเดียว ใบที่สองจะไปเขียนทับใบแรก
        # แล้วข้อมูลหายไปเงียบ ๆ (เคยหายจริง 360 ใบ และใบลาอีก 121 ใบ)
        #
        # กุญแจยังมีประโยชน์ตอนจับคู่ครั้งแรกกับของที่ฝั่ง 18 มีอยู่ก่อนแล้ว
        # จึงเก็บไว้ แต่ถ้าแถวนั้นมีเจ้าของแล้วให้ถือว่าไม่เจอ ไปสร้างใบใหม่แทน
        owner = self.env['npd.hrms.sync.map'].sudo().search([
            ('o14_model', '=', spec['o14_model']),
            ('res_model', '=', spec_o18_model(spec)),
            ('res_id', '=', candidate.id),
        ], limit=1)
        if owner and owner.o14_id != row['id']:
            return Target.browse()
        return candidate

    @staticmethod
    def _natural_key_text(spec, values):
        return ' | '.join('%s=%s' % (k, values.get(k))
                          for k in (spec.get('key') or []))

    # ==================================================================
    # ลูกของระเบียน
    # ==================================================================
    def _sync_children(self, config, spec, parent_row, parent_record):
        """ยกลูกมาทั้งชุด — ลบของเดิมทิ้งแล้วสร้างใหม่

        บรรทัดในสลิปไม่มีกุญแจธรรมชาติของตัวเอง (ชื่อซ้ำกันได้ ยอดซ้ำกันได้)
        การจับคู่ทีละบรรทัดจึงเชื่อถือไม่ได้ ยกมาทั้งชุดตรงกว่าและเร็วกว่า
        ของเดิมที่ลบคือของที่เคยยกมาจากฝั่ง 14 เท่านั้น ไม่ใช่ของที่ฝั่ง 18 ทำเอง
        """
        Map = self.env['npd.hrms.sync.map']
        for child in spec['children']:
            child_o14 = child['o14_model']
            child_o18 = MODEL_RENAMES.get(child_o14, child_o14)
            if child_o18 not in self.env:
                continue
            Child = self._writable(child_o18)
            parent_field = child['parent_field']
            if parent_field not in Child._fields:
                continue

            old = Child.search([(parent_field, '=', parent_record.id)])
            if old:
                Map.search([('o14_model', '=', child_o14),
                            ('res_id', 'in', old.ids)]).unlink()
                old.unlink()

            plan = self._build_field_plan(config, {'o14_model': child_o14})
            read_fields = sorted(set(plan['read']) | {'write_date'})
            rows = config.execute_kw(
                child_o14, 'search_read',
                [[(parent_field, '=', parent_row['id'])], read_fields])
            for row in rows:
                values = self._row_to_values({'o14_model': child_o14}, plan, row)
                values[parent_field] = parent_record.id
                record = Child.create(values)
                Map.remember(child_o14, row['id'], record,
                             o14_write_date=row.get('write_date'))

    # ==================================================================
    # หัวข้อที่สองฝั่งเก็บคนละรูปแบบ ต้องมีตัวจัดการของตัวเอง
    # ==================================================================
    def _sync_leave_balance(self, config, spec, incremental):
        """โควตาวันลา — ฝั่ง 14 เก็บเป็นคอลัมน์ ฝั่ง 18 เก็บเป็นแถว

        ฝั่ง 14 ตาราง hr.leave.type.custom มีหนึ่งแถวต่อพนักงาน แล้วเอาประเภทลา
        ทั้งแปดประเภทมาเป็นคอลัมน์ (leave_sick_total, leave_vacation_total, ...)
        ฝั่ง 18 แยกประเภทลาเป็นตารางหลักของตัวเอง แล้วเก็บยอดเป็นหนึ่งแถว
        ต่อพนักงานต่อประเภทต่อปี เทียบช่องต่อช่องจึงทำไม่ได้ ต้องแตกแถวออกมา

        ตัวเชื่อมสองฝั่งคือ ``code`` ของประเภทลาฝั่ง 18 ซึ่งตั้งไว้ตรงกับชื่อ
        คอลัมน์ฝั่ง 14 พอดี เช่น code ``leave_sick`` คู่กับ ``leave_sick_total``

        ช่อง ``*_used`` ฝั่ง 14 เก็บชื่อประเภทลาเป็นข้อความ ไม่ใช่จำนวนวัน
        จำนวนที่ใช้ไปจึงคิดจาก ยอดทั้งหมด ลบ ยอดคงเหลือ
        """
        Balance = self._writable('hrms.leave.balance')
        leave_types = self.env['hrms.leave.type'].sudo().search([])
        if not leave_types:
            return {'fetched': 0, 'created_count': 0, 'updated_count': 0,
                    'skipped_count': 0, 'error_count': 0,
                    'message': 'ฝั่ง 18 ยังไม่มีประเภทการลา จึงยังยกโควตามาไม่ได้'}

        remote = config.remote_fields(spec['o14_model'])
        year = fields.Date.context_today(self).year
        Map = self.env['npd.hrms.sync.map']

        read_fields = ['id', 'employee_id', 'write_date']
        usable_types = []
        for leave_type in leave_types:
            code = (leave_type.code or '').strip()
            if not code:
                continue
            total_field = '%s_total' % code
            remaining_field = '%s_total_remaining' % code
            if total_field not in remote or remaining_field not in remote:
                continue
            usable_types.append((leave_type, total_field, remaining_field))
            read_fields += [total_field, remaining_field]

        if not usable_types:
            return {'fetched': 0, 'created_count': 0, 'updated_count': 0,
                    'skipped_count': 0, 'error_count': 0,
                    'message': 'ไม่มีประเภทลาไหนที่ code ตรงกับคอลัมน์ฝั่ง 14 '
                               'ต้องไปตั้ง code ของประเภทลาให้ตรงก่อน'}

        counters = {'fetched': 0, 'created_count': 0, 'updated_count': 0,
                    'skipped_count': 0, 'error_count': 0}
        errors, missing_employees = [], []

        for rows in config.search_read_batched(spec['o14_model'], [], read_fields):
            counters['fetched'] += len(rows)
            for row in rows:
                raw_employee = row.get('employee_id')
                remote_employee_id = raw_employee[0] \
                    if isinstance(raw_employee, (list, tuple)) else raw_employee
                employee_id = Map.lookup('employee.salary', remote_employee_id)
                if not employee_id:
                    # พนักงานคนนี้ยังไม่ได้ยกมา (อาจติดปัญหาในหัวข้อพนักงาน)
                    # ข้ามไปก่อน รอบถัดไปจะได้เอง ไม่ใช่ความผิดพลาดของหัวข้อนี้
                    counters['skipped_count'] += 1
                    if len(missing_employees) < 20:
                        missing_employees.append(str(remote_employee_id))
                    continue
                try:
                    with self.env.cr.savepoint():
                        for leave_type, total_field, remaining_field in usable_types:
                            total = row.get(total_field) or 0
                            remaining = row.get(remaining_field) or 0
                            values = {
                                'employee_id': employee_id,
                                'leave_type_id': leave_type.id,
                                'year': year,
                                'total': total,
                                'remaining': remaining,
                                'used': max(total - remaining, 0),
                            }
                            existing = Balance.search([
                                ('employee_id', '=', employee_id),
                                ('leave_type_id', '=', leave_type.id),
                                ('year', '=', year),
                            ], limit=1)
                            if existing:
                                existing.write(values)
                                counters['updated_count'] += 1
                            else:
                                Balance.create(values)
                                counters['created_count'] += 1
                except Exception as error:
                    counters['error_count'] += 1
                    if len(errors) < 20:
                        errors.append('แถว id %s: %s' % (row.get('id'), error))
            self.env.cr.commit()

        notes = []
        if missing_employees:
            notes.append('ข้ามเพราะยังไม่ได้ยกพนักงานคนนั้นมา (id ฝั่ง 14): '
                         + ', '.join(missing_employees))
        if errors:
            notes.append('\n'.join(errors))
        if notes:
            counters['message'] = '\n'.join(notes)
        return counters

    def _sync_checkin_distance(self, config, spec, incremental):
        """ระยะเช็คอินรายสาขา — ฝั่ง 14 เป็นตารางแยก ฝั่ง 18 เป็นช่องบนตัวสาขา

        ฝั่ง 14 เก็บพิกัดกับระยะที่อนุญาตไว้ในตารางของตัวเอง แล้วผูกกลับไปหาสาขา
        ส่วนฝั่ง 18 ย้ายมาเก็บบนสาขาโดยตรง เพราะเป็นคุณสมบัติของสาขาอยู่แล้ว
        ไม่ใช่รายการแยกต่างหาก จึงเทียบตารางต่อตารางไม่ได้ ต้องเขียนลงสาขาแทน

        แถวที่ยังไม่ได้ผูกสาขา (เช่นรายการทดสอบ) จะข้ามไป เพราะไม่รู้ว่าของสาขาไหน
        """
        Branch = self._writable('res.branch')
        Map = self.env['npd.hrms.sync.map']
        counters = {'fetched': 0, 'created_count': 0, 'updated_count': 0,
                    'skipped_count': 0, 'error_count': 0}
        errors, skipped = [], []

        read_fields = ['id', 'branch_id', 'branch_name', 'distance_meter',
                       'latitude', 'longitude', 'write_date']
        for rows in config.search_read_batched(spec['o14_model'], [], read_fields):
            counters['fetched'] += len(rows)
            for row in rows:
                raw = row.get('branch_id')
                remote_branch_id = raw[0] if isinstance(raw, (list, tuple)) else raw
                branch = Branch.browse(
                    Map.lookup('hr.branch.custom', remote_branch_id)).exists() \
                    if remote_branch_id else Branch.browse()
                if not branch:
                    # ไม่ได้ผูกสาขาไว้ ลองเทียบด้วยชื่อที่พิมพ์ไว้เป็นทางสำรอง
                    name = (row.get('branch_name') or '').strip()
                    branch = Branch.search([('name', '=', name)], limit=1) if name else branch
                if not branch:
                    counters['skipped_count'] += 1
                    if len(skipped) < 20:
                        skipped.append(row.get('branch_name') or 'id %s' % row.get('id'))
                    continue

                try:
                    with self.env.cr.savepoint():
                        branch.write({
                            'hr_checkin_latitude': (row.get('latitude') or '').strip(),
                            'hr_checkin_longitude': (row.get('longitude') or '').strip(),
                            'hr_checkin_radius': self._to_int(row.get('distance_meter')),
                        })
                        Map.remember(spec['o14_model'], row['id'], branch,
                                     natural_key=branch.name,
                                     o14_write_date=row.get('write_date'))
                    counters['updated_count'] += 1
                except Exception as error:
                    counters['error_count'] += 1
                    if len(errors) < 20:
                        errors.append('id %s: %s' % (row.get('id'), error))
            self.env.cr.commit()

        notes = []
        if skipped:
            notes.append('ข้ามเพราะยังไม่ได้ผูกสาขา: ' + ', '.join(skipped))
        if errors:
            notes.append('\n'.join(errors))
        if notes:
            counters['message'] = '\n'.join(notes)
        return counters

    @staticmethod
    def _to_int(value):
        """ฝั่ง 14 เก็บระยะเป็นข้อความ เช่น "50" หรือ "50 " — ฝั่ง 18 เป็นตัวเลข"""
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return 0

    # ==================================================================
    # ตัวแปลงเฉพาะหัวข้อ
    # ==================================================================
    def _resolve_branch(self, row, values):
        """สาขาฝั่ง 14 มีทั้งเลขอ้างอิงและชื่อเป็นข้อความ ใช้เลขก่อน ถ้าไม่มีค่อยใช้ชื่อ"""
        if values.get('branch_id'):
            return values
        name = (row.get('branch') or '').strip()
        if name:
            branch = self._writable('res.branch').search(
                [('name', '=', name)], limit=1)
            if branch:
                values['branch_id'] = branch.id
        return values

    def _tf_common(self, config, spec, row, values, warnings=None):
        """ตัวแปลงพื้นฐาน — บริษัท สาขา และรหัสพนักงาน"""
        o18_model = spec_o18_model(spec)
        local = self.env[o18_model]._fields

        warnings = warnings if warnings is not None else []
        raw_company = (row.get('company') or '').strip()
        if 'company_id' in local:
            company_id = self.env['npd.hrms.sync.company.map'].resolve(raw_company) \
                if raw_company else False

            # หลายตารางฝั่ง 14 ไม่มีช่องบริษัทของตัวเอง (เช่นสลิปเงินเดือน ลงเวลา)
            # แต่ผูกกับพนักงานอยู่ ซึ่งรู้บริษัทแน่นอน จึงยึดบริษัทของพนักงานแทน
            # ถ้าไม่ทำ ทุกแถวจะไปกองที่บริษัทสำรองบริษัทเดียว แล้วรายงานที่แยก
            # ตามบริษัทจะผิดทั้งหมด ทั้งที่ยอดรวมทั้งเครือยังดูถูกต้อง
            if not company_id and values.get('employee_id'):
                employee = self._writable('employee.salary').browse(
                    values['employee_id']).exists()
                if employee and employee.company_id:
                    company_id = employee.company_id.id

            if company_id:
                values['company_id'] = company_id
            elif 'company' in row:
                # ฝั่ง 18 บังคับว่าทุกแถวต้องสังกัดบริษัท ถ้าไม่ใส่ Odoo จะเติม
                # บริษัทหลักให้เองเงียบ ๆ แล้วข้อมูลไปกองผิดบริษัทโดยไม่มีใครรู้
                # จึงใส่บริษัทสำรองที่ตั้งไว้ และแจ้งชื่อออกมาทุกรอบให้ตามแก้
                fallback = config.fallback_company_id
                if fallback:
                    values['company_id'] = fallback.id
                label = row.get('employee_code') or row.get('id')
                if raw_company:
                    warnings.append('%s: บริษัท "%s" ของฝั่ง 14 ยังไม่ได้จับคู่ '
                                    'ต้องไปจับคู่ที่หน้าจอจับคู่บริษัท' % (label, raw_company))
                else:
                    warnings.append('%s: ฝั่ง 14 ไม่ได้ระบุบริษัท จึงใส่ "%s" ไว้ก่อน '
                                    'ต้องไปแก้ให้ถูกบริษัท'
                                    % (label, fallback.name if fallback
                                       else 'บริษัทหลักตามค่าตั้งต้น'))

        if 'branch_id' in local and not values.get('branch_id'):
            values = self._resolve_branch(row, values)

        # แถวที่ฝั่ง 14 ไม่ได้ผูกพนักงานไว้ ให้จับคู่จากชื่อที่บันทึกไว้แทน
        if 'employee_id' in local and not values.get('employee_id'):
            raw_name = self._clean_name(row.get('username'))
            index = spec.get('_name_index') or {}
            # ชื่อฝรั่งฝั่ง 14 พิมพ์ใหญ่เล็กไม่ตรงกับทะเบียนอยู่บ่อย
            # (เช่น "Aung ko sint" กับ "Aung Ko Sint") เทียบแบบไม่สนตัวพิมพ์
            # จึงจับคู่ได้เพิ่มโดยไม่เสี่ยงจับผิดคน เพราะชื่อซ้ำถูกตัดจากดัชนีแล้ว
            matched = (index.get(raw_name)
                       or index.get(raw_name.casefold())
                       or index.get(raw_name.replace(' ', '').casefold()))
            # บางแถวฝั่ง 14 ใส่ "รหัสพนักงาน" ลงช่องชื่อแทนชื่อจริง
            # เป็นตัวเลขล้วนจึงแยกออกจากชื่อคนได้ชัด ไม่ต้องเดา
            if not matched and raw_name.isdigit():
                by_code = self._writable('employee.salary').search(
                    [('employee_code', '=', raw_name)], limit=1)
                matched = by_code.id if by_code else None
            if matched:
                values['employee_id'] = matched
            elif local['employee_id'].required:
                raise SkipRow('ฝั่ง 14 ไม่ได้ผูกพนักงานไว้ และชื่อ "%s" '
                              'หาคู่ไม่ได้หรือซ้ำกันหลายคน'
                              % (raw_name or '(ไม่มีชื่อ)'))

        # รหัสพนักงานยึดของฝั่ง 14 เสมอ ไม่สร้างใหม่
        if 'employee_code' in local and not values.get('employee_code'):
            employee_id = values.get('employee_id')
            if employee_id:
                employee = self.env['employee.salary'].sudo().browse(employee_id)
                if employee.exists() and employee.employee_code:
                    values['employee_code'] = employee.employee_code
        return values

    def _tf_employee(self, config, spec, row, values, warnings=None):
        """พนักงาน — รหัสต้องตรงกับฝั่ง 14 เป๊ะ และต้องมีรหัสเสมอ

        สองเรื่องที่ฝั่ง 14 ปล่อยผ่านมาได้แต่ฝั่ง 18 ไม่ยอมรับ ต้องจัดการที่นี่
        ไม่ปล่อยให้ทั้งแถวพลาด เพราะคนหายจากระบบเสียหายกว่าข้อมูลไม่ครบบางช่อง
        """
        warnings = warnings if warnings is not None else []
        values = self._tf_common(config, spec, row, values, warnings)
        code = (row.get('employee_code') or '').strip()
        if not code:
            raise UserError(_(
                'พนักงาน id %s ของฝั่ง 14 ไม่มีรหัสพนักงาน ยกมาไม่ได้ '
                'เพราะรหัสคือกุญแจที่ใช้จับคู่และใช้ล็อกอินแอป') % row.get('id'))
        values['employee_code'] = code

        # ฝั่ง 18 บังคับว่า PIN ต้องเป็นตัวเลขหกหลัก ฝั่ง 14 มีบางคนเป็น 0 หรือห้าหลัก
        # ยกมาโดยไม่ใส่ PIN แล้วแจ้งให้ตั้งใหม่ ดีกว่าทิ้งคนนั้นไว้ไม่ยกมาเลย
        pin = (values.get('pin') or '').strip()
        if pin and not (pin.isdigit() and len(pin) == 6):
            warnings.append('รหัส %s: PIN ฝั่ง 14 เป็น "%s" ใช้ไม่ได้ '
                            'ต้องตั้ง PIN ใหม่ให้' % (code, pin))
            values.pop('pin', None)
            pin = ''

        # ฝั่ง 14 ไม่ได้ห้าม PIN ซ้ำ จึงมีหลายคนใช้ PIN เดียวกันอยู่จริง
        # ฝั่ง 18 ใช้ PIN เป็นตัวล็อกอิน ปล่อยให้ซ้ำไม่ได้เพราะจะเข้าผิดคน
        # คนแรกที่ยกมาได้ PIN ไป คนที่ซ้ำยกมาโดยไม่มี PIN แล้วแจ้งให้ตั้งใหม่
        if pin:
            clash = self._writable('employee.salary').search([
                ('pin', '=', pin), ('employee_code', '!=', code),
            ], limit=1)
            if clash:
                warnings.append('รหัส %s: PIN %s ซ้ำกับรหัส %s (ฝั่ง 14 ปล่อยให้ซ้ำได้) '
                                'ยกมาโดยไม่ใส่ PIN ต้องตั้ง PIN ใหม่ให้คนนี้'
                                % (code, pin, clash.employee_code or clash.id))
                values.pop('pin', None)

        # ฝั่ง 18 บังคับว่าคนที่สถานะไม่ใช้งานต้องมีวันที่ออกจากงาน
        # ห้ามเดาวันให้เอง เพราะวันที่ออกเป็นตัวกำหนดสูตรคืนเงินประกันการทำงาน
        # เดาผิดวันเดียวก็คืนเงินผิดหรือคืนซ้ำได้ จึงยกมาเป็นยังใช้งานไว้ก่อน
        # แล้วแจ้งชื่อให้ HR ไปเติมวันที่ออกเอง
        if values.get('status') == 'inactive' and not values.get('resign_date'):
            warnings.append('รหัส %s: ฝั่ง 14 สถานะพ้นสภาพแต่ไม่มีวันที่ออกจากงาน '
                            'ยกมาเป็นยังใช้งานไว้ก่อน ต้องเติมวันที่ออกแล้วปิดสถานะเอง'
                            % code)
            values['status'] = 'active'

        # ฝั่ง 18 มีช่องเปิดปิดการใช้งานซึ่งฝั่ง 14 ไม่มี คนที่ยกมาให้ใช้งานได้ปกติ
        if 'active' in self.env['employee.salary']._fields:
            values.setdefault('active', True)
        return values

    def _tf_payroll(self, config, spec, row, values, warnings=None):
        """สลิปเงินเดือน — ถือเป็นประวัติที่ปิดยอดแล้ว ห้ามให้ฝั่ง 18 คำนวณทับ

        ค่าคอมมิชชั่นสองฝั่งเก็บคนละแบบ ฝั่ง 14 เป็นบรรทัดรายได้ในสลิป
        ส่วนฝั่ง 18 มีเอนจินคำนวณและเก็บลงช่องของตัวเอง สลิปที่ยกมาจึงไม่ไป
        แตะช่องค่าคอมของฝั่ง 18 เลย ปล่อยให้เป็นศูนย์ ยอดที่จ่ายจริงอยู่ใน
        บรรทัดรายได้ที่ยกมาพร้อมกันแล้ว
        """
        values = self._tf_common(config, spec, row, values, warnings)
        local = self.env['payroll.salary']._fields
        if 'state' in local:
            selection = dict(local['state'].selection or [])
            if 'done' in selection:
                values['state'] = 'done'
        # กันไว้อีกชั้น เผื่อแผนช่องดันหยิบช่องค่าคอมมาได้
        for name in list(values):
            if name.startswith('commission_'):
                values.pop(name)
        return values

    def _tf_period(self, config, spec, row, values, warnings=None):
        """รอบทำเงินเดือน — ชุดสถานะสองฝั่งไม่เหมือนกัน

        ฝั่ง 14 มีสถานะเดียวที่ใช้จริงคือ done ซึ่งหมายถึงรอบที่ปิดและจ่ายแล้ว
        ฝั่ง 18 แยกละเอียดเป็น ร่าง/คำนวณแล้ว/อนุมัติแล้ว/จ่ายแล้ว/ยกเลิก
        รอบที่ยกมาจากฝั่ง 14 จึงลงเป็น "จ่ายแล้ว" ตรงกับความหมายเดิมที่สุด
        """
        values = self._tf_common(config, spec, row, values, warnings)
        mapping = {'done': 'paid', 'draft': 'draft', 'cancel': 'cancelled'}
        raw_state = row.get('state')
        selection = dict(self.env['payroll.period']._fields['state'].selection or {})
        target = mapping.get(raw_state, raw_state)
        values['state'] = target if target in selection else 'paid'
        return values

    def _resolve_approver(self, row, values, local):
        """ผู้อนุมัติ — ฝั่ง 14 เก็บเป็นชื่อคน ฝั่ง 18 อ้างถึงพนักงานจริง

        จับคู่ด้วยชื่อ ถ้าชื่อซ้ำหรือหาไม่เจอก็ปล่อยว่าง ช่องนี้ไม่บังคับ
        และการเดาผิดคนแย่กว่าการไม่รู้ว่าใครอนุมัติ
        """
        raw = (row.get('approved_by') or '').strip()
        if 'approved_by' not in local:
            return values
        if not raw:
            values['approved_by'] = False
            return values
        Employee = self._writable('employee.salary')
        found = Employee.search([('firstname', '=', raw)], limit=2)
        if len(found) != 1:
            # ลองแบบชื่อเต็ม "ชื่อ นามสกุล" ซึ่งเป็นรูปที่ฝั่ง 14 ใช้บ่อยกว่า
            parts = raw.split()
            if len(parts) >= 2:
                found = Employee.search([('firstname', '=', parts[0]),
                                         ('lastname', '=', ' '.join(parts[1:]))], limit=2)
        values['approved_by'] = found.id if len(found) == 1 else False
        return values

    def _tf_leave(self, config, spec, row, values, warnings=None):
        """การลา — ฝั่ง 14 เก็บประเภทลาเป็นข้อความ ฝั่ง 18 อ้างถึงประเภทลาจริง

        ชื่อประเภทลาสองฝั่งตรงกันทุกตัว (ลากิจได้รับค่าจ้าง ลาป่วยมีใบรับรองแพทย์
        สิทธิหยุดวันเสาร์ ฯลฯ) จับคู่ด้วยชื่อได้เลย ประเภทไหนยังไม่มีฝั่ง 18
        จะสร้างให้ เพราะถ้าไม่สร้าง ใบลาทั้งใบจะยกมาไม่ได้ และประวัติการลาจะขาด
        """
        warnings = warnings if warnings is not None else []
        values = self._tf_common(config, spec, row, values, warnings)
        local = self.env['hr.attendance.branch.leave']._fields
        values = self._resolve_approver(row, values, local)

        name = (row.get('leave_type') or '').strip()
        if name:
            LeaveType = self._writable('hrms.leave.type')
            leave_type = LeaveType.search([('name', '=', name)], limit=1)
            if not leave_type:
                leave_type = LeaveType.create({'name': name})
                warnings.append('สร้างประเภทการลา "%s" ให้ใหม่ '
                                'เพราะฝั่ง 18 ยังไม่มี' % name)
            values['leave_type_id'] = leave_type.id
            if 'leave_type_name' in local:
                values['leave_type_name'] = name
            if leave_type.code == 'leave_saturday':
                values = self._fix_saturday_leave(row, values, warnings)
        return values

    @staticmethod
    def _fix_saturday_leave(row, values, warnings):
        """ซ่อมใบสิทธิหยุดวันเสาร์ที่ฝั่ง 14 กรอกวันสิ้นสุดเพี้ยน

        สิทธิหยุดวันเสาร์คือหยุดวันเสาร์หนึ่งวัน แต่ฝั่ง 14 มีใบที่ช่องวันสิ้นสุด
        ถูกทิ้งไว้เป็น "วันที่กรอกใบ" แทนวันที่หยุดจริง เช่นเริ่มเสาร์ 22 ส.ค.
        แต่สิ้นสุด 25 ส.ค. (วันที่กดบันทึก) ถ้ายกมาตรง ๆ สิทธิ์จะถูกหักยาว
        ทั้งช่วงแทนที่จะหักวันเดียว

        ยึดวันเสาร์เป็นวันที่หยุดจริง แล้วบีบให้เป็นวันเดียว
        ใบที่ไม่มีวันเสาร์อยู่เลยไม่เดาให้ ปล่อยให้ตีกลับแล้วรายงานชื่อ
        """
        start = values.get('leave_start_date')
        end = values.get('leave_end_date')
        if not start or not end or start == end:
            return values
        start_date = fields.Date.to_date(start)
        end_date = fields.Date.to_date(end)
        if not start_date or not end_date:
            return values
        if start_date.weekday() == 5:
            saturday = start_date
        elif end_date.weekday() == 5:
            saturday = end_date
        else:
            return values
        values['leave_start_date'] = saturday
        values['leave_end_date'] = saturday
        warnings.append(
            'ใบลา id %s: สิทธิหยุดวันเสาร์ฝั่ง 14 ลงช่วง %s ถึง %s '
            'ซึ่งวันสิ้นสุดเป็นวันที่กรอกใบ ไม่ใช่วันหยุดจริง '
            'ยกมาเป็นวันเสาร์ %s วันเดียวตามความหมายของสิทธิ์'
            % (row.get('id'), start_date.strftime('%d/%m/%Y'),
               end_date.strftime('%d/%m/%Y'), saturday.strftime('%d/%m/%Y')))
        return values

    def _tf_deposit_payment(self, config, spec, row, values, warnings=None):
        """งวดการจ่ายเงินประกัน — ยุบประเภทค่าธรรมเนียมให้เข้ากับฝั่ง 18

        ฝั่ง 14 แยกไว้ห้าแบบ (รายเดือน / ค่าต่อใบอนุญาตทำงาน / ค่าวีซ่า /
        ค่าทำเอกสาร / อื่นๆ) ฝั่ง 18 เหลือสองแบบตามที่สูตรคืนเงินต้องใช้จริง
        ถ้าส่งค่าเดิมไปตรงๆ ฝั่ง 18 จะตีกลับทั้งแถว (เคยตกไป 26 งวด)
        ยอดเงินและเดือนที่หักยกมาครบ เสียแค่ป้ายประเภทย่อย จึงแจ้งชื่อไว้
        """
        warnings = warnings if warnings is not None else []
        values = self._tf_common(config, spec, row, values, warnings)
        raw = (row.get('payment_type') or 'regular')
        raw = raw.strip() if isinstance(raw, str) else 'regular'
        mapped = DEPOSIT_PAYMENT_TYPES.get(raw, 'work_permit')
        if raw != mapped:
            warnings.append(
                'งวดจ่าย id %s: ฝั่ง 14 เป็น "%s" ซึ่งฝั่ง 18 ไม่มี '
                'ยกมาเป็น "Work Permit / อื่นๆ" ยอดเงินเท่าเดิม'
                % (row.get('id'), raw))
        values['payment_type'] = mapped
        return values

    def _tf_manual(self, config, spec, row, values, warnings=None):
        """ขอลงเวลาย้อนหลัง — ฝั่ง 14 พิมพ์เหตุผลเป็นข้อความอิสระ

        ฝั่ง 18 ทำเหตุผลเป็นตารางหลักเพื่อให้เลือกจากรายการเดียวกันทุกสาขา
        เหตุผลที่ฝั่ง 14 มีอยู่จริงสิบกว่าแบบจึงถูกสร้างเป็นรายการให้ตามที่พบ
        ไม่ใช่ทิ้งใบนั้นไป เพราะใบขอเวลาย้อนหลังเป็นหลักฐานการจ่ายเบี้ยเลี้ยง
        """
        warnings = warnings if warnings is not None else []
        values = self._tf_common(config, spec, row, values, warnings)
        local = self.env['hr.manual.time.log']._fields
        values = self._resolve_approver(row, values, local)

        name = (row.get('reason_type') or '').strip() or 'ไม่ระบุ'
        Reason = self._writable('hrms.manual.time.reason')
        reason = Reason.search([('name', '=', name)], limit=1)
        if not reason:
            reason = Reason.create({'name': name})
            warnings.append('สร้างเหตุผล "%s" ให้ใหม่ เพราะฝั่ง 18 ยังไม่มี' % name)
        values['reason_type_id'] = reason.id
        if 'reason_type_name' in local:
            values['reason_type_name'] = name
        return values

    def _tf_attendance(self, config, spec, row, values, warnings=None):
        """เข้างานออกงาน — เวลาไทยที่เป็นข้อความ ต้องกลายเป็นวันเวลาแบบ UTC"""
        values = self._tf_common(config, spec, row, values, warnings)
        raw = row.get('checked_at')
        stamp = self._thai_text_to_utc(raw)
        if not stamp:
            raise UserError(_(
                'แถว id %s ไม่มีเวลาเข้าออกงานที่อ่านได้ (ค่าที่เก็บไว้คือ %r)'
            ) % (row.get('id'), raw))
        values['checked_at'] = stamp
        # work_date ฝั่ง 18 คำนวณเองจาก checked_at จึงไม่ต้องเขียน
        values.pop('work_date', None)
        values.pop('date_requested', None)
        return values

    @staticmethod
    def _thai_text_to_utc(text):
        """'2026-09-24 16:01:24' (เวลาไทย) -> วันเวลาแบบ UTC ที่ Odoo เก็บ"""
        if not text:
            return False
        if isinstance(text, datetime):
            return text - THAI_UTC_OFFSET
        text = str(text).strip().replace('T', ' ')
        for pattern in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
            try:
                return datetime.strptime(text[:19], pattern) - THAI_UTC_OFFSET
            except ValueError:
                continue
        return False
