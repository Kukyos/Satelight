# Export the deck in final/ to PDF with PowerPoint (adapted from SIH26P3 submission/sih/topdf.ps1).
#
#     powershell -ExecutionPolicy Bypass -File submission/topdf.ps1
#
# New-Object -ComObject attaches to a running PowerPoint, so it quits only an instance it started.
param([string]$name = 'Satelight-SIH2026')   # -name <other> when the deck is open elsewhere
$final = Join-Path $PSScriptRoot 'final'
$src = Join-Path $final "$name.pptx"
$wasRunning = [bool](Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application
try {
    $doc = $app.Presentations.Open($src, $true, $false, $false)   # readonly, untitled, no window
    $doc.SaveAs((Join-Path $final "$name.pdf"), 32)               # 32 = ppSaveAsPDF
    $doc.Close()
    Write-Host "wrote final/$name.pdf"
} finally { if (-not $wasRunning) { $app.Quit() } }
