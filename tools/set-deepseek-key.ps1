# Ask for a DeepSeek API key (hidden as it is typed), check it with DeepSeek, and save it as the
# DEEPSEEK_API_KEY variable for this Windows user. setup.ps1 opens this in its own window so the key
# never appears in a Claude chat or in the window that ran the setup.
#   powershell -NoProfile -ExecutionPolicy Bypass -File set-deepseek-key.ps1
$Host.UI.RawUI.WindowTitle = 'DeepSeek API key'
Write-Host ''
Write-Host 'DeepSeek API key' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Get one at https://platform.deepseek.com/api_keys (sign in, "Create new API key", copy it).'
Write-Host 'Your account needs some credit: https://platform.deepseek.com/top_up'
Write-Host ''
Write-Host 'Paste the key below and press Enter. Nothing shows while you paste; that is normal.'
while ($true) {
    $secure = Read-Host 'DeepSeek API key' -AsSecureString
    $key = [Net.NetworkCredential]::new('', $secure).Password.Trim()
    if (-not $key) { Write-Host 'Nothing was entered. Try again, or close this window to stop.' -ForegroundColor Yellow; continue }
    try {
        $balance = Invoke-RestMethod -Uri 'https://api.deepseek.com/user/balance' -Headers @{ Authorization = "Bearer $key" } -TimeoutSec 20
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        if ($code -eq 401) { Write-Host 'DeepSeek says that key is not valid. Check you copied all of it, then try again.' -ForegroundColor Red; continue }
        Write-Host "Couldn't reach DeepSeek to check the key ($($_.Exception.Message)). Saving it anyway." -ForegroundColor Yellow
        $balance = $null
    }
    [Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY', $key, 'User')
    Write-Host ''
    Write-Host 'Saved. Only your Windows account can read it.' -ForegroundColor Green
    if ($balance) {
        $info = @($balance.balance_infos) | Select-Object -First 1
        if ($info) { Write-Host "Your DeepSeek balance: $($info.total_balance) $($info.currency)" -ForegroundColor Green }
        if ($balance.is_available -eq $false) { Write-Host 'Your balance is too low for the workers to run. Add credit at https://platform.deepseek.com/top_up' -ForegroundColor Yellow }
    }
    Write-Host ''
    Write-Host 'You can close this window now, then restart Claude.' -ForegroundColor Cyan
    break
}
