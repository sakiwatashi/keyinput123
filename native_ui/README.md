# Smart Priority Bopomofo native candidate UI

There are two implementations of the Japanese-inspired candidate window here.
**`helper/` is the one to use.**

- **`helper/` — out-of-process (preferred).** A standalone executable that
  draws the vertical-first grid in its own process and never loads into
  another application. Every process, games included, keeps only PIME's
  original signed `PIMETextService.dll`. See `../OUT_OF_PROCESS_UI_DESIGN.md`.
- **`src/` — in-process (legacy, discouraged).** A rebuilt
  `PIMETextService.dll`. Because a TSF text service is loaded into every
  application that accepts text, this unsigned DLL also enters game processes.
  VALORANT's Vanguard force-unloaded it mid-process and the game crashed with
  a BEX64 fault; that incident is what the out-of-process design exists to
  remove. It is kept for reference and for the explicit opt-in below.

The rest of this file describes the legacy in-process build.

This directory contains the source and reproducible build script for the
Japanese-inspired candidate window bundled with Smart Priority Bopomofo.

- Upstream PIME commit: `26fcf6ac8874e76b8f75f6826811b03bfdfc2e89`
  (`v1.3.0-stable`, matching the bundled PIME runtime)
- Upstream libIME2 commit: `8ad3c9b433d930ce5614c483461dfa78cedb5efd`
- Upstream: https://github.com/EasyIME/PIME
- License: LGPL-2.0-or-later; see `LGPL-2.0.txt`.

`src/CandidateWindow.cpp` owns the Japanese surface and the two-column
vertical-first grid (left 1–5, right 6–0). `src/PIMETextService.cpp` forces
that window to stay visible even when apps try to take over TSF UI elements
(which would otherwise hide our window and drop the layout). The UI uses a warm
paper background, indigo accents, rounded clipping, a thin neutral border,
DPI-scaled spacing, and double-buffered painting. `src/CMakeLists.txt` excludes
PIMELauncher because the product keeps the signed launcher's existing binary
and rebuilds only `PIMETextService.dll`.

Run `build_native_ui.ps1` on Windows with Visual Studio 2022 C++ tools to
reproduce `bin/x86/PIMETextService.dll` and `bin/x64/PIMETextService.dll`.

These locally built DLLs are not code-signed and are therefore not installed
by default. The source installer accepts the explicit
`-EnableUnsignedNativeUi` switch when no other PIME input-method modules are
present. It backs up the original shared DLLs and remembers the opt-in across
normal and EXE updates. `-DisableUnsignedNativeUi` or uninstall explicitly
restores the signed PIME binaries when game or anti-cheat compatibility is
more important than the custom appearance.
