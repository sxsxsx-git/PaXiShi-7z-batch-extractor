# PaXiShi 7z Batch Extractor

GUI tool for renaming, extracting, and cleaning up 7z files.
Designed for PaXiShi download collections.

## Files
- gui_app.py: GUI entry (uses shared core)
- cli_app.py: CLI entry (uses shared core)
- paxishi_extractor/: shared pipeline + file-processing logic
- build_gui_exe.py: build script for Windows exe
- pyinstaller_gui.spec: PyInstaller spec for GUI build
- tests/: pytest coverage for core logic

## Requirements
- Python 3.9+
- pip install -r requirements.txt

## Development
- pip install -r requirements-dev.txt
- pytest

## Run GUI
- python gui_app.py

## Run CLI
- python cli_app.py --root D:/b/ --password 1151

## Build EXE
- python build_gui_exe.py

## CI Build and Release
- The workflow builds a Windows EXE on tags like v1.0.0.
- Push a tag to trigger a release upload:
  - git tag v1.0.0
  - git push origin v1.0.0

Notes
- Default password: 1151
- Logs are written to process.log
