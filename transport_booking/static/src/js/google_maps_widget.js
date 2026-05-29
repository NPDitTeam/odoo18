/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";

const GOOGLE_API_KEY = "AIzaSyAorvWR_BL6tgkNgkkRO4NIb8ZTKq92S3U";

export class GoogleMapsWidget extends Component {
    setup() {
        this.mapRef = useRef("googleMap");
        this.map = null;
        this.directionsService = null;
        this.directionsRenderer = null;
        this.alternativeRenderers = [];
        this.mapLoaded = false;
        this.retryCount = 0;
        this.lastOrigin = "";
        this.lastDestination = "";
        this.isInitialized = false; // ตรวจสอบว่า map ถูกสร้างแล้ว
        
        // ใช้ useState สำหรับ isCalculating เพื่อให้ UI อัพเดท
        this.state = useState({
            isCalculating: false
        });

        onMounted(() => {
            setTimeout(() => this.initializeMap(), 100);
        });

        onWillUpdateProps((nextProps) => {
            const newOrigin = nextProps.record.data.pickup_location || "";
            const newDestination = nextProps.record.data.destination || "";
            const newMapTrigger = nextProps.record.data.map_trigger || "";
            const oldMapTrigger = this.props.record.data.map_trigger || "";
            const newState = nextProps.record.data.state || 'draft';
            const oldState = this.props.record.data.state || 'draft';
            
            console.log("=".repeat(50));
            console.log("🔄 onWillUpdateProps triggered!");
            console.log("📋 ALL RECORD DATA:", nextProps.record.data);
            console.log("📊 Current values:");
            console.log("  - lastOrigin:", this.lastOrigin);
            console.log("  - lastDestination:", this.lastDestination);
            console.log("  - oldMapTrigger:", oldMapTrigger);
            console.log("  - oldState:", oldState);
            console.log("📦 New values from props:");
            console.log("  - newOrigin:", newOrigin);
            console.log("  - newDestination:", newDestination);
            console.log("  - newMapTrigger:", newMapTrigger);
            console.log("  - newState:", newState);
            console.log("🔍 Status:");
            console.log("  - isInitialized:", this.isInitialized);
            console.log("  - state.isCalculating:", this.state.isCalculating);
            console.log("=".repeat(50));
            
            // อัพเดท draggable เมื่อสถานะเปลี่ยน
            if (newState !== oldState && this.directionsRenderer) {
                const isDraggable = (newState !== 'done' && newState !== 'cancelled');
                this.directionsRenderer.setOptions({ draggable: isDraggable });
                console.log("🔄 Updated map draggable to:", isDraggable, "(state:", newState + ")");
            }
            
            // เช็คว่ามีการเปลี่ยนแปลงจริงๆ โดยดูจาก map_trigger
            const hasMapTriggerChanged = (newMapTrigger !== oldMapTrigger && newMapTrigger !== "");
            const hasValidData = newOrigin && newDestination;
            
            console.log("🔎 Decision factors:");
            console.log("  - hasMapTriggerChanged:", hasMapTriggerChanged);
            console.log("  - hasValidData:", hasValidData);
            console.log("  - newMapTrigger !== '':", newMapTrigger !== "");
            
            if (hasMapTriggerChanged && hasValidData) {
                console.log("✅ Map trigger changed! Forcing route recalculation...");
                console.log("   Old trigger:", oldMapTrigger);
                console.log("   New trigger:", newMapTrigger);
                
                this.lastOrigin = newOrigin;
                this.lastDestination = newDestination;
                
                if (this.isInitialized) {
                    // ยกเลิก flag isCalculating ชั่วคราวเพื่อให้อัพเดทได้
                    this.state.isCalculating = false;
                    
                    // ให้เวลา DOM อัพเดทก่อนคำนวณเส้นทาง
                    setTimeout(() => {
                        console.log("🚀 Calling calculateRoute from map_trigger change");
                        this.calculateRoute();
                    }, 300);
                } else {
                    console.log("⏭️ Map not ready yet, will calculate when initialized");
                }
            } else {
                console.log("⏭️ Skipping route calculation:", {
                    hasMapTriggerChanged,
                    hasValidData,
                    isInitialized: this.isInitialized,
                    isCalculating: this.state.isCalculating
                });
            }
        });

        onWillUnmount(() => {
            if (this.directionsRenderer) this.directionsRenderer.setMap(null);
            this.alternativeRenderers.forEach(r => r.setMap(null));
        });
    }

    get origin() {
        const value = this.props.record.data.pickup_location || "";
        console.log("📍 [Google Maps] get origin:", value);
        return value;
    }

    get destination() {
        const value = this.props.record.data.destination || "";
        console.log("📍 [Google Maps] get destination:", value);
        return value;
    }

    async loadGoogleMapsScript() {
        return new Promise((resolve, reject) => {
            if (window.google && window.google.maps) {
                resolve();
                return;
            }

            const script = document.createElement("script");
            script.src = `https://maps.googleapis.com/maps/api/js?key=${GOOGLE_API_KEY}&libraries=places`;
            script.async = true;
            script.defer = true;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("Failed to load Google Maps"));
            document.head.appendChild(script);
        });
    }

    async initializeMap() {
        if (!this.mapRef.el) {
            if (this.retryCount < 5) {
                this.retryCount++;
                setTimeout(() => this.initializeMap(), 200);
            }
            return;
        }

        console.log('🗺️ Initializing Google Maps...');
        console.log('📦 Record data:', this.props.record.data);
        console.log('📍 Origin (getter):', this.origin);
        console.log('📍 Destination (getter):', this.destination);

        try {
            await this.loadGoogleMapsScript();
            
            this.map = new google.maps.Map(this.mapRef.el, {
                zoom: 13,
                center: { lat: 13.7563, lng: 100.5018 },
                mapTypeControl: true,
                streetViewControl: true,
                fullscreenControl: true,
            });

            console.log('✅ Map initialized successfully');

            this.directionsService = new google.maps.DirectionsService();
            
            // ตรวจสอบสถานะ - ปิดการลากเส้นทางถ้าเป็นสถานะ 'done' หรือ 'cancelled'
            const currentState = this.props.record.data.state || 'draft';
            const isDraggable = (currentState !== 'done' && currentState !== 'cancelled'); // ปิด draggable เมื่อสถานะเป็น done หรือ cancelled
            
            console.log('🔍 Map draggable status:', {
                currentState: currentState,
                isDraggable: isDraggable
            });
            
            // เปิดใช้งานการลากเส้นทาง (draggable) - ยกเว้นสถานะ done
            this.directionsRenderer = new google.maps.DirectionsRenderer({
                map: this.map,
                draggable: isDraggable, // ปิดการลากเมื่อสถานะเป็น done
                suppressMarkers: false,
                polylineOptions: {
                    strokeColor: "#4285F4",  // สีน้ำเงิน Google
                    strokeOpacity: 0.8,
                    strokeWeight: 6,
                },
            });

            // เมื่อลากเส้นทางเสร็จ ให้อัพเดทข้อมูล (ถ้า draggable = true)
            if (isDraggable) {
                google.maps.event.addListener(this.directionsRenderer, 'directions_changed', () => {
                    if (this.state.isCalculating) return; // ป้องกันการ trigger ซ้ำ
                    this.updateRouteInfo();
                });
            }

            this.mapLoaded = true;
            this.isInitialized = true;
            
            // รอให้ record มีข้อมูลก่อน
            setTimeout(() => {
                const currentOrigin = this.origin;
                const currentDestination = this.destination;
                
                console.log('🔍 Checking for route data...');
                console.log('  Origin:', currentOrigin);
                console.log('  Destination:', currentDestination);
                
                if (currentOrigin && currentDestination) {
                    console.log('🚀 Starting route calculation...');
                    this.lastOrigin = currentOrigin;
                    this.lastDestination = currentDestination;
                    this.calculateRoute();
                } else {
                    console.warn('⚠️ No origin or destination provided');
                    console.log('Will wait for data from Transport Order selection...');
                }
            }, 500);
        } catch (error) {
            console.error("❌ Error initializing map:", error);
        }
    }

    updateRouteInfo() {
        // อัพเดทข้อมูลระยะทางและเวลาหลังจากลากเส้นทาง
        const directions = this.directionsRenderer.getDirections();
        if (directions && directions.routes && directions.routes.length > 0) {
            const route = directions.routes[0];
            if (route.legs && route.legs.length > 0) {
                const leg = route.legs[0];
                const distance = leg.distance.text;
                const duration = leg.duration.text;
                const distanceKm = leg.distance.value / 1000; // แปลงเป็น กม.
                
                // ดึงที่อยู่ใหม่หลังจากลาก
                const newOrigin = leg.start_address;
                const newDestination = leg.end_address;
                
                // ✅ เก็บ waypoints (จุดกึ่งกลางที่ผู้ใช้ลาก)
                const waypoints = [];
                if (route.legs.length > 1 || leg.via_waypoints?.length > 0) {
                    // ถ้ามีจุดกึ่งกลาง
                    if (leg.via_waypoints) {
                        leg.via_waypoints.forEach(wp => {
                            waypoints.push({
                                location: { lat: wp.lat(), lng: wp.lng() },
                                stopover: false
                            });
                        });
                    }
                }
                
                // เก็บ waypoints เป็น JSON
                const waypointsJson = waypoints.length > 0 ? JSON.stringify(waypoints) : '';
                
                console.log('💾 Saving waypoints:', waypoints);
                
                // อัพเดทข้อมูลใน Odoo
                if (this.props.record && this.props.record.update) {
                    this.props.record.update({
                        distance: distance,
                        estimated_time: duration,
                        distance_km: distanceKm,
                        pickup_location: newOrigin,
                        destination: newDestination,
                        waypoints_json: waypointsJson, // ✅ บันทึก waypoints
                    });
                    
                    // อัพเดท lastOrigin และ lastDestination เพื่อป้องกัน re-render
                    this.lastOrigin = newOrigin;
                    this.lastDestination = newDestination;
                }
            }
        }
    }

    async calculateRoute() {
        if (!this.origin || !this.destination || !this.directionsService) {
            console.warn('⚠️ Cannot calculate route - missing data:', {
                origin: this.origin,
                destination: this.destination,
                directionsService: !!this.directionsService
            });
            return;
        }

        // ป้องกันการเรียก API ซ้ำ
        if (this.state.isCalculating) {
            console.log('⏳ Already calculating route...');
            return;
        }

        console.log('🔄 Calculating route from:', this.origin, 'to:', this.destination);
        this.state.isCalculating = true;

        try {
            // ✅ โหลด waypoints จากฐานข้อมูล (ถ้ามี)
            let waypoints = [];
            const waypointsJson = this.props.record.data.waypoints_json;
            if (waypointsJson) {
                try {
                    waypoints = JSON.parse(waypointsJson);
                    console.log('📍 Loaded waypoints from database:', waypoints);
                } catch (e) {
                    console.warn('⚠️ Failed to parse waypoints_json:', e);
                }
            }

            const result = await this.directionsService.route({
                origin: this.origin,
                destination: this.destination,
                waypoints: waypoints, // ✅ ใช้ waypoints ที่บันทึกไว้
                travelMode: google.maps.TravelMode.DRIVING,
                provideRouteAlternatives: waypoints.length === 0, // เฉพาะเมื่อไม่มี waypoints
            });

            console.log('✅ Route calculated successfully:', result);
            console.log('📍 Routes found:', result.routes.length);
            console.log('🗺️ Setting directions on map...');

            this.directionsRenderer.setDirections(result);
            console.log('✅ Directions set on renderer');
            
            // Force re-render
            this.directionsRenderer.setMap(null);
            this.directionsRenderer.setMap(this.map);
            console.log('🔄 Forced map re-render');

            // ลบเส้นทางทางเลือกเก่าออก
            this.alternativeRenderers.forEach(renderer => renderer.setMap(null));
            this.alternativeRenderers = [];

            // วาดเส้นทางทางเลือก (ถ้ามี)
            if (result.routes.length > 1) {
                console.log(`📍 Found ${result.routes.length} alternative routes`);
                for (let i = 1; i < result.routes.length; i++) {
                    const renderer = new google.maps.DirectionsRenderer({
                        map: this.map,
                        directions: result,
                        routeIndex: i,
                        polylineOptions: {
                            strokeColor: "#999999",
                            strokeOpacity: 0.5,
                            strokeWeight: 4,
                        },
                        suppressMarkers: true,
                    });
                    this.alternativeRenderers.push(renderer);

                    // เพิ่ม click event สำหรับเปลี่ยนเส้นทาง
                    google.maps.event.addListener(renderer, 'click', () => {
                        this.switchToAlternativeRoute(i);
                    });
                }
            }

            // อัพเดทข้อมูลระยะทางและเวลา
            const mainRoute = result.routes[0];
            if (mainRoute && mainRoute.legs[0]) {
                const distance = mainRoute.legs[0].distance.text;
                const duration = mainRoute.legs[0].duration.text;
                const distanceKm = mainRoute.legs[0].distance.value / 1000; // แปลงเป็น กม.
                
                console.log('📏 Distance:', distance, '| Duration:', duration);
                
                // ✅ ปรับ zoom ให้เห็นเส้นทางทั้งหมด พร้อม padding
                const bounds = new google.maps.LatLngBounds();
                mainRoute.legs.forEach(leg => {
                    leg.steps.forEach(step => {
                        step.path.forEach(point => {
                            bounds.extend(point);
                        });
                    });
                });
                
                // เพิ่ม padding เพื่อซูมออกมากขึ้น
                this.map.fitBounds(bounds, {
                    top: 100,      // ซูมออกด้านบน
                    right: 100,    // ซูมออกด้านขวา
                    bottom: 100,   // ซูมออกด้านล่าง
                    left: 100      // ซูมออกด้านซ้าย
                });
                console.log('🔍 Map bounds adjusted with padding');
                
                if (this.props.record && this.props.record.update) {
                    this.props.record.update({
                        distance: distance,
                        estimated_time: duration,
                        distance_km: distanceKm,
                    });
                }
            }
        } catch (error) {
            console.error("❌ Error calculating route:", error);
        } finally {
            // ปล่อย flag หลังจากคำนวณเสร็จ
            setTimeout(() => {
                this.state.isCalculating = false;
                console.log('✅ Route calculation completed');
            }, 500);
        }
    }

    switchToAlternativeRoute(routeIndex) {
        // เปลี่ยนไปใช้เส้นทางทางเลือก
        const directions = this.directionsRenderer.getDirections();
        if (directions && directions.routes[routeIndex]) {
            this.directionsRenderer.setDirections({
                ...directions,
                routes: [directions.routes[routeIndex]]
            });
            this.updateRouteInfo();
        }
    }

    async forceRecalculate() {
        // ฟังก์ชันสำหรับ force recalculate เส้นทาง
        console.log("🔄 Force recalculating route...");
        const currentOrigin = this.origin;
        const currentDestination = this.destination;
        
        if (currentOrigin && currentDestination) {
            this.lastOrigin = currentOrigin;
            this.lastDestination = currentDestination;
            await this.calculateRoute();
        } else {
            console.warn("⚠️ Cannot recalculate: missing origin or destination");
        }
    }
}

GoogleMapsWidget.template = "transport_booking.GoogleMapsWidget";

registry.category("fields").add("google_maps_widget", {
    component: GoogleMapsWidget,
});
