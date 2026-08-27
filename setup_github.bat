@echo off
REM GitHub Setup Script for Fyers Trading Strategy
REM Run this script to set up your GitHub repository

echo ============================================================
echo GITHUB SETUP FOR FYERS TRADING STRATEGY
echo ============================================================
echo.

REM Check if git is installed
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Git is not installed!
    echo Please install Git from: https://git-scm.com/downloads
    pause
    exit /b 1
)

echo Step 1: Initializing Git repository...
git init
git add .
git commit -m "Initial trading strategy with SUPER GOLD config"

echo.
echo Step 2: Setting up main branch...
git branch -M main

echo.
echo ============================================================
echo NEXT STEPS:
echo ============================================================
echo 1. Go to https://github.com/new
echo 2. Create a new repository named "fyers-trading-strategy"
echo 3. DO NOT initialize with README, .gitignore, or license
echo 4. Copy the repository URL
echo 5. Run these commands:
echo.
echo    git remote add origin https://github.com/YOUR_USERNAME/fyers-trading-strategy.git
echo    git push -u origin main
echo.
echo 6. After pushing, go to your repo on GitHub
echo 7. Click "Code" button - then "Codespaces" tab
echo 8. Click "Create codespace on main"
echo 9. Wait for environment to build
echo.
echo 10. In the codespace terminal, run:
echo     pip install -r requirements.txt
echo     cd Research
echo     python find_profitable_stocks.py
echo.
echo ============================================================
echo ALTERNATIVE: Install GitHub CLI for one-command setup
echo ============================================================
echo Download from: https://cli.github.com/
echo.
echo After installing GitHub CLI, run:
echo    gh auth login
echo    gh repo create fyers-trading-strategy --public --source=. --remote=origin --push
echo.
echo This will create the repo AND push in one command!
echo ============================================================
pause
