using System.IO;
using System.IO.Compression;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;
using MoriaMODCreator.Models;

namespace MoriaMODCreator.Services;

/// <summary>
/// Handles the complete import workflow: game file extraction, secrets extraction,
/// JSON conversion, and duplicate row stripping.
/// Mirrors Python combined_import_dialog.py pipeline.
/// </summary>
public class ImportService
{
    private readonly ConfigService _config;
    private readonly RetocService _retoc;
    private readonly UAssetService _uasset;
    private readonly JsonDataService _jsonData;
    private readonly ILogger<ImportService> _logger;

    public ImportService(
        ConfigService config, RetocService retoc,
        UAssetService uasset, JsonDataService jsonData,
        ILogger<ImportService> logger)
    {
        _config = config;
        _retoc = retoc;
        _uasset = uasset;
        _jsonData = jsonData;
        _logger = logger;
    }

    /// <summary>
    /// Run the complete combined import (game files + secrets).
    /// </summary>
    public async Task<ImportResult> RunCombinedImportAsync(
        IProgress<ImportProgress>? progress = null,
        CancellationToken ct = default)
    {
        try
        {
            // Step 1: Clean directories
            progress?.Report(new("Preparing import...", "Clearing directories...", 0.0));
            _logger.LogInformation("Import: cleaning directories");
            await Task.Run(CleanDirectories, ct);

            // Step 2: Extract game files
            progress?.Report(new("Importing Game Files", "Extracting game data...", 0.05));
            _logger.LogInformation("Import: extracting game files");
            var gameResult = await ExtractGameFilesAsync(progress, ct);
            if (!gameResult)
            {
                _logger.LogError("Import: game file extraction failed");
                return new ImportResult(false, "Game file extraction failed");
            }

            // Step 3: Import secrets (if available)
            progress?.Report(new("Importing Secrets", "Checking for secrets...", 0.50));
            _logger.LogInformation("Import: starting secrets import");
            var secretsResult = await ImportSecretsAsync(progress, ct);

            progress?.Report(new("Import Complete", "Done!", 1.0));
            return new ImportResult(true, "Import completed successfully");
        }
        catch (OperationCanceledException)
        {
            return new ImportResult(false, "Import cancelled");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Import failed");
            return new ImportResult(false, $"Import failed: {ex.Message}");
        }
    }

    /// <summary>
    /// Run the secrets-only import pipeline.
    /// </summary>
    public async Task<ImportResult> ImportSecretsAsync(
        IProgress<ImportProgress>? progress = null,
        CancellationToken ct = default)
    {
        var secretsDir = _config.SecretsSourceDir;
        if (!Directory.Exists(secretsDir))
        {
            _logger.LogWarning("Secrets Source directory not found");
            return new ImportResult(true, "No secrets to import");
        }

        // Step 1: Extract ZIPs
        progress?.Report(new("Importing Secrets", "Extracting ZIP files...", 0.52));
        _logger.LogInformation("Secrets: extracting ZIPs");
        await Task.Run(() => ExtractSecretsZips(secretsDir), ct);

        // Step 2: IoStore extraction (retoc to-legacy)
        progress?.Report(new("Importing Secrets", "Extracting IoStore files...", 0.55));
        _logger.LogInformation("Secrets: IoStore extraction");
        await ExtractSecretsIoStoreAsync(secretsDir, progress, ct);

        // Step 3: Convert uasset to JSON → jsondata_full/
        progress?.Report(new("Converting Secrets", "Converting to JSON...", 0.65));
        _logger.LogInformation("Secrets: converting to JSON");
        await ConvertSecretsToJsonAsync(secretsDir, progress, ct);

        // Step 3b: Copy jsondata_full/ → jsondata/, then strip duplicate rows
        progress?.Report(new("Filtering Secrets", "Removing game data from secrets...", 0.80));
        _logger.LogInformation("Secrets: stripping duplicate rows");
        await Task.Run(() => CopyFullToFiltered(secretsDir), ct);
        await Task.Run(() => StripDuplicateRows(secretsDir, progress), ct);

        // Step 3c: Copy to New Secrets
        progress?.Report(new("Finalizing", "Copying to New Secrets...", 0.92));
        _logger.LogInformation("Secrets: copying to New Secrets");
        await Task.Run(() => CopyToNewSecrets(secretsDir), ct);

        // Step 4: Generate manifest
        progress?.Report(new("Finalizing", "Generating manifest...", 0.95));
        _logger.LogInformation("Secrets: generating manifest");
        await Task.Run(() => GenerateSecretsManifest(secretsDir), ct);

        return new ImportResult(true, "Secrets import completed");
    }

    // --- Game file extraction ---

    private async Task<bool> ExtractGameFilesAsync(
        IProgress<ImportProgress>? progress, CancellationToken ct)
    {
        var gamePaksPath = _config.GetGamePaksPath();
        if (gamePaksPath == null || !Directory.Exists(gamePaksPath))
        {
            _logger.LogError("Game Paks directory not found");
            return false;
        }

        var retocDir = _config.OutputRetocDir;
        var jsonDataDir = _config.OutputJsonDataDir;
        Directory.CreateDirectory(retocDir);
        Directory.CreateDirectory(jsonDataDir);

        // Scan .def files for required game files
        progress?.Report(new("Importing Game Files", "Scanning definition files...", 0.08));
        var requiredPaths = ScanDefFilesForGamePaths();
        _logger.LogInformation("Found {Count} required game file paths", requiredPaths.Count);

        // Create temp dir with game pak + global files
        var tempPaks = Path.Combine(Path.GetTempPath(), $"game_paks_{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempPaks);

        try
        {
            // Copy global files
            foreach (var name in new[] { "global.ucas", "global.utoc" })
            {
                var src = Path.Combine(gamePaksPath, name);
                if (File.Exists(src))
                    File.Copy(src, Path.Combine(tempPaks, name));
            }

            // Copy main game pak (large files — run on background thread)
            foreach (var ext in new[] { ".pak", ".ucas", ".utoc" })
            {
                var src = Path.Combine(gamePaksPath, $"Moria-WindowsNoEditor{ext}");
                if (File.Exists(src))
                {
                    progress?.Report(new("Importing Game Files", $"Copying game files{ext}...", 0.10));
                    _logger.LogInformation("Copying {File}...", Path.GetFileName(src));
                    var dst = Path.Combine(tempPaks, $"Moria-WindowsNoEditor{ext}");
                    await Task.Run(() => File.Copy(src, dst), ct);
                }
            }

            // Run retoc to-legacy with filter for each required file
            progress?.Report(new("Importing Game Files", "Extracting game assets...", 0.15));
            var result = await _retoc.ToLegacyAsync(tempPaks, retocDir, ct: ct);
            if (!result.Success)
            {
                // Check for partial extraction
                var partialFiles = Directory.GetFiles(retocDir, "*.uasset", SearchOption.AllDirectories);
                if (partialFiles.Length == 0)
                {
                    _logger.LogError("retoc extraction failed completely: {Output}", result.Output);
                    return false;
                }
                _logger.LogWarning("retoc crashed but extracted {Count} files", partialFiles.Length);
            }

            // Convert required uasset files to JSON
            progress?.Report(new("Importing Game Files", "Converting to JSON...", 0.25));
            var uassetFiles = new List<string>();
            foreach (var reqPath in requiredPaths)
            {
                var uassetPath = Path.Combine(retocDir, Path.ChangeExtension(reqPath, ".uasset"));
                if (File.Exists(uassetPath))
                    uassetFiles.Add(uassetPath);
            }

            if (uassetFiles.Count > 0)
            {
                var convResult = await _uasset.BatchToJsonAsync(
                    uassetFiles, retocDir, jsonDataDir,
                    new Progress<(int Done, int Total)>(p =>
                        progress?.Report(new("Importing Game Files",
                            $"Converting {p.Done}/{p.Total}...",
                            0.25 + 0.20 * p.Done / Math.Max(p.Total, 1)))),
                    ct);
                _logger.LogInformation("Game files: converted {Converted}/{Total}",
                    convResult.Converted, uassetFiles.Count);
            }

            return true;
        }
        finally
        {
            try { Directory.Delete(tempPaks, true); } catch { /* cleanup */ }
        }
    }

    // --- Secrets extraction ---

    private void ExtractSecretsZips(string secretsDir)
    {
        foreach (var zipFile in Directory.GetFiles(secretsDir, "*.zip"))
        {
            var extractDir = Path.Combine(secretsDir,
                Path.GetFileNameWithoutExtension(zipFile));
            if (Directory.Exists(extractDir))
                Directory.Delete(extractDir, true);
            Directory.CreateDirectory(extractDir);

            using var archive = ZipFile.OpenRead(zipFile);
            foreach (var entry in archive.Entries)
            {
                if (string.IsNullOrEmpty(entry.Name)) continue;
                var destPath = Path.Combine(extractDir, entry.Name);
                Directory.CreateDirectory(Path.GetDirectoryName(destPath)!);
                entry.ExtractToFile(destPath, true);
            }
            _logger.LogInformation("Extracted {Count} files from {Zip}",
                archive.Entries.Count, Path.GetFileName(zipFile));
        }
    }

    private async Task ExtractSecretsIoStoreAsync(
        string secretsDir, IProgress<ImportProgress>? progress, CancellationToken ct)
    {
        var retocDir = Path.Combine(secretsDir, "retoc");
        Directory.CreateDirectory(retocDir);

        var gamePaksPath = _config.GetGamePaksPath();
        if (gamePaksPath == null) return;

        var skipDirs = new HashSet<string> { "retoc", "jsondata", "jsondata_full" };
        var skipStems = new HashSet<string>(Constants.SkipSecretsPakStems);

        // Find .utoc files in extracted subdirectories
        foreach (var subdir in Directory.GetDirectories(secretsDir))
        {
            if (skipDirs.Contains(Path.GetFileName(subdir))) continue;

            foreach (var utocFile in Directory.GetFiles(subdir, "*.utoc"))
            {
                var stem = Path.GetFileNameWithoutExtension(utocFile);
                if (skipStems.Contains(stem)) continue;

                progress?.Report(new("Importing Secrets", $"Extracting {stem}...", 0.58));

                var tempPaks = Path.Combine(Path.GetTempPath(), $"secrets_paks_{Guid.NewGuid():N}");
                Directory.CreateDirectory(tempPaks);

                try
                {
                    // Copy pak files
                    foreach (var ext in new[] { ".pak", ".ucas", ".utoc" })
                    {
                        var src = Path.Combine(subdir, stem + ext);
                        if (File.Exists(src))
                            File.Copy(src, Path.Combine(tempPaks, stem + ext));
                    }

                    // Copy global files
                    foreach (var name in new[] { "global.ucas", "global.utoc" })
                    {
                        var src = Path.Combine(gamePaksPath, name);
                        if (File.Exists(src))
                            File.Copy(src, Path.Combine(tempPaks, name));
                    }

                    // Extract with retoc (secrets-only, no game pak)
                    var result = await _retoc.ToLegacyAsync(tempPaks, retocDir, ct: ct);
                    var extractedCount = Directory.GetFiles(retocDir, "*.uasset", SearchOption.AllDirectories).Length;
                    _logger.LogInformation("Extracted {Count} files from {Stem} (success={Success})",
                        extractedCount, stem, result.Success);
                }
                finally
                {
                    try { Directory.Delete(tempPaks, true); } catch { /* cleanup */ }
                }
            }
        }
    }

    private async Task ConvertSecretsToJsonAsync(
        string secretsDir, IProgress<ImportProgress>? progress, CancellationToken ct)
    {
        var retocDir = Path.Combine(secretsDir, "retoc");
        var jsonDataFullDir = Path.Combine(secretsDir, "jsondata_full");
        Directory.CreateDirectory(jsonDataFullDir);

        if (!Directory.Exists(retocDir)) return;

        // Convert ALL extracted uasset files (no filtering — secrets pak only has ~232 files)
        var uassetFiles = Directory.GetFiles(retocDir, "*.uasset", SearchOption.AllDirectories)
            .Concat(Directory.GetFiles(retocDir, "*.umap", SearchOption.AllDirectories))
            .ToList();

        if (uassetFiles.Count == 0)
        {
            _logger.LogWarning("No uasset files found in secrets retoc output");
            return;
        }

        _logger.LogInformation("Converting {Count} secrets files to JSON", uassetFiles.Count);
        var convResult = await _uasset.BatchToJsonAsync(
            uassetFiles, retocDir, jsonDataFullDir,
            new Progress<(int Done, int Total)>(p =>
                progress?.Report(new("Converting Secrets",
                    $"Converted {p.Done}/{p.Total}...",
                    0.65 + 0.15 * p.Done / Math.Max(p.Total, 1)))),
            ct);
        _logger.LogInformation("Secrets conversion: {Converted}/{Total} ({Errors} errors)",
            convResult.Converted, uassetFiles.Count, convResult.Errors);
    }

    private void CopyFullToFiltered(string secretsDir)
    {
        var fullDir = Path.Combine(secretsDir, "jsondata_full");
        var filteredDir = Path.Combine(secretsDir, "jsondata");
        Directory.CreateDirectory(filteredDir);

        if (!Directory.Exists(fullDir)) return;

        foreach (var srcFile in Directory.GetFiles(fullDir, "*.json", SearchOption.AllDirectories))
        {
            var relPath = Path.GetRelativePath(fullDir, srcFile);
            var dstFile = Path.Combine(filteredDir, relPath);
            Directory.CreateDirectory(Path.GetDirectoryName(dstFile)!);
            File.Copy(srcFile, dstFile, true);
        }
    }

    private void StripDuplicateRows(string secretsDir, IProgress<ImportProgress>? progress)
    {
        var filteredDir = Path.Combine(secretsDir, "jsondata");
        var gameJsonDir = _config.OutputJsonDataDir;

        if (!Directory.Exists(filteredDir) || !Directory.Exists(gameJsonDir)) return;

        var jsonFiles = Directory.GetFiles(filteredDir, "*.json", SearchOption.AllDirectories)
            .OrderBy(f => new FileInfo(f).Length) // Small files first
            .ToList();

        int totalStripped = 0, filesStripped = 0;

        for (int i = 0; i < jsonFiles.Count; i++)
        {
            var secretsJson = jsonFiles[i];
            var relPath = Path.GetRelativePath(filteredDir, secretsJson);
            var gameJson = Path.Combine(gameJsonDir, relPath);

            var sizeMb = new FileInfo(secretsJson).Length / (1024.0 * 1024.0);
            progress?.Report(new("Filtering Secrets Data",
                $"Comparing {Path.GetFileName(secretsJson)} ({sizeMb:F1} MB)...",
                0.80 + 0.10 * (i + 1) / jsonFiles.Count));

            if (!File.Exists(gameJson)) continue;

            var (removed, _) = _jsonData.StripDuplicateRows(secretsJson, gameJson);
            if (removed > 0)
            {
                filesStripped++;
                totalStripped += removed;
            }
        }

        _logger.LogInformation("Stripped {TotalRows} rows from {Files} files",
            totalStripped, filesStripped);
    }

    private void CopyToNewSecrets(string secretsDir)
    {
        var filteredDir = Path.Combine(secretsDir, "jsondata");
        var newSecretsDir = _config.NewSecretsJsonDataDir;

        if (!Directory.Exists(filteredDir)) return;

        if (Directory.Exists(newSecretsDir))
            Directory.Delete(newSecretsDir, true);
        Directory.CreateDirectory(newSecretsDir);

        foreach (var srcFile in Directory.GetFiles(filteredDir, "*.json", SearchOption.AllDirectories))
        {
            var relPath = Path.GetRelativePath(filteredDir, srcFile);
            var dstFile = Path.Combine(newSecretsDir, relPath);
            Directory.CreateDirectory(Path.GetDirectoryName(dstFile)!);
            File.Copy(srcFile, dstFile, true);
        }
    }

    private void GenerateSecretsManifest(string secretsDir)
    {
        var jsonDataDir = Path.Combine(secretsDir, "jsondata");
        var manifestPath = Path.Combine(secretsDir, "secrets manifest.def");

        if (!Directory.Exists(jsonDataDir)) return;

        var jsonFiles = Directory.GetFiles(jsonDataDir, "*.json", SearchOption.AllDirectories);

        var root = new XElement("definition",
            new XElement("title", "Secrets Manifest"),
            new XElement("author", "Moria MOD Creator"),
            new XElement("description", $"{jsonFiles.Length} secrets files"));

        foreach (var jsonFile in jsonFiles)
        {
            var relPath = Path.GetRelativePath(jsonDataDir, jsonFile).Replace('\\', '/');
            root.Add(new XElement("mod", new XAttribute("file", $"Secrets Source/jsondata/{relPath}")));
        }

        var doc = new XDocument(new XDeclaration("1.0", "UTF-8", null), root);
        doc.Save(manifestPath);
        _logger.LogInformation("Generated secrets manifest with {Count} entries", jsonFiles.Length);
    }

    // --- Path conversion and file scanning utilities ---

    /// <summary>
    /// Scan includes.xml files for additional mod file paths.
    /// Secondary scan used when .def files reference an includes.xml.
    /// </summary>
    public HashSet<string> ScanIncludesXmlForModPaths()
    {
        var paths = new HashSet<string>();
        var defDir = _config.DefinitionsDir;
        if (!Directory.Exists(defDir)) return paths;

        foreach (var xmlFile in Directory.GetFiles(defDir, "includes.xml", SearchOption.AllDirectories))
        {
            try
            {
                var doc = XDocument.Load(xmlFile);
                foreach (var includeElem in doc.Descendants("include"))
                {
                    var filePath = includeElem.Attribute("file")?.Value;
                    if (filePath != null)
                        paths.Add(DefinitionService.NormalizePath(filePath));
                }
            }
            catch { /* skip invalid XML */ }
        }

        return paths;
    }

    /// <summary>
    /// Convert a JSON relative path to its corresponding .uasset path.
    /// e.g., "Moria/Content/Tech/Data/Items/DT_Weapons.json" →
    ///        "Moria/Content/Tech/Data/Items/DT_Weapons.uasset"
    /// </summary>
    public static string ConvertJsonPathToUasset(string jsonRelPath)
    {
        return Path.ChangeExtension(jsonRelPath, ".uasset");
    }

    /// <summary>
    /// Get all game file paths that need to be imported based on .def files.
    /// Returns paths relative to the game content directory.
    /// </summary>
    public HashSet<string> GetGameFilePathsToImport()
    {
        var paths = ScanDefFilesForGamePaths();

        // Also scan includes.xml
        var includesPaths = ScanIncludesXmlForModPaths();
        foreach (var p in includesPaths)
            paths.Add(p);

        return paths;
    }

    // --- Helpers ---

    private void CleanDirectories()
    {
        var dirs = new[]
        {
            _config.OutputRetocDir,
            _config.OutputJsonDataDir,
        };

        foreach (var dir in dirs)
        {
            if (Directory.Exists(dir))
                Directory.Delete(dir, true);
            Directory.CreateDirectory(dir);
        }

        // Clean secrets subdirectories
        var secretsDir = _config.SecretsSourceDir;
        if (Directory.Exists(secretsDir))
        {
            foreach (var subDir in new[] { "retoc", "jsondata", "jsondata_full" })
            {
                var path = Path.Combine(secretsDir, subDir);
                if (Directory.Exists(path))
                    Directory.Delete(path, true);
            }

            // Remove ZIPs
            foreach (var zip in Directory.GetFiles(secretsDir, "*.zip"))
            {
                try { File.Delete(zip); } catch { /* ignore */ }
            }

            // Clear extracted subdirectories (but keep .def and .ini files)
            foreach (var subdir in Directory.GetDirectories(secretsDir))
            {
                var name = Path.GetFileName(subdir);
                if (name is "retoc" or "jsondata" or "jsondata_full") continue;
                try { Directory.Delete(subdir, true); } catch { /* ignore */ }
            }
        }

        _logger.LogInformation("Cleaned import directories");
    }

    private HashSet<string> ScanDefFilesForGamePaths()
    {
        var paths = new HashSet<string>();
        var defDir = _config.DefinitionsDir;
        if (!Directory.Exists(defDir)) return paths;

        foreach (var defFile in Directory.GetFiles(defDir, "*.def", SearchOption.AllDirectories))
        {
            try
            {
                var doc = XDocument.Load(defFile);
                foreach (var modElem in doc.Descendants("mod"))
                {
                    var filePath = modElem.Attribute("file")?.Value;
                    if (filePath == null) continue;
                    if (filePath.Contains("Secrets Source", StringComparison.OrdinalIgnoreCase))
                        continue;
                    var normalized = DefinitionService.NormalizePath(filePath);
                    paths.Add(normalized);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to parse def file: {File}", defFile);
            }
        }

        return paths;
    }
}

public record ImportProgress(string Title, string Status, double Progress);
public record ImportResult(bool Success, string Message);
