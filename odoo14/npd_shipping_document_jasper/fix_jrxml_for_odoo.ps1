# แปลง JRXML ที่เซฟจาก Jaspersoft Studio 6.21 ให้ JasperReports 6.5.1 (บนเซิร์ฟเวอร์) อ่านได้
# วิธีใช้: คลิกขวา > Run with PowerShell  หรือรันใน PowerShell:
#   powershell -ExecutionPolicy Bypass -File fix_jrxml_for_odoo.ps1
# จะแก้ไฟล์ .jrxml ทุกไฟล์ในโฟลเดอร์ report\ ของโมดูลนี้

$ErrorActionPreference = 'Stop'
$reportDir = Join-Path $PSScriptRoot 'report'
$files = Get-ChildItem -Path $reportDir -Filter *.jrxml -Recurse

foreach ($file in $files) {
    $text = [System.IO.File]::ReadAllText($file.FullName)
    $orig = $text
    # textAdjust="StretchHeight"  ->  isStretchWithOverflow="true"
    $text = $text -replace 'textAdjust\s*=\s*"StretchHeight"', 'isStretchWithOverflow="true"'
    # textAdjust="CutText" / "ScaleFont"  ->  เอา attribute ออก (เวอร์ชันเก่าไม่รองรับ)
    $text = $text -replace '\s*textAdjust\s*=\s*"(CutText|ScaleFont)"', ''
    if ($text -ne $orig) {
        # เขียนกลับเป็น UTF-8 ไม่มี BOM
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($file.FullName, $text, $utf8)
        Write-Host ("[FIXED] {0}" -f $file.Name)
    } else {
        Write-Host ("[OK]    {0} (ไม่มี textAdjust)" -f $file.Name)
    }
}
Write-Host "เสร็จแล้ว - อย่าลืม Upgrade โมดูลใน Odoo เพื่อ sync jrxml"
