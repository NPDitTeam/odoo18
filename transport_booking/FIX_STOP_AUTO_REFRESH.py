# -*- coding: utf-8 -*-
"""
🛑 แก้ไขให้หยุด Auto-refresh เมื่อ state = 'done'

ปัญหา:
- Auto-refresh ยังทำงานต่อแม้ว่า booking state = 'done' แล้ว
- ต้องหยุด timer ทันทีเมื่อตรวจพบว่างานเสร็จสิ้น

การแก้ไข:
1. เช็ค booking.state ตอนโหลดหน้าครั้งแรก
2. เช็ค state ในทุกๆ update cycle
3. หยุด updateTimer และ countdownTimer ทันทีเมื่อ state = 'done'
4. แสดงข้อความว่างานเสร็จสิ้นแล้ว
5. ป้องกันไม่ให้สร้าง timer ใหม่ถ้างานเสร็จแล้ว
"""

def fix_auto_refresh_stop():
    """แก้ไขให้หยุด auto-refresh เมื่อ state = 'done'"""
    
    print('╔═══════════════════════════════════════════════════════════╗')
    print('║      🛑 แก้ไขให้หยุด Auto-refresh เมื่อ state = done     ║')
    print('╚═══════════════════════════════════════════════════════════╝\n')
    
    template_path = r'C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking\views\tracking_map_food_delivery.xml'
    
    try:
        # อ่านไฟล์
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes = []
        
        # ===================================================================
        # FIX 1: เพิ่มการเช็ค state ตอน initMap() ครั้งแรก
        # ===================================================================
        print('🔧 FIX 1: เพิ่มการเช็ค booking state ตอนโหลดครั้งแรก...')
        
        old_init_check = '''                        // เริ่มต้น auto-update
                        console.log('🔄 Starting initial tracking update...');
                        await updateTracking();
                        startAutoUpdate();'''
        
        new_init_check = '''                        // 🛑 เช็ค booking state ก่อนเริ่ม auto-update
                        console.log('🔍 Checking booking state before starting auto-update...');
                        const initialState = await checkBookingState();
                        
                        if (initialState === 'done') {
                            console.log('🏁 Booking already completed. Skipping auto-update.');
                            bookingState = 'done';
                            
                            // แสดงข้อความว่าเสร็จสิ้นแล้ว
                            const countdownEl = document.getElementById('countdownText');
                            if (countdownEl) {
                                countdownEl.textContent = '✅ การขนส่งเสร็จสิ้นแล้ว';
                                countdownEl.style.color = '#edf5f2';
                                countdownEl.style.fontWeight = 'bold';
                            }
                            
                            // อัปเดตแผนที่ครั้งสุดท้าย
                            await updateTracking();
                            return; // ไม่เริ่ม auto-update
                        }
                        
                        // เริ่มต้น auto-update เฉพาะเมื่อยังไม่เสร็จ
                        console.log('🔄 Starting initial tracking update...');
                        await updateTracking();
                        startAutoUpdate();'''
        
        if old_init_check in content:
            content = content.replace(old_init_check, new_init_check)
            changes.append('✅ FIX 1: เพิ่มการเช็ค state ตอนโหลดครั้งแรก')
        else:
            print('⚠️  ไม่พบโค้ด initMap check pattern')
        
        # ===================================================================
        # FIX 2: เพิ่ม function checkBookingState()
        # ===================================================================
        print('🔧 FIX 2: เพิ่ม function checkBookingState()...')
        
        # หาตำแหน่งที่จะแทรก function (ก่อน updateTracking function)
        insert_before = '''                    // 🔄 Update Tracking Data
                    async function updateTracking() {'''
        
        check_function = '''                    // 🛑 Check Booking State
                    async function checkBookingState() {
                        try {
                            const response = await fetch('/web/dataset/call_kw/vehicle.booking/read', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    jsonrpc: '2.0',
                                    method: 'call',
                                    params: {
                                        model: 'vehicle.booking',
                                        method: 'read',
                                        args: [[CONFIG.bookingId], ['state']],
                                        kwargs: {}
                                    },
                                    id: Date.now(),
                                })
                            });
                            
                            const data = await response.json();
                            if (data.result && data.result.length > 0) {
                                const state = data.result[0].state;
                                console.log(`📊 Current booking state: ${state}`);
                                return state;
                            }
                        } catch (error) {
                            console.error('❌ Error checking booking state:', error);
                        }
                        return null;
                    }
                    
                    // 🔄 Update Tracking Data
                    async function updateTracking() {'''
        
        if insert_before in content:
            content = content.replace(insert_before, check_function)
            changes.append('✅ FIX 2: เพิ่ม function checkBookingState()')
        else:
            print('⚠️  ไม่พบตำแหน่งสำหรับแทรก checkBookingState()')
        
        # ===================================================================
        # FIX 3: ปรับปรุงการเช็ค state ใน updateTracking()
        # ===================================================================
        print('🔧 FIX 3: ปรับปรุงการเช็ค state ใน updateTracking()...')
        
        old_state_check = '''                                // 🛑 ตรวจสอบ: ถ้า state = 'done' ให้หยุดการรีเฟรชทันที
                                if (booking.state === 'done') {
                                    console.log('🏁 Booking completed! Stopping auto-refresh...');
                                    
                                    // หยุด Auto-refresh Timer
                                    if (updateTimer) {
                                        clearInterval(updateTimer);
                                        updateTimer = null;
                                    }
                                    
                                    // หยุด Countdown Timer
                                    if (countdownTimer) {
                                        clearInterval(countdownTimer);
                                        countdownTimer = null;
                                    }
                                    
                                    // แสดงข้อความว่าเสร็จสิ้นแล้ว
                                    const countdownEl = document.getElementById('countdownText');
                                    if (countdownEl) {
                                        countdownEl.textContent = '✅ การขนส่งเสร็จสิ้นแล้ว';
                                        countdownEl.style.color = '#edf5f2';
                                        countdownEl.style.fontWeight = 'bold';
                                    }
                                    
                                    // อัปเดตแผนที่ครั้งสุดท้าย
                                    updateMapPositions(booking);
                                    
                                    return; // ออกจากฟังก์ชัน ไม่ทำอะไรต่อ
                                }'''
        
        new_state_check = '''                                // 🛑 ตรวจสอบ: ถ้า state = 'done' ให้หยุดการรีเฟรชทันทีและถาวร
                                if (booking.state === 'done') {
                                    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                                    console.log('🏁 BOOKING COMPLETED! STOPPING ALL TIMERS...');
                                    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                                    
                                    // 🛑 บันทึก state เพื่อป้องกันการเริ่ม timer ใหม่
                                    bookingState = 'done';
                                    
                                    // 🛑 หยุด Auto-refresh Timer
                                    if (updateTimer) {
                                        console.log('🛑 Stopping update timer...');
                                        clearInterval(updateTimer);
                                        updateTimer = null;
                                    }
                                    
                                    // 🛑 หยุด Countdown Timer
                                    if (countdownTimer) {
                                        console.log('🛑 Stopping countdown timer...');
                                        clearInterval(countdownTimer);
                                        countdownTimer = null;
                                    }
                                    
                                    // 📊 แสดงข้อความว่าเสร็จสิ้นแล้ว
                                    const countdownEl = document.getElementById('countdownText');
                                    if (countdownEl) {
                                        countdownEl.textContent = '✅ การขนส่งเสร็จสิ้นแล้ว';
                                        countdownEl.style.color = '#edf5f2';
                                        countdownEl.style.fontWeight = 'bold';
                                    }
                                    
                                    // 🗺️ อัปเดตแผนที่ครั้งสุดท้าย
                                    updateMapPositions(booking);
                                    
                                    console.log('✅ All timers stopped. Auto-refresh disabled permanently.');
                                    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                                    
                                    return; // ออกจากฟังก์ชัน ไม่ทำอะไรต่อ
                                }'''
        
        if old_state_check in content:
            content = content.replace(old_state_check, new_state_check)
            changes.append('✅ FIX 3: ปรับปรุงการเช็ค state ใน updateTracking()')
        else:
            print('⚠️  ไม่พบ state check pattern ใน updateTracking()')
        
        # ===================================================================
        # FIX 4: ปรับปรุง startAutoUpdate() ให้เช็ค state ก่อนเริ่ม
        # ===================================================================
        print('🔧 FIX 4: ปรับปรุง startAutoUpdate() ให้เช็ค state ก่อนเริ่ม...')
        
        old_start_auto = '''                    // 🔄 Start Auto Update Timer
                    function startAutoUpdate() {
                        // 🛑 ตรวจสอบ: ถ้า state = 'done' อยู่แล้ว ไม่ต้องเริ่ม timer
                        if (bookingState === 'done') {
                            console.log('🏁 Booking already completed. Skipping auto-update timer.');
                            
                            // แสดงข้อความเสร็จสิ้น
                            const countdownEl = document.getElementById('countdownText');
                            if (countdownEl) {
                                countdownEl.textContent = '✅ การขนส่งเสร็จสิ้นแล้ว';
                                countdownEl.style.color = '#edf5f2';
                                countdownEl.style.fontWeight = 'bold';
                            }
                            return; // ออกจากฟังก์ชันทันที
                        }'''
        
        new_start_auto = '''                    // 🔄 Start Auto Update Timer
                    function startAutoUpdate() {
                        // 🛑 ตรวจสอบ: ถ้า state = 'done' อยู่แล้ว ไม่ต้องเริ่ม timer
                        if (bookingState === 'done') {
                            console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                            console.log('🛑 CANNOT START AUTO-UPDATE: Booking already completed');
                            console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                            
                            // แสดงข้อความเสร็จสิ้น
                            const countdownEl = document.getElementById('countdownText');
                            if (countdownEl) {
                                countdownEl.textContent = '✅ การขนส่งเสร็จสิ้นแล้ว';
                                countdownEl.style.color = '#edf5f2';
                                countdownEl.style.fontWeight = 'bold';
                            }
                            return; // ออกจากฟังก์ชันทันที
                        }
                        
                        console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                        console.log(`⏰ STARTING AUTO-UPDATE: Interval = ${updateInterval}ms`);
                        console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');'''
        
        if old_start_auto in content:
            content = content.replace(old_start_auto, new_start_auto)
            changes.append('✅ FIX 4: ปรับปรุง startAutoUpdate() ให้เช็ค state')
        else:
            print('⚠️  ไม่พบ startAutoUpdate pattern')
        
        # บันทึกไฟล์
        if content != original_content:
            # สำรองไฟล์เดิม
            backup_path = template_path + '.backup_stop_refresh'
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            print(f'\n💾 สำรองไฟล์เดิมไว้ที่: {backup_path}')
            
            # บันทึกไฟล์ใหม่
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print('\n📝 การแก้ไขที่ทำทั้งหมด:')
            for i, change in enumerate(changes, 1):
                print(f'   {i}. {change}')
            
            print(f'\n✅ แก้ไขไฟล์สำเร็จ! ({len(changes)} การแก้ไข)')
            return True
        else:
            print('\n⚠️  ไม่พบโค้ดที่ต้องแก้ไข (อาจแก้ไขแล้ว)')
            return False
            
    except Exception as e:
        print(f'\n❌ Error: {str(e)}')
        import traceback
        traceback.print_exc()
        return False

def main():
    print('\n')
    success = fix_auto_refresh_stop()
    
    print('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    
    if success:
        print('✅ การแก้ไขเสร็จสมบูรณ์!')
        print('\n📋 สิ่งที่แก้ไข:')
        print('   1. เพิ่มการเช็ค booking.state ตอนโหลดหน้าครั้งแรก')
        print('   2. เพิ่ม function checkBookingState() สำหรับตรวจสอบ state')
        print('   3. ปรับปรุงการเช็ค state ใน updateTracking() ให้ละเอียดขึ้น')
        print('   4. ปรับปรุง startAutoUpdate() ให้ป้องกันการเริ่ม timer ใหม่')
        
        print('\n📋 ผลลัพธ์ที่คาดหวัง:')
        print('   ✅ เมื่อ state = "done" จะหยุด auto-refresh ทันที')
        print('   ✅ แสดงข้อความ "การขนส่งเสร็จสิ้นแล้ว"')
        print('   ✅ ไม่สามารถเริ่ม timer ใหม่ได้')
        print('   ✅ หยุดทั้ง updateTimer และ countdownTimer')
        
        print('\n📋 ขั้นตอนต่อไป:')
        print('   1. รัน restart_odoo_final.bat')
        print('   2. เคลียร์ cache เบราว์เซอร์')
        print('   3. เปิดหน้า tracking map ของ booking ที่ state = "done"')
        print('   4. ตรวจสอบ console log (F12) ควรเห็น:')
        print('      - "🏁 BOOKING COMPLETED! STOPPING ALL TIMERS..."')
        print('      - "✅ All timers stopped. Auto-refresh disabled permanently."')
    else:
        print('❌ การแก้ไขล้มเหลว หรือไม่พบโค้ดที่ต้องแก้')
        print('\n💡 ลองตรวจสอบ:')
        print('   - ไฟล์ tracking_map_food_delivery.xml มีอยู่จริง')
        print('   - โครงสร้างโค้ดยังเหมือนเดิม')
        print('   - ไม่มีการแก้ไขไปก่อนหน้านี้')
    
    print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    
    input('\n\nกด Enter เพื่อปิด...')

if __name__ == '__main__':
    main()
