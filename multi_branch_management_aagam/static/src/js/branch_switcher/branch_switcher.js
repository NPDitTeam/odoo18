/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";

/**
 * Navbar branch switcher.
 *
 * Lets users who belong to the "Multi Branch" group tick one or more of their
 * allowed branches. The selection is saved to res.users.multi_branch_id and the
 * page reloads so the branch record rules re-filter every model.
 */
export class BranchSwitcher extends Component {
    static template = "multi_branch_management_aagam.BranchSwitcher";
    static components = { Dropdown };
    static props = {};

    setup() {
        this.orm = useService("orm");
        // [{id, name}] of branches the user is allowed to use.
        this.allowedBranches = session.allowed_branches || [];
        this.state = useState({
            selectedIds: [...(session.current_branch_ids || [])],
        });
    }

    get currentLabel() {
        const selected = this.allowedBranches.filter((b) =>
            this.state.selectedIds.includes(b.id)
        );
        if (selected.length === 0) {
            return _t("Branch");
        }
        if (selected.length === 1) {
            return selected[0].name;
        }
        return _t("%s branches", selected.length);
    }

    isSelected(branchId) {
        return this.state.selectedIds.includes(branchId);
    }

    /** Tick / untick a branch (always keep at least one selected). */
    toggleBranch(branchId) {
        if (this.state.selectedIds.includes(branchId)) {
            if (this.state.selectedIds.length > 1) {
                this.state.selectedIds = this.state.selectedIds.filter(
                    (id) => id !== branchId
                );
            }
        } else {
            this.state.selectedIds = [...this.state.selectedIds, branchId];
        }
    }

    /** Quick switch: work in this single branch only. */
    async logInto(branchId) {
        await this._apply([branchId]);
    }

    /** Apply the current checkbox selection. */
    async confirm() {
        await this._apply(this.state.selectedIds);
    }

    async _apply(branchIds) {
        await this.orm.call("res.users", "set_active_branches", [branchIds]);
        browser.location.reload();
    }
}

export const systrayItem = { Component: BranchSwitcher };

// Only mount the switcher for users allowed to switch branches.
if (session.display_switch_branch_menu) {
    registry
        .category("systray")
        .add("multi_branch_management_aagam.BranchSwitcher", systrayItem, {
            sequence: 1,
        });
}
