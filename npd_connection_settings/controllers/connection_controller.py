import json
from odoo import http
from odoo.http import request


class NPDConnectionController(http.Controller):
    
    @http.route('/api/npd/connection/get_active', type='http', auth='public', methods=['GET', 'POST'])
    def get_active_connection(self):
        """ดึงการตั้งค่าการเชื่อมต่อที่ใช้งานอยู่"""
        try:
            connection = request.env['npd.connection.config'].sudo().search(
                [('is_active', '=', True)],
                limit=1
            )
            
            if connection:
                result = {
                    'success': True,
                    'data': connection.get_connection_dict()
                }
            else:
                result = {
                    'success': False,
                    'message': 'ไม่พบการตั้งค่าการเชื่อมต่อที่ใช้งาน กรุณาตั้งค่าการเชื่อมต่อในหน้า NPD Connection Settings'
                }
            
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
        except Exception as e:
            result = {
                'success': False,
                'message': f'Error: {str(e)}'
            }
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
    
    @http.route('/api/npd/connection/get_all', type='http', auth='public', methods=['GET', 'POST'])
    def get_all_connections(self):
        """ดึงการตั้งค่าการเชื่อมต่อทั้งหมด"""
        try:
            connections = request.env['npd.connection.config'].sudo().search([])
            
            result = {
                'success': True,
                'data': [conn.get_connection_dict() for conn in connections]
            }
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
        except Exception as e:
            result = {
                'success': False,
                'message': f'Error: {str(e)}'
            }
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
    
    @http.route('/api/npd/connection/get_by_id/<int:connection_id>', type='http', auth='public', methods=['GET', 'POST'])
    def get_connection_by_id(self, connection_id):
        """ดึงการตั้งค่าการเชื่อมต่อตาม ID"""
        try:
            connection = request.env['npd.connection.config'].sudo().browse(connection_id)
            
            if connection.exists():
                result = {
                    'success': True,
                    'data': connection.get_connection_dict()
                }
            else:
                result = {
                    'success': False,
                    'message': f'ไม่พบการตั้งค่าการเชื่อมต่อ ID {connection_id}'
                }
            
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
        except Exception as e:
            result = {
                'success': False,
                'message': f'Error: {str(e)}'
            }
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
    
    @http.route('/api/npd/connection/set_active/<int:connection_id>', type='http', auth='public', methods=['POST'])
    def set_active_connection(self, connection_id):
        """ตั้งการเชื่อมต่อให้เป็นแบบใช้งาน"""
        try:
            # ปิดการใช้งานทั้งหมด
            all_connections = request.env['npd.connection.config'].sudo().search([])
            all_connections.write({'is_active': False})
            
            # เปิดใช้งานที่ระบุ
            connection = request.env['npd.connection.config'].sudo().browse(connection_id)
            if connection.exists():
                connection.write({'is_active': True})
                result = {
                    'success': True,
                    'message': f'การเชื่อมต่อ "{connection.name}" เปิดใช้งานแล้ว',
                    'data': connection.get_connection_dict()
                }
            else:
                result = {
                    'success': False,
                    'message': f'ไม่พบการตั้งค่าการเชื่อมต่อ ID {connection_id}'
                }
            
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
        except Exception as e:
            result = {
                'success': False,
                'message': f'Error: {str(e)}'
            }
            return request.make_response(
                json.dumps(result),
                headers={'Content-Type': 'application/json'}
            )
