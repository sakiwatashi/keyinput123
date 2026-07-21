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
- Shift punctuation, ten-item two-column candidate pages, Right/Down pagination,
  and right-side character editing are core behaviors. The left column must
  contain 1-5 from top to bottom and the right column 6-0; never bind A-J as
  candidate labels. Do not replace or
  remove these behaviors without an explicit user request.
- Candidate editing must offer and atomically apply common/personal phrases
  spanning 2-12 syllables while keeping high-frequency single-character and
  literal-Zhuyin choices available on the first ten-item page.
- Automatic composition and the candidate editor share
  `_ranked_phrase_options()`. Before opening Down or committing through any
  path, `_apply_phrase_ranking()` must synchronize the editable buffer. A
  better whole-buffer candidate must never be hidden behind Down; arrows are
  for overriding the default, not obtaining a default the engine already knew.
- Ranking order is a core contract: an explicit user candidate selection is
  first. Bundled candidates compare exact reading-span coverage before source
  weight, so a shorter suffix cannot overwrite a longer complete conversion;
  equal spans prefer Taiwan character/word frequencies, then engine/Rime.
  A stored single-character pin stays candidate zero for isolated input but
  is not a context lock; a reliable word or whole-buffer conversion may
  override it. Only a choice made explicitly in the current composition or a
  learned personal phrase locks its covered segments.
  Automatic commits must not silently teach the personal stores.
- Enter-only autocorrection is conservative and offline. Apply only exact,
  same-length high-confidence rules from `data/common_typos.json`; Space must
  preserve the composed text. A currently selected candidate or a learned
  personal phrase is protected and must outrank every autocorrection rule; a
  stored single-character pin alone is not a context lock. Do not add
  context-dependent pairs such as 的/得/地 or
  在/再 as unconditional replacements, and never upload text for correction.
- Unlocked spans are re-ranked live from their exact retained Bopomofo readings
  through `phonetic_corrector.py` and the bundled phrase indexes. Enter also
  enables reviewed fuzzy phonetic-slot confusions before applying fallback
  typo rules. Surface variants such as 音該/英該 must not be enumerated as
  separate rules, and a valid exact-reading phrase must be preserved.
- Activation, a Windows keyboard-close status, and forced focus termination
  restore the profile to keyboard-open Bopomofo mode. Password fields and apps
  that explicitly disable IMEs remain under Windows control.
- Numpad 0-9, decimal, divide, multiply, subtract, and add always emit their
  literal ASCII characters and never Bopomofo or candidate numbers.
  Shift+A-Z and Shift punctuation replace only an unfinished active syllable,
  preserve completed Chinese, and emit at the active caret.
- Literal Bopomofo is a core behavior. For any lone initial, medial, or rime,
  Space first asks the dictionary for the corresponding first-tone Chinese
  syllable; do not classify every initial as invalid because ㄙ and ㄓ,
  and similar syllabic initials are real readings. When candidate zero is
  Chinese, it is auto-selected and raw Zhuyin stays within the first four
  candidates. When candidate zero is literal Zhuyin, open the literal-first
  menu even if libchewing appended obscure Han characters to the tail.
  Completed readings also offer their literal spelling within the
  first four candidates, including sentence editing. With no active syllable,
  bare DaQian tone keys emit their
  tone marks (3=ˇ, 6=ˊ, 4=ˋ, 7=˙), while Shift+Space emits ˉ. Numpad digits
  and operators remain literal text.
- Feedback collection records only explicit conversion corrections. Never add
  surrounding text, application identity, automatic upload, or a network call
  to the IME runtime. The user must review records before opening a report.
- `bopomofo_core/data/high_frequency_phrases.json` is a generated LGPL-3.0
  derivative of pinned Rime Essay data. Never hand-edit it; preserve its
  attribution, generator, source hashes, and bundled license.
- `bopomofo_core/data/taiwan_frequency.json` is generated from the Ministry of
  Education's official open-data character and word tables. Never hand-edit
  it; preserve attribution, source hashes, generator, and data notice.
- `bopomofo_core/data/common_typos.json` is a reviewed source-attributed rule
  list. Keep source identifiers and URLs, require equal-length replacements,
  and add regression tests for every policy change.
- Add a regression assertion to `tests/pime_adapter_smoke.py` whenever a core
  interaction is fixed.
- Candidate font, grid width, labels, and navigation can be changed through
  PIME's Python protocol. The authorized native style lives under `native_ui/`
  and is built from the exact bundled PIME `v1.3.0-stable` source. Install it
  only when PIME has no unrelated modules, preserve the original DLLs, and
  restore them only when the installed hashes still match our build.

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
