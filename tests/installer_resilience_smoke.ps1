# Two installer defects that first surfaced on a real user's machine
# (2026-08-01, v0.6.5).
#
# 1. A leftover HKLM PIME registry key pointing at a deleted directory made
#    install.ps1 skip the bundled PIME installer and fail one step later with
#    "A valid PIME installation directory was not found". Detection must
#    validate the directory, not merely read the value.
# 2. install.ps1 and uninstall.ps1 stop their transcript in `finally`, but an
#    uncaught error prints only after that, so the log the failure dialog
#    points at ended up empty. Both scripts must catch, record, and rethrow.
#
# These are source-shape assertions in the spirit of
# installer_payload_smoke.ps1: they cannot run the installer against a fake
# registry, but they stop the guarded pattern from being simplified away.
$ErrorActionPreference = "Stop"

$projectRoot = Join-Path $PSScriptRoot ".."
$install = Get-Content -LiteralPath (Join-Path $projectRoot "installer\install.ps1") -Raw
$uninstall = Get-Content -LiteralPath (Join-Path $projectRoot "installer\uninstall.ps1") -Raw
$transactionHelper = Join-Path $projectRoot "installer\module_transaction.ps1"

$problems = @()

# --- 1. Registry detection must validate the directory ---
if ($install -notmatch 'function\s+Find-PimeInstallRoot') {
    $problems += "install.ps1 no longer defines Find-PimeInstallRoot"
}
elseif ($install -match '(?s)function\s+Find-PimeInstallRoot.*?\r?\n\}') {
    if ($Matches[0] -notmatch 'Test-Path\s+-LiteralPath\s+\$root') {
        $problems += "Find-PimeInstallRoot no longer validates the directory it reads from the registry"
    }
}
$uses = [regex]::Matches($install, 'Find-PimeInstallRoot\s+-RegistryPaths').Count
if ($uses -lt 2) {
    $problems += "install.ps1 must resolve the PIME root through Find-PimeInstallRoot both before and after installing the bundled PIME (found $uses call sites)"
}

# --- 1b. Stopping the helper must wait for its exit, and module replacement
#         must preserve the previous version. Stop-Process alone races the file
#         lock: the helper
#         runs on every machine now that the candidate window ships
#         enabled, and uninstall failed with "file in use" on a real
#         user's machine (2026-08-01). ---
foreach ($entry in @(
    @{ Name = "install.ps1"; Text = $install },
    @{ Name = "uninstall.ps1"; Text = $uninstall }
)) {
    if ($entry.Text -notmatch 'WaitForExit') {
        $problems += "$($entry.Name) no longer waits for SmartPriorityCandidateUI to exit after stopping it"
    }
}
if ($install -notmatch 'Install-SmartPriorityModuleTransaction') {
    $problems += "install.ps1 no longer replaces the module through the rollback-capable transaction helper"
}
if ($install -notmatch 'Enter-SmartPriorityModuleTransactionLock' -or
    $install -notmatch 'Recover-SmartPriorityModuleTransaction') {
    $problems += "install.ps1 no longer serializes module changes and recovers stale transactions"
}
if ($uninstall -notmatch '\.\s*\(Join-Path\s+\$PSScriptRoot\s+"module_transaction\.ps1"\)' -or
    $uninstall -notmatch 'Enter-SmartPriorityModuleTransactionLock' -or
    $uninstall -notmatch 'Recover-SmartPriorityModuleTransaction') {
    $problems += "uninstall.ps1 no longer shares the module transaction lock and recovery helper"
}
$uninstallLockReleaseIndex = $uninstall.LastIndexOf('Exit-SmartPriorityModuleTransactionLock')
$languageCleanupIndex = $uninstall.IndexOf('Get-WinUserLanguageList')
$profileCleanupIndex = $uninstall.IndexOf('Remove-Item -LiteralPath $profileKey')
if ($uninstallLockReleaseIndex -lt $languageCleanupIndex -or
    $uninstallLockReleaseIndex -lt $profileCleanupIndex) {
    $problems += "uninstall.ps1 must hold the shared lock through language and CTF profile cleanup"
}
$recoveryIndex = $install.IndexOf('Recover-SmartPriorityModuleTransaction')
if ($recoveryIndex -lt 0 -or $recoveryIndex -gt $install.IndexOf('Resolve-SmartPriorityNativeUiPreference')) {
    $problems += "stale module transactions must recover before native UI preflight"
}
if ($install -notmatch '(?s)Install-SmartPriorityModuleTransaction `.*?-LockAlreadyHeld') {
    $problems += "install.ps1 must hold the shared module lock across the module transaction"
}
if ($uninstall -notmatch 'Remove-DirectoryWithRetry') {
    $problems += "uninstall.ps1 no longer retries module-directory removal"
}
if ($install -match 'WaitForExit\(5000\)\s*\|\s*Out-Null') {
    $problems += "install.ps1 ignores whether the stopped process actually exited"
}

# Native UI eligibility is a precondition for update, not a post-copy check.
$preferenceIndex = $install.IndexOf('Resolve-SmartPriorityNativeUiPreference')
$eligibilityIndex = $install.IndexOf('Test-SmartPriorityNativeUiEligibility `')
$nativeGuardIndex = $install.IndexOf('The remembered custom candidate UI cannot be installed.')
$transactionIndex = $install.IndexOf('Install-SmartPriorityModuleTransaction `')
$restoreIndex = $install.IndexOf('Restore-OriginalPimeTextService -PimeRoot')
if ($preferenceIndex -lt 0 -or $eligibilityIndex -lt $preferenceIndex -or
    $nativeGuardIndex -lt $eligibilityIndex -or
    $transactionIndex -lt 0 -or $nativeGuardIndex -gt $transactionIndex) {
    $problems += "native UI preference and eligibility must be resolved before module replacement"
}
if ($restoreIndex -lt $transactionIndex) {
    $problems += "signed text-service restoration must remain after update preflight and module replacement"
}

# Exercise the transaction in an isolated temporary PIME-shaped tree. A
# failed compiler must leave the current module intact; a publish failure after
# moving the old directory must restore it.
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("smart-priority-transaction-" + [Guid]::NewGuid().ToString("N"))
$pythonRoot = Join-Path $testRoot "python"
$methodsRoot = Join-Path $pythonRoot "input_methods"
$sourceRoot = Join-Path $testRoot "source"
$failingCompiler = Join-Path $testRoot "failing-python.cmd"
$targetModule = Join-Path $methodsRoot "pinned_bopomofo"
New-Item -ItemType Directory -Path $methodsRoot, $sourceRoot -Force | Out-Null
New-Item -ItemType Directory -Path $targetModule -Force | Out-Null
Set-Content -LiteralPath (Join-Path $targetModule "version.txt") -Value "old" -Encoding UTF8
Set-Content -LiteralPath (Join-Path $sourceRoot "version.txt") -Value "new" -Encoding UTF8
Set-Content -LiteralPath $failingCompiler -Value @('@echo off', 'exit /b 1') -Encoding Ascii
. $transactionHelper

function Reset-SmartPriorityTestModule {
    param([string]$Path, [AllowNull()][object]$Value)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    if ($null -ne $Value) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $Path "version.txt") -Value ([string]$Value) -Encoding UTF8
    }
}

function New-SmartPriorityTransactionFixture {
    param(
        [string]$TestRoot,
        [string]$TransactionParent,
        [string]$TargetPath,
        [AllowNull()][object]$BackupValue = $null,
        [AllowNull()][object]$TargetValue = $null,
        [AllowNull()][object]$StageValue = $null,
        [switch]$Committed,
        [switch]$Rollback,
        [switch]$Legacy
    )
    $transactionRoot = Join-Path $TransactionParent (
        ".smartpriority-module-update-" + [Guid]::NewGuid().ToString("N")
    )
    New-Item -ItemType Directory -Path $transactionRoot -Force | Out-Null
    if (-not $Legacy) {
        Write-SmartPriorityTransactionManifest `
            -TransactionRoot $transactionRoot -PimeRoot $TestRoot -TargetPath $TargetPath
    }
    if ($null -ne $BackupValue) {
        Reset-SmartPriorityTestModule -Path (Join-Path $transactionRoot "backup\pinned_bopomofo") -Value $BackupValue
    }
    if ($null -ne $StageValue) {
        Reset-SmartPriorityTestModule -Path (Join-Path $transactionRoot "stage\pinned_bopomofo") -Value $StageValue
    }
    Reset-SmartPriorityTestModule -Path $TargetPath -Value $TargetValue
    if (-not $Legacy) {
        Write-SmartPriorityTransactionMarker -TransactionRoot $transactionRoot -Name "stage.ready"
        if ($Committed) {
            Write-SmartPriorityTransactionMarker -TransactionRoot $transactionRoot -Name "committed"
        }
        if ($Rollback) {
            Write-SmartPriorityTransactionMarker -TransactionRoot $transactionRoot -Name "rollback"
        }
    }
    return $transactionRoot
}

$crashProcess = $null
try {
    Install-SmartPriorityModuleTransaction `
        -SourceDirectory $sourceRoot `
        -TargetDirectory $targetModule `
        -TransactionParent $pythonRoot
    if ((Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "new") {
        $problems += "successful transaction did not publish the staged module"
    }

    $sourceFailed = $false
    try {
        Install-SmartPriorityModuleTransaction `
            -SourceDirectory (Join-Path $testRoot "missing-source") `
            -TargetDirectory $targetModule `
            -TransactionParent $pythonRoot
    }
    catch {
        $sourceFailed = $true
    }
    if (-not $sourceFailed -or
        (Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "new") {
        $problems += "a missing source directory changed the installed module"
    }

    $compilerFailed = $false
    try {
        Install-SmartPriorityModuleTransaction `
            -SourceDirectory $sourceRoot `
            -TargetDirectory $targetModule `
            -TransactionParent $pythonRoot `
            -PythonExecutable $failingCompiler
    }
    catch {
        $compilerFailed = $true
    }
    # The failing compiler is a native process, so its exit code stays in
    # $LASTEXITCODE after the expected failure. GitHub Actions ends every
    # PowerShell step with "exit $LASTEXITCODE", which turned this test's PASS
    # into a failed step and skipped the 0.8.2 release job. The failure was
    # the point of this check; do not let it leak out as the script's result.
    $global:LASTEXITCODE = 0
    if (-not $compilerFailed -or
        (Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "new") {
        $problems += "a staged compile failure changed the installed module"
    }

    Set-Content -LiteralPath (Join-Path $sourceRoot "version.txt") -Value "candidate" -Encoding UTF8
    $global:smartPriorityMoveCount = 0
    function global:Move-Item {
        [CmdletBinding()]
        param(
            [Parameter(Mandatory = $true)][string]$LiteralPath,
            [Parameter(Mandatory = $true)][string]$Destination,
            [switch]$Force
        )
        $global:smartPriorityMoveCount++
        if ($global:smartPriorityMoveCount -eq 2) {
            throw "Injected module publish failure"
        }
        Microsoft.PowerShell.Management\Move-Item `
            -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
    }
    $publishFailed = $false
    try {
        Install-SmartPriorityModuleTransaction `
            -SourceDirectory $sourceRoot `
            -TargetDirectory $targetModule `
            -TransactionParent $pythonRoot
    }
    catch {
        $publishFailed = $_.Exception.Message -match 'Injected module publish failure'
    }
    finally {
        Remove-Item Function:\global:Move-Item -ErrorAction SilentlyContinue
    }
    if (-not $publishFailed -or
        (Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "new") {
        $problems += "a failed publish did not restore the previous module"
    }
    if (@(Get-ChildItem -LiteralPath $pythonRoot -Directory -Filter ".smartpriority-module-update-*").Count -ne 0) {
        $problems += "completed or rolled-back transactions left staging directories behind"
    }

    $lockNameA = Get-SmartPriorityModuleTransactionMutexName -PimeRoot $testRoot
    $lockNameB = Get-SmartPriorityModuleTransactionMutexName -PimeRoot ($testRoot.ToUpperInvariant())
    $lockNameOther = Get-SmartPriorityModuleTransactionMutexName -PimeRoot ($testRoot + "-other")
    if ($lockNameA -ne $lockNameB -or $lockNameA -eq $lockNameOther) {
        $problems += "module transaction lock names are not stable per canonical PIME root"
    }
    $mutexProbeScript = Join-Path $testRoot "hold-module-lock.ps1"
    $mutexProbeSignal = Join-Path $testRoot "module-lock-held.txt"
    Set-Content -LiteralPath $mutexProbeScript -Value @(
        'param([string]$MutexName, [string]$SignalPath)',
        '$m = [System.Threading.Mutex]::new($false, $MutexName)',
        '$held = $false',
        'try { $held = $m.WaitOne(10000); if ($held) { [IO.File]::WriteAllText($SignalPath, "held"); Start-Sleep -Milliseconds 2500 } }',
        'finally { if ($held) { $m.ReleaseMutex() }; $m.Dispose() }'
    ) -Encoding Ascii
    $powershellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
    $probeArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $mutexProbeScript +
        '" -MutexName "' + $lockNameA + '" -SignalPath "' + $mutexProbeSignal + '"'
    $mutexProbe = Start-Process -FilePath $powershellExe -ArgumentList $probeArguments -PassThru -WindowStyle Hidden
    $probeReady = $false
    for ($waitAttempt = 1; $waitAttempt -le 50; $waitAttempt++) {
        if (Test-Path -LiteralPath $mutexProbeSignal) { $probeReady = $true; break }
        if ($mutexProbe.HasExited) { break }
        Start-Sleep -Milliseconds 100
    }
    $sameRootWasBlocked = $false
    if ($probeReady) {
        try {
            $unexpectedLock = Enter-SmartPriorityModuleTransactionLock -PimeRoot $testRoot -TimeoutMilliseconds 100
            Exit-SmartPriorityModuleTransactionLock -Mutex $unexpectedLock
        }
        catch { $sameRootWasBlocked = $_.Exception.Message -match 'Timed out waiting' }
    }
    $mutexProbe.WaitForExit(10000) | Out-Null
    if (-not $probeReady -or -not $sameRootWasBlocked -or $mutexProbe.ExitCode -ne 0) {
        $problems += "module transactions for the same PIME root are not serialized across processes"
    }

    # Terminate a real child process after the candidate directory has been
    # published but before the commit marker is written. Keep a mutex handle
    # open in this process so the next lock acquisition observes abandonment.
    Reset-SmartPriorityTestModule -Path $targetModule -Value "old-before-process-crash"
    $crashProbeScript = Join-Path $testRoot "crash-module-update.ps1"
    $crashProbeSignal = Join-Path $testRoot "module-published-before-commit.txt"
    $crashProbeOutput = Join-Path $testRoot "crash-module-update.out.txt"
    $crashProbeError = Join-Path $testRoot "crash-module-update.err.txt"
    Set-Content -LiteralPath $crashProbeScript -Value @(
        'param([string]$HelperPath, [string]$SourcePath, [string]$TargetPath, [string]$TransactionParent, [string]$SignalPath)',
        '$ErrorActionPreference = "Stop"',
        '. $HelperPath',
        'function global:Move-Item {',
        '  [CmdletBinding()]',
        '  param([Parameter(Mandatory=$true)][string]$LiteralPath, [Parameter(Mandatory=$true)][string]$Destination, [switch]$Force)',
        '  Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force',
        '  if ($LiteralPath -match "\\stage\\pinned_bopomofo$") { [IO.File]::WriteAllText($SignalPath, "published", [Text.Encoding]::ASCII); Start-Sleep -Seconds 30 }',
        '}',
        'Install-SmartPriorityModuleTransaction -SourceDirectory $SourcePath -TargetDirectory $TargetPath -TransactionParent $TransactionParent'
    ) -Encoding Ascii
    $crashLockProbe = [System.Threading.Mutex]::new(
        $false, (Get-SmartPriorityModuleTransactionMutexName -PimeRoot $testRoot)
    )
    $crashArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $crashProbeScript +
        '" -HelperPath "' + $transactionHelper + '" -SourcePath "' + $sourceRoot +
        '" -TargetPath "' + $targetModule + '" -TransactionParent "' + $pythonRoot +
        '" -SignalPath "' + $crashProbeSignal + '"'
    $crashProcess = Start-Process -FilePath $powershellExe -ArgumentList $crashArguments `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput $crashProbeOutput -RedirectStandardError $crashProbeError
    $crashReachedPublish = $false
    for ($waitAttempt = 1; $waitAttempt -le 100; $waitAttempt++) {
        if (Test-Path -LiteralPath $crashProbeSignal) { $crashReachedPublish = $true; break }
        if ($crashProcess.HasExited) { break }
        Start-Sleep -Milliseconds 100
    }
    try {
        if (-not $crashProcess.HasExited) {
            Stop-Process -Id $crashProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    catch {}
    $crashProcess.WaitForExit(5000) | Out-Null
    $crashRoots = @(Get-SmartPriorityModuleTransactionRoots -PimeRoot $testRoot)
    $moduleAtCrash = if (Test-Path -LiteralPath (Join-Path $targetModule "version.txt")) {
        (Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim()
    } else { "" }
    $crashTopologyValid = (
        $crashReachedPublish -and $moduleAtCrash -eq "candidate" -and
        $crashRoots.Count -eq 1 -and
        (Test-Path -LiteralPath (Join-Path $crashRoots[0].FullName "backup\pinned_bopomofo")) -and
        -not (Test-Path -LiteralPath (Join-Path $crashRoots[0].FullName "committed"))
    )
    $crashLock = $null
    try {
        $crashLock = Enter-SmartPriorityModuleTransactionLock -PimeRoot $testRoot -TimeoutMilliseconds 3000
        Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null
    }
    catch {
        $problems += "abrupt process termination could not be followed by stale transaction recovery: $($_.Exception.Message)"
    }
    finally {
        if ($null -ne $crashLock) {
            Exit-SmartPriorityModuleTransactionLock -Mutex $crashLock
        }
        $crashLockProbe.Dispose()
    }
    $moduleAfterRecovery = if (Test-Path -LiteralPath (Join-Path $targetModule "version.txt")) {
        (Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim()
    } else { "" }
    if (-not $crashReachedPublish -or
        $moduleAfterRecovery -ne "old-before-process-crash" -or
        @(Get-SmartPriorityModuleTransactionRoots -PimeRoot $testRoot).Count -ne 0) {
        $crashDetails = if (Test-Path -LiteralPath $crashProbeError) {
            (Get-Content -LiteralPath $crashProbeError -Raw).Trim()
        } else { "" }
        $problems += "a killed installer child was not recovered to the previous module (reached publish=$crashReachedPublish; $crashDetails)"
    }
    if (-not $crashTopologyValid) {
        $problems += "the killed installer child did not stop in the expected published-but-uncommitted filesystem state"
    }
    $retryFailed = $false
    try {
        Install-SmartPriorityModuleTransaction `
            -SourceDirectory $sourceRoot -TargetDirectory $targetModule -TransactionParent $pythonRoot
    }
    catch { $retryFailed = $true }
    if ($retryFailed -or
        (Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "candidate") {
        $problems += "a clean installer retry failed after abandoned-process recovery"
    }

    # A process may disappear after moving the old module but before publish.
    $recoveryRoot = New-SmartPriorityTransactionFixture `
        -TestRoot $testRoot -TransactionParent $pythonRoot -TargetPath $targetModule `
        -BackupValue "old-backup-only" -StageValue "uncommitted-stage"
    Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null
    if ((Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "old-backup-only" -or
        (Test-Path -LiteralPath $recoveryRoot)) {
        $problems += "backup-only crash recovery did not restore the previous module"
    }
    Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null

    # If publish happened but the committed marker did not, the safe outcome is
    # to restore the known-good backup and discard the candidate.
    $recoveryRoot = New-SmartPriorityTransactionFixture `
        -TestRoot $testRoot -TransactionParent $pythonRoot -TargetPath $targetModule `
        -BackupValue "old-before-commit" -TargetValue "candidate-before-commit"
    Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null
    if ((Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "old-before-commit") {
        $problems += "an uncommitted target incorrectly won over the old backup"
    }

    # A durable committed marker makes the new target authoritative even if
    # cleanup was interrupted while the backup still exists.
    $recoveryRoot = New-SmartPriorityTransactionFixture `
        -TestRoot $testRoot -TransactionParent $pythonRoot -TargetPath $targetModule `
        -BackupValue "old-after-commit" -TargetValue "committed-target" -Committed
    Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null
    if ((Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "committed-target") {
        $problems += "a committed target was rolled back during stale cleanup"
    }

    # Prior helper versions wrote no manifest. Accept their exact directory
    # shape for backup restoration, while never promoting an orphaned stage.
    $recoveryRoot = New-SmartPriorityTransactionFixture `
        -TestRoot $testRoot -TransactionParent $pythonRoot -TargetPath $targetModule `
        -BackupValue "legacy-backup" -Legacy
    Reset-SmartPriorityTestModule -Path $targetModule -Value $null
    Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null
    if ((Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "legacy-backup") {
        $problems += "a valid legacy transaction backup was not restored"
    }
    $recoveryRoot = New-SmartPriorityTransactionFixture `
        -TestRoot $testRoot -TransactionParent $pythonRoot -TargetPath $targetModule `
        -StageValue "orphaned-stage"
    Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null
    if ((Test-Path -LiteralPath $targetModule) -or (Test-Path -LiteralPath $recoveryRoot)) {
        $problems += "an orphaned stage was promoted instead of discarded"
    }

    # A mismatched manifest fails closed and leaves both target and recovery
    # evidence untouched.
    $recoveryRoot = New-SmartPriorityTransactionFixture `
        -TestRoot $testRoot -TransactionParent $pythonRoot -TargetPath $targetModule `
        -BackupValue "malformed-backup" -TargetValue "malformed-candidate"
    $badManifestPath = Join-Path $recoveryRoot "manifest.json"
    $badManifest = [IO.File]::ReadAllText($badManifestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
    $badManifest.productGuid = "00000000-0000-0000-0000-000000000000"
    [IO.File]::WriteAllText($badManifestPath, ($badManifest | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
    $malformedFailed = $false
    try { Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null }
    catch { $malformedFailed = $true }
    if (-not $malformedFailed -or -not (Test-Path -LiteralPath $recoveryRoot) -or
        -not (Test-Path -LiteralPath (Join-Path $recoveryRoot "backup\pinned_bopomofo")) -or
        (Get-Content -LiteralPath (Join-Path $targetModule "version.txt") -Raw).Trim() -ne "malformed-candidate") {
        $problems += "a malformed transaction did not fail closed with its evidence preserved"
    }
    Remove-Item -LiteralPath $recoveryRoot -Recurse -Force

    # If restoration itself fails, retain the backup path and report it.
    $recoveryRoot = New-SmartPriorityTransactionFixture `
        -TestRoot $testRoot -TransactionParent $pythonRoot -TargetPath $targetModule `
        -BackupValue "must-survive-failed-restore" -TargetValue "remove-me"
    function global:Move-Item {
        [CmdletBinding()]
        param(
            [Parameter(Mandatory = $true)][string]$LiteralPath,
            [Parameter(Mandatory = $true)][string]$Destination,
            [switch]$Force
        )
        if ($LiteralPath -match '\\backup\\pinned_bopomofo$') {
            throw "Injected recovery restore failure"
        }
        Microsoft.PowerShell.Management\Move-Item `
            -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
    }
    $restoreFailed = $false
    try { Recover-SmartPriorityModuleTransaction -PimeRoot $testRoot | Out-Null }
    catch { $restoreFailed = $_.Exception.Message -match [regex]::Escape((Join-Path $recoveryRoot "backup\pinned_bopomofo")) }
    finally { Remove-Item Function:\global:Move-Item -ErrorAction SilentlyContinue }
    if (-not $restoreFailed -or -not (Test-Path -LiteralPath (Join-Path $recoveryRoot "backup\pinned_bopomofo"))) {
        $problems += "a failed recovery move did not preserve and identify the backup"
    }
}
finally {
    if ($null -ne $crashProcess -and -not $crashProcess.HasExited) {
        Stop-Process -Id $crashProcess.Id -Force -ErrorAction SilentlyContinue
        $crashProcess.WaitForExit(5000) | Out-Null
    }
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}

# --- 2. Failures must reach the log the dialog points at ---
foreach ($entry in @(
    @{ Name = "install.ps1"; Text = $install },
    @{ Name = "uninstall.ps1"; Text = $uninstall }
)) {
    if ($entry.Text -notmatch '(?s)catch\s*\{[^}]*Write-Output[^}]*\bthrow\b') {
        $problems += "$($entry.Name) must catch, write the error into the transcript, and rethrow"
    }
}

if ($problems.Count -gt 0) {
    throw ("Installer resilience problems:`n  " + ($problems -join "`n  "))
}

Write-Output "PASS: installer preflight and transactional module replacement preserve the working version on failure"
