/**
 * 🔄 Vehicle Tracking Auto-Refresh - Backend Only (No UI)
 * ✅ ดึงค่า tracking_interval จากฐานข้อมูล
 * ✅ รีเฟรชอัตโนมัติทุก 3 นาที
 * ✅ ไม่มี UI, Debug Panel, หรือ Countdown
 */

(function() {
    'use strict';

    // ⚙️ Configuration
    let autoRefreshInterval = 3 * 60 * 1000; // Default: 3 minutes
    let autoRefreshTimer = null;
    let shouldRefresh = true;

    /**
     * 📡 Load tracking_interval from database with timeout
     */
    async function loadTrackingInterval() {
        try {
            console.log('📡 [Auto-Refresh] Loading tracking_interval...');
            
            // Create controller with 5 second timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch('/api/settings/get', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jsonrpc: '2.0', params: {} }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.result && data.result.success && data.result.data) {
                const interval = data.result.data.tracking_interval || 3;
                autoRefreshInterval = interval * 60 * 1000;
                console.log(`✅ [Auto-Refresh] Loaded: ${interval} minutes (${autoRefreshInterval}ms)`);
                return autoRefreshInterval;
            } else {
                throw new Error('Invalid API response');
            }
        } catch (error) {
            console.warn(`⚠️ [Auto-Refresh] API failed: ${error.message} - Using default 3 minutes`);
            autoRefreshInterval = 3 * 60 * 1000;
            return autoRefreshInterval;
        }
    }

    /**
     * 🔄 Setup Auto-Refresh
     */
    function setupAutoRefresh() {
        if (autoRefreshTimer) {
            clearInterval(autoRefreshTimer);
        }

        console.log(`✅ [Auto-Refresh] Started - Refresh every ${autoRefreshInterval / 60000} minutes`);

        autoRefreshTimer = setInterval(async () => {
            if (!shouldRefresh) {
                console.log('⏹️ [Auto-Refresh] Paused');
                return;
            }

            try {
                // Try to click refresh button
                const refreshBtn = document.querySelector(
                    'button[data-tooltip="Refresh"], ' +
                    'button[title="Refresh"], ' +
                    'button[aria-label="Refresh"]'
                );

                if (refreshBtn) {
                    refreshBtn.click();
                    console.log('🔄 [Auto-Refresh] Refreshed vehicle tracking list');
                } else {
                    console.warn('⚠️ [Auto-Refresh] Refresh button not found');
                }
            } catch (error) {
                console.error(`❌ [Auto-Refresh] Error: ${error.message}`);
            }
        }, autoRefreshInterval);
    }

    /**
     * 🚀 Initialize on page load
     */
    document.addEventListener('DOMContentLoaded', async () => {
        console.log('📍 [Auto-Refresh] Vehicle Tracking page initialized');
        
        // Load interval from database
        await loadTrackingInterval();
        
        // Start auto-refresh
        setupAutoRefresh();
        
        console.log('✅ [Auto-Refresh] System running in background');
    });

    // Global control
    window.trackingAutoRefresh = {
        pause: () => { shouldRefresh = false; console.log('⏸️ Auto-refresh paused'); },
        resume: () => { shouldRefresh = true; console.log('▶️ Auto-refresh resumed'); },
        stop: () => { clearInterval(autoRefreshTimer); console.log('⏹️ Auto-refresh stopped'); },
        status: () => console.log({ autoRefreshInterval, shouldRefresh, isRunning: !!autoRefreshTimer })
    };

    console.log('🎉 Auto-Refresh System Loaded');
})();
