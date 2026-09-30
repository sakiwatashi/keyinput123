$ErrorActionPreference = "Stop"

$script:SmartPriorityModuleDirectoryName = "pinned_bopomofo"
$script:SmartPriorityProductGuid = "26EA5CF3-D515-40BE-9535-E7E98D5EE554"

function Get-SmartPriorityCanonicalPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [IO.Path]::GetFullPath($Path).TrimEnd("\")
}

function Get-SmartPriorityModuleTransactionMutexName {
    param([Parameter(Mandatory = $true)][string]$PimeRoot)
    $canonicalRoot = (Get-SmartPriorityCanonicalPath $PimeRoot).ToLowerInvariant()
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = [BitConverter]::ToString(
            $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonicalRoot))
        ).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
    return "Global\SmartPriorityBopomofo.ModuleTransaction.$hash"
}

function Enter-SmartPriorityModuleTransactionLock {
    param(
        [Parameter(Mandatory = $true)][string]$PimeRoot,
        [int]$TimeoutMilliseconds = 120000
    )
    $mutexName = Get-SmartPriorityModuleTransactionMutexName -PimeRoot $PimeRoot
    $mutex = [System.Threading.Mutex]::new($false, $mutexName)
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne($TimeoutMilliseconds)
        }
        catch [System.Threading.AbandonedMutexException] {
            # Windows grants ownership to this waiter when the previous owner
            # died. Recovery is exactly what must happen after that event.
            $acquired = $true
        }
        if (-not $acquired) {
            throw "Timed out waiting for the PIME module transaction lock '$mutexName'."
        }
        return $mutex
    }
    catch {
        if (-not $acquired) { $mutex.Dispose() }
        throw
    }
}

function Exit-SmartPriorityModuleTransactionLock {
    param([Parameter(Mandatory = $true)][System.Threading.Mutex]$Mutex)
    try { $Mutex.ReleaseMutex() }
    finally { $Mutex.Dispose() }
}

function Get-SmartPriorityModuleTransactionRoots {
    param([Parameter(Mandatory = $true)][string]$PimeRoot)
    $pythonRoot = Join-Path (Get-SmartPriorityCanonicalPath $PimeRoot) "python"
    if (-not (Test-Path -LiteralPath $pythonRoot -PathType Container)) { return @() }
    return @(
        Get-ChildItem -LiteralPath $pythonRoot -Directory -Force |
            Where-Object { $_.Name -match '^\.smartpriority-module-update-[0-9a-fA-F]{32}$' } |
            Sort-Object -Property Name
    )
}

function Assert-SmartPriorityNoReparsePoints {
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to recover a transaction containing a reparse point: $Path"
    }
    if ($item.PSIsContainer) {
        foreach ($child in @(Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction Stop)) {
            if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing to recover a transaction containing a reparse point: $($child.FullName)"
            }
        }
    }
}

function Get-SmartPriorityTransactionLayout {
    param(
        [Parameter(Mandatory = $true)][string]$TransactionRoot,
        [Parameter(Mandatory = $true)][string]$PimeRoot
    )
    $root = Get-SmartPriorityCanonicalPath $TransactionRoot
    $canonicalPimeRoot = Get-SmartPriorityCanonicalPath $PimeRoot
    $pythonRoot = Join-Path $canonicalPimeRoot "python"
    $targetPath = Get-SmartPriorityCanonicalPath (
        Join-Path $canonicalPimeRoot ("python\input_methods\" + $script:SmartPriorityModuleDirectoryName)
    )
    $expectedNamePattern = '^\.smartpriority-module-update-([0-9a-fA-F]{32})$'
    $rootItem = Get-Item -LiteralPath $root -Force -ErrorAction Stop
    if (-not $rootItem.PSIsContainer -or $rootItem.Name -notmatch $expectedNamePattern) {
        throw "Refusing to recover an unexpected transaction directory: $root"
    }
    if (-not (Get-SmartPriorityCanonicalPath $rootItem.Parent.FullName).Equals(
        (Get-SmartPriorityCanonicalPath $pythonRoot), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to recover a transaction outside the PIME Python directory: $root"
    }
    Assert-SmartPriorityNoReparsePoints -Path $root

    $allowedRootNames = @(
        "stage", "backup", "manifest.json", "manifest.pending",
        "stage.ready", "stage.ready.pending", "committed", "committed.pending",
        "rollback", "rollback.pending"
    )
    foreach ($child in @(Get-ChildItem -LiteralPath $root -Force)) {
        if ($allowedRootNames -notcontains $child.Name) {
            throw "Refusing to recover an unrecognized transaction item: $($child.FullName)"
        }
    }
    foreach ($fileName in @(
        "manifest.json", "manifest.pending", "stage.ready", "stage.ready.pending",
        "committed", "committed.pending", "rollback", "rollback.pending"
    )) {
        $filePath = Join-Path $root $fileName
        if ((Test-Path -LiteralPath $filePath) -and
            -not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            throw "Refusing to recover an invalid transaction file: $filePath"
        }
    }

    foreach ($containerName in @("stage", "backup")) {
        $containerPath = Join-Path $root $containerName
        if (-not (Test-Path -LiteralPath $containerPath)) { continue }
        $container = Get-Item -LiteralPath $containerPath -Force
        if (-not $container.PSIsContainer) {
            throw "Refusing to recover an invalid transaction container: $containerPath"
        }
        Assert-SmartPriorityNoReparsePoints -Path $containerPath
        foreach ($child in @(Get-ChildItem -LiteralPath $containerPath -Force)) {
            if ($child.Name -ne $script:SmartPriorityModuleDirectoryName -or -not $child.PSIsContainer) {
                throw "Refusing to recover an unexpected module entry: $($child.FullName)"
            }
        }
    }

    $manifestPath = Join-Path $root "manifest.json"
    $pendingManifest = Test-Path -LiteralPath (Join-Path $root "manifest.pending") -PathType Leaf
    $manifestPresent = Test-Path -LiteralPath $manifestPath -PathType Leaf
    $legacy = -not $manifestPresent
    if ($manifestPresent) {
        $manifest = [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
        if ([int]$manifest.schemaVersion -ne 1 -or
            $manifest.product -ne "SmartPriorityBopomofo" -or
            $manifest.productGuid -ne $script:SmartPriorityProductGuid -or
            $manifest.moduleDirectory -ne $script:SmartPriorityModuleDirectoryName -or
            $manifest.transactionId -ne $rootItem.Name.Substring(".smartpriority-module-update-".Length) -or
            -not ([string]$manifest.pimeRoot).Equals($canonicalPimeRoot, [StringComparison]::OrdinalIgnoreCase) -or
            -not ([string]$manifest.targetPath).Equals($targetPath, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to recover a transaction with a mismatched manifest: $root"
        }
        if ($pendingManifest) {
            throw "Refusing to recover a transaction that has both committed and pending manifests: $root"
        }
    }
    elseif ($pendingManifest) {
        # The pending file is atomically renamed to manifest.json before any
        # stage or backup is created. It is safe to discard only this untouched
        # pre-transaction state.
        if ((Test-Path -LiteralPath (Join-Path $root "stage")) -or
            (Test-Path -LiteralPath (Join-Path $root "backup")) -or
            (Test-Path -LiteralPath (Join-Path $root "stage.ready")) -or
            (Test-Path -LiteralPath (Join-Path $root "committed")) -or
            (Test-Path -LiteralPath (Join-Path $root "rollback"))) {
            throw "Refusing to recover a transaction with a pending manifest and mutated state: $root"
        }
    }
    elseif ((Test-Path -LiteralPath (Join-Path $root "stage.ready.pending")) -or
        (Test-Path -LiteralPath (Join-Path $root "committed.pending")) -or
        (Test-Path -LiteralPath (Join-Path $root "rollback.pending")) -or
        (Test-Path -LiteralPath (Join-Path $root "stage.ready")) -or
        (Test-Path -LiteralPath (Join-Path $root "committed")) -or
        (Test-Path -LiteralPath (Join-Path $root "rollback"))) {
        throw "Refusing to recover marker state without a transaction manifest: $root"
    }

    $backupModule = Join-Path $root ("backup\" + $script:SmartPriorityModuleDirectoryName)
    $stageModule = Join-Path $root ("stage\" + $script:SmartPriorityModuleDirectoryName)
    return [pscustomobject]@{
        Root = $root
        Target = $targetPath
        Backup = $backupModule
        Stage = $stageModule
        HasBackup = (Test-Path -LiteralPath $backupModule -PathType Container)
        HasStage = (Test-Path -LiteralPath $stageModule -PathType Container)
        HasCommit = (Test-Path -LiteralPath (Join-Path $root "committed") -PathType Leaf)
        HasRollback = (Test-Path -LiteralPath (Join-Path $root "rollback") -PathType Leaf)
        Legacy = $legacy
    }
}

function Write-SmartPriorityTransactionManifest {
    param(
        [Parameter(Mandatory = $true)][string]$TransactionRoot,
        [Parameter(Mandatory = $true)][string]$PimeRoot,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )
    $transactionId = (Split-Path -Leaf $TransactionRoot).Substring(".smartpriority-module-update-".Length)
    $manifest = [ordered]@{
        schemaVersion = 1
        product = "SmartPriorityBopomofo"
        productGuid = $script:SmartPriorityProductGuid
        moduleDirectory = $script:SmartPriorityModuleDirectoryName
        transactionId = $transactionId
        pimeRoot = Get-SmartPriorityCanonicalPath $PimeRoot
        targetPath = Get-SmartPriorityCanonicalPath $TargetPath
    }
    $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(($manifest | ConvertTo-Json -Compress))
    $pendingPath = Join-Path $TransactionRoot "manifest.pending"
    $stream = [IO.File]::Open($pendingPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
    [IO.File]::Move($pendingPath, (Join-Path $TransactionRoot "manifest.json"))
}

function Write-SmartPriorityTransactionMarker {
    param(
        [Parameter(Mandatory = $true)][string]$TransactionRoot,
        [Parameter(Mandatory = $true)][ValidateSet("stage.ready", "committed", "rollback")][string]$Name
    )
    $markerPath = Join-Path $TransactionRoot $Name
    if (Test-Path -LiteralPath $markerPath) { return }
    $bytes = [Text.Encoding]::ASCII.GetBytes($Name)
    $pendingPath = Join-Path $TransactionRoot ($Name + ".pending")
    $stream = [IO.File]::Open($pendingPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
    [IO.File]::Move($pendingPath, $markerPath)
}

function Recover-SmartPriorityModuleTransaction {
    param([Parameter(Mandatory = $true)][string]$PimeRoot)
    $roots = @(Get-SmartPriorityModuleTransactionRoots -PimeRoot $PimeRoot)
    if ($roots.Count -gt 1) {
        throw "Multiple stale Smart Priority module transactions were found under '$PimeRoot'; preserved them for inspection."
    }
    foreach ($rootItem in $roots) {
        $layout = Get-SmartPriorityTransactionLayout -TransactionRoot $rootItem.FullName -PimeRoot $PimeRoot
        $targetExists = Test-Path -LiteralPath $layout.Target
        if ($targetExists) {
            $targetItem = Get-Item -LiteralPath $layout.Target -Force
            if (-not $targetItem.PSIsContainer) {
                throw "Refusing to replace an unexpected non-directory module target: $($layout.Target)"
            }
            Assert-SmartPriorityNoReparsePoints -Path $layout.Target
        }

        if ($layout.HasBackup -and -not ($layout.HasCommit -and $targetExists)) {
            # A backup without a durable commit marker wins, even if a staged
            # target exists. This safely rolls back termination between the
            # publish rename and the commit marker.
            if ($targetExists) {
                Remove-Item -LiteralPath $layout.Target -Recurse -Force -ErrorAction Stop
            }
            try {
                Move-Item -LiteralPath $layout.Backup -Destination $layout.Target -Force -ErrorAction Stop
            }
            catch {
                $restoreCompletedDespiteProviderError = (
                    -not (Test-Path -LiteralPath $layout.Backup) -and
                    (Test-Path -LiteralPath $layout.Target -PathType Container)
                )
                if (-not $restoreCompletedDespiteProviderError) {
                    throw "Could not restore the previous module. Recovery copy preserved at '$($layout.Backup)': $($_.Exception.Message)"
                }
            }
            Write-Output "Restored the previous Smart Priority module from '$($layout.Backup)'."
        }
        elseif (-not $targetExists -and -not $layout.HasBackup) {
            # Never promote an abandoned stage. A clean install can be rerun.
            Write-Output "Discarding an uncommitted Smart Priority staging directory '$($layout.Root)'."
        }

        try {
            Remove-Item -LiteralPath $layout.Root -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Could not remove the recovered transaction directory '$($layout.Root)': $($_.Exception.Message)"
        }
    }
}

function Install-SmartPriorityModuleTransaction {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceDirectory,
        [Parameter(Mandatory = $true)]
        [string]$TargetDirectory,
        [Parameter(Mandatory = $true)]
        [string]$TransactionParent,
        [string]$PythonExecutable,
        [switch]$LockAlreadyHeld
    )

    if (-not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
        throw "The staged input-method source directory does not exist: $SourceDirectory"
    }
    if (-not (Test-Path -LiteralPath $TransactionParent -PathType Container)) {
        throw "The module transaction parent directory does not exist: $TransactionParent"
    }

    $sourcePath = Get-SmartPriorityCanonicalPath $SourceDirectory
    $targetPath = Get-SmartPriorityCanonicalPath $TargetDirectory
    $transactionParentPath = Get-SmartPriorityCanonicalPath $TransactionParent
    $targetParentPath = Get-SmartPriorityCanonicalPath (Split-Path -Parent $targetPath)
    $pimeRoot = Get-SmartPriorityCanonicalPath (Split-Path -Parent $transactionParentPath)
    $expectedPythonRoot = Get-SmartPriorityCanonicalPath (Join-Path $pimeRoot "python")
    $expectedTarget = Get-SmartPriorityCanonicalPath (
        Join-Path $pimeRoot ("python\input_methods\" + $script:SmartPriorityModuleDirectoryName)
    )
    if (-not $transactionParentPath.Equals($expectedPythonRoot, [StringComparison]::OrdinalIgnoreCase) -or
        -not $targetPath.Equals($expectedTarget, [StringComparison]::OrdinalIgnoreCase)) {
        throw "The module transaction paths do not match the expected PIME module layout."
    }
    if ($transactionParentPath.Equals($targetParentPath, [StringComparison]::OrdinalIgnoreCase) -or
        $transactionParentPath.StartsWith($targetParentPath + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "The transaction directory must be outside PIME's input_methods directory."
    }
    if (-not ([IO.Path]::GetPathRoot($transactionParentPath)).Equals(
        [IO.Path]::GetPathRoot($targetParentPath), [StringComparison]::OrdinalIgnoreCase)) {
        throw "The transaction directory and input-method directory must use the same drive."
    }

    $mutex = $null
    if (-not $LockAlreadyHeld) {
        $mutex = Enter-SmartPriorityModuleTransactionLock -PimeRoot $pimeRoot
    }
    try {
        Recover-SmartPriorityModuleTransaction -PimeRoot $pimeRoot | Out-Null
        New-Item -ItemType Directory -Path $targetParentPath -Force | Out-Null

        $transactionRoot = Join-Path $transactionParentPath (".smartpriority-module-update-" + [Guid]::NewGuid().ToString("N"))
        $stagedModule = Join-Path $transactionRoot ("stage\" + $script:SmartPriorityModuleDirectoryName)
        $backupModule = Join-Path $transactionRoot ("backup\" + $script:SmartPriorityModuleDirectoryName)
        $targetWasPresent = Test-Path -LiteralPath $targetPath
        $backupMoved = $false
        $preserveTransaction = $false

        try {
            New-Item -ItemType Directory -Path $transactionRoot -Force | Out-Null
            Write-SmartPriorityTransactionManifest `
                -TransactionRoot $transactionRoot -PimeRoot $pimeRoot -TargetPath $targetPath
            New-Item -ItemType Directory -Path $stagedModule -Force | Out-Null
            Get-ChildItem -LiteralPath $sourcePath -Force |
                Copy-Item -Destination $stagedModule -Recurse -Force

            if ($PythonExecutable) {
                if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
                    throw "The embedded Python compiler was not found: $PythonExecutable"
                }
                & $PythonExecutable -m compileall -q $stagedModule
                if ($LASTEXITCODE -ne 0) {
                    throw "The staged module compile check failed with exit code $LASTEXITCODE."
                }
            }
            Write-SmartPriorityTransactionMarker -TransactionRoot $transactionRoot -Name "stage.ready"

            try {
                if ($targetWasPresent) {
                    New-Item -ItemType Directory -Path (Split-Path -Parent $backupModule) -Force | Out-Null
                    $movedToBackup = $false
                    for ($attempt = 1; $attempt -le 10; $attempt++) {
                        try {
                            Move-Item -LiteralPath $targetPath -Destination $backupModule -Force
                            $movedToBackup = $true
                            break
                        }
                        catch {
                            if ($attempt -eq 10) { throw }
                            Start-Sleep -Milliseconds 500
                        }
                    }
                    if (-not $movedToBackup) {
                        throw "Could not move the installed input method into the transaction backup."
                    }
                    $backupMoved = $true
                }
                Move-Item -LiteralPath $stagedModule -Destination $targetPath -Force
                Write-SmartPriorityTransactionMarker -TransactionRoot $transactionRoot -Name "committed"
            }
            catch {
                $replacementFailure = $_
                if (-not $backupMoved -and $targetWasPresent -and
                    (Test-Path -LiteralPath $backupModule -PathType Container) -and
                    -not (Test-Path -LiteralPath $targetPath)) {
                    # A provider can report an error after a same-volume rename
                    # actually completed. Inspect the topology before deciding
                    # whether the previous module is safe to clean up.
                    $backupMoved = $true
                }
                if ($backupMoved) {
                    try {
                        Write-SmartPriorityTransactionMarker -TransactionRoot $transactionRoot -Name "rollback"
                        if (Test-Path -LiteralPath $targetPath) {
                            Remove-Item -LiteralPath $targetPath -Recurse -Force
                        }
                        Move-Item -LiteralPath $backupModule -Destination $targetPath -Force
                        $backupMoved = $false
                    }
                    catch {
                        if ((Test-Path -LiteralPath $targetPath -PathType Container) -and
                            -not (Test-Path -LiteralPath $backupModule)) {
                            $backupMoved = $false
                        }
                        else {
                            $preserveTransaction = $true
                            throw "Module replacement failed: $($replacementFailure.Exception.Message) Previous module restoration also failed: $($_.Exception.Message). Recovery copy preserved at '$backupModule'."
                        }
                    }
                }
                elseif (-not $targetWasPresent -and (Test-Path -LiteralPath $targetPath)) {
                    Remove-Item -LiteralPath $targetPath -Recurse -Force
                }
                throw $replacementFailure
            }
        }
        finally {
            if (-not $preserveTransaction -and (Test-Path -LiteralPath $transactionRoot)) {
                try {
                    Remove-Item -LiteralPath $transactionRoot -Recurse -Force
                }
                catch {
                    Write-Warning "Could not remove the completed module transaction directory '$transactionRoot': $($_.Exception.Message)"
                }
            }
        }
    }
    finally {
        if ($null -ne $mutex) {
            Exit-SmartPriorityModuleTransactionLock -Mutex $mutex
        }
    }
}
