@echo off
setlocal
set "REPO=%~dp0..\..\.."
set "TOOLS=%USERPROFILE%\git\raywonder\.github\raywonder-repo-bootstrap"
if not exist "%TOOLS%\run-repo-bootstrap.bat" set "TOOLS=%USERPROFILE%\dev\apps\.GITHUB\raywonder-repo-bootstrap"
if not exist "%TOOLS%\run-repo-bootstrap.bat" (
  echo Could not find raywonder-repo-bootstrap tooling.
  echo Expected in one of:
  echo   %USERPROFILE%\git\raywonder\.github\raywonder-repo-bootstrap
  echo   %USERPROFILE%\dev\apps\.GITHUB\raywonder-repo-bootstrap
  exit /b 1
)
call "%TOOLS%\run-repo-bootstrap.bat" "%REPO%"
exit /b %errorlevel%
