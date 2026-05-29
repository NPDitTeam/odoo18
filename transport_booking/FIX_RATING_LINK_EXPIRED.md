# 🔧 RATING LINK EXPIRED - COMPLETE FIX GUIDE

## ⚡ Quick Fix (5 minutes)

### Step 1: Identify the Problem
The error "Link หมดอายุหรือไม่ถูกต้อง" appears when:
- ❌ Rating record state is marked as 'expired'
- ❌ Rating token doesn't exist in database
- ❌ Booking record was deleted

### Step 2: Reset Expired Rating Links

**In Odoo Admin:**

1. Go to: **Transport Booking → Delivery Rating** (or **Ratings**)
2. Find the booking with the expired link
3. Click to open the rating record
4. In the **State** field, change from "expired" → "pending"
5. Click **Save**
6. Copy the link from **Rating Link** field
7. Test the link in a new browser window/private tab

### Step 3: If No Records Show

**In Odoo Admin:**

1. Go to: **Transport Booking → Vehicle Booking**
2. Find the delivery you want to rate
3. Click the button **"Create Rating Link"** (if it exists)
4. A new rating will be created
5. Copy the link and test it

### Step 4: Clear Cache (If still not working)

```bash
# Windows - Open Command Prompt and run:
cd C:\Program Files\Odoo 18.0.20251009\server
python manage.py clear_cache

# Or manually clear Odoo cache:
# 1. Stop Odoo (Ctrl+C)
# 2. Delete: C:\Program Files\Odoo 18.0.20251009\.odoo\cache\*
# 3. Start Odoo again
```

---

## 🛠️ Technical Fix (If issue persists)

### Issue 1: Strict State Check

**BEFORE (Broken):**
```python
rating = self.search([
    ('rating_token', '=', token),
    ('state', '=', 'pending')  # ❌ Only finds pending
], limit=1)
```

**AFTER (Fixed):**
```python
rating = self.search([
    ('rating_token', '=', token),
    ('state', '!=', 'expired')  # ✅ Finds pending OR done
], limit=1)
```

✅ **This fix has already been applied to your delivery_rating.py**

---

## 🧪 Testing the Fix

### Test Case 1: Link for Unrated Delivery
```
1. Create a new booking
2. Mark as "done"
3. Create rating link
4. Click link from another browser (incognito/private)
5. Should show rating form ✓
```

### Test Case 2: Allow Re-rating
```
1. Rate a delivery with 5 stars
2. Try accessing the same link again
3. Should show the form again (can update rating) ✓
4. Save new rating ✓
```

### Test Case 3: Expired Link
```
1. Manually set rating state to "expired" in admin
2. Try accessing the link
3. Should show "expired" message ✓
```

---

## 🚀 Advanced: SQL Direct Query

If you need to check database directly:

```sql
-- Check all ratings
SELECT 
    id, 
    rating_token, 
    state, 
    create_date,
    CONCAT('/rating/', rating_token) as link
FROM delivery_rating
ORDER BY create_date DESC
LIMIT 20;

-- Reset expired ratings
UPDATE delivery_rating 
SET state = 'pending' 
WHERE state = 'expired';

-- Find duplicate tokens
SELECT rating_token, COUNT(*) as count
FROM delivery_rating
GROUP BY rating_token
HAVING COUNT(*) > 1;
```

---

## 📞 Troubleshooting

### Problem: Link still shows expired after fix
**Solution:**
1. Clear browser cache (Ctrl+Shift+Delete)
2. Use incognito/private window
3. Restart Odoo server
4. Check if rating_token field has value

### Problem: Multiple expired links
**Solution:**
```bash
# Run diagnostic
python check_rating_links.py

# Or in Odoo:
# Select all expired → use dropdown action to change state
```

### Problem: 404 Not Found
**Solution:**
1. Check URL: should be `/rating/TOKEN_VALUE`
2. Verify token in database matches URL
3. Check routing in controllers/rating_controller.py
4. Restart Odoo

---

## ✅ Verification Checklist

- [ ] Odoo server restarted
- [ ] Rating record state changed from "expired" to "pending"
- [ ] Browser cache cleared
- [ ] Testing with incognito/private window
- [ ] Token is correct in URL
- [ ] Booking exists and marked as "done"
- [ ] Can submit rating successfully

---

## 📊 Files Modified

1. **models/delivery_rating.py**
   - Fixed `get_rating_info()` method
   - Removed strict 'pending' state check
   - Added unique constraint on token field
   - Added better logging

2. **check_rating_links.py** (NEW)
   - Diagnostic script to check all ratings

---

## 🔄 After Fix

1. **Test URL:** `http://localhost:8078/rating/YOUR_TOKEN`
2. **Should see:** Rating form (not expired message)
3. **Can submit:** Rating with stars and comment
4. **Redirect to:** Success page

---

Generated: 2025-11-01
For NPD Transport Booking System (Odoo 18)
