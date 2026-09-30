# Export the deck in final/ to PDF with PowerPoint (adapted from SIH26P3 submission/sih/topdf.ps1).
#
#     powershell -ExecutionPolicy Bypass -File submission/topdf.ps1
#
# New-Object -ComObject attaches to a running PowerPoint, so it quits only an instance it started.
$final = Join-Path $PSScriptRoot 'final'
$src = Join-Path $final 'OceanEmbed-SIH2026.pptx'
$wasRunning = [bool](Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application
try {
    $doc = $app.Presentations.Open($src, $true, $false, $false)   # readonly, untitled, no window
    $doc.SaveAs((Join-Path $final 'OceanEmbed-SIH2026.pdf'), 32)  # 32 = ppSaveAsPDF
    $doc.Close()
    Write-Host 'wrote final/OceanEmbed-SIH2026.pdf'
} finally { if (-not $wasRunning) { $app.Quit() } }
