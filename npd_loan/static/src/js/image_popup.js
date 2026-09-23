/** @odoo-module **/
/**
 * Field widget: npd_image_popup
 * =============================
 * แสดงรูปย่อในช่องตาราง กดแล้วเด้ง popup รูปขนาดเต็มทันที
 *
 *   <field name="image_preview" widget="npd_image_popup"
 *          options="{'src_field': 'attachment', 'title_field': 'name', 'height': 45}"/>
 *
 * ทำไมไม่ใช้ kanban + modal ของ Bootstrap:
 *   ใน list ที่อยู่ในฟอร์ม การคลิกการ์ด/แถวถูก Odoo ดักไปเปิดฟอร์มของเรกคอร์ดก่อน
 *   modal จึงไม่เด้ง (และถ้าฟอร์มถูกเปิดเป็น dialog ซ้อน จะไปทับหน้าอื่น)
 *   widget นี้จึง stopPropagation แล้วเปิด Dialog ของ Odoo เองแทน
 *
 * options
 *   src_field   ฟิลด์ที่ใช้ดึงรูปจริง (ค่าตั้งต้น = ฟิลด์ที่ widget วางอยู่)
 *               ปกติชี้ไปฟิลด์ที่เก็บไฟล์จริง เพื่อให้ได้รูปเต็มความละเอียด
 *   title_field ฟิลด์ที่ใช้เป็นหัวข้อ popup (ค่าตั้งต้น 'name')
 *   height      ความสูงรูปย่อเป็น px (ค่าตั้งต้น 45)
 */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { Component } from "@odoo/owl";

const THUMB_HEIGHT = 45;

export class ImagePopupDialog extends Component {
    static template = "npd_loan.ImagePopupDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        src: String,
    };
}

export class ImagePopupField extends Component {
    static template = "npd_loan.ImagePopupField";
    static props = {
        ...standardFieldProps,
        srcField: { type: String, optional: true },
        titleField: { type: String, optional: true },
        height: { type: Number, optional: true },
    };

    setup() {
        this.dialog = useService("dialog");
    }

    get record() {
        return this.props.record;
    }

    /** มีรูปให้แสดงไหม (แถวใหม่ที่ยังไม่บันทึกจะยังไม่มี id จึงสร้าง URL ไม่ได้) */
    get hasImage() {
        return Boolean(this.record.data[this.props.name]) && Boolean(this.record.resId);
    }

    get src() {
        const field = this.props.srcField || this.props.name;
        return `/web/image/${this.record.resModel}/${this.record.resId}/${field}`;
    }

    get title() {
        return this.record.data[this.props.titleField || "name"] || "";
    }

    get height() {
        return this.props.height || THUMB_HEIGHT;
    }

    onClick(ev) {
        // กันไม่ให้ list เอาคลิกนี้ไปเปิดฟอร์มของแถว
        ev.stopPropagation();
        ev.preventDefault();
        this.dialog.add(ImagePopupDialog, { title: this.title, src: this.src });
    }
}

export const imagePopupField = {
    component: ImagePopupField,
    displayName: "รูปย่อ กดดูขนาดเต็ม",
    supportedTypes: ["binary"],
    extractProps: ({ options }) => ({
        srcField: options.src_field,
        titleField: options.title_field,
        height: options.height,
    }),
};

registry.category("fields").add("npd_image_popup", imagePopupField);
