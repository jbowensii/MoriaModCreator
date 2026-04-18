using System.IO;
using System.IO.Compression;
using Microsoft.Extensions.Logging.Abstractions;
using MoriaMODCreator.Services;
using Xunit;

namespace MoriaMODCreator.Tests;

public class ImportServiceTests
{
    // =========================================================================
    // ExtractGitHubJsonFiles logic (tested via helper that mirrors the method)
    // =========================================================================

    [Fact]
    public void ExtractGitHubJsonFiles_ExtractsFullRepoTree()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), $"test_github_{Guid.NewGuid():N}");
        var zipPath = Path.Combine(tempDir, "SecretsOfKhazadDum.zip");
        var outputDir = Path.Combine(tempDir, "github");
        Directory.CreateDirectory(tempDir);
        Directory.CreateDirectory(outputDir);

        try
        {
            // Create a mock TobiIchiro/SecretsOfKhazadDum ZIP structure
            using (var stream = new FileStream(zipPath, FileMode.Create))
            using (var archive = new ZipArchive(stream, ZipArchiveMode.Create))
            {
                // DataTable JSON in json/Moria/Content/...
                var entry = archive.CreateEntry("SecretsOfKhazadDum-main/json/Moria/Content/Tech/Data/Items/DT_Weapons.json");
                using (var writer = new StreamWriter(entry.Open()))
                    writer.Write("{\"test\": true}");

                var entry2 = archive.CreateEntry("SecretsOfKhazadDum-main/json/Moria/Content/Tech/Data/Building/DT_Constructions.json");
                using (var writer2 = new StreamWriter(entry2.Open()))
                    writer2.Write("{\"test2\": true}");

                // StringTables at repo root
                var entry3 = archive.CreateEntry("SecretsOfKhazadDum-main/StringTables/ST_Mod_Items.json");
                using (var writer3 = new StreamWriter(entry3.Open()))
                    writer3.Write("{\"strings\": true}");

                // Other repo folders also kept
                var entry4 = archive.CreateEntry("SecretsOfKhazadDum-main/scripts/build.sh");
                using (var writer4 = new StreamWriter(entry4.Open()))
                    writer4.Write("#!/bin/sh");

                // README at root
                var entry5 = archive.CreateEntry("SecretsOfKhazadDum-main/README.md");
                using (var writer5 = new StreamWriter(entry5.Open()))
                    writer5.Write("# README");
            }

            int extracted = ExtractGitHubJsonFilesHelper(zipPath, outputDir);

            Assert.Equal(5, extracted);
            // json/ tree preserved — this is where DataTable JSON lives now
            Assert.True(File.Exists(Path.Combine(outputDir, "json", "Moria", "Content", "Tech", "Data", "Items", "DT_Weapons.json")));
            Assert.True(File.Exists(Path.Combine(outputDir, "json", "Moria", "Content", "Tech", "Data", "Building", "DT_Constructions.json")));
            // StringTables/ at root, ready to be copied to cache
            Assert.True(File.Exists(Path.Combine(outputDir, "StringTables", "ST_Mod_Items.json")));
            // Non-DataTable files kept (full tree extraction)
            Assert.True(File.Exists(Path.Combine(outputDir, "scripts", "build.sh")));
            Assert.True(File.Exists(Path.Combine(outputDir, "README.md")));

            var content = File.ReadAllText(Path.Combine(outputDir, "json", "Moria", "Content", "Tech", "Data", "Items", "DT_Weapons.json"));
            Assert.Contains("test", content);
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void ExtractGitHubJsonFiles_ReturnsZero_WhenZipEmpty()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), $"test_github_{Guid.NewGuid():N}");
        var zipPath = Path.Combine(tempDir, "test.zip");
        var outputDir = Path.Combine(tempDir, "output");
        Directory.CreateDirectory(tempDir);
        Directory.CreateDirectory(outputDir);

        try
        {
            // Create an empty ZIP (no entries at all)
            using (var stream = new FileStream(zipPath, FileMode.Create))
            using (var _ = new ZipArchive(stream, ZipArchiveMode.Create))
            {
                // no entries
            }

            int extracted = ExtractGitHubJsonFilesHelper(zipPath, outputDir);
            Assert.Equal(0, extracted);
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void ExtractGitHubJsonFiles_ReturnsZero_WhenZipMissing()
    {
        var outputDir = Path.Combine(Path.GetTempPath(), $"test_output_{Guid.NewGuid():N}");
        Directory.CreateDirectory(outputDir);
        try
        {
            int extracted = ExtractGitHubJsonFilesHelper(
                Path.Combine(Path.GetTempPath(), "nonexistent.zip"), outputDir);
            Assert.Equal(0, extracted);
        }
        finally
        {
            Directory.Delete(outputDir, true);
        }
    }

    // =========================================================================
    // ImportProgress record
    // =========================================================================

    [Fact]
    public void ImportProgress_DefaultFileCountsAreZero()
    {
        var p = new ImportProgress("Title", "Status", 0.5);
        Assert.Equal(0, p.FilesDone);
        Assert.Equal(0, p.FilesTotal);
        Assert.Equal(0, p.Errors);
    }

    [Fact]
    public void ImportProgress_WithFileCounts()
    {
        var p = new ImportProgress("Title", "Status", 0.5, 10, 20, 2);
        Assert.Equal(10, p.FilesDone);
        Assert.Equal(20, p.FilesTotal);
        Assert.Equal(2, p.Errors);
    }

    // =========================================================================
    // Helper — mirrors ImportService.ExtractGitHubJsonFiles logic (full repo extraction)
    // =========================================================================

    private static int ExtractGitHubJsonFilesHelper(string zipPath, string outputDir)
    {
        if (!File.Exists(zipPath)) return 0;

        try
        {
            using var archive = ZipFile.OpenRead(zipPath);

            // Detect the top-level repo folder (e.g. "RtoM-ArmorBuildings-Mod-NoFatStacks/")
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
            if (rootPrefix == null) rootPrefix = "";

            int filesExtracted = 0;
            foreach (var entry in archive.Entries)
            {
                if (entry.FullName == rootPrefix || string.IsNullOrEmpty(entry.FullName)) continue;
                if (!entry.FullName.StartsWith(rootPrefix, StringComparison.Ordinal)) continue;

                var relativePath = entry.FullName[rootPrefix.Length..];
                if (string.IsNullOrEmpty(relativePath)) continue;

                if (string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(Path.Combine(outputDir, relativePath));
                }
                else
                {
                    var destPath = Path.Combine(outputDir, relativePath);
                    Directory.CreateDirectory(Path.GetDirectoryName(destPath)!);
                    entry.ExtractToFile(destPath, overwrite: true);
                    filesExtracted++;
                }
            }
            return filesExtracted;
        }
        catch
        {
            return 0;
        }
    }
}
