param(
    [string]$DevicePattern = 'RACE TX10',
    [int]$DurationSeconds = 3,
    [int]$FrequencyHz = 660
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public static class WaveOutTone {
    const uint CALLBACK_NULL = 0;
    const uint WHDR_DONE = 0x00000001;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    struct WAVEOUTCAPS {
        public ushort wMid, wPid;
        public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szPname;
        public uint dwFormats;
        public ushort wChannels, wReserved1;
        public uint dwSupport;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct WAVEFORMATEX {
        public ushort wFormatTag, nChannels;
        public uint nSamplesPerSec, nAvgBytesPerSec;
        public ushort nBlockAlign, wBitsPerSample, cbSize;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct WAVEHDR {
        public IntPtr lpData;
        public uint dwBufferLength, dwBytesRecorded;
        public UIntPtr dwUser;
        public uint dwFlags, dwLoops;
        public IntPtr lpNext;
        public UIntPtr reserved;
    }

    [DllImport("winmm.dll")] static extern uint waveOutGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Auto)] static extern uint waveOutGetDevCaps(UIntPtr id, out WAVEOUTCAPS caps, uint size);
    [DllImport("winmm.dll")] static extern uint waveOutOpen(out IntPtr handle, uint id, ref WAVEFORMATEX format, IntPtr callback, IntPtr instance, uint flags);
    [DllImport("winmm.dll")] static extern uint waveOutPrepareHeader(IntPtr handle, ref WAVEHDR header, uint size);
    [DllImport("winmm.dll")] static extern uint waveOutWrite(IntPtr handle, ref WAVEHDR header, uint size);
    [DllImport("winmm.dll")] static extern uint waveOutUnprepareHeader(IntPtr handle, ref WAVEHDR header, uint size);
    [DllImport("winmm.dll")] static extern uint waveOutClose(IntPtr handle);

    static void Check(uint result, string operation) {
        if (result != 0) throw new Win32Exception((int)result, operation + " failed with MMRESULT " + result);
    }

    public static string[] Devices() {
        uint count = waveOutGetNumDevs();
        string[] names = new string[count];
        for (uint i = 0; i < count; i++) {
            WAVEOUTCAPS caps;
            Check(waveOutGetDevCaps((UIntPtr)i, out caps, (uint)Marshal.SizeOf<WAVEOUTCAPS>()), "waveOutGetDevCaps");
            names[i] = caps.szPname;
        }
        return names;
    }

    public static string Play(string pattern, int seconds, int frequency) {
        string[] names = Devices();
        int device = Array.FindIndex(names, n => n.IndexOf(pattern, StringComparison.OrdinalIgnoreCase) >= 0);
        if (device < 0) throw new InvalidOperationException("No waveOut device matches '" + pattern + "'. Found: " + string.Join(", ", names));

        const int rate = 44100;
        const int channels = 2;
        const int bytesPerSample = 2;
        int frames = checked(rate * seconds);
        byte[] pcm = new byte[frames * channels * bytesPerSample];
        for (int frame = 0; frame < frames; frame++) {
            short sample = (short)(Math.Sin(2.0 * Math.PI * frequency * frame / rate) * 5000);
            int offset = frame * 4;
            pcm[offset] = (byte)sample;
            pcm[offset + 1] = (byte)(sample >> 8);
            pcm[offset + 2] = (byte)sample;
            pcm[offset + 3] = (byte)(sample >> 8);
        }

        WAVEFORMATEX format = new WAVEFORMATEX {
            wFormatTag = 1, nChannels = channels, nSamplesPerSec = rate,
            nAvgBytesPerSec = rate * channels * bytesPerSample,
            nBlockAlign = channels * bytesPerSample, wBitsPerSample = 16, cbSize = 0
        };
        IntPtr output;
        Check(waveOutOpen(out output, (uint)device, ref format, IntPtr.Zero, IntPtr.Zero, CALLBACK_NULL), "waveOutOpen");
        GCHandle pin = GCHandle.Alloc(pcm, GCHandleType.Pinned);
        WAVEHDR header = new WAVEHDR { lpData = pin.AddrOfPinnedObject(), dwBufferLength = (uint)pcm.Length };
        try {
            uint headerSize = (uint)Marshal.SizeOf<WAVEHDR>();
            Check(waveOutPrepareHeader(output, ref header, headerSize), "waveOutPrepareHeader");
            Check(waveOutWrite(output, ref header, headerSize), "waveOutWrite");
            while ((header.dwFlags & WHDR_DONE) == 0) Thread.Sleep(20);
            Check(waveOutUnprepareHeader(output, ref header, headerSize), "waveOutUnprepareHeader");
        } finally {
            pin.Free();
            waveOutClose(output);
        }
        return names[device];
    }
}
'@

$devices = [WaveOutTone]::Devices()
Write-Host ('waveOut devices: ' + ($devices -join '; '))
$selected = [WaveOutTone]::Play($DevicePattern, $DurationSeconds, $FrequencyHz)
Write-Host "Played ${FrequencyHz}Hz stereo PCM for ${DurationSeconds}s through: $selected"
