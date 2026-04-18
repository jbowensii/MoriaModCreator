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
    public const string ModeSecrets = "secrets";
    public const string ModeConstructions = "constructions";

    private readonly ConfigService _config;
    private readonly RetocService _retoc;
    private readonly UAssetService _uasset;
    private readonly JsonDataService _jsonData;
    private readonly ILogger<ImportService> _logger;
    private readonly System.Net.Http.HttpClient _httpClient;

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
        _httpClient = new System.Net.Http.HttpClient();
        _httpClient.Timeout = TimeSpan.FromMinutes(5);
        _httpClient.DefaultRequestHeaders.UserAgent.ParseAdd($"MoriaMODCreator/{Models.Constants.AppVersion}");
    }

    /// <summary>
    /// Combine a zip-entry relative path with a destination root, verifying the result
    /// stays inside the root. Guards against zip-slip (entries like "..\..\etc\passwd").
    /// </summary>
    private static string SafeCombine(string root, string relative)
    {
        var dest = Path.GetFullPath(Path.Combine(root, relative));
        var rootFull = Path.GetFullPath(root) + Path.DirectorySeparatorChar;
        if (!dest.StartsWith(rootFull, StringComparison.OrdinalIgnoreCase))
            throw new IOException($"Zip entry escapes destination: {relative}");
        return dest;
    }

    /// <summary>
    /// Run the complete combined import (game files + secrets).
    /// </summary>
    /// <param name="progress">Progress reporter</param>
    /// <param name="secretsZipProvider">
    /// Optional callback invoked on the UI thread to prompt the user for a secrets ZIP.
    /// Must be invoked via Dispatcher. Returns the path to the ZIP, or null to skip.
    /// </param>
    /// <param name="ct">Cancellation token</param>
    public async Task<ImportResult> RunCombinedImportAsync(
        IProgress<ImportProgress>? progress = null,
        Func<Task<string?>>? secretsZipProvider = null,
        CancellationToken ct = default)
    {
        try
        {
            // Immediate feedback — user sees this within milliseconds of clicking Import
            progress?.Report(new("Starting Import", "Initializing...", 0.01));

            // Step 1: Clean directories
            progress?.Report(new("Preparing Import", "Clearing previous import data...", 0.01));
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

            // Step 2.5: Prompt user for secrets ZIP if no ZIPs exist
            var secretsDir = _config.SecretsSourceDir;
            if (secretsZipProvider != null)
            {
                var existingZips = Directory.Exists(secretsDir)
                    ? Directory.GetFiles(secretsDir, "*.zip")
                    : Array.Empty<string>();
                if (existingZips.Length == 0)
                {
                    _logger.LogInformation("Import: prompting user for secrets ZIP");
                    progress?.Report(new("Secrets Required", "Waiting for secrets ZIP file...", 0.50));
                    var zipPath = await secretsZipProvider();
                    if (zipPath == null)
                    {
                        _logger.LogInformation("Import: user skipped secrets import");
                        progress?.Report(new("Import Complete", "Game files imported (secrets skipped).", 1.0));
                        return new ImportResult(true, "Game files imported successfully (secrets skipped)");
                    }
                }
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

    // GitHub repo ZIP for Tobi's full secrets repo (main branch only, no fallback)
    // Contains: /json/Moria/Content/... (DataTable JSON), /StringTables/*.json, and other assets
    private const string GitHubZipUrl =
        "https://github.com/TobiIchiro/SecretsOfKhazadDum/archive/refs/heads/main.zip";
    private const string GitHubZipFilename = "SecretsOfKhazadDum.zip";

    /// <summary>
    /// Run the secrets-only import pipeline.
    /// 1. Download TobiIchiro/SecretsOfKhazadDum full repo ZIP (no fallback)
    /// 2. Unzip to Secrets Source/github/, then delete the ZIP
    /// 3. Copy github/json/Moria/Content/** → jsondata_github/modified-json/Moria/Content/**
    /// 4. Copy github/StringTables/** → cache/secrets/string_tables/
    /// 5. Strip game-duplicate rows from secrets JSON into jsondata/
    /// 6. Copy to New Secrets + generate manifest
    /// </summary>
    public async Task<ImportResult> ImportSecretsAsync(
        IProgress<ImportProgress>? progress = null,
        CancellationToken ct = default)
    {
        var secretsDir = _config.SecretsSourceDir;
        Directory.CreateDirectory(secretsDir);

        var githubRawDir = _config.SecretsGitHubRawDir;        // Secrets Source/github/
        var jsonDataGitHubDir = _config.SecretsJsonDataGitHubDir; // Secrets Source/jsondata_github/

        // Clear and recreate both directories
        foreach (var dir in new[] { githubRawDir, jsonDataGitHubDir })
        {
            if (Directory.Exists(dir))
                Directory.Delete(dir, true);
            Directory.CreateDirectory(dir);
        }

        // =====================================================
        // Step 1: Download full repo ZIP from TobiIchiro/SecretsOfKhazadDum main
        // =====================================================
        progress?.Report(new("Importing Secrets", "Downloading full repo from GitHub...", 0.51));
        _logger.LogInformation("Secrets: downloading GitHub repo (TobiIchiro/SecretsOfKhazadDum main)");
        var githubSuccess = await DownloadGitHubRepoAsync(secretsDir, progress, ct);

        if (!githubSuccess)
        {
            _logger.LogError("Secrets: GitHub download failed — cannot proceed");
            progress?.Report(new("GitHub Download Failed",
                "Could not download from TobiIchiro/SecretsOfKhazadDum main branch.", 0.55));
            return new ImportResult(false,
                "Failed to download secrets data from GitHub (TobiIchiro/SecretsOfKhazadDum main). " +
                "Check your internet connection and try again.");
        }

        progress?.Report(new("Importing Secrets", "GitHub download successful!", 0.55));

        // =====================================================
        // Step 2: Unzip to Secrets Source/github/, then delete the ZIP
        // =====================================================
        progress?.Report(new("Importing Secrets", "Extracting repo contents...", 0.60));
        var extracted = await Task.Run(() => ExtractGitHubJsonFiles(secretsDir, githubRawDir), ct);
        _logger.LogInformation("Secrets: extracted {Count} files from GitHub → {Dir}", extracted, githubRawDir);

        if (extracted == 0)
        {
            return new ImportResult(false,
                "GitHub ZIP downloaded but no files found inside. " +
                "The repository structure may have changed.");
        }

        // Delete the ZIP file — no longer needed after extraction
        var zipPath = Path.Combine(secretsDir, GitHubZipFilename);
        try
        {
            if (File.Exists(zipPath))
            {
                File.Delete(zipPath);
                _logger.LogInformation("Deleted GitHub ZIP after extraction: {Path}", zipPath);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Could not delete GitHub ZIP (non-fatal)");
        }

        // =====================================================
        // Step 3: Copy github/json/Moria/Content/** → jsondata_github/modified-json/Moria/Content/**
        // =====================================================
        progress?.Report(new("Importing Secrets", "Organizing secrets JSON...", 0.68));
        _logger.LogInformation("Secrets: copying json/Moria/Content → jsondata_github/modified-json/Moria/Content");
        var jsonCopied = await Task.Run(() => CopyJsonContentToJsondataGitHub(githubRawDir, jsonDataGitHubDir), ct);
        if (jsonCopied == 0)
        {
            return new ImportResult(false,
                "json/Moria/Content/ not found inside downloaded repo. " +
                "The repository structure may have changed.");
        }

        // =====================================================
        // Step 4: Copy StringTables/ from github/ → cache/secrets/string_tables/
        // =====================================================
        progress?.Report(new("Importing Secrets", "Copying string tables to cache...", 0.75));
        _logger.LogInformation("Secrets: copying StringTables to cache");
        var stringTablesCopied = await Task.Run(() => CopyStringTablesToCache(githubRawDir), ct);
        if (stringTablesCopied == 0)
        {
            return new ImportResult(false,
                "StringTables/ folder not found inside downloaded repo. " +
                "The repository structure may have changed.");
        }

        // =====================================================
        // Step 5: Extract companion paks from user-provided Nexus ZIP
        // (SecretsOfKhazadDum_LocTags_P.pak, TobiModsAddons_P.*)
        // These are packaged as-is into the final mod ZIP by Build Phase F.
        // =====================================================
        progress?.Report(new("Importing Secrets", "Extracting companion pak files...", 0.78));
        _logger.LogInformation("Secrets: extracting companion paks from Nexus ZIP");
        await Task.Run(() => ExtractCompanionPaksFromNexusZip(secretsDir), ct);

        // =====================================================
        // Step 6: Filter (strip game duplicate rows)
        // Source: jsondata_github/modified-json/Moria/  →  jsondata/
        // =====================================================
        progress?.Report(new("Filtering Secrets", "Removing game data from secrets...", 0.82));
        _logger.LogInformation("Secrets: stripping duplicate rows");
        await Task.Run(() => CopyModifiedJsonToFiltered(secretsDir), ct);
        await Task.Run(() => StripDuplicateRows(secretsDir, progress), ct);

        // =====================================================
        // Step 6: Copy filtered secrets to New Secrets + manifest
        // =====================================================
        progress?.Report(new("Finalizing", "Copying to New Secrets...", 0.92));
        _logger.LogInformation("Secrets: copying to New Secrets");
        await Task.Run(() => CopyToNewSecrets(secretsDir), ct);

        progress?.Report(new("Finalizing", "Generating manifest...", 0.95));
        _logger.LogInformation("Secrets: generating manifest");
        await Task.Run(() => GenerateSecretsManifest(secretsDir), ct);

        return new ImportResult(true, "Secrets import completed");
    }

    // =========================================================================
    // GITHUB DOWNLOADS
    // Full TobiIchiro/SecretsOfKhazadDum repo ZIP from main branch. No fallback.
    // =========================================================================

    /// <summary>
    /// Download TobiIchiro/SecretsOfKhazadDum full repo ZIP (main branch).
    /// Streams to disk to avoid loading the entire ZIP into memory.
    /// No fallback — if this URL fails, returns false.
    /// </summary>
    private async Task<bool> DownloadGitHubRepoAsync(
        string secretsDir, IProgress<ImportProgress>? progress, CancellationToken ct)
    {
        var zipPath = Path.Combine(secretsDir, GitHubZipFilename);

        if (File.Exists(zipPath))
        {
            try { File.Delete(zipPath); }
            catch (Exception ex) { _logger.LogDebug(ex, "Could not delete old ZIP before download"); }
        }

        try
        {
            progress?.Report(new("Importing Secrets",
                "Downloading SecretsOfKhazadDum from GitHub...", 0.52));

            using var response = await _httpClient.GetAsync(GitHubZipUrl,
                System.Net.Http.HttpCompletionOption.ResponseHeadersRead, ct);
            response.EnsureSuccessStatusCode();

            await using var fileStream = File.Create(zipPath);
            await response.Content.CopyToAsync(fileStream, ct);

            var sizeKb = new FileInfo(zipPath).Length / 1024;
            _logger.LogInformation("Downloaded SecretsOfKhazadDum repo ({Size} KB) from {Url}", sizeKb, GitHubZipUrl);
            return true;
        }
        catch (System.Net.Http.HttpRequestException ex)
        {
            _logger.LogError(ex, "GitHub download failed for {Url}", GitHubZipUrl);
            return false;
        }
    }

    /// <summary>
    /// Extract the entire GitHub repo ZIP to Secrets Source/github/.
    /// Strips the top-level repo folder (e.g. "SecretsOfKhazadDum-main/")
    /// but preserves the full directory tree underneath (json/, StringTables/, scripts/, etc.).
    /// Returns the number of files extracted.
    /// </summary>
    private int ExtractGitHubJsonFiles(string secretsDir, string githubDir, CancellationToken ct = default)
    {
        var zipPath = Path.Combine(secretsDir, GitHubZipFilename);
        if (!File.Exists(zipPath)) return 0;

        try
        {
            using var archive = ZipFile.OpenRead(zipPath);

            // GitHub ZIPs have a single root folder like "SecretsOfKhazadDum-main/"
            // Detect and strip it so extraction lands directly under github/.
            string? rootPrefix = null;
            foreach (var entry in archive.Entries)
            {
                var slashIdx = entry.FullName.IndexOf('/');
                if (slashIdx > 0)
                {
                    rootPrefix = entry.FullName[..(slashIdx + 1)];
                    break;
                }
            }

            if (rootPrefix == null)
            {
                _logger.LogWarning("GitHub ZIP has no root folder — extracting as-is");
                rootPrefix = "";
            }

            _logger.LogInformation("Stripping root prefix from ZIP: {Prefix}", rootPrefix);

            int filesExtracted = 0;
            foreach (var entry in archive.Entries)
            {
                ct.ThrowIfCancellationRequested();

                if (entry.FullName == rootPrefix || string.IsNullOrEmpty(entry.FullName)) continue;
                if (!entry.FullName.StartsWith(rootPrefix, StringComparison.Ordinal)) continue;

                var relativePath = entry.FullName[rootPrefix.Length..];
                if (string.IsNullOrEmpty(relativePath)) continue;

                if (string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(SafeCombine(githubDir, relativePath));
                }
                else
                {
                    var destPath = SafeCombine(githubDir, relativePath);
                    Directory.CreateDirectory(Path.GetDirectoryName(destPath)!);
                    entry.ExtractToFile(destPath, overwrite: true);
                    filesExtracted++;
                }
            }

            _logger.LogInformation("Extracted {Count} files from GitHub ZIP to github/", filesExtracted);
            return filesExtracted;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to extract GitHub ZIP");
            return 0;
        }
    }

    /// <summary>
    /// Copy github/json/Moria/Content/** → jsondata_github/modified-json/Moria/Content/**
    /// Walks the entire json/Moria/Content directory tree, preserves full structure.
    /// Returns the number of files copied.
    /// </summary>
    private int CopyJsonContentToJsondataGitHub(string githubRawDir, string jsonDataGitHubDir, CancellationToken ct = default)
    {
        var sourceDir = Path.Combine(githubRawDir, "json", "Moria", "Content");
        var destDir = Path.Combine(jsonDataGitHubDir, "modified-json", "Moria", "Content");

        if (!Directory.Exists(sourceDir))
        {
            _logger.LogWarning("json/Moria/Content not found in extracted repo at {Path}", sourceDir);
            return 0;
        }

        Directory.CreateDirectory(destDir);

        int copied = 0;
        foreach (var srcFile in Directory.GetFiles(sourceDir, "*", SearchOption.AllDirectories))
        {
            ct.ThrowIfCancellationRequested();
            var relPath = Path.GetRelativePath(sourceDir, srcFile);
            var dstFile = Path.Combine(destDir, relPath);
            Directory.CreateDirectory(Path.GetDirectoryName(dstFile)!);
            File.Copy(srcFile, dstFile, true);
            copied++;
        }

        _logger.LogInformation("Copied {Count} files from github/json/Moria/Content → jsondata_github/modified-json/Moria/Content", copied);
        return copied;
    }

    /// <summary>
    /// Copy StringTables/*.json from the extracted repo (Secrets Source/github/StringTables/)
    /// to %APPDATA%/MoriaMODCreator/cache/secrets/string_tables/.
    /// Needed by BuildingsDataService.ResolveDisplayNames for display name lookup.
    /// Returns the number of files copied.
    /// </summary>
    private int CopyStringTablesToCache(string githubRawDir, CancellationToken ct = default)
    {
        var sourceDir = Path.Combine(githubRawDir, "StringTables");
        var destDir = Path.Combine(_config.CacheDir, "secrets", "string_tables");

        if (Directory.Exists(destDir))
            Directory.Delete(destDir, true);
        Directory.CreateDirectory(destDir);

        if (!Directory.Exists(sourceDir))
        {
            _logger.LogWarning("StringTables/ not found in extracted repo at {Path}", sourceDir);
            return 0;
        }

        int copied = 0;
        foreach (var srcFile in Directory.GetFiles(sourceDir, "*.json", SearchOption.AllDirectories))
        {
            ct.ThrowIfCancellationRequested();
            var relPath = Path.GetRelativePath(sourceDir, srcFile);
            var dstFile = Path.Combine(destDir, relPath);
            Directory.CreateDirectory(Path.GetDirectoryName(dstFile)!);
            File.Copy(srcFile, dstFile, true);
            copied++;
        }

        _logger.LogInformation("Copied {Count} string tables to cache/secrets/string_tables/", copied);
        return copied;
    }

    /// <summary>
    /// Extract companion pak files (SecretsOfKhazadDum_LocTags_P.pak, TobiModsAddons_P.*)
    /// from the user-provided Nexus ZIP (any .zip in Secrets Source/ that isn't the GitHub ZIP).
    /// These are stored in Secrets Source/companion_paks/ for Build Phase F to copy as-is.
    /// </summary>
    private void ExtractCompanionPaksFromNexusZip(string secretsDir)
    {
        var companionDir = Path.Combine(secretsDir, "companion_paks");
        if (Directory.Exists(companionDir))
            Directory.Delete(companionDir, true);
        Directory.CreateDirectory(companionDir);

        var companionNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "SecretsOfKhazadDum_LocTags_P.pak",
            "TobiModsAddons_P.pak",
            "TobiModsAddons_P.ucas",
            "TobiModsAddons_P.utoc",
        };

        // Find all ZIPs in Secrets Source (the GitHub ZIP was already deleted)
        var zipFiles = Directory.GetFiles(secretsDir, "*.zip");
        int extracted = 0;

        foreach (var zipFile in zipFiles)
        {
            try
            {
                using var archive = ZipFile.OpenRead(zipFile);
                foreach (var entry in archive.Entries)
                {
                    if (string.IsNullOrEmpty(entry.Name)) continue;
                    if (!companionNames.Contains(entry.Name)) continue;

                    var destPath = SafeCombine(companionDir, entry.Name);
                    entry.ExtractToFile(destPath, overwrite: true);
                    extracted++;
                    _logger.LogInformation("Extracted companion pak: {Name} from {Zip}",
                        entry.Name, Path.GetFileName(zipFile));
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Could not read ZIP {Zip} for companion paks", Path.GetFileName(zipFile));
            }
        }

        if (extracted > 0)
            _logger.LogInformation("Extracted {Count} companion paks to {Dir}", extracted, companionDir);
        else
            _logger.LogWarning("No companion pak files found in any ZIP in Secrets Source/");
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
        progress?.Report(new("Phase 1/5: Scanning", "Scanning definition files for required paths...", 0.02));
        var requiredPaths = ScanDefFilesForGamePaths();

        // Always extract the 8 category DataTable JSONs needed by Secrets + Constructions views
        // These may not be referenced by any .def file but are required for filtering and display
        foreach (var catPath in CategoryDataService.SecretsPaths.Values)
        {
            requiredPaths.Add($"Moria/Content/{catPath.DefinitionPath}");
            if (catPath.RecipePath != null)
                requiredPaths.Add($"Moria/Content/{catPath.RecipePath}");
        }

        progress?.Report(new("Phase 1/5: Scanning", $"Found {requiredPaths.Count} required game files.", 0.04));
        _logger.LogInformation("Found {Count} required game file paths (including mandatory category files)", requiredPaths.Count);

        // Create temp dir with game pak + global files
        var tempPaks = Path.Combine(Path.GetTempPath(), $"game_paks_{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempPaks);

        try
        {
            // Copy global index files
            progress?.Report(new("Phase 2/5: Copying", "Copying global index files...", 0.05));
            foreach (var name in new[] { "global.ucas", "global.utoc" })
            {
                var src = Path.Combine(gamePaksPath, name);
                if (File.Exists(src))
                {
                    progress?.Report(new("Phase 2/5: Copying", $"Copying {name}...", 0.06));
                    File.Copy(src, Path.Combine(tempPaks, name));
                }
            }

            // Copy main game pak (large files — stream with progress)
            var exts = new[] { ".pak", ".ucas", ".utoc" };
            for (int i = 0; i < exts.Length; i++)
            {
                var ext = exts[i];
                var src = Path.Combine(gamePaksPath, $"Moria-WindowsNoEditor{ext}");
                if (File.Exists(src))
                {
                    var fileSize = new FileInfo(src).Length;
                    var sizeMb = fileSize / (1024.0 * 1024.0);
                    var basePct = 0.07 + 0.03 * i / exts.Length;
                    var pctRange = 0.03 / exts.Length;

                    progress?.Report(new("Phase 2/5: Copying",
                        $"Copying Moria-WindowsNoEditor{ext} ({sizeMb:F0} MB)...", basePct));
                    _logger.LogInformation("Copying {File} ({Size} MB)...", Path.GetFileName(src), sizeMb.ToString("F0"));

                    var dst = Path.Combine(tempPaks, $"Moria-WindowsNoEditor{ext}");

                    // Stream copy with progress for large files (15GB+)
                    await Task.Run(() =>
                    {
                        ct.ThrowIfCancellationRequested();
                        using var srcStream = new FileStream(src, FileMode.Open, FileAccess.Read, FileShare.Read, 81920);
                        using var dstStream = new FileStream(dst, FileMode.Create, FileAccess.Write, FileShare.None, 81920);
                        var buffer = new byte[81920];
                        long totalCopied = 0;
                        long lastReportAt = 0;
                        int bytesRead;
                        while ((bytesRead = srcStream.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            ct.ThrowIfCancellationRequested();
                            dstStream.Write(buffer, 0, bytesRead);
                            totalCopied += bytesRead;

                            // Report progress every 100MB
                            if (totalCopied - lastReportAt > 100 * 1024 * 1024)
                            {
                                lastReportAt = totalCopied;
                                var copiedMb = totalCopied / (1024.0 * 1024.0);
                                var filePct = basePct + pctRange * totalCopied / fileSize;
                                progress?.Report(new("Phase 2/5: Copying",
                                    $"Copying Moria-WindowsNoEditor{ext} — {copiedMb:F0}/{sizeMb:F0} MB", filePct));
                            }
                        }
                    }, ct);

                    progress?.Report(new("Phase 2/5: Copying",
                        $"Copied Moria-WindowsNoEditor{ext} ({sizeMb:F0} MB)", basePct + pctRange));
                }
            }

            // Run retoc to-legacy — slow step, add heartbeat to show files appearing
            progress?.Report(new("Phase 3/5: Extracting",
                "Extracting game assets with retoc (this takes 1-2 minutes)...", 0.12));

            // Start a heartbeat timer that counts files as retoc extracts them
            using var heartbeat = new System.Timers.Timer(3000);
            heartbeat.Elapsed += (_, _) =>
            {
                try
                {
                    if (Directory.Exists(retocDir))
                    {
                        var count = Directory.GetFiles(retocDir, "*.uasset", SearchOption.AllDirectories).Length;
                        progress?.Report(new("Phase 3/5: Extracting",
                            $"retoc extracting... {count} files so far", 0.14));
                    }
                }
                catch { /* ignore timer race conditions */ }
            };
            heartbeat.Start();

            RetocResult result;
            try
            {
                result = await _retoc.ToLegacyAsync(tempPaks, retocDir, ct: ct);
            }
            finally
            {
                heartbeat.Stop();
            }

            var finalCount = Directory.Exists(retocDir)
                ? Directory.GetFiles(retocDir, "*.uasset", SearchOption.AllDirectories).Length
                : 0;
            progress?.Report(new("Phase 3/5: Extracting",
                $"retoc extraction complete — {finalCount} files extracted.", 0.25));
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
            progress?.Report(new("Phase 4/5: Converting", "Finding extracted uasset files...", 0.30));
            var uassetFiles = new List<string>();
            foreach (var reqPath in requiredPaths)
            {
                var uassetPath = Path.Combine(retocDir, Path.ChangeExtension(reqPath, ".uasset"));
                if (File.Exists(uassetPath))
                    uassetFiles.Add(uassetPath);
            }

            if (uassetFiles.Count > 0)
            {
                progress?.Report(new("Phase 4/5: Converting",
                    $"Converting {uassetFiles.Count} files to JSON...", 0.30,
                    0, uassetFiles.Count));

                var convResult = await _uasset.BatchToJsonAsync(
                    uassetFiles, retocDir, jsonDataDir,
                    new Progress<(int Done, int Total)>(p =>
                        progress?.Report(new("Phase 4/5: Converting",
                            $"Converting {p.Done}/{p.Total} files to JSON...",
                            0.30 + 0.15 * p.Done / Math.Max(p.Total, 1),
                            p.Done, p.Total))),
                    ct);
                _logger.LogInformation("Game files: converted {Converted}/{Total}",
                    convResult.Converted, uassetFiles.Count);
            }

            progress?.Report(new("Phase 5/5: Finalizing", "Game file import complete.", 0.48));

            return true;
        }
        finally
        {
            try { Directory.Delete(tempPaks, true); } catch { /* cleanup */ }
        }
    }

    // --- Secrets filter pipeline ---

    /// <summary>
    /// Copy jsondata_github/modified-json/Moria/* → jsondata/Moria/* (strips the modified-json/ prefix
    /// so jsondata/ mirrors Moria/Content/... directly, matching game JSON layout).
    /// </summary>
    private void CopyModifiedJsonToFiltered(string secretsDir)
    {
        var sourceDir = Path.Combine(_config.SecretsJsonDataGitHubDir, "modified-json");
        var filteredDir = Path.Combine(secretsDir, "jsondata");

        if (Directory.Exists(filteredDir))
            Directory.Delete(filteredDir, true);
        Directory.CreateDirectory(filteredDir);

        if (!Directory.Exists(sourceDir))
        {
            _logger.LogWarning("Expected modified-json/ inside jsondata_github/ — not found at {Path}", sourceDir);
            return;
        }

        foreach (var srcFile in Directory.GetFiles(sourceDir, "*.json", SearchOption.AllDirectories))
        {
            var relPath = Path.GetRelativePath(sourceDir, srcFile);
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
            catch (System.Xml.XmlException ex)
            {
                _logger.LogWarning(ex, "Skipping invalid .def XML file: {File}", xmlFile);
            }
            catch (System.IO.IOException ex)
            {
                _logger.LogWarning(ex, "Failed to read .def file: {File}", xmlFile);
            }
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
            // Active directories (recreated fresh on each import)
            foreach (var subDir in new[] { "jsondata", "github", "jsondata_github", "companion_paks" })
            {
                var path = Path.Combine(secretsDir, subDir);
                if (Directory.Exists(path))
                    Directory.Delete(path, true);
            }

            // Legacy directories from prior versions — remove if still present
            foreach (var legacy in new[] { "jsondata_full", "retoc" })
            {
                var legacyPath = Path.Combine(secretsDir, legacy);
                if (Directory.Exists(legacyPath))
                {
                    try { Directory.Delete(legacyPath, true); }
                    catch (Exception ex) { _logger.LogWarning(ex, "Could not remove legacy directory {Path}", legacyPath); }
                }
            }

            // Remove any stale ZIPs (a fresh ZIP gets downloaded and then deleted during import)
            foreach (var zip in Directory.GetFiles(secretsDir, "*.zip"))
            {
                try { File.Delete(zip); }
                catch (Exception ex) { _logger.LogWarning(ex, "Could not delete stale ZIP {Path}", zip); }
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

public record ImportProgress(string Title, string Status, double Progress, int FilesDone = 0, int FilesTotal = 0, int Errors = 0);
public record ImportResult(bool Success, string Message);
