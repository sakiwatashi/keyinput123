$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\installer\native_ui_preference.ps1")

$temporaryRoot = Join-Path $env:TEMP ("SmartPriorityNativePreference-" + [Guid]::NewGuid().ToString("N"))
try {
    $pimeRoot = Join-Path $temporaryRoot "PIME"
    $stateRoot = Join-Path $temporaryRoot "state"
    $preferencePath = Join-Path $temporaryRoot "native-ui-preference.json"
    foreach ($architecture in @("x86", "x64")) {
        New-Item -ItemType Directory -Path (Join-Path $pimeRoot $architecture) -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $pimeRoot "$architecture\PIMETextService.dll") `
            -Value "signed-$architecture" -Encoding ASCII
    }

    $fresh = Resolve-SmartPriorityNativeUiPreference `
        -PreferencePath $preferencePath -PimeRoot $pimeRoot -StateRoot $stateRoot
    if ($fresh) { throw "A fresh install must keep the signed default." }

    $enabled = Resolve-SmartPriorityNativeUiPreference `
        -PreferencePath $preferencePath -PimeRoot $pimeRoot -StateRoot $stateRoot `
        -EnableUnsignedNativeUi
    if (-not $enabled) { throw "Explicit custom UI opt-in was ignored." }
    Save-SmartPriorityNativeUiPreference -PreferencePath $preferencePath -Enabled $enabled
    $remembered = Resolve-SmartPriorityNativeUiPreference `
        -PreferencePath $preferencePath -PimeRoot $pimeRoot -StateRoot $stateRoot
    if (-not $remembered) { throw "Custom UI preference was not remembered." }

    $disabled = Resolve-SmartPriorityNativeUiPreference `
        -PreferencePath $preferencePath -PimeRoot $pimeRoot -StateRoot $stateRoot `
        -DisableUnsignedNativeUi
    if ($disabled) { throw "Explicit signed UI selection was ignored." }
    Save-SmartPriorityNativeUiPreference -PreferencePath $preferencePath -Enabled $disabled
    $rememberedDisabled = Resolve-SmartPriorityNativeUiPreference `
        -PreferencePath $preferencePath -PimeRoot $pimeRoot -StateRoot $stateRoot
    if ($rememberedDisabled) { throw "Signed UI preference was not remembered." }

    Remove-Item -LiteralPath $preferencePath -Force
    $hashes = @{}
    foreach ($architecture in @("x86", "x64")) {
        $customDll = Join-Path $pimeRoot "$architecture\PIMETextService.dll"
        Set-Content -LiteralPath $customDll -Value "custom-$architecture" -Encoding ASCII
        $hashes[$architecture] = (Get-FileHash -Algorithm SHA256 -LiteralPath $customDll).Hash
    }
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    $hashes | ConvertTo-Json | Set-Content `
        -LiteralPath (Join-Path $stateRoot "native-ui.json") -Encoding UTF8
    $migrated = Resolve-SmartPriorityNativeUiPreference `
        -PreferencePath $preferencePath -PimeRoot $pimeRoot -StateRoot $stateRoot
    if (-not $migrated) { throw "Existing custom UI state was not migrated." }

    $conflictRejected = $false
    try {
        Resolve-SmartPriorityNativeUiPreference `
            -PreferencePath $preferencePath -PimeRoot $pimeRoot -StateRoot $stateRoot `
            -EnableUnsignedNativeUi -DisableUnsignedNativeUi | Out-Null
    }
    catch {
        $conflictRejected = $true
    }
    if (-not $conflictRejected) { throw "Conflicting UI switches were accepted." }

    Write-Output "PASS: native UI preference is persistent and explicitly reversible"
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
