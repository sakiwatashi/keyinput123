$ErrorActionPreference = "Stop"

function Ensure-SmartPriorityNativeMethods {
    if ("SmartPriorityNativeMethods" -as [type]) {
        return
    }
    Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class SmartPriorityNativeMethods {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool MoveFileEx(
        string existingFile,
        string newFile,
        int flags
    );
}
"@
}

function Test-SmartPriorityOwnedCustomDll {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetDll,
        [Parameter(Mandatory = $true)]
        [string]$TargetHash,
        [Parameter(Mandatory = $true)]
        $NativeHashes,
        [Parameter(Mandatory = $true)]
        [string]$Architecture
    )

    $expectedCustomHash = $NativeHashes.$Architecture
    if ($expectedCustomHash -and $TargetHash -eq $expectedCustomHash) {
        return $true
    }

    # A pending custom replacement means this installation still owns the
    # native UI transition, even when the loaded DLL is an older intermediate
    # unsigned build that no longer matches the marker hash.
    if ($NativeHashes.($Architecture + "Pending")) {
        return $true
    }

    # Any unsigned text-service DLL under our native-ui marker is treated as a
    # custom UI residual. Games and anti-cheat expect PIME's original signed
    # binary; leaving an intermediate unsigned file breaks that contract.
    $targetSignature = Get-AuthenticodeSignature -LiteralPath $TargetDll
    return $targetSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid
}

function Copy-OrScheduleSmartPriorityDll {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceDll,
        [Parameter(Mandatory = $true)]
        [string]$TargetDll,
        [Parameter(Mandatory = $true)]
        [string]$RestoreDll,
        [Parameter(Mandatory = $true)]
        [string]$Architecture
    )

    Ensure-SmartPriorityNativeMethods
    try {
        Copy-Item -LiteralPath $SourceDll -Destination $TargetDll -Force
        return "copied"
    }
    catch [System.IO.IOException], [System.UnauthorizedAccessException] {
        # The TSF DLL is normally loaded by desktop and game clients.
        # Keep a persistent signed source and replace it at reboot.
        New-Item -ItemType Directory -Path (Split-Path -Parent $RestoreDll) -Force | Out-Null
        Copy-Item -LiteralPath $SourceDll -Destination $RestoreDll -Force
        $scheduled = [SmartPriorityNativeMethods]::MoveFileEx(
            $RestoreDll,
            $TargetDll,
            0x4 -bor 0x1
        )
        if (-not $scheduled) {
            $win32Error = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "Unable to schedule the $Architecture signed PIME DLL restore (Win32 $win32Error)."
        }
        return "scheduled"
    }
}

function Clear-SmartPriorityScheduledSignedRestore {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StateRoot
    )

    # A signed-DLL restore that was deferred to the next reboot must not undo
    # a later explicit re-enable of the custom UI. Deleting the staged source
    # turns the queued kernel move into a no-op, mirroring how pending custom
    # replacements are cancelled before a restore.
    foreach ($architecture in @("x86", "x64")) {
        $restoreDll = Join-Path $StateRoot "restore\$architecture\PIMETextService.dll"
        if (Test-Path -LiteralPath $restoreDll) {
            Remove-Item -LiteralPath $restoreDll -Force
        }
    }
}

function Restore-OriginalPimeTextService {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PimeRoot,
        [Parameter(Mandatory = $true)]
        [string]$StateRoot,
        [switch]$PassThru
    )

    $nativeMarker = Join-Path $StateRoot "native-ui.json"
    $backupRoot = Join-Path $StateRoot "backup"
    $pendingRoot = Join-Path $StateRoot "pending"
    if (-not (Test-Path -LiteralPath $nativeMarker) -or
        -not (Test-Path -LiteralPath $backupRoot)) {
        $result = [pscustomobject]@{
            Status = "noop"
            Message = "No native UI state to restore."
        }
        if ($PassThru) { return $result }
        Write-Output $result.Message
        return
    }

    $nativeHashes = Get-Content -LiteralPath $nativeMarker -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $nativeStateCanBeRemoved = $true
    $restoreScheduled = $false
    $restoredNow = $false

    foreach ($architecture in @("x86", "x64")) {
        $targetDll = Join-Path $PimeRoot "$architecture\PIMETextService.dll"
        $backupDll = Join-Path $backupRoot "$architecture\PIMETextService.dll"
        $pendingDll = Join-Path $pendingRoot "$architecture\PIMETextService.dll"

        # Always cancel a queued custom replacement first. Deleting the pending
        # source makes an unfinished MoveFileEx no-op at the next reboot.
        if (Test-Path -LiteralPath $pendingDll) {
            Remove-Item -LiteralPath $pendingDll -Force
        }

        if (-not (Test-Path -LiteralPath $targetDll) -or
            -not (Test-Path -LiteralPath $backupDll)) {
            $nativeStateCanBeRemoved = $false
            continue
        }

        $backupSignature = Get-AuthenticodeSignature -LiteralPath $backupDll
        if ($backupSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
            throw "Refusing to restore an unsigned or invalid $architecture PIME backup."
        }

        $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetDll).Hash
        $backupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupDll).Hash
        if ($targetHash -eq $backupHash) {
            continue
        }

        $ownedCustom = Test-SmartPriorityOwnedCustomDll `
            -TargetDll $targetDll `
            -TargetHash $targetHash `
            -NativeHashes $nativeHashes `
            -Architecture $architecture
        if (-not $ownedCustom) {
            # Another product replaced the shared signed DLL. Keep evidence.
            $nativeStateCanBeRemoved = $false
            continue
        }

        $restoreDll = Join-Path $StateRoot "restore\$architecture\PIMETextService.dll"
        $action = Copy-OrScheduleSmartPriorityDll `
            -SourceDll $backupDll `
            -TargetDll $targetDll `
            -RestoreDll $restoreDll `
            -Architecture $architecture
        if ($action -eq "scheduled") {
            $nativeStateCanBeRemoved = $false
            $restoreScheduled = $true
        }
        else {
            $restoredNow = $true
        }
    }

    if ($nativeStateCanBeRemoved -and (Test-Path -LiteralPath $StateRoot)) {
        Remove-Item -LiteralPath $StateRoot -Recurse -Force
        $message = "Restored the signed PIME text-service DLLs."
        $status = "restored"
    }
    elseif ($restoreScheduled) {
        $message = "The signed PIME text-service DLL restore will finish after Windows restarts."
        $status = "scheduled"
    }
    elseif ($restoredNow) {
        $message = "Restored the signed PIME text-service DLLs."
        $status = "restored"
    }
    else {
        $message = "Preserved the native UI backup because the shared PIME DLL was changed by another product."
        $status = "preserved"
    }

    $result = [pscustomobject]@{
        Status = $status
        Message = $message
    }
    if ($PassThru) { return $result }
    Write-Output $message
}
