using System.IO;
using System.IO.Compression;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging;
using MoriaMODCreator.Models;

namespace MoriaMODCreator.Services;

/// <summary>
/// Build pipeline for creating mods. Implements Phases A through G.
/// </summary>
public class BuildService
{
    private readonly ConfigService _config;
    private readonly DefinitionService _defService;
    private readonly JsonDataService _jsonService;
    private readonly UAssetService _uassetService;
    private readonly RetocService _retocService;
    private readonly ILogger<BuildService> _logger;

    public BuildService(
        ConfigService config,
        DefinitionService defService,
        JsonDataService jsonService,
        UAssetService uassetService,
        RetocService retocService,
        ILogger<BuildService> logger)
    {
        _config = config;
        _defService = defService;
        _jsonService = jsonService;
        _uassetService = uassetService;
        _retocService = retocService;
        _logger = logger;
    }

    /// <summary>
    /// Build a mod from a list of .def files.
    /// </summary>
    public async Task<BuildResult> BuildAsync(
        string modName,
        IReadOnlyList<string> defFiles,
        bool includeSecrets,
        IProgress<BuildProgress>? progress = null,
        CancellationToken ct = default)
    {
        var jsonFilesDir = _config.GetModJsonFilesDir(modName);
        var uassetDir = _config.GetModUAssetDir(modName);
        var finalDir = _config.GetModFinalDir(modName);

        try
        {
            // Phase 0: Clean build directories
            progress?.Report(new("Cleaning previous build...", 0.0));
            CleanDirectories(jsonFilesDir, uassetDir, finalDir);

            // Parse all .def files
            var definitions = defFiles.Select(f => _defService.Parse(f)).ToList();
            var usesSecrets = definitions.Any(d => _defService.ReferencesSecrets(d));
            if (includeSecrets) usesSecrets = true;

            // Phase A: Copy source JSON files
            progress?.Report(new("Copying source files...", 0.05));
            await Task.Run(() => PhaseA_CopySources(definitions, jsonFilesDir), ct);

            // Phase B: Overlay secrets
            if (usesSecrets)
            {
                progress?.Report(new("Overlaying secrets data...", 0.15));
                await Task.Run(() => PhaseB_OverlaySecrets(jsonFilesDir), ct);
            }

            // Phase C: Apply .def changes
            progress?.Report(new("Applying mod changes...", 0.20));
            var (applied, errors) = await Task.Run(
                () => PhaseC_ApplyChanges(definitions, jsonFilesDir), ct);
            _logger.LogInformation("Phase C: {Applied} changes applied, {Errors} errors", applied, errors);

            // Phase D: Convert JSON back to uasset (json→uasset via UAssetGUI fromjson)
            progress?.Report(new("Converting to uasset...", 0.40));
            await PhaseD_ConvertToUasset(jsonFilesDir, uassetDir, progress, ct);

            // Phase E: Package with retoc
            progress?.Report(new("Packaging mod files...", 0.70));
            var modPakName = $"{modName}_P";
            var modFinalDir = Path.Combine(finalDir, modPakName);
            Directory.CreateDirectory(modFinalDir);
            var utocPath = Path.Combine(modFinalDir, $"{modPakName}.utoc");

            var retocResult = await _retocService.ToZenAsync(uassetDir, utocPath, ct: ct);
            if (!retocResult.Success)
                return new BuildResult(false, $"retoc packaging failed: {retocResult.Output}");

            // Phase F: Copy secrets pak files
            if (usesSecrets)
            {
                progress?.Report(new("Copying secrets pak files...", 0.85));
                await Task.Run(() => PhaseF_CopySecretsPaks(modFinalDir), ct);
            }

            // Phase G: Create ZIP
            progress?.Report(new("Creating zip file...", 0.90));
            var downloadsDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
            var zipPath = Path.Combine(downloadsDir, $"{modName}.zip");

            if (File.Exists(zipPath)) File.Delete(zipPath);
            ZipFile.CreateFromDirectory(finalDir, zipPath);

            progress?.Report(new("Build complete!", 1.0));
            _logger.LogInformation("Build complete: {ZipPath}", zipPath);
            return new BuildResult(true, zipPath);
        }
        catch (OperationCanceledException)
        {
            return new BuildResult(false, "Build cancelled");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Build failed");
            return new BuildResult(false, $"Build failed: {ex.Message}");
        }
    }

    // --- Phase implementations ---

    private void PhaseA_CopySources(List<ModDefinition> definitions, string jsonFilesDir)
    {
        _logger.LogInformation("Phase A: Copying source files");
        var jsonDataDir = _config.OutputJsonDataDir;

        foreach (var def in definitions)
        {
            foreach (var modFile in def.ModFiles)
            {
                // Skip secrets files — Phase B handles them
                if (modFile.FilePath.Contains("Secrets Source", StringComparison.OrdinalIgnoreCase))
                    continue;

                var normalizedPath = DefinitionService.NormalizePath(modFile.FilePath);
                var srcPath = Path.Combine(jsonDataDir, normalizedPath);
                var dstPath = Path.Combine(jsonFilesDir, normalizedPath);

                if (!File.Exists(srcPath))
                {
                    _logger.LogWarning("Phase A: Source file not found: {Path}", srcPath);
                    continue;
                }

                Directory.CreateDirectory(Path.GetDirectoryName(dstPath)!);
                File.Copy(srcPath, dstPath, overwrite: true);
                _logger.LogDebug("Phase A: Copied {Path}", normalizedPath);
            }
        }
    }

    private void PhaseB_OverlaySecrets(string jsonFilesDir)
    {
        // Source is jsondata_github/modified-json/Moria/ — post-processed DataTable JSON
        // (copied from Secrets Source/github/json/Moria/Content/ during import).
        var sourceDir = Path.Combine(_config.SecretsJsonDataGitHubDir, "modified-json", "Moria");
        if (!Directory.Exists(sourceDir) ||
            Directory.GetFiles(sourceDir, "*.json", SearchOption.AllDirectories).Length == 0)
        {
            throw new InvalidOperationException(
                "Phase B: Secrets JSON not found at jsondata_github/modified-json/Moria/. " +
                "Run Import to download secrets data from GitHub first.");
        }

        int copied = 0;
        foreach (var jsonFile in Directory.GetFiles(sourceDir, "*.json", SearchOption.AllDirectories))
        {
            // Destination should be jsonFiles/Moria/... (matches game JSON layout)
            var relFromMoria = Path.GetRelativePath(Path.GetDirectoryName(sourceDir)!, jsonFile);
            var dstPath = Path.Combine(jsonFilesDir, relFromMoria);
            Directory.CreateDirectory(Path.GetDirectoryName(dstPath)!);
            File.Copy(jsonFile, dstPath, overwrite: true);
            copied++;
        }

        _logger.LogInformation("Phase B: Overlaid {Count} secrets files from jsondata_github/modified-json/Moria/", copied);
    }

    private (int Applied, int Errors) PhaseC_ApplyChanges(
        List<ModDefinition> definitions, string jsonFilesDir)
    {
        _logger.LogInformation("Phase C: Applying .def changes");
        int totalApplied = 0, totalErrors = 0;

        foreach (var def in definitions)
        {
            foreach (var modFile in def.ModFiles)
            {
                var normalizedPath = DefinitionService.NormalizePath(modFile.FilePath);
                var jsonPath = Path.Combine(jsonFilesDir, normalizedPath);

                if (!File.Exists(jsonPath))
                {
                    _logger.LogWarning("Phase C: JSON file not found: {Path}", jsonPath);
                    totalErrors++;
                    continue;
                }

                var root = JsonNode.Parse(File.ReadAllText(jsonPath));
                if (root == null) continue;

                bool modified = false;

                // Apply deletes
                foreach (var del in modFile.Deletes)
                {
                    if (_jsonService.RemoveGameplayTag(root, del.Item, del.Property, del.Value))
                    {
                        totalApplied++;
                        modified = true;
                    }
                    else
                    {
                        _logger.LogWarning("Phase C: Delete failed: {Item}.{Prop}", del.Item, del.Property);
                        totalErrors++;
                    }
                }

                // Apply changes
                foreach (var change in modFile.Changes)
                {
                    bool ok;
                    if (IsGameplayTagProperty(root, change.Item, change.Property))
                    {
                        // Tag change: remove old, add new
                        if (change.Original != null)
                            _jsonService.RemoveGameplayTag(root, change.Item, change.Property, change.Original);
                        ok = _jsonService.AddGameplayTag(root, change.Item, change.Property, change.Value);
                    }
                    else
                    {
                        ok = _jsonService.ApplyChange(root, change.Item, change.Property, change.Value);
                    }

                    if (ok)
                    {
                        totalApplied++;
                        modified = true;
                        // Sync NameMap for new values
                        _jsonService.SyncNameMap(root, change.Value);
                    }
                    else
                    {
                        _logger.LogWarning("Phase C: Change failed: {Item}.{Prop}={Val}",
                            change.Item, change.Property, change.Value);
                        totalErrors++;
                    }
                }

                if (modified)
                {
                    var options = new JsonSerializerOptions { WriteIndented = true };
                    File.WriteAllText(jsonPath, root.ToJsonString(options));
                }
            }
        }

        return (totalApplied, totalErrors);
    }

    private async Task PhaseD_ConvertToUasset(
        string jsonFilesDir, string uassetDir,
        IProgress<BuildProgress>? progress, CancellationToken ct)
    {
        var jsonFiles = Directory.GetFiles(jsonFilesDir, "*.json", SearchOption.AllDirectories);
        int converted = 0, errors = 0;
        int total = jsonFiles.Length;

        foreach (var jsonFile in jsonFiles)
        {
            ct.ThrowIfCancellationRequested();
            var relPath = Path.GetRelativePath(jsonFilesDir, jsonFile);
            var uassetPath = Path.Combine(uassetDir, Path.ChangeExtension(relPath, ".uasset"));

            var ok = await _uassetService.FromJsonAsync(jsonFile, uassetPath, ct);
            if (ok) converted++; else errors++;

            progress?.Report(new($"Converting {Path.GetFileName(jsonFile)}...",
                0.40 + 0.30 * (converted + errors) / Math.Max(total, 1)));
        }

        if (errors > 0)
            _logger.LogWarning("Phase D: {Errors} conversion errors", errors);
        _logger.LogInformation("Phase D: Converted {Converted}/{Total} files", converted, total);
    }

    private void PhaseF_CopySecretsPaks(string modFinalDir)
    {
        // These companion paks must be included as-is in the final mod ZIP.
        // They come from the user-provided Nexus Secrets ZIP, extracted during import
        // to Secrets Source/companion_paks/
        var companionDir = Path.Combine(_config.SecretsSourceDir, "companion_paks");
        var secretsFiles = new[]
        {
            "SecretsOfKhazadDum_LocTags_P.pak",
            "TobiModsAddons_P.pak",
            "TobiModsAddons_P.ucas",
            "TobiModsAddons_P.utoc",
        };

        foreach (var fileName in secretsFiles)
        {
            // Check companion_paks first, then search all of Secrets Source as fallback
            var src = Path.Combine(companionDir, fileName);
            if (!File.Exists(src))
            {
                var matches = Directory.Exists(_config.SecretsSourceDir)
                    ? Directory.GetFiles(_config.SecretsSourceDir, fileName, SearchOption.AllDirectories)
                    : [];
                if (matches.Length > 0)
                    src = matches[0];
                else
                {
                    _logger.LogWarning("Phase F: Companion pak not found: {File}", fileName);
                    continue;
                }
            }

            File.Copy(src, Path.Combine(modFinalDir, fileName), overwrite: true);
            _logger.LogInformation("Phase F: Copied {File}", fileName);
        }
    }

    private static bool IsGameplayTagProperty(JsonNode root, string itemName, string property)
    {
        var dataArray = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (dataArray == null) return false;

        var row = dataArray.FirstOrDefault(r => r?["Name"]?.GetValue<string>() == itemName);
        if (row == null) return false;

        var valueArray = row["Value"] as JsonArray;
        if (valueArray == null) return false;

        var propName = property.Split('.')[0];
        return valueArray.Any(p =>
            p?["Name"]?.GetValue<string>() == propName &&
            p["StructType"]?.GetValue<string>() == "GameplayTagContainer");
    }

    private static void CleanDirectories(params string[] dirs)
    {
        foreach (var dir in dirs)
        {
            if (Directory.Exists(dir))
                Directory.Delete(dir, recursive: true);
            Directory.CreateDirectory(dir);
        }
    }
}

public record BuildProgress(string Status, double Progress);
public record BuildResult(bool Success, string Message);
