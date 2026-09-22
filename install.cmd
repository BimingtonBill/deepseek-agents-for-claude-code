@echo off
rem Installs the DeepSeek worker skills into %USERPROFILE%\.claude\skills (backs up any existing copy).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install-skill.ps1"
echo.
if defined DEEPSEEK_API_KEY (echo DeepSeek key: found.) else (powershell -NoProfile -Command "if ([Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')) { 'DeepSeek key: found.' } else { 'DeepSeek key: NOT SET YET - see step 1 in README-FIRST.md.' }")
echo Now restart Claude so it picks up the skills.
pause
