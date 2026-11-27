# Ayudante de "Sistema" de ControlPC. Queda abierto y responde una línea JSON por orden.
#
# Órdenes:
#   specs   componentes de la PC (procesador, gráfica, memoria, discos, placa, Windows)
#   gpu     uso actual de la gráfica (%) y memoria de video usada
#
# Se usan clases CIM/WMI, que tienen el mismo nombre en Windows en español o en inglés
# (los nombres de los contadores de rendimiento clásicos cambian según el idioma).

$ErrorActionPreference = "Stop"
try { [Console]::InputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Responder($objeto) {
    [Console]::Out.WriteLine(($objeto | ConvertTo-Json -Compress -Depth 5))
    [Console]::Out.Flush()
}

function Texto($valor) {
    if ($null -eq $valor) { return $null }
    $t = "$valor".Trim()
    if ($t) { return $t } else { return $null }
}

function Memoria-Grafica($nombre) {
    # AdapterRAM de WMI se corta en 4 GB; el registro guarda el valor real (qwMemorySize).
    try {
        $clave = "HKLM:\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        foreach ($sub in Get-ChildItem $clave -ErrorAction SilentlyContinue) {
            $p = Get-ItemProperty $sub.PSPath -ErrorAction SilentlyContinue
            if ($p.DriverDesc -eq $nombre -and $p."HardwareInformation.qwMemorySize") {
                return [int64]$p."HardwareInformation.qwMemorySize"
            }
        }
    } catch { }
    return $null
}

function Specs {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $so = Get-CimInstance Win32_OperatingSystem
    $placa = Get-CimInstance Win32_BaseBoard
    $equipo = Get-CimInstance Win32_ComputerSystem

    $graficas = @(Get-CimInstance Win32_VideoController | Where-Object { $_.Name -notlike "*Basic Display*" } | ForEach-Object {
        $memoria = Memoria-Grafica $_.Name
        if (-not $memoria -and $_.AdapterRAM -gt 0) { $memoria = [int64]$_.AdapterRAM }
        @{ nombre = Texto $_.Name; memoria = $memoria; driver = Texto $_.DriverVersion }
    })

    $modulos = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
        @{ capacidad = [int64]$_.Capacity; velocidad = $_.ConfiguredClockSpeed; fabricante = Texto $_.Manufacturer }
    })

    $discos = @(Get-CimInstance Win32_DiskDrive | ForEach-Object {
        @{ modelo = Texto $_.Model; tamano = [int64]$_.Size; interfaz = Texto $_.InterfaceType }
    })
    # Tipo de disco (SSD/HDD) cuando Windows lo sabe.
    try {
        $fisicos = @(Get-PhysicalDisk | ForEach-Object { @{ modelo = Texto $_.FriendlyName; tipo = "$($_.MediaType)"; bus = "$($_.BusType)" } })
    } catch { $fisicos = @() }

    return @{
        equipo     = Texto $env:COMPUTERNAME
        fabricante = Texto $equipo.Manufacturer
        modelo     = Texto $equipo.Model
        procesador = @{
            nombre  = Texto $cpu.Name
            nucleos = $cpu.NumberOfCores
            hilos   = $cpu.NumberOfLogicalProcessors
            mhz     = $cpu.MaxClockSpeed
        }
        graficas   = $graficas
        memoria    = @{ total = [int64]$equipo.TotalPhysicalMemory; modulos = $modulos }
        discos     = $discos
        discos_tipo = $fisicos
        placa      = @{ fabricante = Texto $placa.Manufacturer; modelo = Texto $placa.Product }
        windows    = @{ nombre = Texto $so.Caption; version = Texto $so.Version; compilacion = Texto $so.BuildNumber }
    }
}

function Gpu {
    $uso = $null
    $memoria = $null
    try {
        # Igual que el Administrador de tareas: el motor 3D más ocupado de cada proceso, sumado.
        $motores = Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine |
            Where-Object { $_.Name -like "*engtype_3D*" }
        $suma = ($motores | Measure-Object -Property UtilizationPercentage -Sum).Sum
        if ($null -ne $suma) { $uso = [math]::Min(100, [int]$suma) }
    } catch { }
    try {
        $adaptadores = Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory
        $memoria = [int64](($adaptadores | Measure-Object -Property DedicatedUsage -Maximum).Maximum)
    } catch { }
    return @{ uso = $uso; memoria_usada = $memoria }
}

Responder @{ listo = $true }

while ($null -ne ($linea = [Console]::In.ReadLine())) {
    try {
        switch ($linea.Trim()) {
            "specs" { Responder (Specs) }
            "gpu"   { Responder (Gpu) }
            default { Responder @{ error = "Orden desconocida" } }
        }
    } catch {
        [Console]::Error.WriteLine("Sistema: $($_.Exception.Message)")
        Responder @{ error = $_.Exception.Message }
    }
}
