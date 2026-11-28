# Ayudante de "Control remoto" de ControlPC. Queda abierto y responde una línea JSON por orden.
#
# Orden:
#   captura <ancho_maximo> <calidad>
#     Toma la pantalla principal (con el cursor), la reduce a <ancho_maximo> píxeles de ancho
#     y la devuelve como JPEG en base64, junto con el tamaño real de la pantalla.

$ErrorActionPreference = "Stop"
try { [Console]::InputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

Add-Type -AssemblyName System.Drawing

$codigo = @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;

public static class CapturaPantalla {
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr valor);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int indice);
    [DllImport("user32.dll")] static extern bool GetCursorInfo(ref CURSORINFO info);
    [DllImport("user32.dll")] static extern bool DrawIconEx(IntPtr hdc, int x, int y, IntPtr icono, int ancho, int alto, int paso, IntPtr pincel, int banderas);
    [DllImport("user32.dll")] static extern bool GetIconInfo(IntPtr icono, out ICONINFO info);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr objeto);

    [StructLayout(LayoutKind.Sequential)] struct PUNTO { public int x; public int y; }
    [StructLayout(LayoutKind.Sequential)] struct CURSORINFO { public int cbSize; public int flags; public IntPtr hCursor; public PUNTO pos; }
    [StructLayout(LayoutKind.Sequential)] struct ICONINFO { public bool fIcon; public int xHotspot; public int yHotspot; public IntPtr hbmMask; public IntPtr hbmColor; }

    static ImageCodecInfo codecJpeg;

    public static void Iniciar() {
        // Sin esto, en pantallas con escala (125 %, 150 %…) Windows entrega una captura recortada.
        try { if (!SetProcessDpiAwarenessContext(new IntPtr(-4))) SetProcessDPIAware(); } catch { SetProcessDPIAware(); }
        foreach (ImageCodecInfo c in ImageCodecInfo.GetImageEncoders()) if (c.MimeType == "image/jpeg") codecJpeg = c;
    }

    public static int Ancho() { return GetSystemMetrics(0); }
    public static int Alto() { return GetSystemMetrics(1); }

    public static string Tomar(int anchoMaximo, long calidad) {
        int ancho = Ancho(), alto = Alto();
        using (Bitmap completa = new Bitmap(ancho, alto, PixelFormat.Format24bppRgb)) {
            using (Graphics g = Graphics.FromImage(completa)) {
                g.CopyFromScreen(0, 0, 0, 0, new Size(ancho, alto), CopyPixelOperation.SourceCopy);
                DibujarCursor(g);
            }
            Bitmap final = completa;
            if (anchoMaximo > 0 && ancho > anchoMaximo) {
                int altoFinal = (int)Math.Round((double)alto * anchoMaximo / ancho);
                final = new Bitmap(anchoMaximo, altoFinal, PixelFormat.Format24bppRgb);
                using (Graphics g = Graphics.FromImage(final)) {
                    g.InterpolationMode = InterpolationMode.Bilinear;
                    g.PixelOffsetMode = PixelOffsetMode.HighSpeed;
                    g.DrawImage(completa, 0, 0, anchoMaximo, altoFinal);
                }
            }
            try {
                using (MemoryStream salida = new MemoryStream()) {
                    EncoderParameters parametros = new EncoderParameters(1);
                    parametros.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, calidad);
                    final.Save(salida, codecJpeg, parametros);
                    return Convert.ToBase64String(salida.ToArray());
                }
            } finally { if (final != completa) final.Dispose(); }
        }
    }

    static void DibujarCursor(Graphics g) {
        CURSORINFO info = new CURSORINFO();
        info.cbSize = Marshal.SizeOf(typeof(CURSORINFO));
        if (!GetCursorInfo(ref info) || info.flags != 1) return;  // 1 = cursor visible
        ICONINFO icono;
        int x = info.pos.x, y = info.pos.y;
        if (GetIconInfo(info.hCursor, out icono)) {
            x -= icono.xHotspot; y -= icono.yHotspot;
            if (icono.hbmMask != IntPtr.Zero) DeleteObject(icono.hbmMask);
            if (icono.hbmColor != IntPtr.Zero) DeleteObject(icono.hbmColor);
        }
        IntPtr hdc = g.GetHdc();
        try { DrawIconEx(hdc, x, y, info.hCursor, 0, 0, 0, IntPtr.Zero, 3); } finally { g.ReleaseHdc(hdc); }
    }
}
"@

Add-Type -TypeDefinition $codigo -ReferencedAssemblies System.Drawing
[CapturaPantalla]::Iniciar()

function Responder($objeto) {
    [Console]::Out.WriteLine(($objeto | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
}

Responder @{ listo = $true }

while ($null -ne ($linea = [Console]::In.ReadLine())) {
    $partes = $linea.Trim().Split(" ")
    try {
        switch ($partes[0]) {
            "captura" {
                $anchoMax = if ($partes.Count -gt 1) { [int]$partes[1] } else { 1280 }
                $calidad = if ($partes.Count -gt 2) { [long]$partes[2] } else { 60 }
                $jpeg = [CapturaPantalla]::Tomar($anchoMax, $calidad)
                Responder @{ ancho = [CapturaPantalla]::Ancho(); alto = [CapturaPantalla]::Alto(); jpeg = $jpeg }
            }
            default { Responder @{ error = "Orden desconocida" } }
        }
    } catch {
        [Console]::Error.WriteLine("Pantalla: $($_.Exception.Message)")
        Responder @{ error = $_.Exception.Message }
    }
}
