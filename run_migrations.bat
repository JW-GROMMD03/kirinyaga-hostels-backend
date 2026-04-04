@echo off
echo ========================================
echo   Running Migrations with SQLite
echo ========================================

cd /d C:\Users\eugki\OneDrive\Desktop\kirinyaga-hostels\backend

echo Temporarily disabling DATABASE_URL...
set DATABASE_URL=

echo Running migrations...
python manage.py makemigrations accounts --name enhance_audit_log
python manage.py migrate accounts
python manage.py migrate

echo.
echo Migration complete!
echo.
pause