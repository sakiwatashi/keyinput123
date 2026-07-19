#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if ! command -v powershell.exe >/dev/null 2>&1; then
  echo "This installer must run on Windows with PowerShell available." >&2
  exit 1
fi

if command -v cygpath >/dev/null 2>&1; then
  installer_path="$(cygpath -w "$script_dir/install.ps1")"
else
  installer_path="$script_dir/install.ps1"
fi

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$installer_path"
