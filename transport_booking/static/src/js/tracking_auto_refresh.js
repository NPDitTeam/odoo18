/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { session } from "@web/session";

/**
 * 🔄 Auto-refresh controller สำหรับ vehicle.tracking list view
 * Version: 4.3 - Fix error message display
 */

console.log("🚀 [Auto-Refresh v4.3] Module loaded!");

patch(ListController.prototype, {
    setup() {
        super.setup();
        
        console.log("🔧 [Auto-Refresh] Setup called for model:", this.props.resModel);
        
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.refreshInterval = null;
        this.trackingIntervalMinutes = 30; // ✅ Default 30 นาที
        
        // ดึงการตั้งค่า tracking_interval
        onWillStart(async () => {
            if (this.props.resModel === "vehicle.tracking") {
                console.log("✅ [Auto-Refresh] This is vehicle.tracking view!");
                await this.loadTrackingSettings();
            } else {
                console.log(`⏭️  [Auto-Refresh] Skipping (model: ${this.props.resModel})`);
            }
        });
        
        // เริ่ม auto-refresh เมื่อ mount
        onMounted(() => {
            if (this.props.resModel === "vehicle.tracking") {
                console.log("🎯 [Auto-Refresh] View mounted, starting auto-refresh...");
                this.startAutoRefresh();
            }
        });
        
        // หยุด auto-refresh เมื่อ unmount
        onWillUnmount(() => {
            if (this.refreshInterval) {
                console.log("🛑 [Auto-Refresh] Stopping auto-refresh...");
                clearInterval(this.refreshInterval);
                this.refreshInterval = null;
            }
        });
    },
    
    /**
     * โหลดการตั้งค่า tracking_interval จาก tracking.settings
     * Version 4.3: แสดง warning แทน error
     */
    async loadTrackingSettings() {
        try {
            console.log("📋 [Auto-Refresh] Loading tracking settings...");
            
            // ✅ วิธีที่ถูกต้องในการเข้าถึง user ID ใน Odoo 18
            let userId = null;
            
            // Method 1: ใช้ session module (imported at top)
            if (session && session.uid) {
                userId = session.uid;
                console.log("✅ [Auto-Refresh] Got user ID from session.uid:", userId);
            }
            // Method 2: ใช้ this.env.session.uid
            else if (this.env && this.env.session && this.env.session.uid) {
                userId = this.env.session.uid;
                console.log("✅ [Auto-Refresh] Got user ID from this.env.session.uid:", userId);
            }
            // Method 3: ใช้ session.user_id
            else if (session && session.user_id) {
                userId = session.user_id;
                console.log("✅ [Auto-Refresh] Got user ID from session.user_id:", userId);
            }
            // Method 4: ใช้ this.env.session.user_id
            else if (this.env && this.env.session && this.env.session.user_id) {
                userId = this.env.session.user_id;
                console.log("✅ [Auto-Refresh] Got user ID from this.env.session.user_id:", userId);
            }
            // Method 5: ใช้ user_context
            else if (this.env && this.env.session && this.env.session.user_context && this.env.session.user_context.uid) {
                userId = this.env.session.user_context.uid;
                console.log("✅ [Auto-Refresh] Got user ID from this.env.session.user_context.uid:", userId);
            }
            else {
                // ⚠️ ใช้ warning แทน error เพราะระบบยังทำงานได้ปกติ
                console.warn("⚠️ [Auto-Refresh] Cannot detect user ID - Using default settings");
                console.warn("   → Default interval: 30 minutes");
                console.warn("   → Auto-refresh will work normally");
                this.trackingIntervalMinutes = 30;
                return; // ออกจาก function และเริ่ม auto-refresh ด้วย default value
            }
            
            // เพิ่ม timestamp เพื่อป้องกัน cache
            const timestamp = new Date().getTime();
            console.log("👤 [Auto-Refresh] Using user ID:", userId);
            
            // ✅ ใช้ ORM call
            const settings = await this.orm.call(
                "tracking.settings",
                "get_user_settings",
                [userId],
                {
                    context: {
                        force_refresh: true,
                        _nocache: timestamp
                    }
                }
            );
            
            if (settings && settings.tracking_interval) {
                this.trackingIntervalMinutes = settings.tracking_interval;
                console.log(`✅ [Auto-Refresh] Loaded interval: ${this.trackingIntervalMinutes} minutes`);
            } else {
                console.warn("⚠️ [Auto-Refresh] tracking_interval not found, using default: 30 minutes");
                this.trackingIntervalMinutes = 30;
            }
            
        } catch (error) {
            console.error("❌ [Auto-Refresh] Failed to load settings:", error.message);
            console.warn("⚠️ [Auto-Refresh] Using default interval: 30 minutes");
            this.trackingIntervalMinutes = 30;
        }
    },
    
    /**
     * เริ่มต้น auto-refresh
     */
    startAutoRefresh() {
        // แปลงนาทีเป็น milliseconds
        const intervalMs = this.trackingIntervalMinutes * 60 * 1000;
        
        console.log("=".repeat(70));
        console.log(`🔄 [Auto-Refresh] Starting auto-refresh`);
        console.log(`   ⏱️  Interval: ${this.trackingIntervalMinutes} minutes`);
        console.log(`   🕐 Milliseconds: ${intervalMs}ms`);
        console.log(`   📅 Next refresh: ${new Date(Date.now() + intervalMs).toLocaleString('th-TH')}`);
        console.log("=".repeat(70));
        
        // แสดง notification
        try {
            this.notification.add(
                `🔄 Auto-refresh เปิดใช้งาน (ทุก ${this.trackingIntervalMinutes} นาที)`,
                {
                    type: "info",
                    sticky: false,
                }
            );
            console.log("✅ [Auto-Refresh] Notification displayed successfully");
        } catch (error) {
            console.error("❌ [Auto-Refresh] Failed to show notification:", error);
        }
        
        // ตั้งเวลา refresh
        this.refreshInterval = setInterval(() => {
            this.refreshList();
        }, intervalMs);
        
        console.log(`✅ [Auto-Refresh] Timer started successfully!`);
        console.log(`   Timer ID: ${this.refreshInterval}`);
        console.log(`   First refresh in: ${this.trackingIntervalMinutes} minutes`);
    },
    
    /**
     * Refresh list view
     */
    async refreshList() {
        const now = new Date().toLocaleString('th-TH');
        try {
            console.log(`🔄 [Auto-Refresh] Refreshing tracking list at ${now}...`);
            await this.model.root.load();
            console.log(`✅ [Auto-Refresh] List refreshed successfully at ${now}`);
        } catch (error) {
            console.error(`❌ [Auto-Refresh] Failed to refresh list at ${now}:`, error);
            console.error("   Error details:", error.message);
            console.error("   Stack trace:", error.stack);
        }
    },
});

console.log("✅ [Auto-Refresh v4.3] Patch applied successfully!");