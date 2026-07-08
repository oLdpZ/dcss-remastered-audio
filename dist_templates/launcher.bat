@echo off
REM DCSS Remastered — doppio clic per giocare.
start "" /min powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0remaster\play-remaster.ps1"
