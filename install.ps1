$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Candidates = @()
$Candidates += Get-ChildItem "C:\Python*\python.exe","$env:LocalAppData\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
$Candidates += @("python", "py")
$Python = $null
foreach ($Candidate in $Candidates) {
    if ($Candidate -eq "py") {
        & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    } else {
        if ($Candidate -ne "python" -and -not (Test-Path $Candidate)) { continue }
        & $Candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    }
    if ($LASTEXITCODE -eq 0) {
        if ($Candidate -eq "py") {
            $Python = (& py -3 -c "import sys; print(sys.executable)").Trim()
        } elseif ($Candidate -eq "python") {
            $Python = (Get-Command python).Source
        } else {
            $Python = $Candidate
        }
        break
    }
}
if (-not $Python) {
    throw "Python 3.11 or newer was not found."
}

Write-Host "Using $Python"
Write-Host "Installing Python dependencies..."
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

Write-Host "Detecting SPSS..."
& $Python -m spss_agent detect
if ($LASTEXITCODE -ne 0) {
    throw "SPSS was not detected. Install IBM SPSS Statistics or set SPSS_STATS_EXE, then run this script again."
}

$Skill = Join-Path $Root ".cursor/skills/spss-empirical"
New-Item -ItemType Directory -Force -Path $Skill | Out-Null
$RootFile = Join-Path $Skill "package_root.txt"
[System.IO.File]::WriteAllText($RootFile, $Root.Trim())
$PythonFile = Join-Path $Skill "python_exe.txt"
[System.IO.File]::WriteAllText($PythonFile, $Python.Trim())

$StoreRoot = Join-Path $env:LOCALAPPDATA "Cursor/AgentStores/cursor_agent_stores"
$Copied = 0
if (Test-Path $StoreRoot) {
    Get-ChildItem $StoreRoot -Directory | ForEach-Object {
        $Files = Join-Path $_.FullName "files"
        if (-not (Test-Path $Files)) { return }
        $Dest = Join-Path $Files "skills/spss-empirical"
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        Copy-Item (Join-Path $Skill "SKILL.md") $Dest -Force
        Copy-Item (Join-Path $Skill "reference.md") $Dest -Force
        Copy-Item $RootFile $Dest -Force
        Copy-Item $PythonFile $Dest -Force
        $script:Copied += 1
        Write-Host "Installed skill: $Dest"
    }
}

if ($Copied -eq 0) {
    Write-Host "No Cursor user skill directory found. Project skill remains at $Skill"
}

Write-Host "Done. Close SPSS before running an analysis."
