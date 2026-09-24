<#
.SYNOPSIS
  Runs several DeepSeek workers in parallel, waits for all of them, and prints each report.

.DESCRIPTION
  This is how a DeepSeek lead (a worker started with ds-agent.ps1 -CanSpawn) launches its own
  workers. Claude can use it too. Each brief becomes one ds-agent.ps1 run; lineage flows through
  the DS_* variables the parent's launcher set, so every child's manifest names its parent and
  the depth limit is enforced by ds-agent.ps1 itself.

  Children are read-only unless -Mode edit is passed, and a lead that is itself read-only cannot
  give its children edit rights (DS_PARENT_MODE).

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File ds-spawn.ps1 -Dir C:\code\app -Briefs a.md,b.md
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory)][string]$Dir,
    # Brief files, comma-separated. Each file name (without .md) becomes the child's label.
    [Parameter(Mandatory)][string[]]$Briefs,
    [ValidateSet('read', 'edit')][string]$Mode = 'read',
    # A report longer than this comes back as its start and end, with the full text in its saved file;
    # 0 prints every report whole.
    [int]$ReportChars = 6000,
    # Children can message each other by default, like every worker; -NoCrosstalk turns it off.
    # -Crosstalk is still accepted from older callers.
    [switch]$Crosstalk,
    [switch]$NoCrosstalk,
    # DeepSeek's three thinking levels.
    [ValidateSet('low', 'high', 'max')][string]$Effort = 'high',
    [int]$MaxTurns = 80,
    [int]$TimeoutMinutes = 25
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false
try { [Console]::OutputEncoding = $utf8 } catch { }
$launcher = Join-Path $PSScriptRoot 'ds-agent.ps1'

$Briefs = @($Briefs -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (-not $Briefs) { [Console]::Error.WriteLine('[ds-spawn] no briefs given'); exit 2 }
if ($Briefs.Count -gt 6) { [Console]::Error.WriteLine('[ds-spawn] at most 6 workers per call; split the work or do more of it yourself'); exit 2 }
if ($Mode -eq 'edit' -and $env:DS_PARENT_MODE -eq 'read') {
    [Console]::Error.WriteLine('[ds-spawn] a read-only lead cannot start editing workers'); exit 2
}
foreach ($b in $Briefs) { if (-not (Test-Path -LiteralPath $b -PathType Leaf)) { [Console]::Error.WriteLine("[ds-spawn] brief not found: $b"); exit 2 } }

$jobs = @()
foreach ($b in $Briefs) {
    $full = (Resolve-Path -LiteralPath $b).ProviderPath
    $label = [IO.Path]::GetFileNameWithoutExtension($full)
    $out = [IO.Path]::GetTempFileName()
    $err = [IO.Path]::GetTempFileName()
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$launcher`"", '-TaskFile', "`"$full`"",
        '-Dir', "`"$Dir`"", '-Label', $label, '-Mode', $Mode, '-Effort', $Effort,
        '-MaxTurns', $MaxTurns, '-TimeoutMinutes', $TimeoutMinutes)
    if ($NoCrosstalk) { $argList += '-NoCrosstalk' } elseif ($Crosstalk) { $argList += '-Crosstalk' }
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -NoNewWindow -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $jobs += [pscustomobject]@{ Label = $label; Proc = $p; Out = $out; Err = $err }
    # Stagger starts so two children never read the manifest counter at the same instant.
    Start-Sleep -Milliseconds 800
}
Write-Output "[ds-spawn] started $($jobs.Count) worker(s) under $(if ($env:DS_RUN_ID) { $env:DS_RUN_ID } else { 'Claude' }): $($jobs.Label -join ', ')"

$deadline = (Get-Date).AddMinutes($TimeoutMinutes + 2)
foreach ($j in $jobs) {
    $left = [int][Math]::Max(1000, ($deadline - (Get-Date)).TotalMilliseconds)
    if (-not $j.Proc.WaitForExit($left)) { & taskkill.exe /PID $j.Proc.Id /T /F 2>$null | Out-Null }
}

# Where the launcher keeps run records, by the launcher's own rule (launcher/ds-state.ps1, beside this
# script): DS_STATE_DIR, then the project's "stateDir", then local/agents when local/ exists, else
# ~/.claude-deepseek/agents. Only used to tell the lead where each report is saved.
$stateDir = & (Join-Path $PSScriptRoot 'ds-state.ps1') -Dir $Dir

$failed = 0
foreach ($j in $jobs) {
    $text = [IO.File]::ReadAllText($j.Out, $utf8).TrimEnd()
    $errText = ([IO.File]::ReadAllText($j.Err, $utf8) -split "`r?`n" | Where-Object { $_ -match '^\[ds-agent\]' }) -join "`n"
    $footer = ($text -split "`r?`n" | Where-Object { $_ -match '^\[ds-agent\] run=' } | Select-Object -Last 1)
    $runId = if ($footer -match 'run=(\S+)') { $Matches[1] } else { $j.Label }
    if (-not ($footer -match 'status=ok')) { $failed++ }
    Write-Output ''
    Write-Output "===== report from $runId ====="
    # Where the same report is on disk, so a lead can re-read it instead of guessing a path or scraping
    # this output. lead-026 (OpenSkyrim, 2026-09-23) reported a child's report as "not written by the
    # harness" and recovered it from the spawn text; the file was there all along.
    $reportPath = Join-Path (Join-Path $stateDir 'runs') (Join-Path $runId 'report.md')
    if (Test-Path -LiteralPath $reportPath) { Write-Output "(also saved at $reportPath)" }
    # A long report comes back as its start and end, with the rest left in the saved file. Whatever a lead
    # takes in, it re-reads on every later step: OpenSkyrim leads' children wrote a median of 17,000
    # characters each, and one lead took in 211,000 (docs/todo.md item 6).
    $body = ($text -split "`r?`n" | Where-Object { $_ -notmatch '^\[ds-agent\] run=' }) -join "`n"
    if ($ReportChars -gt 0 -and $body.Length -gt $ReportChars -and (Test-Path -LiteralPath $reportPath)) {
        $head = [int]($ReportChars * 0.75); $tail = $ReportChars - $head
        Write-Output $body.Substring(0, $head).TrimEnd()
        Write-Output ""
        Write-Output "[... $($body.Length - $ReportChars) characters of this report left out here; they are in $($reportPath): Read the parts you need to check ...]"
        Write-Output ""
        Write-Output $body.Substring($body.Length - $tail).TrimStart()
        if ($footer) { Write-Output $footer }
    } elseif ($text) { Write-Output $text } else { Write-Output '(no output)' }
    if ($errText) { Write-Output $errText }
    Remove-Item -LiteralPath $j.Out, $j.Err -ErrorAction SilentlyContinue
}
Write-Output ''
Write-Output "[ds-spawn] done: $($jobs.Count - $failed) ok, $failed failed"
if ($failed) { exit 1 }
