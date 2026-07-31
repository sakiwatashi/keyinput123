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
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' ./tests/pime_all_readings_audit.py
```

## Protected interaction contracts

- Tapping Shift toggles persistent Chinese/English mode.
- Holding Shift and pressing A-Z emits one temporary uppercase English letter
  without changing modes. Pending Chinese must be committed before the letter.
- Chinese punctuation lives on **Ctrl**, following Microsoft Bopomofo, and
  **Shift is reserved for plain ASCII**. Binding punctuation to Shift made one
  physical key mean two things depending on mode, which is why it was changed;
  do not move it back. `Ctrl+,` `Ctrl+.` `Ctrl+'` `Ctrl+;` and their
  `Ctrl+Shift` variants must keep working in **both** Chinese and English mode,
  so the check has to precede the English-mode passthrough in both
  `filterKeyDown` and `onKeyDown`. `「」` sits on `Ctrl+[` / `Ctrl+]` and `『』`
  on `Ctrl+Shift+[` / `Ctrl+Shift+]`; this deliberately differs from Microsoft,
  which puts the rarer `【】` there.
- A shifted non-letter key must never reach the Bopomofo table. These keys
  carry Bopomofo unshifted (`,`=ㄝ `.`=ㄡ `/`=ㄥ `;`=ㄤ), so a gap inserts a
  Bopomofo symbol where a symbol belongs. Prefer the host's `charCode` so the
  active keyboard layout wins, and keep the fallback table for hosts that send
  none.
- Ten-item two-column candidate pages, Right/Down pagination,
  and right-side character editing are core behaviors. The left column must
  contain 1-5 from top to bottom and the right column 6-0; never bind A-J as
  candidate labels. Do not replace or
  remove these behaviors without an explicit user request.
- The two-column **vertical-first** grid and Japanese-inspired candidate chrome
  live only in `native_ui/` (`CandidateWindow.cpp` + built `PIMETextService.dll`).
  Stock signed PIME treats `candPerRow=2` as row-major horizontal pairs
  (`1 2 / 3 4 / …`), which is a regression. Once the user has opted in
  (`native-ui-preference.json` `enabled: true`), **never** restore signed
  DLLs, never run `-DisableUnsignedNativeUi`, and never “fix Chinese input”
  by forcing `Valid` Authenticode on `PIMETextService.dll`. Emergency recovery
  may only fix language list / tip Enable / launcher — not candidate UI.
- Candidate editing must offer and atomically apply common/personal phrases
  spanning 2-12 syllables while keeping high-frequency single-character and
  literal-Zhuyin choices available on the first ten-item page. At the end of
  the composition, phrase/sentence choices lead. After the caret moves inside
  the composition, the single character to its right must lead, so candidate
  1 locks only that syllable and advances instead of confirming the sentence.
- Automatic composition and the candidate editor share
  `_ranked_phrase_options()`. Conservative fuzzy-reading and exact typo
  corrections must enter that function as visible whole-sentence candidates;
  Enter must never perform a hidden final rewrite. Before opening Down or
  committing through any path, `_apply_phrase_ranking()` must synchronize the
  editable buffer. A better whole-buffer candidate must never be hidden behind
  Down; arrows are for overriding the default, not obtaining a default the
  engine already knew.
- Ranking order is a core contract: an explicit user candidate selection is
  first. Bundled candidates compare exact reading-span coverage before source
  weight through the global phrase lattice, so a shorter suffix cannot
  overwrite a longer complete conversion; equal spans prefer the pinned
  Rime/McBopomofo occurrence weights before the legacy engine.
  A stored single-character pin stays candidate zero for isolated input but
  is not a context lock; a reliable word or whole-buffer conversion may
  override it. Only a choice made explicitly in the current composition or a
  learned personal phrase locks its covered segments.
  Automatic commits must not silently teach the personal stores.
- Single-character ranking preserves libchewing's reading-aware dictionary
  default, then uses global Taiwan frequency for the remaining tail. Global
  frequency has no pronunciation information and must never promote a common
  alternate-reading character such as 員 over 運 for ㄩㄣˋ.
- Text/weight-only frequency indexes are search aids, not pronunciation
  evidence. Before a corpus phrase or fuzzy-reading correction changes live
  text, validate the complete span through `phrase_candidates(readings)`.
  Character-column membership alone must never let an alternate reading
  borrow an unrelated word (for example 貝殼 for ㄅㄟˋ ㄑㄩㄝˋ).
- Autocorrection is conservative, offline, and visible before commit. Apply
  only exact, same-length high-confidence rules from `data/common_typos.json`
  as whole-sentence candidates. A currently selected candidate or a learned
  personal phrase is protected and must outrank every autocorrection rule; a
  stored single-character pin alone is not a context lock. Do not add
  context-dependent pairs such as 的/得/地 or
  在/再 as unconditional replacements, and never upload text for correction.
- Unlocked spans are re-ranked live from their retained Bopomofo readings by
  `phrase_decoder.py` and the exact-reading index. Do not run a second greedy
  exact-phrase pass after the lattice; it can destroy a globally coherent
  result. `phonetic_corrector.py`, reviewed fuzzy phonetic-slot confusions,
  and fallback typo rules must become visible
  whole-sentence candidates before Enter. Surface variants such as 音該/英該
  must not be enumerated as separate rules, and a valid exact-reading phrase
  must be preserved as an alternate candidate.
- Activation and forced focus termination reset only the profile's internal
  Shift toggle. Respect the TSF keyboard-open state supplied by the host;
  never reopen a compartment after an app closes it. This prevents games and
  secure/custom controls from entering an open/close feedback loop.
- Numpad 0-9, decimal, divide, multiply, subtract, and add always emit their
  literal ASCII characters and never Bopomofo or candidate numbers.
  Shift+A-Z, shifted ASCII symbols, and Ctrl punctuation replace only an
  unfinished active syllable, preserve completed Chinese, and emit at the
  active caret. They are emitted by the service rather than passed through to
  the application, because a pending composition has to commit first.
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
  tone marks (3=ˇ, 6=ˊ, 4=ˋ, 7=˙). Shift+Space no longer emits ˉ: Shift is
  reserved for plain ASCII, so it emits a space like any shifted non-letter
  key. The first-tone mark has no standalone binding. Numpad digits
  and operators remain literal text. When completed segments already exist,
  raw Zhuyin and bare tone marks stay as protected segments in the editable
  composition; they must not commit the surrounding text like Enter.
- Feedback collection records only explicit conversion corrections. Never add
  surrounding text, application identity, automatic upload, or a network call
  to the IME runtime. The user must review records before opening a report.
- `bopomofo_core/data/high_frequency_phrases.json` is a generated LGPL-3.0
  derivative of pinned Rime Essay data. Never hand-edit it; preserve its
  attribution, generator, source hashes, and bundled license.
- `bopomofo_core/data/reading_phrases.json.gz` is a generated exact-reading
  index from pinned McBopomofo and libchewing-data rows, ranked with pinned
  Rime Essay occurrences. Never hand-edit it; preserve the generator, source
  hashes, MIT/LGPL notices, and the alternate-reading regression.
- `bopomofo_core/data/taiwan_frequency.json` is generated from the Ministry of
  Education's official open-data character and word tables. Never hand-edit
  it; preserve attribution, source hashes, generator, and data notice.
- `bopomofo_core/data/common_typos.json` is a reviewed source-attributed rule
  list. Keep source identifiers and URLs, require equal-length replacements,
  and add regression tests for every policy change.
- Add a regression assertion to `tests/pime_adapter_smoke.py` whenever a core
  interaction is fixed.
- Single-character ranking changes must also pass
  `tests/pime_all_readings_audit.py`, which enumerates every Bopomofo slot and
  tone combination accepted by libchewing. Never replace this with a handful
  of reported syllable examples.
- Candidate font, grid width, labels, and navigation can be changed through
  PIME's Python protocol. The authorized native style lives under `native_ui/`
  and is built from the exact bundled PIME `v1.3.0-stable` source. Install it
  only through the explicit `-EnableUnsignedNativeUi` opt-in, only when PIME
  has no unrelated modules, preserve the original DLLs, and restore them only
  when the installed hashes still match our build. Fresh installs keep the
  signed DLLs for game compatibility. Once opted in, persist that preference
  across normal and EXE updates; never silently restore the signed UI during
  a Python-layer update. `-DisableUnsignedNativeUi` is the explicit rollback.

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
