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
- Candidate editing must offer and atomically apply common/personal phrases
  spanning 2-12 syllables while keeping single-character choices available in
  the compact five-row menu.
- Ranking order is a core contract: an explicit user candidate selection is
  first. Bundled candidates compare exact reading-span coverage before source
  weight, so a shorter suffix cannot overwrite a longer complete conversion;
  equal spans prefer Taiwan character/word frequencies, then engine/Rime.
  Automatic commits must not silently teach the personal stores.
- Activation, a Windows keyboard-close status, and forced focus termination
  restore the profile to keyboard-open Bopomofo mode. Password fields and apps
  that explicitly disable IMEs remain under Windows control.
- Numpad 0-9 always emits digits and never Bopomofo or candidate numbers.
  Shift+A-Z and Shift punctuation replace only an unfinished active syllable,
  preserve completed Chinese, and emit at the active caret.
- Feedback collection records only explicit conversion corrections. Never add
  surrounding text, application identity, automatic upload, or a network call
  to the IME runtime. The user must review records before opening a report.
- `bopomofo_core/data/high_frequency_phrases.json` is a generated LGPL-3.0
  derivative of pinned Rime Essay data. Never hand-edit it; preserve its
  attribution, generator, source hashes, and bundled license.
- `bopomofo_core/data/taiwan_frequency.json` is generated from the Ministry of
  Education's official open-data character and word tables. Never hand-edit
  it; preserve attribution, source hashes, generator, and data notice.
- Add a regression assertion to `tests/pime_adapter_smoke.py` whenever a core
  interaction is fixed.

Run `./build_release.ps1` for a distributable installer. Update all version
locations together when cutting a new version.

## User data and safety

- `%APPDATA%\PinnedBopomofo` contains private learned input and local feedback.
  Do not read,
  upload, commit, or publish it unless the user explicitly requests that.
- Installation and removal must preserve PIME installations that existed
  before this product and must preserve personal learning data.
- Stage and commit only files in this repository; the parent workspace may
  contain unrelated projects and uncommitted work.
