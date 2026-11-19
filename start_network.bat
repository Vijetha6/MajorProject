@echo off
echo ================================================================
echo MedInfo - Network Access Mode
echo ================================================================
echo.
echo Starting Flask application with network access...
echo Your application will be accessible at:
echo.
echo   From this laptop: http://localhost:5000
echo   From mobile/tablet: http://10.158.88.1:5000
echo.
echo Make sure:
echo   1. This laptop and mobile device are on the same Wi-Fi
echo   2. Windows Firewall allows Python (will prompt on first run)
echo.
echo Press Ctrl+C to stop the server
echo ================================================================
echo.
python app.py
