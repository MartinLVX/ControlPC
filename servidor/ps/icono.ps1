# Guarda como PNG el icono que Windows muestra para un programa, acceso directo o app de la Tienda.
param([Parameter(Mandatory = $true)][string]$Ruta, [Parameter(Mandatory = $true)][string]$Salida, [int]$Tam = 128)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$codigo = @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public static class IconoShell {
    [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItemImageFactory { [PreserveSig] int GetImage(TAMANO tam, int opciones, out IntPtr hbm); }

    [StructLayout(LayoutKind.Sequential)] struct TAMANO { public int cx; public int cy; }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string ruta, IntPtr pbc,
        [MarshalAs(UnmanagedType.LPStruct)] Guid riid, [MarshalAs(UnmanagedType.Interface)] out IShellItemImageFactory ppv);

    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);

    public static void Guardar(string ruta, string salida, int tam) {
        IShellItemImageFactory fabrica;
        SHCreateItemFromParsingName(ruta, IntPtr.Zero, typeof(IShellItemImageFactory).GUID, out fabrica);
        IntPtr hbm;
        // 0x1 = se acepta un tamaño mayor, 0x4 = solo el icono (sin miniatura del contenido)
        int hr = fabrica.GetImage(new TAMANO { cx = tam, cy = tam }, 0x1 | 0x4, out hbm);
        if (hr != 0) Marshal.ThrowExceptionForHR(hr);
        try {
            using (Bitmap origen = Image.FromHbitmap(hbm)) {
                // FromHbitmap pierde la transparencia: se copian los bytes como ARGB para conservarla.
                Rectangle area = new Rectangle(0, 0, origen.Width, origen.Height);
                BitmapData datos = origen.LockBits(area, ImageLockMode.ReadOnly, origen.PixelFormat);
                try {
                    using (Bitmap conAlfa = new Bitmap(datos.Width, datos.Height, datos.Stride, PixelFormat.Format32bppArgb, datos.Scan0)) {
                        conAlfa.Save(salida, ImageFormat.Png);
                    }
                } finally { origen.UnlockBits(datos); }
            }
        } finally { DeleteObject(hbm); }
    }
}
"@

try {
    Add-Type -TypeDefinition $codigo -ReferencedAssemblies System.Drawing
    [IconoShell]::Guardar($Ruta, $Salida, $Tam)
} catch {
    # Plan B: el icono asociado clásico (32x32).
    $icono = [System.Drawing.Icon]::ExtractAssociatedIcon($Ruta)
    $icono.ToBitmap().Save($Salida, [System.Drawing.Imaging.ImageFormat]::Png)
}
