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

    $pythonMethods = Join-Path $pimeRoot "python\input_methods"
    $chewingModule = Join-Path $pythonMethods "chewing"
    $projectModule = Join-Path $pythonMethods "pinned_bopomofo"
    $nativePayload = Join-Path $temporaryRoot "native-ui-payload"
    foreach ($directory in @(
        $chewingModule,
        $projectModule,
        (Join-Path $nativePayload "x86"),
        (Join-Path $nativePayload "x64")
    )) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    Set-Content -LiteralPath (Join-Path $nativePayload "x86\PIMETextService.dll") -Value "x86" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $nativePayload "x64\PIMETextService.dll") -Value "x64" -Encoding ASCII

    $freshPimeEligible = Test-SmartPriorityNativeUiEligibility `
        -PimeRoot $pimeRoot -NativeUiPayload $nativePayload -Requested $true `
        -PythonModulesRemovedByInstaller @("chewing")
    if (-not $freshPimeEligible) {
        throw "The bundled New Chewing module must not block custom UI when this installer removes it."
    }
    $existingChewingBlocked = Test-SmartPriorityNativeUiEligibility `
        -PimeRoot $pimeRoot -NativeUiPayload $nativePayload -Requested $true
    if ($existingChewingBlocked) {
        throw "An unrelated module in an existing PIME installation must block the custom UI."
    }

    $unrelatedPythonModule = Join-Path $pythonMethods "unrelated"
    New-Item -ItemType Directory -Path $unrelatedPythonModule -Force | Out-Null
    $unrelatedPythonBlocked = Test-SmartPriorityNativeUiEligibility `
        -PimeRoot $pimeRoot -NativeUiPayload $nativePayload -Requested $true `
        -PythonModulesRemovedByInstaller @("chewing")
    if ($unrelatedPythonBlocked) {
        throw "An unrelated Python input method did not block the custom UI."
    }
    Remove-Item -LiteralPath $unrelatedPythonModule -Recurse -Force

    $unrelatedNodeModule = Join-Path $pimeRoot "node\input_methods\unrelated"
    New-Item -ItemType Directory -Path $unrelatedNodeModule -Force | Out-Null
    $unrelatedNodeBlocked = Test-SmartPriorityNativeUiEligibility `
        -PimeRoot $pimeRoot -NativeUiPayload $nativePayload -Requested $true `
        -PythonModulesRemovedByInstaller @("chewing")
    if ($unrelatedNodeBlocked) {
        throw "An unrelated Node input method did not block the custom UI."
    }
    Remove-Item -LiteralPath (Split-Path -Parent $unrelatedNodeModule) -Recurse -Force

    Remove-Item -LiteralPath (Join-Path $nativePayload "x64\PIMETextService.dll") -Force
    $missingPayloadBlocked = Test-SmartPriorityNativeUiEligibility `
        -PimeRoot $pimeRoot -NativeUiPayload $nativePayload -Requested $true `
        -PythonModulesRemovedByInstaller @("chewing")
    if ($missingPayloadBlocked) {
        throw "The custom UI was considered eligible without both architecture DLLs."
    }

    Write-Output "PASS: native UI preference persists, rolls back explicitly, and checks install eligibility"
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
