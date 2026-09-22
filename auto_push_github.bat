@echo off
setlocal enabledelayedexpansion

REM ======================================================================
REM SMART AUTO-UPDATE AND PUSH TO GITHUB WITH EMAIL ALERT ON ERROR
REM Only pushes if download succeeds and changes are detected
REM ======================================================================

cd C:\Users\fawaz\Desktop\trading_dashboard
call venv\Scripts\activate

echo ======================================================================
echo TRADING DASHBOARD - SMART AUTO-UPDATE
echo ======================================================================
echo Start Time: %date% %time%
echo.

REM ===== STEP 1: Download NSE + BSE Data =====
echo [1/4] Downloading NSE + BSE data...
echo ----------------------------------------------------------------------
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python auto_update_smart.py

REM Check if download was successful (errorlevel 0 = success)
if errorlevel 1 (
    echo.
    echo ======================================================================
    echo ERROR: Download failed!
    echo ======================================================================
    echo Reason: auto_update_smart.py returned error code
    echo Action: Skipping GitHub push to avoid pushing incomplete data
    echo Check:  logs/downloads.log for details
    echo ======================================================================
    goto :error
)

echo.
echo Download successful!
echo.

REM ===== STEP 2: Sanity Check Diagnostics =====
echo [2/5] Running Pipeline Diagnostics...
echo ----------------------------------------------------------------------
venv\Scripts\python.exe diagnostic.py

if errorlevel 1 (
    echo.
    echo ======================================================================
    echo ERROR: Diagnostics Failed!
    echo ======================================================================
    echo Reason: Data sanity check failed ^(missing columns or huge row drop^)
    echo Action: Skipping GitHub push to avoid corrupting production
    echo ======================================================================
    goto :error
)

echo.

REM ===== STEP 3: Stage files and check if anything actually changed =====
echo [3/5] Staging files and checking for changes...
echo ----------------------------------------------------------------------

REM Stage all trackable output files FIRST, then diff the index
git add data/*.csv *.py *.bat

REM Check if staging produced any diff vs last commit
git diff --cached --quiet
if not errorlevel 1 (
    echo.
    echo ======================================================================
    echo NO CHANGES DETECTED
    echo ======================================================================
    echo Reason: Data files are identical to last commit
    echo Action: Skipping GitHub push - nothing to update
    echo Note:   This is normal on weekends/holidays
    echo ======================================================================
    git reset HEAD >nul 2>nul
    goto :end_success
)

echo Changes detected! Preparing to push...
echo.

REM ===== STEP 4: Files already staged in Step 3 =====
echo [4/5] Files already staged...
echo ----------------------------------------------------------------------

echo Files staged
echo.

REM ===== STEP 5: Commit and Push to GitHub =====
echo [5/5] Pushing to GitHub...
echo ----------------------------------------------------------------------

REM Create commit message with timestamp
set commit_msg=Auto-update: %date% %time%
git commit -m "%commit_msg%"

if errorlevel 1 (
    echo ERROR: Failed to commit changes
    goto :error
)

echo Committed locally
echo.
REM Push only if on main branch
for /f "tokens=*" %%b in ('git branch --show-current') do set current_branch=%%b
if "!current_branch!" NEQ "main" (
    echo.
    echo ======================================================================
    echo ERROR: Cannot push from feature branch '!current_branch!'
    echo ======================================================================
    echo Reason: Automation is only allowed to push the 'main' branch to production.
    echo Action: Merge to main manually, then push.
    echo ======================================================================
    goto :error
)
echo Pushing branch !current_branch! to GitHub...

REM --- Push to prospike (Dash app on Render) ---
git push prospike main

if errorlevel 1 (
    echo.
    echo ======================================================================
    echo ERROR: GitHub push to prospike failed!
    echo ======================================================================
    echo Possible reasons:
    echo   - No internet connection
    echo   - GitHub authentication expired
    echo   - Repository permissions issue
    echo.
    echo To fix: Run 'git push prospike main' manually
    echo ======================================================================
    goto :error
)

echo Pushed to prospike (Dash / Render) successfully.
echo.

REM --- Push to origin (Streamlit live dashboard) ---
echo Pushing to origin (Streamlit)...
git push origin main

if errorlevel 1 (
    echo.
    echo ======================================================================
    echo ERROR: GitHub push to origin (Streamlit) failed!
    echo ======================================================================
    echo To fix: Run 'git push origin main' manually
    echo ======================================================================
    goto :error
)

echo Pushed to origin (Streamlit) successfully.
echo.
echo ======================================================================
echo SUCCESS! BOTH DASHBOARDS UPDATED
echo ======================================================================
echo Commit: %commit_msg%
echo.
echo [prospike] https://github.com/canvachaad-cell/Pro-spike  (Dash / Render)
echo [origin]   https://github.com/fawaz2023/trading-dashboard (Streamlit)
echo.
echo Both dashboards will reflect the new data immediately.
echo ======================================================================
goto :end_success

REM ===== ERROR HANDLER WITH EMAIL ALERT =====
:error
echo.
echo Sending error notification email...
venv\Scripts\python.exe send_error_email.py
echo.
echo End Time: %date% %time%
echo ======================================================================
echo.
exit /b 1

REM ===== SUCCESS EXIT =====
:end_success
echo.
echo End Time: %date% %time%
echo ======================================================================
echo.
echo Press any key to close...
REM pause removed for Task Scheduler compatibility
exit /b 0

endlocal
