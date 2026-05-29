/** @odoo-module **/

import { registry } from "@web/core/registry";
import { loadJS } from "@web/core/assets";
import { Component, onWillStart, onMounted, useState } from "@odoo/owl";

export class VehicleTrackingMapWidget extends Component {
    setup() {
        this.state = useState({
            map: null,
            markers: {},
            routes: {},
            infoWindows: {},
        });

        onWillStart(async () => {
            await this.loadGoogleMaps();
        });

        onMounted(() => {
            this.initMap();
            this.loadTrackingData();
            // Auto refresh every 30 seconds
            this.intervalId = setInterval(() => {
                this.loadTrackingData();
            }, 30000);
        });
    }

    async loadGoogleMaps() {
        const apiKey = await this.env.services.orm.call(
            'transport.user.settings',
            'get_google_maps_api_key',
            []
        );
        
        if (!window.google || !window.google.maps) {
            await loadJS(`https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`);
        }
    }

    initMap() {
        const mapElement = this.el.querySelector('.o_tracking_map_view');
        
        this.state.map = new google.maps.Map(mapElement, {
            center: { lat: 13.7563, lng: 100.5018 }, // Bangkok
            zoom: 12,
            mapTypeId: 'roadmap',
            styles: [
                {
                    featureType: 'poi',
                    stylers: [{ visibility: 'off' }]
                }
            ]
        });
    }

    async loadTrackingData() {
        try {
            const result = await this.env.services.orm.call(
                'vehicle.tracking',
                'search_read',
                [
                    [['booking_id.state', 'in', ['in_transit', 'at_destination']]],
                    ['booking_id', 'driver_id', 'vehicle_id', 'latitude', 'longitude', 
                     'speed', 'is_moving', 'timestamp', 'address']
                ],
                { limit: 100, order: 'timestamp desc' }
            );

            this.updateMarkers(result);
        } catch (error) {
            console.error('Error loading tracking data:', error);
        }
    }

    updateMarkers(trackingData) {
        // Group by booking_id to get latest position
        const latestPositions = {};
        
        trackingData.forEach(track => {
            const bookingId = track.booking_id[0];
            if (!latestPositions[bookingId] || 
                new Date(track.timestamp) > new Date(latestPositions[bookingId].timestamp)) {
                latestPositions[bookingId] = track;
            }
        });

        // Clear old markers
        Object.values(this.state.markers).forEach(marker => marker.setMap(null));
        this.state.markers = {};

        // Create new markers
        const bounds = new google.maps.LatLngBounds();

        Object.entries(latestPositions).forEach(([bookingId, track]) => {
            const position = { lat: track.latitude, lng: track.longitude };
            
            // Create custom marker
            const markerIcon = {
                path: google.maps.SymbolPath.CIRCLE,
                fillColor: track.is_moving ? '#28a745' : '#ffc107',
                fillOpacity: 1,
                strokeColor: '#ffffff',
                strokeWeight: 2,
                scale: 10
            };

            const marker = new google.maps.Marker({
                position: position,
                map: this.state.map,
                icon: markerIcon,
                title: track.booking_id[1]
            });

            // Create info window
            const infoWindow = new google.maps.InfoWindow({
                content: this.createInfoWindowContent(track)
            });

            marker.addListener('click', () => {
                // Close all other info windows
                Object.values(this.state.infoWindows).forEach(iw => iw.close());
                infoWindow.open(this.state.map, marker);
            });

            this.state.markers[bookingId] = marker;
            this.state.infoWindows[bookingId] = infoWindow;

            bounds.extend(position);
        });

        // Fit bounds if we have markers
        if (Object.keys(this.state.markers).length > 0) {
            this.state.map.fitBounds(bounds);
        }
    }

    createInfoWindowContent(track) {
        const statusClass = track.is_moving ? 'moving' : 'stopped';
        const statusText = track.is_moving ? 'กำลังเคลื่อนที่' : 'หยุด';
        
        return `
            <div class="tracking_info_window">
                <h4>${track.booking_id[1]}</h4>
                <div class="info_row">
                    <span class="info_label">รถ:</span>
                    ${track.vehicle_id ? track.vehicle_id[1] : 'N/A'}
                </div>
                <div class="info_row">
                    <span class="info_label">คนขับ:</span>
                    ${track.driver_id ? track.driver_id[1] : 'N/A'}
                </div>
                <div class="info_row">
                    <span class="info_label">สถานะ:</span>
                    <span class="status_badge ${statusClass}">${statusText}</span>
                </div>
                ${track.speed ? `
                <div class="info_row">
                    <span class="info_label">ความเร็ว:</span>
                    ${Math.round(track.speed)} km/h
                </div>
                ` : ''}
                <div class="info_row">
                    <span class="info_label">เวลา:</span>
                    ${new Date(track.timestamp).toLocaleString('th-TH')}
                </div>
                ${track.address ? `
                <div class="info_row">
                    <span class="info_label">ที่อยู่:</span>
                    ${track.address}
                </div>
                ` : ''}
            </div>
        `;
    }

    willUnmount() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
        }
    }
}

VehicleTrackingMapWidget.template = "transport_booking.VehicleTrackingMap";

// Odoo 18 format - must use object with component property
registry.category("fields").add("vehicle_tracking_map", {
    component: VehicleTrackingMapWidget,
});
