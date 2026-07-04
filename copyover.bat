@echo off
setlocal EnableExtensions
cls

REM ============================
REM  Companion Control Console deploy packager
REM ============================
set "src=%~dp0"
if "%src:~-1%"=="\" set "src=%src:~0,-1%"

set "backupRoot=%src%\bkup\deploy_versions"
set "deployRoot=D:\shared\MemoryManager"
set "current=%deployRoot%\Current"
set "archives=%deployRoot%\Archives"
set "intermediaryRoot=D:\shared\ascended\Current\MemoryManager"
set "intermediaryCurrent=%intermediaryRoot%\Current"
set "intermediaryArchives=%intermediaryRoot%\Archives"

REM ============================
REM  Locate Version File
REM ============================
for /f "delims=" %%F in ('dir "%src%\Version-*.md" /b /a-d /o-n 2^>nul') do (
    set "verfile=%%F"
    goto :found_version
)

:found_version
if not defined verfile (
    echo ERROR: No Version-*.md file found.
    pause
    exit /b 1
)

REM Extract version number from filename
REM Version-0.1.10.0.md -> 0.1.10.0
set "version=%verfile:Version-=%"
set "version=%version:.md=%"

echo Detected version: %version%

for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "stamp=%%T"

REM ============================
REM  Prepare Folders
REM ============================
if not exist "%backupRoot%" mkdir "%backupRoot%"
if not exist "%archives%" mkdir "%archives%"
if not exist "%intermediaryArchives%" mkdir "%intermediaryArchives%"
if exist "%current%" rmdir /S /Q "%current%"
mkdir "%current%"

REM ============================
REM  Create Full Versioned Backup
REM ============================
set "zipname=CompanionControlConsole.%version%.%stamp%.zip"
set "ziptemp=%TEMP%\%zipname%"

echo Creating full backup: %zipname%

if exist "%ziptemp%" del /Q "%ziptemp%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$src = '%src%';" ^
  "$zip = '%ziptemp%';" ^
  "$exclude = @('\bkup\','\deploy_package\','\__pycache__\');" ^
  "$files = Get-ChildItem -LiteralPath $src -Recurse -File | Where-Object { $p = $_.FullName.Substring($src.Length); -not ($exclude | Where-Object { $p.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) }) };" ^
  "Compress-Archive -LiteralPath $files.FullName -DestinationPath $zip -Force"

if errorlevel 1 (
    echo ERROR: Backup archive failed.
    pause
    exit /b 1
)

copy /Y "%ziptemp%" "%backupRoot%\%zipname%" >nul
del /Q "%ziptemp%" >nul 2>nul

echo Backup saved:
echo   %backupRoot%\%zipname%

REM ============================
REM  Copy Web Console Runtime
REM ============================
echo Copying deployable web console files...

copy /Y "%src%\Companion_Web.py" "%current%\Companion_Web.py" >nul
copy /Y "%src%\Memory_Manager.py" "%current%\Memory_Manager.py" >nul
copy /Y "%src%\WEB_CONSOLE.md" "%current%\WEB_CONSOLE.md" >nul
if exist "%src%\README.md" copy /Y "%src%\README.md" "%current%\README.md" >nul
if exist "%src%\COMMANDS.md" copy /Y "%src%\COMMANDS.md" "%current%\COMMANDS.md" >nul
if exist "%src%\CHANGELOG.md" copy /Y "%src%\CHANGELOG.md" "%current%\CHANGELOG.md" >nul
if exist "%src%\testlog.md" copy /Y "%src%\testlog.md" "%current%\testlog.md" >nul
copy /Y "%src%\%verfile%" "%current%\%verfile%" >nul

if exist "%src%\deploy_scripts" robocopy "%src%\deploy_scripts" "%current%\deploy_scripts" /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NC /NS /NP
if errorlevel 8 goto :copy_error

REM Do not package live companion registry, memory packets, directives, or proof.
REM Those are server-owned runtime data once the console is deployed.

REM Optional tracker import data used by the Tracker Imports tab.
if exist "%src%\tracker_data" robocopy "%src%\tracker_data" "%current%\tracker_data" /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NC /NS /NP
if errorlevel 8 goto :copy_error

REM Server helper scripts/docs for the copy target.
(
  echo # Companion Control Console deploy package
  echo.
  echo Version: %version%
  echo Packaged: %stamp%
  echo.
  echo Start locally/server-side with:
  echo.
  echo ```bash
  echo python3 Companion_Web.py --host 127.0.0.1 --port 8787
  echo ```
  echo.
  echo For public/subdomain use, put this behind Apache HTTPS, authentication, and a reverse proxy.
  echo.
  echo First-time Linux server setup:
  echo.
  echo ```bash
  echo sudo bash deploy_scripts/linux_setup_subdomain.sh
  echo ```
  echo.
  echo Repeat Linux sync from local Linux staging folder:
  echo.
  echo ```bash
  echo sudo bash deploy_scripts/linux_sync_from_local.sh
  echo ```
  echo.
  echo Default Linux source: /home/paradigm/memorymanager
  echo Copy the deploy package contents there before running the sync script.
  echo Live server companion registry, memory packets, directives, and proof files are preserved by sync.
  echo Daily check-ins are stored in control_data/daily_checkins.json and are preserved by sync.
  echo Tracker imports are packaged from tracker_data when present.
  echo.
  echo Default subdomain: companions.paradigmlabs.dev
  echo DNS must point to the Linux server before certbot can issue a certificate.
) > "%current%\DEPLOY_README.md"

(
  echo #!/usr/bin/env bash
  echo set -euo pipefail
  echo cd "$(dirname "$0")"
  echo python3 Companion_Web.py --host "${HOST:-127.0.0.1}" --port "${PORT:-8787}"
) > "%current%\run_web_console.sh"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$path = '%current%\run_web_console.sh';" ^
  "(Get-Content -Raw -LiteralPath $path).Replace(\"`r`n\", \"`n\") | Set-Content -NoNewline -LiteralPath $path"

REM Also make a zip of the clean deploy package for easy transfer.
set "deployzip=CompanionControlConsole.deploy.%version%.%stamp%.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%current%\*' -DestinationPath '%archives%\%deployzip%' -Force"

if errorlevel 1 (
    echo ERROR: Deploy package archive failed.
    pause
    exit /b 1
)

REM Mirror the clean package to the shared handoff path for manual transfer to Linux.
if exist "%intermediaryCurrent%" rmdir /S /Q "%intermediaryCurrent%"
mkdir "%intermediaryCurrent%"
robocopy "%current%" "%intermediaryCurrent%" /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NC /NS /NP
if errorlevel 8 goto :copy_error
copy /Y "%archives%\%deployzip%" "%intermediaryArchives%\%deployzip%" >nul

echo.
echo Deploy package ready:
echo   %current%
echo.
echo Deploy zip ready:
echo   %archives%\%deployzip%
echo.
echo Full backup ready:
echo   %backupRoot%\%zipname%
echo.
echo Shared handoff root:
echo   %deployRoot%
echo.
echo Shared/manual handoff root:
echo   %intermediaryRoot%
echo.
echo Linux sync default source:
echo   /home/paradigm/memorymanager
echo.
echo Copy the deploy package contents from:
echo   %intermediaryCurrent%
echo to the Linux source folder above, then run:
echo   sudo bash deploy_scripts/linux_sync_from_local.sh
echo.
echo All tasks completed successfully.
pause
exit /b 0

:copy_error
echo ERROR: Robocopy reported a copy failure.
pause
exit /b 1
