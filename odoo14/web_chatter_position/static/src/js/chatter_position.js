/** @odoo-module **/

import { FormRenderer } from "@web/views/form/form_renderer";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched, useRef } from "@odoo/owl";
import { session } from "@web/session";

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.rootRef = useRef("compiled_view_root");

        const doApply = () => this._applyChatterPosition();
        onMounted(doApply);
        onPatched(doApply);
    },

    _applyChatterPosition() {
        const root = this.rootRef.el;
        if (!root) return;

        const chatterEl = root.querySelector(
            ".o-mail-Form-chatter, .o_FormRenderer_chatterContainer"
        );
        if (!chatterEl) return;

        const sheetBg = root.querySelector(".o_form_sheet_bg");
        if (!sheetBg) return;

        const parent = sheetBg.parentElement;
        if (!parent) return;

        // Read from session_info (injected by ir.http)
        const position = session.chatter_position || "sided";

        if (position === "sided") {
            parent.style.display = "flex";
            parent.style.flexWrap = "nowrap";
            sheetBg.style.flex = "1 1 auto";
            sheetBg.style.minWidth = "0";
            sheetBg.style.overflow = "auto";
            chatterEl.style.flex = "0 0 400px";
            chatterEl.style.maxWidth = "400px";
            chatterEl.style.borderLeft = "1px solid #dee2e6";
            chatterEl.style.overflowY = "auto";
            chatterEl.style.maxHeight = "calc(100vh - 100px)";
        } else {
            parent.style.display = "";
            parent.style.flexWrap = "";
            sheetBg.style.flex = "";
            sheetBg.style.minWidth = "";
            sheetBg.style.overflow = "";
            chatterEl.style.flex = "";
            chatterEl.style.maxWidth = "";
            chatterEl.style.borderLeft = "";
            chatterEl.style.overflowY = "";
            chatterEl.style.maxHeight = "";
        }
    },
});
