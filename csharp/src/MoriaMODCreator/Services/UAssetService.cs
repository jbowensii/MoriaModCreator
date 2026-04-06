using System.Diagnostics;
using System.IO;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Handles uasset ↔ JSON conversion.
/// Currently wraps UAssetGUI.exe; will be replaced with embedded UAssetAPI
/// once the NuGet package or project reference is integrated.
/// </summary>
public class UAssetService
{
    private const string UeVersion = "VER_UE4_27";
    private readonly ConfigService _config;
    private readonly ILogger<UAssetService> _logger;

    public UAssetService(ConfigService config, ILogger<UAssetService> logger)
    {
        _config = config;
        _logger = logger;
    }

    /// <summary>Convert a .uasset file to JSON.</summary>
    public async Task<bool> ToJsonAsync(string uassetPath, string jsonPath, CancellationToken ct = default)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(jsonPath)!);
        var args = $"tojson \"{uassetPath}\" \"{jsonPath}\" {UeVersion}";
        var result = await RunUAssetGuiAsync(args, ct);
        return result && File.Exists(jsonPath);
    }

    /// <summary>Convert a JSON file back to .uasset.</summary>
    public async Task<bool> FromJsonAsync(string jsonPath, string uassetPath, CancellationToken ct = default)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(uassetPath)!);
        var args = $"fromjson \"{jsonPath}\" \"{uassetPath}\" {UeVersion}";
        var result = await RunUAssetGuiAsync(args, ct);
        return result && File.Exists(uassetPath);
    }

    /// <summary>Convert multiple uasset files to JSON in parallel.</summary>
    public async Task<(int Converted, int Errors)> BatchToJsonAsync(
        IReadOnlyList<string> uassetFiles,
        string sourceBaseDir,
        string destBaseDir,
        IProgress<(int Done, int Total)>? progress = null,
        CancellationToken ct = default)
    {
        int converted = 0, errors = 0;
        var total = uassetFiles.Count;
        var semaphore = new SemaphoreSlim(Environment.ProcessorCount);

        var tasks = uassetFiles.Select(async uassetPath =>
        {
            await semaphore.WaitAsync(ct);
            try
            {
                var relPath = Path.GetRelativePath(sourceBaseDir, uassetPath);
                var jsonPath = Path.Combine(destBaseDir,
                    Path.ChangeExtension(relPath, ".json"));

                var ok = await ToJsonAsync(uassetPath, jsonPath, ct);
                if (ok)
                    Interlocked.Increment(ref converted);
                else
                    Interlocked.Increment(ref errors);

                progress?.Report((converted + errors, total));
            }
            finally
            {
                semaphore.Release();
            }
        });

        await Task.WhenAll(tasks);
        return (converted, errors);
    }

    private async Task<bool> RunUAssetGuiAsync(string args, CancellationToken ct)
    {
        var exePath = _config.UAssetGuiExePath;
        if (!File.Exists(exePath))
        {
            _logger.LogError("UAssetGUI.exe not found at {Path}", exePath);
            return false;
        }

        var psi = new ProcessStartInfo
        {
            FileName = exePath,
            Arguments = args,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        using var process = new Process { StartInfo = psi };
        process.Start();

        var exited = await Task.Run(() => process.WaitForExit(60_000), ct);
        if (!exited)
        {
            process.Kill(entireProcessTree: true);
            _logger.LogWarning("UAssetGUI timed out for args: {Args}", args);
            return false;
        }

        return process.ExitCode == 0;
    }
}
