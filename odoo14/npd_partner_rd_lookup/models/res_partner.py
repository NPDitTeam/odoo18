# -*- coding: utf-8 -*-
import logging
import re
import xml.etree.ElementTree as ET

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# บริการตรวจสอบผู้ประกอบการจดทะเบียน VAT ของกรมสรรพากร (ฟรี ไม่ต้องใช้คีย์)
RD_URL = 'https://rdws.rd.go.th/serviceRD3/vatserviceRD3.asmx'
RD_NS = 'https://rdws.rd.go.th/serviceRD3/vatserviceRD3'
RD_TIMEOUT = 8
EMPTY = (None, '', '-')
FIELD_LABELS = {'name': 'ชื่อ', 'branch': 'รหัสสาขา', 'street': 'ที่อยู่', 'street2': 'ตำบล/แขวง',
                'city': 'อำเภอ/เขต', 'state_id': 'จังหวัด', 'zip': 'รหัสไปรษณีย์', 'country_id': 'ประเทศ'}
BRANCH_IN_NAME = re.compile(r'สาขา\s*(?:ที่)?\s*(\d{1,5})')


def npd_tin_digits(vat):
    return re.sub(r'\D', '', vat or '')


def npd_tin_valid(tin):
    """เลขประจำตัวผู้เสียภาษี 13 หลัก ตรวจหลักสุดท้าย (mod 11)"""
    if not re.fullmatch(r'\d{13}', tin or ''):
        return False
    total = sum(int(tin[i]) * (13 - i) for i in range(12))
    return (11 - total % 11) % 10 == int(tin[12])


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ---------- เรียกกรมสรรพากร ----------
    @api.model
    def _npd_rd_query(self, tin, branch_no=0):
        """คืน dict ข้อมูลผู้ประกอบการ หรือ None ถ้าไม่พบ; เครือข่ายมีปัญหา -> raise UserError"""
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            '<Service xmlns="%s"><username>anonymous</username><password>anonymous</password>'
            '<TIN>%s</TIN><ProvinceCode>0</ProvinceCode><BranchNumber>%d</BranchNumber>'
            '<AmphurCode>0</AmphurCode></Service></soap:Body></soap:Envelope>'
        ) % (RD_NS, tin, int(branch_no or 0))
        try:
            resp = requests.post(RD_URL, data=body.encode('utf-8'), timeout=RD_TIMEOUT, headers={
                'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': '"%s/Service"' % RD_NS})
            resp.raise_for_status()
            result = ET.fromstring(resp.content).find('.//{%s}ServiceResult' % RD_NS)
        except Exception as e:
            _logger.warning('npd_partner_rd_lookup: เรียกกรมสรรพากรไม่สำเร็จ %s: %s', tin, e)
            raise UserError(_('เชื่อมต่อระบบกรมสรรพากรไม่ได้ในขณะนี้ กรุณากรอกข้อมูลเอง หรือลองใหม่ภายหลัง'))
        if result is None:
            return None
        data = {}
        for col in result:
            vals = [a.text for a in col]
            data[col.tag.split('}')[1]] = vals[0].strip() if vals and vals[0] else None
        if data.get('vmsgerr') or data.get('vName') in EMPTY:
            return None
        return data

    @api.model
    def _npd_rd_address(self, d):
        def v(key):
            val = (d.get(key) or '').strip()
            return '' if val in EMPTY else val
        parts = [v('vHouseNumber')]
        if v('vBuildingName'):
            parts.append(v('vBuildingName') if v('vBuildingName').startswith('อาคาร') else 'อาคาร' + v('vBuildingName'))
        if v('vFloorNumber'):
            parts.append('ชั้น ' + v('vFloorNumber'))
        if v('vRoomNumber'):
            parts.append('ห้อง ' + v('vRoomNumber'))
        if v('vVillageName'):
            parts.append(v('vVillageName') if v('vVillageName').startswith('หมู่บ้าน') else 'หมู่บ้าน' + v('vVillageName'))
        if v('vMooNumber'):
            parts.append('หมู่ที่ ' + v('vMooNumber'))
        if v('vSoiName'):
            parts.append('ซ.' + v('vSoiName'))
        if v('vYaek'):
            parts.append('แยก' + v('vYaek'))
        if v('vStreetName'):
            parts.append('ถ.' + v('vStreetName'))
        province = v('vProvince')
        bangkok = 'กรุงเทพ' in province
        tambon, amphur = v('vThambol'), v('vAmphur')
        state = self.env['res.country.state']
        thailand = self.env.ref('base.th', raise_if_not_found=False)
        if province and thailand:
            short = province.replace('จังหวัด', '').strip()
            state = state.search([('country_id', '=', thailand.id), '|', '|',
                                  ('name', '=', short), ('name', '=', 'จ.' + short), ('name', 'ilike', short)], limit=1)
        return {
            'street': ' '.join(p for p in parts if p),
            'street2': (('แขวง' if bangkok else 'ต.') + tambon) if tambon else False,
            'city': (('เขต' if bangkok else 'อ.') + amphur) if amphur else False,
            'state_id': state.id or False,
            'zip': v('vPostCode') or False,
            'country_id': thailand.id if thailand else False,
        }

    @api.model
    def _npd_rd_values(self, data, branch_no):
        title = '' if (data.get('vtitleName') or '-') in EMPTY else data['vtitleName'].strip()
        name = data['vName'].strip()
        if title and not name.startswith(title):
            name = '%s %s' % (title, name)
        if branch_no:
            name = '%s สาขาที่ %05d' % (name, branch_no)
        vals = {'name': name}
        vals.update(self._npd_rd_address(data))
        if 'branch' in self._fields:
            vals['branch'] = '%05d' % branch_no
        return vals

    def _npd_rd_branch_no(self):
        """รหัสสาขาจากช่องสาขา ถ้าว่าง/00000 ลองอ่านจากชื่อ (ข้อมูลเดิมหลายรายเขียนสาขาไว้ในชื่อ เช่น 'สาขา00012')"""
        branch = ((self.branch if 'branch' in self._fields else '') or '').strip()
        if re.fullmatch(r'\d{1,5}', branch) and int(branch):
            return int(branch)
        m = BRANCH_IN_NAME.search(self.name or '')
        if m and int(m.group(1)):
            return int(m.group(1))
        return int(branch) if re.fullmatch(r'\d{1,5}', branch) else 0

    # ---------- หน้าจอ ----------
    @api.onchange('vat', 'branch')
    def _onchange_npd_rd_lookup(self):
        """บริษัท: กรอกเลขผู้เสียภาษี (และรหัสสาขา) แล้วดึงข้อมูลจากกรมสรรพากรมาเติมช่องที่ยังว่าง"""
        if not self.is_company or not self.vat:
            return
        tin = npd_tin_digits(self.vat)
        if len(tin) != 13:
            return
        if not npd_tin_valid(tin):
            return {'warning': {'title': _('เลขประจำตัวผู้เสียภาษีไม่ถูกต้อง'),
                                'message': _('เลข %s ไม่ผ่านการตรวจสอบหลักสุดท้าย กรุณาตรวจสอบอีกครั้ง') % tin}}
        branch_no = self._npd_rd_branch_no()
        try:
            data = self._npd_rd_query(tin, branch_no)
        except UserError as e:
            return {'warning': {'title': _('ดึงข้อมูลกรมสรรพากรไม่ได้'), 'message': str(e.args[0])}}
        if not data:
            return {'warning': {'title': _('ไม่พบในระบบกรมสรรพากร'), 'message': _(
                'ไม่พบผู้ประกอบการจดทะเบียน VAT เลข %s สาขา %05d\n(อาจไม่ได้จด VAT หรือรหัสสาขาไม่ถูกต้อง) กรุณากรอกข้อมูลเอง')
                % (tin, branch_no)}}
        vals = self._npd_rd_values(data, branch_no)
        filled = []
        for fname, value in vals.items():
            if fname not in self._fields or not value:
                continue
            current = self[fname]
            if fname == 'branch' and current and current.strip() not in ('', '00000'):
                continue
            if not current or (fname == 'branch' and current.strip() == '00000'):
                self[fname] = value
                filled.append(FIELD_LABELS.get(fname, self._fields[fname].string))
        dup = self._npd_rd_duplicate(tin, branch_no)
        msg = []
        if filled:
            msg.append(_('เติมข้อมูลจากกรมสรรพากรแล้ว: %s') % ', '.join(filled))
        if not filled:
            msg.append(_('พบในกรมสรรพากร: %s (ช่องที่กรอกไว้แล้วไม่ได้เปลี่ยน กดปุ่ม "ดึงข้อมูลกรมสรรพากร" ถ้าต้องการใช้ข้อมูลกรมทั้งหมด)')
                       % vals['name'])
        if dup:
            msg.append(_('คำเตือน: มีผู้ติดต่อเลขนี้และสาขานี้อยู่แล้ว: %s') % ', '.join(dup.mapped('display_name')[:3]))
        if dup or not filled:
            return {'warning': {'title': _('ข้อมูลกรมสรรพากร'), 'message': '\n'.join(msg)}}

    def _npd_rd_duplicate(self, tin, branch_no):
        domain = [('is_company', '=', True), ('vat', 'like', tin)]
        if 'branch' in self._fields:
            domain.append(('branch', 'in', ['%05d' % branch_no] + (['', False] if not branch_no else [])))
        own = self._origin.id if self._origin else False
        if own:
            domain.append(('id', '!=', own))
        return self.sudo().search(domain, limit=3)

    def action_npd_rd_fill(self):
        """ปุ่ม: ใช้ข้อมูลจากกรมสรรพากรทับทุกช่อง (ชื่อ สาขา ที่อยู่)"""
        self.ensure_one()
        tin = npd_tin_digits(self.vat)
        if not npd_tin_valid(tin):
            raise UserError(_('เลขประจำตัวผู้เสียภาษีไม่ถูกต้อง (ต้องเป็นเลข 13 หลักที่ถูกต้อง)'))
        branch_no = self._npd_rd_branch_no()
        data = self._npd_rd_query(tin, branch_no)
        if not data:
            raise UserError(_('ไม่พบผู้ประกอบการจดทะเบียน VAT เลข %s สาขา %05d ในระบบกรมสรรพากร') % (tin, branch_no))
        vals = {k: v for k, v in self._npd_rd_values(data, branch_no).items() if k in self._fields and v}
        # o14 มีโมดูลบังคับอีเมลผู้ติดต่อ — การเติมข้อมูลจากกรมไม่ควรติดเงื่อนไขนั้น
        self.with_context(skip_email_required=True).write(vals)
        self.message_post(body=_('ดึงข้อมูลจากกรมสรรพากร (เลข %s สาขา %05d): %s') % (tin, branch_no, vals.get('name')))
        return True
