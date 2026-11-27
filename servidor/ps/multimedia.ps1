# Ayudante de multimedia de ControlPC.
#
# Queda abierto y recibe una orden por línea (stdin); responde una línea JSON (stdout).
# Así no hay que arrancar PowerShell en cada consulta y los botones responden al instante.
#
# Órdenes:
#   estado <ruta_portada>   lo que suena (y guarda la carátula en esa ruta si cambió)
#   play_pausa | siguiente | anterior
#
# Usa los controles de medios de Windows (Windows 10 u 11). Con -App se elige qué
# aplicación controlar (por ejemplo "Spotify"); sin -App se usa la sesión actual de Windows.
param([string]$App = "")

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGenerico = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Esperar($operacion, [Type]$tipo) {
    $tarea = $asTaskGenerico.MakeGenericMethod($tipo).Invoke($null, @($operacion))
    $tarea.Wait(5000) | Out-Null
    $tarea.Result
}

$tipoGestor = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
$tipoPropiedades = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType = WindowsRuntime]
$tipoFlujo = [Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType = WindowsRuntime]
$tipoEntrada = [Windows.Storage.Streams.IInputStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
# PowerShell recibe el flujo como __ComObject y no sabe elegir la sobrecarga de AsStreamForRead,
# así que se llama por reflexión indicando el tipo exacto.
$comoFlujoNet = [System.IO.WindowsRuntimeStreamExtensions].GetMethod('AsStreamForRead', [Type[]]@($tipoEntrada))
$gestor = Esperar ($tipoGestor::RequestAsync()) $tipoGestor

$ultimaPista = $null

function Buscar-Sesion {
    if ($App) {
        foreach ($s in $gestor.GetSessions()) {
            if ($s.SourceAppUserModelId -like "*$App*") { return $s }
        }
        return $null
    }
    return $gestor.GetCurrentSession()
}

function Responder($objeto) {
    [Console]::Out.WriteLine(($objeto | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
}

function Estado([string]$rutaPortada) {
    $sesion = Buscar-Sesion
    if (-not $sesion) {
        $script:ultimaPista = $null
        return @{ activo = $false; abierta = $false }
    }
    $propiedades = Esperar ($sesion.TryGetMediaPropertiesAsync()) $tipoPropiedades
    $reproduccion = $sesion.GetPlaybackInfo()
    $linea = $sesion.GetTimelineProperties()

    # La carátula solo se vuelve a guardar cuando cambia la canción.
    $pista = "$($propiedades.Title)|$($propiedades.Artist)|$($propiedades.AlbumTitle)"
    $hayPortada = $false
    if ($rutaPortada -and $propiedades.Thumbnail) {
        if ($pista -eq $script:ultimaPista -and (Test-Path $rutaPortada)) {
            $hayPortada = $true
        } else {
            try {
                $flujo = Esperar ($propiedades.Thumbnail.OpenReadAsync()) $tipoFlujo
                $origen = $comoFlujoNet.Invoke($null, @($flujo))
                $salida = [System.IO.File]::Create($rutaPortada)
                $origen.CopyTo($salida)
                $salida.Close(); $origen.Close()
                $hayPortada = $true
                $script:ultimaPista = $pista
            } catch {
                [Console]::Error.WriteLine("Caratula: $($_.Exception.Message)")
            }
        }
    }

    return @{
        activo   = $true
        abierta  = $true
        titulo   = $propiedades.Title
        artista  = $propiedades.Artist
        album    = $propiedades.AlbumTitle
        app      = $sesion.SourceAppUserModelId
        estado   = $reproduccion.PlaybackStatus.ToString()
        posicion = [math]::Round($linea.Position.TotalSeconds)
        duracion = [math]::Round($linea.EndTime.TotalSeconds)
        portada  = $hayPortada
    }
}

function Control([string]$orden) {
    $sesion = Buscar-Sesion
    if (-not $sesion) { return @{ ok = $false; abierta = $false } }
    $operacion = switch ($orden) {
        "play_pausa" { $sesion.TryTogglePlayPauseAsync() }
        "siguiente"  { $sesion.TrySkipNextAsync() }
        "anterior"   { $sesion.TrySkipPreviousAsync() }
    }
    return @{ ok = [bool](Esperar $operacion ([bool])); abierta = $true }
}

Responder @{ listo = $true }

while ($null -ne ($entrada = [Console]::In.ReadLine())) {
    $partes = $entrada.Split(" ", 2)
    try {
        switch ($partes[0]) {
            "estado" { Responder (Estado ($(if ($partes.Count -gt 1) { $partes[1] } else { "" }))) }
            { $_ -in "play_pausa", "siguiente", "anterior" } { Responder (Control $partes[0]) }
            default { Responder @{ error = "Orden desconocida" } }
        }
    } catch {
        Responder @{ activo = $false; error = $_.Exception.Message }
    }
}
