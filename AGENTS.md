# Repository instructions

This is a Windows Traditional Chinese input method built on PIME and
libchewing. Read `README.md` and `AI_MAINTENANCE.md` before making changes.

## Installation

- PowerShell: `./install.ps1`
- Git Bash: `./install.sh`
- Never hard-code a user name, drive, clone directory, or Documents path.
- Never edit the installed copy under Program Files as the source of truth.

## Required checks

Run after every behavior change:

```powershell
python -m unittest discover -s tests -v
./build_pime_overlay.ps1
```

When PIME is installed, also run:

```powershell
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' ./tests/pime_adapter_smoke.py
```

## Protected interaction contracts

- Tapping Shift toggles persistent Chinese/English mode.
- Holding Shift and pressing A-Z emits one temporary uppercase English letter
  without changing modes. Pending Chinese must be committed before the letter.
- Shift punctuation, the five-item candidate menu, candidate expansion, and
  right-side character editing are core behaviors. Do not replace or remove
  them without an explicit user request.
- Add a regression assertion to `tests/pime_adapter_smoke.py` whenever a core
  interaction is fixed.

Run `./build_release.ps1` for a distributable installer. Update all version
locations together when cutting a new version.

## User data and safety

- `%APPDATA%\PinnedBopomofo` contains private learned input. Do not read,
  upload, commit, or publish it unless the user explicitly requests that.
- Installation and removal must preserve PIME installations that existed
  before this product and must preserve personal learning data.
- Stage and commit only files in this repository; the parent workspace may
  contain unrelated projects and uncommitted work.
