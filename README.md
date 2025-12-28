# PaXiShi 7z Batch Extractor

GUI tool for renaming, extracting, and cleaning up 7z files.
Designed for PaXiShi download collections.

## Files
- gui_app.py: primary GUI (multiprocessing pool)
- gui_app_threaded.py: alternate GUI (thread pool)
- cli_app.py: CLI version (edit path/password in file)
- cli_app_legacy.py: older CLI variant
- build_gui_exe.py: build script for Windows exe
- pyinstaller_gui.spec: PyInstaller spec for GUI build

## Requirements
- Python 3.9+
- pip install py7zr tqdm

## Run GUI
- python gui_app.py

## Run CLI
- python cli_app.py

## Build EXE
- python build_gui_exe.py

Notes
- Default password: 1151
- Logs are written to process.log
