<?php
/**
 * NPD Transport Rating System - API Backend (v2 - JWT Enhanced)
 * 📍 URL: https://npdhrms.com/odoo18/rating/api.php
 * 
 * ✅ ใช้ JWT Token สำหรับความปลอดภัย
 * ✅ ทำงานกับ Odoo 18 RPC API
 */

header('Content-Type: application/json; charset=utf-8');
error_reporting(E_ALL);
ini_set('display_errors', 0);

// ===================================
// ⚙️ Configuration
// ===================================

define('ODOO_URL', 'http://localhost:8078');
define('ODOO_DB', 'NPD_Logistics_demo');
define('ODOO_USERNAME', 'npd_admin');
define('ODOO_PASSWORD', '1234');

// ===================================
// 🔐 JWT Configuration
// ===================================

define('JWT_SECRET', 'npd-transport-rating-secret-2024');
define('TOKEN_EXPIRY', 7 * 24 * 60 * 60); // 7 วัน

// ===================================
// 🔒 JWT Helper Functions
// ===================================

/**
 * สร้าง JWT Token
 */
function createRatingToken($booking_id, $customer_email = '') {
    $issuedAt = time();
    $payload = array(
        'booking_id' => $booking_id,
        'customer_email' => $customer_email,
        'iat' => $issuedAt,
        'exp' => $issuedAt + TOKEN_EXPIRY
    );
    
    $header = json_encode(['alg' => 'HS256', 'typ' => 'JWT']);
    $payload_json = json_encode($payload);
    
    $header_b64 = rtrim(strtr(base64_encode($header), '+/', '-_'), '=');
    $payload_b64 = rtrim(strtr(base64_encode($payload_json), '+/', '-_'), '=');
    
    $signature = hash_hmac(
        'sha256',
        $header_b64 . '.' . $payload_b64,
        JWT_SECRET,
        true
    );
    $signature_b64 = rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');
    
    $token = $header_b64 . '.' . $payload_b64 . '.' . $signature_b64;
    error_log("✅ JWT Token created: booking_id={$booking_id}");
    
    return $token;
}

/**
 * ตรวจสอบ JWT Token
 */
function verifyRatingToken($token) {
    $parts = explode('.', $token);
    
    if (count($parts) !== 3) {
        error_log("❌ Token format invalid");
        return null;
    }
    
    list($header_b64, $payload_b64, $signature_b64) = $parts;
    
    // Verify Signature
    $signature = hash_hmac(
        'sha256',
        $header_b64 . '.' . $payload_b64,
        JWT_SECRET,
        true
    );
    $signature_calc = rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');
    
    if (!hash_equals($signature_b64, $signature_calc)) {
        error_log("❌ Token signature invalid");
        return null;
    }
    
    // Decode Payload
    $payload_json = base64_decode(strtr($payload_b64, '-_', '+/'));
    $payload = json_decode($payload_json, true);
    
    if (!$payload) {
        error_log("❌ Token payload decode failed");
        return null;
    }
    
    // Check Expiration
    if ($payload['exp'] < time()) {
        error_log("❌ Token expired");
        return null;
    }
    
    error_log("✅ JWT Token verified: booking_id=" . $payload['booking_id']);
    return $payload;
}

// ===================================
// 🔌 Odoo RPC Class
// ===================================

class OdooJSONRPC {
    private $url;
    private $db;
    private $username;
    private $password;
    private $uid = null;
    
    public function __construct($url, $db, $username, $password) {
        $this->url = $url;
        $this->db = $db;
        $this->username = $username;
        $this->password = $password;
    }
    
    private function jsonrpc_call($method, $params) {
        $payload = array(
            'jsonrpc' => '2.0',
            'method' => $method,
            'params' => $params,
            'id' => rand(1, 999999)
        );
        
        $ch = curl_init($this->url . '/jsonrpc');
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, array(
            'Content-Type: application/json',
            'Accept: application/json'
        ));
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
        curl_setopt($ch, CURLOPT_TIMEOUT, 10);
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 10);
        
        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curl_error = curl_error($ch);
        curl_close($ch);
        
        if ($curl_error) {
            error_log("CURL Error: " . $curl_error);
            return array('error' => $curl_error);
        }
        
        if ($http_code !== 200) {
            error_log("HTTP Error: {$http_code}");
            return array('error' => "HTTP {$http_code}");
        }
        
        $result = json_decode($response, true);
        
        if (json_last_error() !== JSON_ERROR_NONE) {
            error_log("JSON Error: " . json_last_error_msg());
            return array('error' => json_last_error_msg());
        }
        
        return $result;
    }
    
    public function authenticate() {
        $payload = array(
            'jsonrpc' => '2.0',
            'method' => 'call',
            'params' => array(
                'db' => $this->db,
                'login' => $this->username,
                'password' => $this->password
            ),
            'id' => rand(1, 999999)
        );
        
        $ch = curl_init($this->url . '/web/session/authenticate');
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, array(
            'Content-Type: application/json',
            'Accept: application/json'
        ));
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
        curl_setopt($ch, CURLOPT_TIMEOUT, 10);
        
        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        
        if ($http_code === 200) {
            $result = json_decode($response, true);
            if (isset($result['result']['uid'])) {
                $this->uid = $result['result']['uid'];
                error_log("✅ Authentication successful! UID: " . $this->uid);
                return true;
            }
        }
        
        error_log("❌ Authentication failed");
        return false;
    }
    
    public function get_rating_info_by_booking($booking_id) {
        if (!$this->uid) {
            $this->authenticate();
        }
        
        $result = $this->jsonrpc_call('call', array(
            $this->db,
            $this->uid,
            $this->password,
            'delivery.rating',
            'get_rating_info',
            array($booking_id)
        ));
        
        if (isset($result['result']) && !isset($result['error'])) {
            error_log("✅ Rating info found for booking: " . $booking_id);
            return $result['result'];
        }
        
        error_log("❌ Get rating info failed");
        return isset($result['error']) ? $result['error'] : null;
    }
    
    public function submit_rating($booking_id, $rating_stars, $comment) {
        if (!$this->uid) {
            $this->authenticate();
        }
        
        $result = $this->jsonrpc_call('call', array(
            $this->db,
            $this->uid,
            $this->password,
            'delivery.rating',
            'submit_rating',
            array(
                'booking_id' => (int)$booking_id,
                'rating_stars' => (int)$rating_stars,
                'customer_comment' => $comment
            )
        ));
        
        if (isset($result['result']) && !isset($result['error'])) {
            error_log("✅ Rating submitted for booking: " . $booking_id);
            return $result['result'];
        }
        
        error_log("❌ Submit rating failed");
        return array(
            'success' => false, 
            'error' => isset($result['error']) ? $result['error'] : 'เกิดข้อผิดพลาด'
        );
    }
}

// ===================================
// 📝 Helper Functions
// ===================================

function sanitize($data) {
    return htmlspecialchars(trim($data), ENT_QUOTES, 'UTF-8');
}

function send_json($success, $message = '', $data = null) {
    $response = array('success' => $success);
    
    if ($message) {
        $response['message'] = $message;
    }
    
    if ($data !== null) {
        $response['data'] = $data;
    }
    
    echo json_encode($response, JSON_UNESCAPED_UNICODE);
    exit;
}

// ===================================
// 🔌 Handle API Requests
// ===================================

$action = isset($_GET['action']) ? sanitize($_GET['action']) : '';

// 1️⃣ Verify Token
if ($action === 'verify_token') {
    $token = isset($_GET['token']) ? sanitize($_GET['token']) : '';
    
    if (!$token) {
        send_json(false, 'Token required');
    }
    
    $decoded = verifyRatingToken($token);
    
    if (!$decoded) {
        send_json(false, 'Invalid or expired token');
    }
    
    send_json(true, 'Token valid', array(
        'booking_id' => $decoded['booking_id'],
        'customer_email' => $decoded['customer_email']
    ));
}

// 2️⃣ Get Rating Info
if ($action === 'get_rating') {
    $token = isset($_GET['token']) ? sanitize($_GET['token']) : '';
    
    if (!$token) {
        send_json(false, 'Token required');
    }
    
    $decoded = verifyRatingToken($token);
    
    if (!$decoded) {
        send_json(false, 'Invalid or expired token');
    }
    
    $booking_id = $decoded['booking_id'];
    
    $odoo = new OdooJSONRPC(ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD);
    $info = $odoo->get_rating_info_by_booking($booking_id);
    
    if ($info && !isset($info['error'])) {
        send_json(true, 'Rating info loaded', $info);
    } else {
        send_json(false, isset($info['error']) ? $info['error'] : 'Data not found');
    }
}

// 3️⃣ Submit Rating
if ($action === 'submit_rating') {
    $input = json_decode(file_get_contents('php://input'), true);
    
    $token = isset($input['token']) ? sanitize($input['token']) : '';
    $rating_stars = isset($input['rating_stars']) ? (int)$input['rating_stars'] : 0;
    $comment = isset($input['customer_comment']) ? sanitize($input['customer_comment']) : '';
    
    if (!$token || $rating_stars < 1 || $rating_stars > 5) {
        send_json(false, 'Invalid data');
    }
    
    $decoded = verifyRatingToken($token);
    
    if (!$decoded) {
        send_json(false, 'Invalid or expired token');
    }
    
    $booking_id = $decoded['booking_id'];
    
    $odoo = new OdooJSONRPC(ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD);
    $result = $odoo->submit_rating($booking_id, $rating_stars, $comment);
    
    if ($result && isset($result['success']) && $result['success']) {
        send_json(true, 'Rating submitted successfully', $result);
    } else {
        send_json(false, isset($result['error']) ? $result['error'] : 'Failed to submit rating');
    }
}

// Default
send_json(false, 'Invalid action');
?>
