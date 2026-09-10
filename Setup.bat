```bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Application Setup

echo.
echo ==========================================================
echo              APPLICATION SETUP AND RUNNER
echo ==========================================================
echo.

:: ==========================================================
:: CONFIGURATION
:: ==========================================================

set "PYTHON_VERSION=3.11.5"

:: Official Python 3.11.5 64-bit installer
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.5/python-3.11.5-amd64.exe"

:: Official Git for Windows installer
set "GIT_URL=https://github.com/git-for-windows/git/releases/latest/download/Git-64-bit.exe"

set "SCRIPT_NAME=main.py"
set "VENV_DIR=.venv"

:: Install software inside user's profile
set "LOCAL_APPDATA=%LOCALAPPDATA%"
set "PYTHON_DIR=%LOCALAPPDATA%\Programs\Python\Python311"
set "GIT_DIR=%LOCALAPPDATA%\Programs\Git"

:: Temporary installers
set "PYTHON_INSTALLER=%TEMP%\python-3.11.5-installer.exe"
set "GIT_INSTALLER=%TEMP%\git-installer.exe"

:: ==========================================================
:: MOVE TO BAT FILE DIRECTORY
:: ==========================================================

cd /d "%~dp0"

echo [+] Project directory:
echo     %CD%
echo.

:: ==========================================================
:: 1. CHECK GIT
:: ==========================================================

echo ==========================================================
echo [1/5] CHECKING GIT
echo ==========================================================
echo.

where git >nul 2>&1

if %ERRORLEVEL% EQU 0 (

    echo [+] Git is already installed.
    git --version

) else (

    echo [!] Git was not found.
    echo [!] Installing Git for the current user...
    echo.

    :: Check if Git exists in our expected location
    if exist "%GIT_DIR%\cmd\git.exe" (

        echo [+] Git found in:
        echo     %GIT_DIR%

        set "PATH=%GIT_DIR%\cmd;%GIT_DIR%\bin;%PATH%"

    ) else (

        echo [!] Downloading Git...
        echo.

        powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
        "try { Invoke-WebRequest -Uri '%GIT_URL%' -OutFile '%GIT_INSTALLER%' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"

        if not exist "%GIT_INSTALLER%" (
            echo.
            echo [X] Git download failed.
            echo [X] Please check your internet connection.
            pause
            exit /b 1
        )

        echo [+] Git downloaded.
        echo [!] Installing Git...
        echo.

        :: Git for Windows per-user installation
        start /wait "" "%GIT_INSTALLER%" ^
            /VERYSILENT ^
            /NORESTART ^
            /NOCANCEL ^
            /CURRENTUSER ^
            /SP- ^
            /SUPPRESSMSGBOXES

        if not exist "%GIT_DIR%\cmd\git.exe" (

            echo.
            echo [X] Git installation failed.
            echo.
            echo Possible reason:
            echo The Git installer may require administrator privileges
            echo on this Windows configuration.
            echo.
            del "%GIT_INSTALLER%" >nul 2>&1
            pause
            exit /b 1
        )

        del "%GIT_INSTALLER%" >nul 2>&1

        :: Add Git to current session PATH
        set "PATH=%GIT_DIR%\cmd;%GIT_DIR%\bin;%PATH%"

        echo.
        echo [+] Git installed successfully.
    )
)

echo.

:: ==========================================================
:: 2. CHECK PYTHON
:: ==========================================================

echo ==========================================================
echo [2/5] CHECKING PYTHON %PYTHON_VERSION%
echo ==========================================================
echo.

set "PYTHON_EXE="

:: First check our expected installation
if exist "%PYTHON_DIR%\python.exe" (

    set "PYTHON_EXE=%PYTHON_DIR%\python.exe"

    echo [+] Python found at:
    echo     %PYTHON_DIR%

) else (

    :: Check existing Python in PATH
    where python >nul 2>&1

    if %ERRORLEVEL% EQU 0 (

        for /f "delims=" %%P in ('where python') do (

            if not defined PYTHON_EXE (
                set "PYTHON_EXE=%%P"
            )
        )

    )
)

:: ==========================================================
:: INSTALL PYTHON IF NOT FOUND
:: ==========================================================

if not defined PYTHON_EXE (

    echo [!] Python was not found.
    echo [!] Downloading Python %PYTHON_VERSION%...
    echo.

    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"

    if not exist "%PYTHON_INSTALLER%" (

        echo.
        echo [X] Python download failed.
        echo [X] Please check your internet connection.
        pause
        exit /b 1
    )

    echo [+] Python downloaded.
    echo.
    echo [!] Installing Python for current user...
    echo.

    :: ------------------------------------------------------
    :: IMPORTANT:
    :: InstallAllUsers=0 = current user only
    :: PrependPath=1    = add Python to user's PATH
    :: Include_test=0   = don't install test suite
    :: ------------------------------------------------------

    start /wait "" "%PYTHON_INSTALLER%" ^
        /quiet ^
        InstallAllUsers=0 ^
        PrependPath=1 ^
        Include_test=0 ^
        Include_launcher=1

    if not exist "%PYTHON_DIR%\python.exe" (

        echo.
        echo [X] Python installation failed.
        echo.
        del "%PYTHON_INSTALLER%" >nul 2>&1
        pause
        exit /b 1
    )

    del "%PYTHON_INSTALLER%" >nul 2>&1

    set "PYTHON_EXE=%PYTHON_DIR%\python.exe"

    :: Refresh PATH for current BAT session
    set "PATH=%PYTHON_DIR%;%PYTHON_DIR%\Scripts;%PATH%"

    echo.
    echo [+] Python installed successfully.
)

echo.

:: ==========================================================
:: 3. VERIFY PYTHON
:: ==========================================================

echo ==========================================================
echo VERIFYING PYTHON
echo ==========================================================
echo.

if not defined PYTHON_EXE (

    echo [X] Python executable could not be located.
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (

    echo [X] Python executable does not exist:
    echo     %PYTHON_EXE%
    pause
    exit /b 1
)

"%PYTHON_EXE%" --version

if %ERRORLEVEL% neq 0 (

    echo [X] Python is not working correctly.
    pause
    exit /b 1
)

echo [+] Python is working correctly.
echo.

:: ==========================================================
:: 4. GIT PULL
:: ==========================================================

echo ==========================================================
echo [3/5] UPDATING PROJECT
echo ==========================================================
echo.

if exist ".git" (

    echo [+] Git repository detected.
    echo [!] Pulling latest changes...
    echo.

    git pull

    if %ERRORLEVEL% neq 0 (

        echo.
        echo [X] Git pull failed.
        echo.
        echo Possible reasons:
        echo   - Internet connection problem
        echo   - Git authentication required
        echo   - Local changes conflict with remote changes
        echo.
        pause
        exit /b 1
    )

    echo.
    echo [+] Git pull completed successfully.

) else (

    echo [!] .git folder not found.
    echo [!] This directory is not a Git repository.
    echo [!] Skipping git pull.
)

echo.

:: ==========================================================
:: 5. CREATE VIRTUAL ENVIRONMENT
:: ==========================================================

echo ==========================================================
echo [4/5] SETTING UP PYTHON ENVIRONMENT
echo ==========================================================
echo.

if not exist "%VENV_DIR%\Scripts\python.exe" (

    echo [!] Creating virtual environment...
    echo.

    "%PYTHON_EXE%" -m venv "%VENV_DIR%"

    if %ERRORLEVEL% neq 0 (

        echo.
        echo [X] Failed to create virtual environment.
        pause
        exit /b 1
    )

    echo [+] Virtual environment created.

) else (

    echo [+] Virtual environment already exists.
)

set "VENV_PYTHON=%CD%\%VENV_DIR%\Scripts\python.exe"

echo.

:: ==========================================================
:: UPDATE PIP
:: ==========================================================

echo [!] Updating pip...
echo.

"%VENV_PYTHON%" -m pip install --upgrade pip

if %ERRORLEVEL% neq 0 (

    echo.
    echo [X] Failed to update pip.
    pause
    exit /b 1
)

echo.
echo [+] pip updated successfully.

:: ==========================================================
:: INSTALL REQUIREMENTS
:: ==========================================================

echo.
echo ==========================================================
echo INSTALLING PROJECT DEPENDENCIES
echo ==========================================================
echo.

if exist "requirements.txt" (

    echo [!] Installing requirements.txt...
    echo.

    "%VENV_PYTHON%" -m pip install -r requirements.txt

    if %ERRORLEVEL% neq 0 (

        echo.
        echo [X] Failed to install requirements.
        pause
        exit /b 1
    )

    echo.
    echo [+] Requirements installed successfully.

) else (

    echo [!] requirements.txt was not found.
    echo [!] Skipping dependency installation.
)

:: ==========================================================
:: INSTALL PLAYWRIGHT CHROMIUM
:: ==========================================================

echo.
echo ==========================================================
echo INSTALLING PLAYWRIGHT CHROMIUM
echo ==========================================================
echo.

:: Check if Playwright is installed
"%VENV_PYTHON%" -c "import playwright" >nul 2>&1

if %ERRORLEVEL% EQU 0 (

    echo [!] Installing Playwright Chromium...
    echo.

    "%VENV_PYTHON%" -m playwright install chromium

    if %ERRORLEVEL% neq 0 (

        echo.
        echo [X] Playwright Chromium installation failed.
        pause
        exit /b 1
    )

    echo.
    echo [+] Playwright Chromium installed successfully.

) else (

    echo [!] Playwright is not included in requirements.txt.
    echo [!] Skipping Chromium installation.
)

echo.

:: ==========================================================
:: 6. RUN MAIN.PY
:: ==========================================================

echo ==========================================================
echo [5/5] STARTING APPLICATION
echo ==========================================================
echo.

if exist "%SCRIPT_NAME%" (

    echo [+] Starting %SCRIPT_NAME%...
    echo.
    echo ----------------------------------------------------------
    echo.

    "%VENV_PYTHON%" "%SCRIPT_NAME%"

    set "APP_EXIT_CODE=!ERRORLEVEL!"

    echo.
    echo ----------------------------------------------------------
    echo Application finished.
    echo Exit code: !APP_EXIT_CODE!
    echo ----------------------------------------------------------

) else (

    echo [X] ERROR: %SCRIPT_NAME% was not found.
    echo.
    echo Expected:
    echo %CD%\%SCRIPT_NAME%

    pause
    exit /b 1
)

echo.
echo ==========================================================
echo SETUP / EXECUTION COMPLETE
echo ==========================================================
echo.

pause

exit /b %APP_EXIT_CODE%
```
