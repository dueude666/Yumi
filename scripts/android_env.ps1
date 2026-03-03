param()

$ErrorActionPreference = "Stop"

$jdkHome = Join-Path $env:USERPROFILE "scoop\apps\temurin17-jdk\current"
$sdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$cmdlineBin = Join-Path $sdkRoot "cmdline-tools\latest\bin"
$platformTools = Join-Path $sdkRoot "platform-tools"
$scoopShims = Join-Path $env:USERPROFILE "scoop\shims"

if (-not (Test-Path (Join-Path $jdkHome "bin\java.exe"))) {
    throw "JDK 17 not found at: $jdkHome"
}
if (-not (Test-Path $sdkRoot)) {
    throw "Android SDK not found at: $sdkRoot"
}

$env:JAVA_HOME = $jdkHome
$env:ANDROID_SDK_ROOT = $sdkRoot

$prepend = @(
    (Join-Path $jdkHome "bin"),
    $cmdlineBin,
    $platformTools,
    $scoopShims
)

$current = @()
if ($env:Path) {
    $current = $env:Path.Split(";")
}
# Build path by prepending required entries without duplicates.
$newPath = @()
foreach ($item in $prepend) {
    if ($item -and ($current -notcontains $item) -and ($newPath -notcontains $item)) {
        $newPath += $item
    }
}
$env:Path = (($newPath + $current) -join ";")

Write-Host "JAVA_HOME=$env:JAVA_HOME"
Write-Host "ANDROID_SDK_ROOT=$env:ANDROID_SDK_ROOT"
Write-Host "java: $(where.exe java | Select-Object -First 1)"
if (Test-Path (Join-Path $cmdlineBin "sdkmanager.bat")) {
    Write-Host "sdkmanager: $(Join-Path $cmdlineBin 'sdkmanager.bat')"
}
if (Test-Path (Join-Path $platformTools "adb.exe")) {
    Write-Host "adb: $(Join-Path $platformTools 'adb.exe')"
}
Write-Host "Android environment is ready for this terminal session."
