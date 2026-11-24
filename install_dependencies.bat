@echo off
echo ======================================================================
echo MedInfo - Dependency Installation Script
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/3] Checking Python...
python --version
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found! Please install Python 3.8 or higher.
    pause
    exit /b 1
)
echo.

echo [2/3] Installing all dependencies from requirements.txt...
echo This may take several minutes...
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.

echo [3/3] Verifying installation...
python -c "import flask; import cv2; import numpy; print('✓ Core packages installed')"
python -c "from google import genai; print('✓ Google Genai installed')" 2>nul || echo "⚠ Google Genai not installed (optional)"
python -c "import pytesseract; print('✓ Pytesseract installed')"
python -c "import easyocr; print('✓ EasyOCR installed')"
python -c "import roboflow; print('✓ Roboflow installed')"
python -c "import fpdf; print('✓ FPDF installed')"
python -c "import qrcode; print('✓ QRCode installed')"
echo.

echo ======================================================================
echo Installation complete!
echo ======================================================================
echo.
echo To start the application, run:
echo   python app.py
echo.
echo Or double-click:
echo   start_network.bat
echo.
pause
