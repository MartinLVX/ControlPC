# Devuelve en JSON lo que se esta reproduciendo en Windows (Spotify, YouTube en el navegador, etc.).
# Usa la API de Windows "Global System Media Transport Controls". Requiere Windows 10 o 11.
param([string]$Portada = "")

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTaskGenerico = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

    function Esperar($operacion, [Type]$tipo) {
        $tarea = $asTaskGenerico.MakeGenericMethod($tipo).Invoke($null, @($operacion))
        $tarea.Wait(-1) | Out-Null
        $tarea.Result
    }

    $tipoGestor = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
    $tipoPropiedades = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType = WindowsRuntime]

    $gestor = Esperar ($tipoGestor::RequestAsync()) $tipoGestor
    $sesion = $gestor.GetCurrentSession()
    if (-not $sesion) {
        Write-Output '{"activo": false}'
        exit 0
    }

    $propiedades = Esperar ($sesion.TryGetMediaPropertiesAsync()) $tipoPropiedades
    $reproduccion = $sesion.GetPlaybackInfo()

    $hayPortada = $false
    if ($Portada -and $propiedades.Thumbnail) {
        try {
            $tipoFlujo = [Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType = WindowsRuntime]
            $flujo = Esperar ($propiedades.Thumbnail.OpenReadAsync()) $tipoFlujo
            $entrada = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($flujo)
            $salida = [System.IO.File]::Create($Portada)
            $entrada.CopyTo($salida)
            $salida.Close(); $entrada.Close()
            $hayPortada = $true
        } catch { }
    }

    [pscustomobject]@{
        activo  = $true
        titulo  = $propiedades.Title
        artista = $propiedades.Artist
        album   = $propiedades.AlbumTitle
        app     = $sesion.SourceAppUserModelId
        estado  = $reproduccion.PlaybackStatus.ToString()
        portada = $hayPortada
    } | ConvertTo-Json -Compress
} catch {
    [pscustomobject]@{ activo = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress
}
