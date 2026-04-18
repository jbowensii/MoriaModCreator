using System.Diagnostics;
using System.IO;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Wraps retoc.exe subprocess calls for IoStore operations.
/// </summary>
public class RetocService
{
    private const string RetocUeVersion = "UE4_27";
    private readonly ConfigService _config;
    private readonly ILogger<RetocService> _logger;

    public RetocService(ConfigService config, ILogger<RetocService> logger)
    {
        _config = config;
        _logger = logger;
    }

    /// <summary>
    /// Run retoc to-legacy to extract IoStore pak to legacy .uasset files.
    /// </summary>
    public async Task<RetocResult> ToLegacyAsync(
        string inputDir, string outputDir,
        string? filter = null,
        int timeoutSeconds = 600,
        IProgress<string>? progress = null,
        CancellationToken ct = default)
    {
        var args = $"to-legacy --version {RetocUeVersion}";
        if (filter != null)
            args += $" --filter \"{filter}\"";
        args += $" \"{inputDir}\" \"{outputDir}\"";

        return await RunRetocAsync(args, timeoutSeconds, progress, ct);
    }

    /// <summary>
    /// Run retoc to-zen to package .uasset files into IoStore format.
    /// </summary>
    public async Task<RetocResult> ToZenAsync(
        string inputDir, string outputUtoc,
        int timeoutSeconds = 300,
        IProgress<string>? progress = null,
        CancellationToken ct = default)
    {
        var args = $"to-zen --version {RetocUeVersion} \"{inputDir}\" \"{outputUtoc}\"";
        return await RunRetocAsync(args, timeoutSeconds, progress, ct);
    }

    private async Task<RetocResult> RunRetocAsync(
        string args, int timeoutSeconds,
        IProgress<string>? progress, CancellationToken ct)
    {
        var retocPath = _config.RetocExePath;
        if (!File.Exists(retocPath))
        {
            _logger.LogError("retoc.exe not found at {Path}", retocPath);
            return new RetocResult(false, "retoc.exe not found");
        }

        _logger.LogInformation("Running retoc: {Path} {Args}", retocPath, args);
        progress?.Report($"Running retoc...");

        var psi = new ProcessStartInfo
        {
            FileName = retocPath,
            Arguments = args,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        using var process = new Process { StartInfo = psi };
        process.Start();

        var stdout = process.StandardOutput.ReadToEndAsync(ct);
        var stderr = process.StandardError.ReadToEndAsync(ct);

        var exited = await Task.Run(() =>
            process.WaitForExit(timeoutSeconds * 1000), ct);

        if (!exited)
        {
            process.Kill(entireProcessTree: true);
            _logger.LogError("retoc timed out after {Seconds}s", timeoutSeconds);
            return new RetocResult(false, "retoc timed out");
        }

        var stdoutText = await stdout;
        var stderrText = await stderr;

        if (process.ExitCode != 0)
        {
            _logger.LogWarning("retoc exited with code {Code}: {Stderr}",
                process.ExitCode, stderrText.Trim());
            return new RetocResult(false, stderrText.Trim(), process.ExitCode);
        }

        return new RetocResult(true, stdoutText.Trim(), 0);
    }
}

public record RetocResult(bool Success, string Output, int ExitCode = -1);
