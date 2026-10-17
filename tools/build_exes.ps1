# Build the standalone ace-mixer.exe.
#
#   powershell -ExecutionPolicy Bypass -File tools/build_exes.ps1
#
# Output: dist\ace-mixer.exe

param(
    [string]$Python = "python",
    [string]$OutDir = "dist"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$venv = Join-Path $env:TEMP "ace-mixer-build"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $Python -m venv $venv
}
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --quiet --upgrade pip
& $vpy -m pip install --quiet "numpy>=1.24" "PyYAML>=6.0" pyinstaller

$common = @(
    "--onefile", "--noconfirm", "--clean",
    "--name", "ace-mixer",
    "--distpath", $OutDir,
    "--workpath", (Join-Path $env:TEMP "ace-mixer-pyi"),
    "--specpath", (Join-Path $env:TEMP "ace-mixer-pyi"),
    # Absolute source path: --specpath moves the base directory for relatives.
    "--add-data", ((Join-Path $root "ace_mixer\chain.py") + ";ace_mixer"),
    # The entry script lives in tools\, so the package root must be explicit.
    "--paths", $root,
    # numpy pulls pkg_resources -> plistlib -> pyexpat, whose DLL is not
    # collected; excluding the chain keeps the exe startable.
    "--exclude-module", "pkg_resources",
    "--exclude-module", "setuptools",
    "--exclude-module", "distutils",
    "--exclude-module", "plistlib",
    "--exclude-module", "xml"
)

& $vpy -m PyInstaller @common (Join-Path $root "tools\entry.py")

Get-ChildItem $OutDir -Filter "ace-mixer*" | Select-Object Name, Length | Format-Table -AutoSize
