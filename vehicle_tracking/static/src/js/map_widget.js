/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class MapWidget extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            vehicles: [],
            loading: true,
        });

        onWillStart(async () => {
            await this.loadVehicles();
        });
    }

    async loadVehicles() {
        this.state.loading = true;
        try {
            const vehicles = await this.rpc("/vehicle_tracking/get_vehicles");
            this.state.vehicles = vehicles;
        } catch (error) {
            console.error("Error loading vehicles:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async refreshData() {
        await this.loadVehicles();
    }
}

MapWidget.template = "vehicle_tracking.MapWidget";

registry.category("fields").add("vehicle_map", MapWidget);
