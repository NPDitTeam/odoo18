/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useEffect, useRef } from "@odoo/owl";

export class AutocompleteLocationField extends CharField {
    static template = "pfb_npd_tap_shipment_information.AutocompleteLocationField";

    setup() {
        super.setup();
        this.inputRef = useRef("input");

        useEffect(
            () => {
                if (this.inputRef.el) {
                    this._enableAutocomplete(this.inputRef.el);
                }
            },
            () => [this.inputRef.el]
        );
    }

    _enableAutocomplete(inputEl) {
        if (!window.google || !window.google.maps) {
            // Load Google Maps API if not loaded
            const script = document.createElement("script");
            script.src =
                "https://maps.googleapis.com/maps/api/js?key=AIzaSyCHKkMOyDdI29v52SULcRx_OcB3i-MD7lw&libraries=places";
            script.onload = () => this._initAutocomplete(inputEl);
            document.head.appendChild(script);
        } else {
            this._initAutocomplete(inputEl);
        }
    }

    _initAutocomplete(inputEl) {
        const autocomplete = new google.maps.places.Autocomplete(inputEl, {
            componentRestrictions: { country: "th" },
            fields: ["formatted_address", "geometry", "name", "place_id", "types"],
        });

        autocomplete.addListener("place_changed", () => {
            const place = autocomplete.getPlace();
            if (!place || (!place.formatted_address && !place.name)) {
                return;
            }
            const fullAddress = place.formatted_address || place.name;
            this.props.record.update({ [this.props.name]: fullAddress });
        });
    }
}

export const autocompleteLocationField = {
    ...charField,
    component: AutocompleteLocationField,
};

registry.category("fields").add("autocomplete_location", autocompleteLocationField);
