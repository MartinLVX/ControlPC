# Instala ControlPC para que arranque solo al iniciar sesion en Windows.
# Ejecutar en PowerShell como administrador:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$carpetaServidor = Join-Path $raiz "servidor"
$nombreTarea = "ControlPC"

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "Abre PowerShell como administrador y vuelve a ejecutar este script." -ForegroundColor Red
    exit 1
}

# 1. Buscar pythonw.exe (Python sin ventana).
$pythonw = $null
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    $pythonw = & py -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($cmd) { $pythonw = $cmd.Source }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    Write-Host "No encontre Python. Instalalo desde https://www.python.org/downloads/ (marca 'Add python.exe to PATH')." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $pythonw"

# 2. Crear config.json (con PIN aleatorio) si no existe, y leer el puerto.
$config = Join-Path $carpetaServidor "config.json"
if (-not (Test-Path $config)) {
    & ($pythonw -replace 'pythonw\.exe$', 'python.exe') -c "import sys; sys.path.insert(0, r'$carpetaServidor'); import servidor; servidor.cargar_config()"
}
$datos = Get-Content $config -Raw -Encoding UTF8 | ConvertFrom-Json
$puerto = if ($datos.puerto) { [int]$datos.puerto } else { 8765 }

# 3. Permitir el puerto en el firewall, solo para equipos de la red local.
Get-NetFirewallRule -DisplayName $nombreTarea -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $nombreTarea -Direction Inbound -Protocol TCP -LocalPort $puerto `
    -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
Write-Host "Firewall: puerto $puerto abierto para la red local."

# 4. Tarea programada: arranca al iniciar sesion, con tu usuario (necesario para bloquear la sesion).
$accion = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$carpetaServidor\servidor.py`"" -WorkingDirectory $carpetaServidor
$disparador = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $nombreTarea -Action $accion -Trigger $disparador -Settings $ajustes `
    -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $nombreTarea
Write-Host "Tarea '$nombreTarea' creada e iniciada."

# 5. Mostrar como conectarse.
$ip = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } |
    Select-Object -First 1).IPv4Address.IPAddress
Write-Host ""
Write-Host "Listo. En el iPhone abre Safari en:  http://${ip}:$puerto" -ForegroundColor Green
Write-Host "PIN: $($datos.pin)   (puedes cambiarlo en $config y reiniciar la PC)" -ForegroundColor Green
