<#
.SYNOPSIS
  Reports which tools are installed, using the PATH as saved in Windows now rather than the
  PATH this process inherited.

.DESCRIPTION
  Windows gives a process the PATH it had when it started. A tool installed after the Claude app
  launched (rustup, winget, a pip script) is missing from every session's inherited PATH, so a plain
  `which` wrongly reports it absent. This script rebuilds PATH from the saved Machine and User values
  first, then checks each tool and prints one line per tool: found (with path and version) or MISSING.
  Python packages are checked with the py: prefix.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File ds-which.ps1 g++ cmake cargo rustc clang++ py:numpy py:PIL
#>
param(
    # Exit 1 when anything is missing. Off by default: a missing tool is a finding, not a failure,
    # and a non-zero exit makes the Claude app show the whole check as a failed step.
    [switch]$Strict,
    [Parameter(ValueFromRemainingArguments)][string[]]$Tools
)
$ErrorActionPreference = 'Continue'

$entries = @($env:Path -split ';' | Where-Object { $_ })
$added = @()
foreach ($scope in 'Machine', 'User') {
    foreach ($entry in ([string][Environment]::GetEnvironmentVariable('Path', $scope) -split ';')) {
        if (-not $entry) { continue }
        $expanded = [Environment]::ExpandEnvironmentVariables($entry).TrimEnd('\')
        if (-not ($entries | Where-Object { $_.TrimEnd('\') -ieq $expanded })) { $entries += $expanded; $added += $expanded }
    }
}
$env:Path = $entries -join ';'
if ($added) { "PATH: added $($added.Count) saved entr$(if ($added.Count -eq 1) { 'y' } else { 'ies' }) this session was missing: $($added -join '; ')" }

$missing = @()
$found = 0
foreach ($tool in @($Tools -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    if ($tool -like 'py:*') {
        $module = $tool.Substring(3)
        $out = & python -c "import $module as m; print(getattr(m, '__version__', 'installed'))" 2>$null
        # The import name and the pip name differ for some packages (H17).
        $pipNames = @{ skimage = 'scikit-image'; PIL = 'Pillow'; cv2 = 'opencv-python'; yaml = 'PyYAML'; sklearn = 'scikit-learn'; bs4 = 'beautifulsoup4'; Crypto = 'pycryptodome'; dateutil = 'python-dateutil'; serial = 'pyserial'; usb = 'pyusb'; wx = 'wxPython'; gi = 'PyGObject'; docx = 'python-docx'; pptx = 'python-pptx'; fitz = 'PyMuPDF'; attr = 'attrs'; jwt = 'PyJWT'; OpenSSL = 'pyOpenSSL'; win32api = 'pywin32'; win32com = 'pywin32' }
        $pipName = if ($pipNames.ContainsKey($module)) { $pipNames[$module] } else { $module }
        if ($LASTEXITCODE -eq 0) { "{0,-12} found    python package {1}" -f $tool, ($out | Select-Object -First 1); $found++ }
        else { "{0,-12} MISSING  (python package; install with: python -m pip install {1})" -f $tool, $pipName; $missing += $tool }
        continue
    }
    $cmd = Get-Command $tool -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { "{0,-12} MISSING" -f $tool; $missing += $tool; continue }
    $found++
    $version = ''
    foreach ($flag in '--version', '-version', '/?') {
        $v = & $cmd.Source $flag 2>&1 | Where-Object { "$_".Trim() } | Select-Object -First 1
        if ($v) { $version = "$v".Trim(); break }
    }
    "{0,-12} found    {1}  ({2})" -f $tool, $cmd.Source, $version
}
''
if ($missing) { "summary: $found found, $($missing.Count) missing: $($missing -join ', ')" } else { "summary: all $found found" }
if ($Strict -and $missing) { exit 1 }
exit 0
