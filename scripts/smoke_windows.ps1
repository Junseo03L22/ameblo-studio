# Exercise installation, shortcuts, GUI launch and removal in a disposable CI account.
$ErrorActionPreference = "Stop"
$setup = (Get-ChildItem dist\installer\*.exe | Select-Object -First 1).FullName
$installed = Join-Path $env:LOCALAPPDATA 'Programs\AmebloStudio'
$p = Start-Process $setup -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=desktopicon' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Setup failed: $($p.ExitCode)" }
$exe = Join-Path $installed 'AmebloStudio.exe'
try {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
        $link = Join-Path $folder 'Ameblo Studio.lnk'
        if (!(Test-Path $link)) { throw "Missing shortcut: $link" }
        if ($shell.CreateShortcut($link).TargetPath -ne $exe) { throw "Wrong shortcut target" }
    }
    $env:AMEBLO_STUDIO_HOME = Join-Path $env:RUNNER_TEMP 'ameblo-smoke-data'
    $app = Start-Process $exe -PassThru
    try {
        Start-Sleep -Seconds 12
        $app.Refresh()
        if ($app.HasExited) { throw "Packaged app exited early" }
        if ($app.MainWindowHandle -eq 0) { throw "App did not create a desktop window" }
    } finally {
        if (!$app.HasExited) { Stop-Process -Id $app.Id -Force }
    }
} finally {
    $p = Start-Process (Join-Path $installed 'unins000.exe') -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Uninstall failed" }
}
Write-Host 'Installer, desktop/start menu shortcuts, GUI startup and uninstall passed.'
