/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { rpc } from "@web/core/network/rpc";
import { useEffect, useRef } from "@odoo/owl";

/*
 * Dropdown แนะนำที่อยู่ (autocomplete) สำหรับช่องต้นทาง/ปลายทาง
 *
 * ไม่พึ่ง Google Maps JS (เพราะโมดูลอื่นโหลด google maps ไว้ก่อนด้วยเวอร์ชันเก่า
 * ทำให้ `google.maps.importLibrary` ใช้ไม่ได้ และ `google.maps.places.Autocomplete`
 * ตัวเดิมก็ถูก Google ยกเลิกสำหรับ key ใหม่)
 *
 * แทนที่ด้วยการเรียก backend `/npd/place_autocomplete` ซึ่ง proxy ไป Google
 * Places API (New) ให้ -> เลี่ยงปัญหา CORS และเวอร์ชัน JS ทั้งหมด
 * เมื่อเลือก/พิมพ์เสร็จ ค่าจะ commit และ onchange ฝั่ง python จะคำนวณระยะทางให้
 */
export class AutocompleteLocationField extends CharField {
    static template = "pfb_npd_tap_shipment_information.AutocompleteLocationField";

    setup() {
        super.setup();
        this.inputRef = useRef("input");
        useEffect(
            () => {
                this._buildDropdown(this.inputRef.el);
            },
            () => [this.inputRef.el]
        );
    }

    _buildDropdown(inputEl) {
        if (!inputEl || inputEl.dataset.npdAc) {
            return;
        }
        inputEl.dataset.npdAc = "1";

        const wrap = inputEl.parentElement;
        if (wrap && getComputedStyle(wrap).position === "static") {
            wrap.style.position = "relative";
        }

        const box = document.createElement("div");
        box.style.cssText =
            "position:absolute;left:0;right:0;z-index:1051;background:#fff;" +
            "border:1px solid #ced4da;border-top:none;max-height:260px;overflow-y:auto;" +
            "display:none;box-shadow:0 4px 10px rgba(0,0,0,.12);border-radius:0 0 4px 4px;";
        box.style.top = inputEl.offsetHeight + "px";
        wrap.appendChild(box);

        let timer = null;
        let seq = 0;

        const close = () => {
            box.style.display = "none";
            box.innerHTML = "";
        };

        const choose = async (fullText) => {
            close();
            // สำคัญ: ตั้งค่าในกล่อง input ให้ตรงกับที่เลือกด้วย
            // เพราะ input กำลัง focus อยู่ (dirty) ถ้าไม่ตั้งค่า กล่องจะยังโชว์คำที่พิมพ์ค้าง
            // และตอน blur CharField จะ commit คำเก่าทับค่าที่เลือก -> เหมือนไม่อัปเดต
            inputEl.value = fullText;
            // commit เข้า record (fires onchange -> คำนวณระยะทาง); ตอน blur ทีหลังจะ commit
            // ค่าเดิม (fullText) ซ้ำแบบ no-op จึงไม่ทับ
            await this.props.record.update({ [this.props.name]: fullText });
        };

        const render = (suggestions) => {
            box.innerHTML = "";
            if (!suggestions || !suggestions.length) {
                close();
                return;
            }
            for (const sug of suggestions) {
                const item = document.createElement("div");
                item.style.cssText =
                    "padding:7px 12px;cursor:pointer;border-bottom:1px solid #f1f1f1;";
                item.innerHTML =
                    `<div style="font-size:13px;color:#212529;">${sug.main || sug.text}</div>` +
                    (sug.secondary
                        ? `<div style="font-size:11px;color:#6c757d;">${sug.secondary}</div>`
                        : "");
                item.addEventListener("mouseenter", () => (item.style.background = "#f5f5f5"));
                item.addEventListener("mouseleave", () => (item.style.background = ""));
                // mousedown กัน blur ปิด dropdown ก่อนคลิกติด
                item.addEventListener("mousedown", (ev) => {
                    ev.preventDefault();
                    choose(sug.text);
                });
                box.appendChild(item);
            }
            box.style.display = "block";
        };

        const search = async (text) => {
            if (!text || text.trim().length < 2) {
                close();
                return;
            }
            const mySeq = ++seq;
            try {
                const res = await rpc("/npd/place_autocomplete", { input: text });
                if (mySeq !== seq) {
                    return; // มีการพิมพ์ใหม่กว่าแล้ว ทิ้งผลเก่า
                }
                render(res && res.suggestions);
            } catch (e) {
                console.warn("[autocomplete_location] rpc error:", e);
                close();
            }
        };

        inputEl.addEventListener("input", () => {
            clearTimeout(timer);
            timer = setTimeout(() => search(inputEl.value), 300);
        });
        inputEl.addEventListener("blur", () => setTimeout(close, 200));
        inputEl.addEventListener("keydown", (ev) => {
            if (ev.key === "Escape") {
                close();
            }
        });
    }
}

export const autocompleteLocationField = {
    ...charField,
    component: AutocompleteLocationField,
};

registry.category("fields").add("autocomplete_location", autocompleteLocationField);
