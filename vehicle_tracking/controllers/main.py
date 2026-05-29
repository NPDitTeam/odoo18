# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
import json


class VehicleTrackingController(http.Controller):

    @http.route('/vehicle_tracking/fetch_data', type='json', auth='user')
    def fetch_vehicle_data(self):
        """API endpoint to fetch vehicle data"""
        Vehicle = request.env['gps.vehicle.tracking']
        return Vehicle.fetch_vehicle_data()

    @http.route('/vehicle_tracking/get_vehicles', type='json', auth='user')
    def get_vehicles(self):
        """Get all vehicles data for map display"""
        Vehicle = request.env['gps.vehicle.tracking']
        vehicles = Vehicle.search([])
        
        vehicles_data = []
        for vehicle in vehicles:
            if vehicle.latitude and vehicle.longitude:
                vehicles_data.append({
                    'id': vehicle.id,
                    'name': vehicle.device_name or vehicle.lpn,
                    'latitude': vehicle.latitude,
                    'longitude': vehicle.longitude,
                    'speed': vehicle.speed,
                    'status': vehicle.status_text,
                    'engine_status': vehicle.engine_status,
                })
        
        return vehicles_data
    
    @http.route('/vehicle_tracking/get_vehicle/<int:vehicle_id>', type='json', auth='user')
    def get_vehicle(self, vehicle_id):
        """Get single vehicle data for map display"""
        Vehicle = request.env['gps.vehicle.tracking']
        vehicle = Vehicle.browse(vehicle_id)
        
        if vehicle.exists() and vehicle.latitude and vehicle.longitude:
            return {
                'success': True,
                'data': {
                    'id': vehicle.id,
                    'imei': vehicle.imei,
                    'device_name': vehicle.device_name,
                    'lpn': vehicle.lpn,
                    'fleet_name': vehicle.fleet_name,
                    'latitude': vehicle.latitude,
                    'longitude': vehicle.longitude,
                    'altitude': vehicle.altitude,
                    'speed': vehicle.speed,
                    'course': vehicle.course,
                    'mileage_km': vehicle.mileage_km,
                    'status': vehicle.status_text,
                    'engine_status': vehicle.engine_status,
                    'utc_timestamp': vehicle.utc_timestamp.isoformat() if vehicle.utc_timestamp else None,
                    'battery_voltage': vehicle.battery_voltage,
                    'supply_voltage': vehicle.supply_voltage,
                }
            }
        return {'success': False, 'message': 'Vehicle not found or no GPS data'}
    
    @http.route('/vehicle_tracking/map/<int:vehicle_id>', type='http', auth='user')
    def show_vehicle_map(self, vehicle_id):
        """Display vehicle on interactive map with auto-refresh"""
        Vehicle = request.env['gps.vehicle.tracking']
        vehicle = Vehicle.browse(vehicle_id)
        
        if not vehicle.exists():
            return request.not_found()
        
        return request.render('vehicle_tracking.vehicle_map_view', {
            'vehicle': vehicle,
        })
