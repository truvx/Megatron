$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$RepoUrl = 'https://github.com/truvx/Megatron.git'
$ArchiveUrl = 'https://github.com/truvx/Megatron/archive/refs/heads/main.zip'
$LocalDir = $PSScriptRoot
$Work = Join-Path ([System.IO.Path]::GetTempPath()) ('megatron-bootstrap-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work | Out-Null

function Say([string]$Text) { Write-Host $Text }
function Test-Python([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    & $Path -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) and sys.version_info < (3, 15) else 1)' *> $null
    return ($LASTEXITCODE -eq 0)
}

try {
    $Python = $null
    foreach ($Name in @('python.exe', 'python3.exe', 'python', 'python3')) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($Command -and (Test-Python $Command.Source)) { $Python = $Command.Source; break }
    }
    if (-not $Python) {
        $PyLauncher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
        if ($PyLauncher) {
            & $PyLauncher.Source -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) and sys.version_info < (3, 15) else 1)' *> $null
            if ($LASTEXITCODE -eq 0) {
                $Python = (& $PyLauncher.Source -3 -c 'import sys; print(sys.executable)' | Select-Object -First 1).Trim()
            }
        }
    }

    if (-not $Python) {
        Say 'A compatible Python 3.10–3.14 is not available. Megatron will install Python 3.12 using uv.'
        $UvCommand = Get-Command 'uv.exe' -ErrorAction SilentlyContinue
        $Uv = if ($UvCommand) { $UvCommand.Source } else { $null }
        if (-not $Uv) {
            $UvInstaller = Join-Path $Work 'install-uv.ps1'
            Invoke-WebRequest -Uri 'https://astral.sh/uv/install.ps1' -OutFile $UvInstaller
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $UvInstaller
            foreach ($Candidate in @((Join-Path $HOME '.local\bin\uv.exe'), (Join-Path $HOME '.cargo\bin\uv.exe'))) {
                if (Test-Path -LiteralPath $Candidate -PathType Leaf) { $Uv = $Candidate; break }
            }
            if (-not $Uv) {
                $UvCommand = Get-Command 'uv.exe' -ErrorAction SilentlyContinue
                if ($UvCommand) { $Uv = $UvCommand.Source }
            }
        }
        if (-not $Uv) { throw 'Could not install/find uv. Check the terminal output, then rerun Start-Megatron.cmd.' }
        & $Uv python install 3.12
        if ($LASTEXITCODE -ne 0) { throw 'uv could not install Python 3.12.' }
        $Python = (& $Uv python find 3.12 | Select-Object -First 1).Trim()
        if (-not (Test-Python $Python)) { throw 'uv did not return a usable Python 3.12 interpreter.' }
    }

    Say "Using Python: $Python"
    Say "Downloading the latest Megatron files from $RepoUrl ..."
    $RepoDir = Join-Path $Work 'repo'
    $Git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
    if (-not $Git) { $Git = Get-Command 'git' -ErrorAction SilentlyContinue }
    if ($Git) {
        & $Git.Source clone --depth 1 --branch main $RepoUrl $RepoDir
        if ($LASTEXITCODE -ne 0) {
            if (Test-Path -LiteralPath $RepoDir) { Remove-Item -LiteralPath $RepoDir -Recurse -Force }
        }
    }

    $RequiredFiles = @('install.py', 'requirements.txt', 'config\litellm.yaml')
    $RepoValid = $true
    foreach ($Required in $RequiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $RepoDir $Required) -PathType Leaf)) { $RepoValid = $false }
    }
    if (-not $RepoValid) {
        if (Test-Path -LiteralPath $RepoDir) { Remove-Item -LiteralPath $RepoDir -Recurse -Force -ErrorAction SilentlyContinue }
        $ZipFile = Join-Path $Work 'repo.zip'
        try {
            Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ZipFile
            Expand-Archive -LiteralPath $ZipFile -DestinationPath $Work -Force
            $RepoDir = Join-Path $Work 'Megatron-main'
        } catch {
            Say 'Git clone/archive download failed; checking whether this downloaded package has the installer files.'
        }
        $RepoValid = $true
        foreach ($Required in $RequiredFiles) {
            if (-not (Test-Path -LiteralPath (Join-Path $RepoDir $Required) -PathType Leaf)) { $RepoValid = $false }
        }
    }
    if (-not $RepoValid) {
        $LocalValid = $true
        foreach ($Required in $RequiredFiles) {
            if (-not (Test-Path -LiteralPath (Join-Path $LocalDir $Required) -PathType Leaf)) { $LocalValid = $false }
        }
        if ($LocalValid) {
            $RepoDir = $LocalDir
            Say 'Note: GitHub did not return the new installer files yet; using this downloaded package.'
        } else {
            throw 'GitHub and this local package are missing required installer files. Check https://github.com/truvx/Megatron and retry.'
        }
    }

    Say 'Launching Megatron installer. Software setup and configuration will run in this terminal.'
    & $Python (Join-Path $RepoDir 'install.py')
    $InstallExit = $LASTEXITCODE
    if ($InstallExit -ne 0) { throw "Megatron installer failed with exit code $InstallExit." }
} catch {
    Write-Host "`nMEGATRON SETUP ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue }
}
