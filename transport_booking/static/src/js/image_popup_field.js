/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { isBinarySize } from "@web/core/utils/binary";
import { imageUrl } from "@web/core/utils/urls";
import { ImageField, imageField } from "@web/views/fields/image/image_field";

/**
 * ช่องรูปที่คลิกแล้วเปิดดูรูปขนาดเต็ม ด้วยตัวแสดงไฟล์ของ Odoo เอง (ซูม/หมุน/ดาวน์โหลดได้)
 * ใช้แทน widget="image" ได้ทันที: <field name="..." widget="image_popup"/>
 */
export class ImagePopupField extends ImageField {
    static template = "transport_booking.ImagePopupField";

    setup() {
        super.setup();
        this.fileViewer = useFileViewer();
    }

    onImageClick() {
        const value = this.props.record.data[this.props.name];
        if (!value || !this.state.isValid) {
            return;
        }
        const { resModel, resId } = this.props.record;
        // รูปที่บันทึกแล้วดึงจากเซิร์ฟเวอร์ขนาดจริง / รูปที่ยังไม่บันทึกใช้ข้อมูลในหน้าจอ
        const saved = resId && isBinarySize(value);
        const source = saved
            ? imageUrl(resModel, resId, this.props.name, { unique: this.rawCacheKey })
            : this.getUrl(this.props.name);
        this.fileViewer.open({
            isImage: true,
            isViewable: true,
            isPdf: false,
            isText: false,
            isVideo: false,
            isUrlYoutube: false,
            mimetype: "image/jpeg",
            displayName: this.props.record.fields[this.props.name].string,
            defaultSource: source,
            downloadUrl: saved
                ? `/web/content/${resModel}/${resId}/${this.props.name}?download=true`
                : source,
        });
    }
}

export const imagePopupField = {
    ...imageField,
    component: ImagePopupField,
};

registry.category("fields").add("image_popup", imagePopupField);
