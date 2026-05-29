/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const GOOGLE_API_KEY = "AIzaSyAorvWR_BL6tgkNgkkRO4NIb8ZTKq92S3U";

export class LocationAutocompleteWidget extends Component {
    setup() {
        this.inputRef = useRef("locationInput");
        this.autocomplete = null;
        this.state = useState({
            value: this.props.record.data[this.props.name] || ""
        });

        onMounted(() => {
            this.initializeAutocomplete();
        });

        onWillUpdateProps((nextProps) => {
            // อัพเดท state เมื่อค่าจาก record เปลี่ยน (เช่น จาก onchange ของ transport_order_id)
            const newValue = nextProps.record.data[this.props.name] || "";
            if (newValue !== this.state.value) {
                console.log(`🔄 [${this.props.name}] Updating from:`, this.state.value, "to:", newValue);
                this.state.value = newValue;
                
                // อัพเดท input element ด้วย
                if (this.inputRef.el) {
                    this.inputRef.el.value = newValue;
                }
            }
        });

        onWillUnmount(() => {
            if (this.autocomplete) {
                google.maps.event.clearInstanceListeners(this.autocomplete);
            }
        });
    }

    async loadGoogleMapsScript() {
        return new Promise((resolve, reject) => {
            if (window.google && window.google.maps && window.google.maps.places) {
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

    async initializeAutocomplete() {
        if (!this.inputRef.el) {
            return;
        }

        try {
            await this.loadGoogleMapsScript();

            // สร้าง Autocomplete โดยจำกัดเฉพาะประเทศไทย
            this.autocomplete = new google.maps.places.Autocomplete(this.inputRef.el, {
                componentRestrictions: { country: "th" }, // 🇹🇭 จำกัดเฉพาะประเทศไทย
                fields: ["formatted_address", "geometry", "name", "place_id"],
                types: ["geocode", "establishment"], // รองรับทั้งที่อยู่และสถานที่
            });

            // เมื่อเลือกที่อยู่จาก autocomplete
            this.autocomplete.addListener("place_changed", () => {
                const place = this.autocomplete.getPlace();
                
                if (!place.geometry) {
                    console.warn("No geometry found for selected place");
                    return;
                }

                const selectedAddress = place.formatted_address || place.name || "";
                console.log("✅ Selected location:", selectedAddress);

                // อัพเดทค่าใน state และ record
                this.state.value = selectedAddress;
                
                if (this.props.record && this.props.record.update) {
                    // อัพเดทที่อยู่
                    this.props.record.update({
                        [this.props.name]: selectedAddress
                    });
                    
                    // บังคับให้ record save และ trigger onchange
                    setTimeout(() => {
                        // Trigger การคำนวณเส้นทางใหม่โดยการ notify changes
                        const pickup = this.props.record.data.pickup_location || "";
                        const destination = this.props.record.data.destination || "";
                        
                        console.log("📍 Triggering route update - Origin:", pickup, "Destination:", destination);
                        
                        // Force trigger update ทั้ง 2 ฟิลด์เพื่อให้แผนที่รีเฟรช
                        this.props.record.update({
                            pickup_location: pickup,
                            destination: destination,
                        });
                    }, 100);
                }
            });

            console.log("✅ Location Autocomplete initialized for", this.props.name);
        } catch (error) {
            console.error("❌ Error initializing autocomplete:", error);
        }
    }

    onInputChange(ev) {
        // อัพเดทค่าเมื่อพิมพ์ด้วยตนเอง (ไม่ได้เลือกจาก autocomplete)
        const value = ev.target.value;
        console.log("📝 Manual input change:", value);
        
        // อัพเดท state
        this.state.value = value;
        
        if (this.props.record && this.props.record.update) {
            this.props.record.update({
                [this.props.name]: value
            });
        }
    }
}

LocationAutocompleteWidget.template = "transport_booking.LocationAutocompleteWidget";
LocationAutocompleteWidget.props = {
    ...standardFieldProps,
};

registry.category("fields").add("location_autocomplete", {
    component: LocationAutocompleteWidget,
});
