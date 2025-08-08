@echo off
REM update.bat
REM Load .env if present and run the Python script.

if exist .env (
	for /f "usebackq tokens=*" %%a in (".env") do set %%a
)

python language_charts.py