@echo off
cd /d d:\Projects\MajorProject
echo Testing Python imports...
python -c "print('Python OK')"
timeout /t 2 >nul
