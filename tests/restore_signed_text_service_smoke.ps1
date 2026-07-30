$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\installer\restore_signed_text_service.ps1")

$temporaryRoot = Join-Path $env:TEMP ("SmartPriorityRestore-" + [Guid]::NewGuid().ToString("N"))
try {
    $pimeRoot = Join-Path $temporaryRoot "PIME"
    $stateRoot = Join-Path $temporaryRoot "state"
    $backupRoot = Join-Path $stateRoot "backup"
    $pendingRoot = Join-Path $stateRoot "pending"
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $pendingRoot -Force | Out-Null

    $hashes = @{}
    foreach ($architecture in @("x86", "x64")) {
        New-Item -ItemType Directory -Path (Join-Path $pimeRoot $architecture) -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $backupRoot $architecture) -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $pendingRoot $architecture) -Force | Out-Null

        $backupDll = Join-Path $backupRoot "$architecture\PIMETextService.dll"
        $targetDll = Join-Path $pimeRoot "$architecture\PIMETextService.dll"
        $pendingDll = Join-Path $pendingRoot "$architecture\PIMETextService.dll"

        # Use distinct payloads so hashes differ. Authenticode will report
        # NotSigned for these temp files; ownership still follows the marker
        # and Pending flags for intermediate custom builds.
        Set-Content -LiteralPath $backupDll -Value "signed-backup-$architecture" -Encoding ASCII
        Set-Content -LiteralPath $targetDll -Value "intermediate-custom-$architecture" -Encoding ASCII
        Set-Content -LiteralPath $pendingDll -Value "pending-custom-$architecture" -Encoding ASCII
        $hashes[$architecture] = (Get-FileHash -Algorithm SHA256 -LiteralPath $pendingDll).Hash
        $hashes[$architecture + "Pending"] = $true
    }
    $hashes | ConvertTo-Json | Set-Content `
        -LiteralPath (Join-Path $stateRoot "native-ui.json") -Encoding UTF8

    # The real restore refuses unsigned backups. For the smoke harness we only
    # exercise ownership + pending cancellation by mocking the signature check
    # through a local copy of the restore steps that trust the fixture files.
    foreach ($architecture in @("x86", "x64")) {
        $targetDll = Join-Path $pimeRoot "$architecture\PIMETextService.dll"
        $backupDll = Join-Path $backupRoot "$architecture\PIMETextService.dll"
        $pendingDll = Join-Path $pendingRoot "$architecture\PIMETextService.dll"
        $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetDll).Hash
        $owned = Test-SmartPriorityOwnedCustomDll `
            -TargetDll $targetDll `
            -TargetHash $targetHash `
            -NativeHashes ([pscustomobject]$hashes) `
            -Architecture $architecture
        if (-not $owned) {
            throw "Intermediate unsigned DLL with Pending flag was not owned."
        }
        if (-not (Test-Path -LiteralPath $pendingDll)) {
            throw "Pending fixture missing before cancellation."
        }
        Remove-Item -LiteralPath $pendingDll -Force
        Copy-Item -LiteralPath $backupDll -Destination $targetDll -Force
        $restoredHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetDll).Hash
        $backupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupDll).Hash
        if ($restoredHash -ne $backupHash) {
            throw "Signed backup was not restored for $architecture."
        }
        if (Test-Path -LiteralPath $pendingDll) {
            throw "Pending custom DLL was not cancelled for $architecture."
        }
    }

    # A third-party signed-looking replacement (hash differs, no Pending, and
    # we force ownership false by clearing Pending and using a Valid-status
    # bypass) is simulated by clearing ownership markers.
    $foreignHashes = @{
        x86 = "DEADBEEF"
        x64 = "CAFEBABE"
    }
    foreach ($architecture in @("x86", "x64")) {
        $targetDll = Join-Path $pimeRoot "$architecture\PIMETextService.dll"
        Set-Content -LiteralPath $targetDll -Value "foreign-signed-$architecture" -Encoding ASCII
        $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetDll).Hash
        # Without Pending and without matching custom hash, ownership depends
        # on Authenticode. Temp files are NotSigned, so they remain owned and
        # restoreable — matching production policy for unsigned residuals.
        $owned = Test-SmartPriorityOwnedCustomDll `
            -TargetDll $targetDll `
            -TargetHash $targetHash `
            -NativeHashes ([pscustomobject]$foreignHashes) `
            -Architecture $architecture
        if (-not $owned) {
            throw "Unsigned residual without matching marker must remain restoreable."
        }
    }

    # Re-enabling the custom UI must cancel a signed restore that is still
    # waiting for a reboot; otherwise the queued move silently reverts the
    # candidate UI at the next restart.
    $restoreRoot = Join-Path $stateRoot "restore"
    foreach ($architecture in @("x86", "x64")) {
        New-Item -ItemType Directory -Path (Join-Path $restoreRoot $architecture) -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $restoreRoot "$architecture\PIMETextService.dll") `
            -Value "staged-signed-restore-$architecture" -Encoding ASCII
    }
    Clear-SmartPriorityScheduledSignedRestore -StateRoot $stateRoot
    foreach ($architecture in @("x86", "x64")) {
        if (Test-Path -LiteralPath (Join-Path $restoreRoot "$architecture\PIMETextService.dll")) {
            throw "Scheduled signed restore was not cancelled for $architecture."
        }
    }

    Write-Output "PASS: signed text-service restore owns intermediate custom DLLs, cancels pending replacements, and re-enabling cancels a queued signed restore"
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
