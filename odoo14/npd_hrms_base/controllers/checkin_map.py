# -*- coding: utf-8 -*-
"""หน้าแผนที่ตั้งพิกัดและรัศมีเช็คอินของสาขา

แทนของเดิมที่แค่เปิด google.com/maps ซึ่งแสดงได้แค่หมุด มองไม่เห็นว่ารัศมีที่ตั้งไว้
ครอบพื้นที่แค่ไหน ทำให้ตั้งค่าแบบเดาไปเรื่อย ๆ — หน้านี้วาดวงกลมรัศมีจริงให้เห็น
และคลิก/ลากเพื่อย้ายจุดได้ แล้วบันทึกกลับเข้าสาขาได้เลย

กุญแจ Google Maps อ่านจากพารามิเตอร์ระบบ ``npd_hrms.google_maps_api_key``
ไม่ฝังไว้ในโค้ดเหมือนของเดิม เพราะระบบนี้ปล่อยเช่าได้ แต่ละองค์กรจึงควรใช้
กุญแจและโควตาของตัวเอง ไม่ใช่ใช้ของ NPD ร่วมกันทุกราย
"""
import json

from odoo import http
from odoo.http import request

PARAM_KEY = 'npd_hrms.google_maps_api_key'
DEFAULT_LAT = 13.7563
DEFAULT_LNG = 100.5018


class CheckinMapController(http.Controller):

    def _branch_or_404(self, branch_id):
        branch = request.env['res.branch'].browse(branch_id)
        if not branch.exists():
            return None
        return branch

    @http.route('/hrms/checkin_map/<int:branch_id>', type='http',
                auth='user', website=False)
    def checkin_map(self, branch_id, **kwargs):
        if not request.env.user.has_group('npd_hrms_base.group_hrms_officer'):
            return request.not_found()

        branch = self._branch_or_404(branch_id)
        if branch is None:
            return request.not_found()

        lat = float(branch.hr_checkin_latitude or DEFAULT_LAT)
        lng = float(branch.hr_checkin_longitude or DEFAULT_LNG)
        radius = int(branch._hr_effective_radius())
        api_key = request.env['ir.config_parameter'].sudo().get_param(PARAM_KEY, '')

        context = {
            'branch_id': branch.id,
            'branch_name': branch.name or 'ไม่ระบุสาขา',
            'lat': lat,
            'lng': lng,
            'radius': radius,
            'has_key': bool(api_key),
        }
        html = self._render_page(context, api_key)
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            # หน้านี้มีกุญแจ Google อยู่ในเนื้อหา ห้ามให้ proxy/เบราว์เซอร์เก็บไว้
            ('Cache-Control', 'no-store'),
        ])

    @http.route('/hrms/checkin_map/save', type='json', auth='user')
    def checkin_map_save(self, branch_id, latitude, longitude, radius, **kwargs):
        if not request.env.user.has_group('npd_hrms_base.group_hrms_officer'):
            return {'ok': False, 'error': 'ไม่มีสิทธิ์แก้ไขข้อมูลสาขา'}
        branch = self._branch_or_404(int(branch_id))
        if branch is None:
            return {'ok': False, 'error': 'ไม่พบสาขานี้'}
        try:
            radius = int(radius)
            if radius < 0:
                raise ValueError
        except (TypeError, ValueError):
            return {'ok': False, 'error': 'รัศมีต้องเป็นจำนวนเต็มไม่ติดลบ'}
        branch.write({
            'hr_checkin_latitude': float(latitude),
            'hr_checkin_longitude': float(longitude),
            'hr_checkin_radius': radius,
        })
        return {'ok': True}

    # ------------------------------------------------------------------
    def _render_page(self, ctx, api_key):
        data = json.dumps(ctx, ensure_ascii=False)
        if not api_key:
            return self._render_missing_key(ctx)
        return _PAGE_TEMPLATE % {
            'data': data,
            'key': api_key,
            'title': ctx['branch_name'],
        }

    def _render_missing_key(self, ctx):
        return _NO_KEY_TEMPLATE % {
            'title': ctx['branch_name'],
            'lat': ctx['lat'],
            'lng': ctx['lng'],
            'radius': ctx['radius'],
        }


_NO_KEY_TEMPLATE = """<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
 body{font-family:system-ui,'IBM Plex Sans Thai',sans-serif;margin:0;padding:40px;
      background:#f6f7f9;color:#222;display:flex;justify-content:center}
 .card{background:#fff;border-radius:12px;padding:28px 32px;max-width:560px;
       box-shadow:0 2px 12px rgba(0,0,0,.08)}
 h1{font-size:20px;margin:0 0 12px} code{background:#eee;padding:2px 6px;border-radius:4px}
 li{margin:6px 0;line-height:1.6}
</style></head><body><div class="card">
 <h1>ยังไม่ได้ตั้งกุญแจ Google Maps</h1>
 <p>สาขา <b>%(title)s</b> — พิกัด %(lat)s, %(lng)s รัศมี %(radius)s เมตร</p>
 <p>หน้านี้ต้องใช้กุญแจ Google Maps ถึงจะวาดวงกลมรัศมีให้เห็นได้ วิธีตั้ง:</p>
 <ol>
  <li>ไปที่ <b>ตั้งค่า → เทคนิค → พารามิเตอร์ระบบ</b></li>
  <li>สร้างคีย์ <code>npd_hrms.google_maps_api_key</code></li>
  <li>ใส่กุญแจที่เปิดใช้ <b>Maps JavaScript API</b> ไว้แล้ว</li>
 </ol>
 <p>แนะนำให้จำกัดกุญแจให้ใช้ได้เฉพาะโดเมนของระบบ เพื่อไม่ให้ถูกนำไปใช้จนโควตาหมด</p>
</div></body></html>"""


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
 html,body{height:100%%;margin:0;font-family:system-ui,'IBM Plex Sans Thai',sans-serif}
 #map{position:absolute;top:64px;bottom:0;left:0;right:0}
 #bar{position:absolute;top:0;left:0;right:0;height:64px;background:#fff;
      border-bottom:1px solid #dcdcdc;display:flex;align-items:center;gap:16px;
      padding:0 16px;box-sizing:border-box;z-index:5;flex-wrap:wrap}
 #bar b{font-size:15px}
 .grp{display:flex;align-items:center;gap:6px;font-size:13px;color:#444}
 input[type=number]{width:92px;padding:5px 8px;border:1px solid #ccc;border-radius:6px}
 button{padding:7px 16px;border:0;border-radius:6px;font-size:13px;cursor:pointer}
 #save{background:#00a09d;color:#fff;font-weight:600}
 #save:disabled{opacity:.5;cursor:default}
 #msg{font-size:13px;margin-left:auto}
 .ok{color:#1b8a4b} .err{color:#c0392b}
 #hint{position:absolute;bottom:16px;left:50%%;transform:translateX(-50%%);
       background:rgba(0,0,0,.72);color:#fff;padding:7px 14px;border-radius:16px;
       font-size:12px;z-index:5}
</style></head><body>
<div id="bar">
  <b id="bname"></b>
  <span class="grp">พิกัด <span id="coord"></span></span>
  <span class="grp">รัศมี <input type="number" id="radius" min="0" step="10"> เมตร</span>
  <button id="save">บันทึกลงสาขา</button>
  <span id="msg"></span>
</div>
<div id="map"></div>
<div id="hint">คลิกบนแผนที่หรือลากหมุด เพื่อย้ายจุดเช็คอิน</div>
<script>
var CTX = %(data)s;
var map, marker, circle, dirty = false;

function fmt(n){ return Number(n).toFixed(6); }

function setCenter(lat, lng){
  var p = {lat: lat, lng: lng};
  marker.setPosition(p);
  circle.setCenter(p);
  document.getElementById('coord').textContent = fmt(lat) + ', ' + fmt(lng);
  markDirty();
}

function markDirty(){
  dirty = true;
  document.getElementById('save').disabled = false;
  setMsg('', '');
}

function setMsg(text, cls){
  var el = document.getElementById('msg');
  el.textContent = text; el.className = cls;
}

function initMap(){
  var c = {lat: CTX.lat, lng: CTX.lng};
  document.getElementById('bname').textContent = CTX.branch_name;
  document.getElementById('radius').value = CTX.radius;

  map = new google.maps.Map(document.getElementById('map'),
        {zoom: 17, center: c, mapTypeControl: true, streetViewControl: false});
  marker = new google.maps.Marker({position: c, map: map, draggable: true});
  circle = new google.maps.Circle({
      map: map, center: c, radius: CTX.radius,
      strokeColor: '#00a09d', strokeOpacity: .9, strokeWeight: 2,
      fillColor: '#00a09d', fillOpacity: .15});

  document.getElementById('coord').textContent = fmt(CTX.lat) + ', ' + fmt(CTX.lng);
  document.getElementById('save').disabled = true;

  map.addListener('click', function(e){ setCenter(e.latLng.lat(), e.latLng.lng()); });
  marker.addListener('dragend', function(e){ setCenter(e.latLng.lat(), e.latLng.lng()); });

  document.getElementById('radius').addEventListener('input', function(){
    var v = parseInt(this.value || '0', 10);
    if (isNaN(v) || v < 0) return;
    circle.setRadius(v);
    markDirty();
  });

  document.getElementById('save').addEventListener('click', save);
  window.addEventListener('beforeunload', function(e){
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });
}

function save(){
  var pos = marker.getPosition();
  var body = {jsonrpc: '2.0', method: 'call', params: {
      branch_id: CTX.branch_id,
      latitude: pos.lat(), longitude: pos.lng(),
      radius: parseInt(document.getElementById('radius').value || '0', 10)}};
  document.getElementById('save').disabled = true;
  fetch('/hrms/checkin_map/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)})
    .then(function(r){ return r.json(); })
    .then(function(r){
      var res = r.result || {};
      if (res.ok) { dirty = false; setMsg('บันทึกแล้ว', 'ok'); }
      else { setMsg(res.error || 'บันทึกไม่สำเร็จ', 'err');
             document.getElementById('save').disabled = false; }
    })
    .catch(function(){ setMsg('ติดต่อเซิร์ฟเวอร์ไม่ได้', 'err');
                       document.getElementById('save').disabled = false; });
}
</script>
<script async defer
  src="https://maps.googleapis.com/maps/api/js?key=%(key)s&callback=initMap"></script>
</body></html>"""
