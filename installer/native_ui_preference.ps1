$ErrorActionPreference = "Stop"

function Read-SmartPriorityNativeUiPreference {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PreferencePath
    )

    if (-not (Test-Path -LiteralPath $PreferencePath)) {
        return $null
    }
    try {
        $value = Get-Content -LiteralPath $PreferencePath -Raw -Encoding UTF8 |
            ConvertFrom-Json
        if ($null -eq $value.enabled) {
            return $null
        }
        return [bool]$value.enabled
    }
    catch {
        # A damaged preference must never make installation fail. Fall back to
        # recognizing an already active custom UI, then to the signed default.
        return $null
    }
}

function Test-SmartPriorityCustomNativeUiState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PimeRoot,
        [Parameter(Mandatory = $true)]
        [string]$StateRoot
    )

    $markerPath = Join-Path $StateRoot "native-ui.json"
    if (-not (Test-Path -LiteralPath $markerPath)) {
        return $false
    }
    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
        foreach ($architecture in @("x86", "x64")) {
            $expectedHash = $marker.$architecture
            if (-not $expectedHash) {
                return $false
            }
            $activeDll = Join-Path $PimeRoot "$architecture\PIMETextService.dll"
            if ((Test-Path -LiteralPath $activeDll) -and
                (Get-FileHash -Algorithm SHA256 -LiteralPath $activeDll).Hash -eq $expectedHash) {
                continue
            }
            $pendingDll = Join-Path $StateRoot "pending\$architecture\PIMETextService.dll"
            $pendingProperty = $architecture + "Pending"
            if ($marker.$pendingProperty -and
                (Test-Path -LiteralPath $pendingDll) -and
                (Get-FileHash -Algorithm SHA256 -LiteralPath $pendingDll).Hash -eq $expectedHash) {
                continue
            }
            return $false
        }
        return $true
    }
    catch {
        return $false
    }
}

function Resolve-SmartPriorityNativeUiPreference {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PreferencePath,
        [Parameter(Mandatory = $true)]
        [string]$PimeRoot,
        [Parameter(Mandatory = $true)]
        [string]$StateRoot,
        [switch]$EnableUnsignedNativeUi,
        [switch]$DisableUnsignedNativeUi
    )

    if ($EnableUnsignedNativeUi -and $DisableUnsignedNativeUi) {
        throw "EnableUnsignedNativeUi and DisableUnsignedNativeUi cannot be used together."
    }
    if ($EnableUnsignedNativeUi) {
        return $true
    }
    if ($DisableUnsignedNativeUi) {
        return $false
    }

    $stored = Read-SmartPriorityNativeUiPreference -PreferencePath $PreferencePath
    if ($null -ne $stored) {
        return [bool]$stored
    }

    # Migrate installations created before the preference file existed. An
    # active or correctly staged custom DLL proves that the user opted in.
    return Test-SmartPriorityCustomNativeUiState `
        -PimeRoot $PimeRoot -StateRoot $StateRoot
}

function Save-SmartPriorityNativeUiPreference {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PreferencePath,
        [Parameter(Mandatory = $true)]
        [bool]$Enabled
    )

    $parent = Split-Path -Parent $PreferencePath
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    @{
        enabled = $Enabled
        version = 1
    } | ConvertTo-Json | Set-Content -LiteralPath $PreferencePath -Encoding UTF8
}
