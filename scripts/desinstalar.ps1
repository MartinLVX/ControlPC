# Quita el arranque automatico y la regla del firewall de ControlPC.
# Ejecutar en PowerShell como administrador:
#   powershell -ExecutionPolicy Bypass -File scripts\desinstalar.ps1

$nombreTarea = "ControlPC"
Stop-ScheduledTask -TaskName $nombreTarea -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $nombreTarea -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName $nombreTarea -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*servidor.py*" } | Stop-Process -Force
Write-Host "ControlPC desinstalado. Tus archivos y config.json no se borraron."
