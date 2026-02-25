@echo off
setlocal
set "REPO=%~dp0.."

mkdir "%REPO%\apps\macos\mac-app" 2>nul
mkdir "%REPO%\apps\windows\windows-app" 2>nul
mkdir "%REPO%\servers\api" 2>nul
mkdir "%REPO%\servers\signal" 2>nul
mkdir "%REPO%\servers\windows" 2>nul

type nul > "%REPO%\apps\macos\mac-app\.gitkeep"
type nul > "%REPO%\apps\windows\windows-app\.gitkeep"
type nul > "%REPO%\servers\api\.gitkeep"
type nul > "%REPO%\servers\signal\.gitkeep"
type nul > "%REPO%\servers\windows\.gitkeep"

echo Layout folders ensured in: %REPO%
exit /b 0
