using System.IO;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Simple file-based logger provider that appends log entries to MoriaMODCreator.log.
/// Thread-safe via lock. No external NuGet dependency needed.
/// </summary>
public sealed class FileLoggerProvider : ILoggerProvider
{
    private readonly string _filePath;
    private readonly LogLevel _minLevel;
    private readonly object _lock = new();

    public FileLoggerProvider(string filePath, LogLevel minLevel = LogLevel.Information)
    {
        _filePath = filePath;
        _minLevel = minLevel;
    }

    public ILogger CreateLogger(string categoryName) =>
        new FileLogger(categoryName, _filePath, _minLevel, _lock);

    public void Dispose() { }

    private sealed class FileLogger(string category, string filePath, LogLevel minLevel, object fileLock) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => logLevel >= minLevel;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state,
            Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (!IsEnabled(logLevel)) return;

            var level = logLevel switch
            {
                LogLevel.Trace => "TRACE",
                LogLevel.Debug => "DEBUG",
                LogLevel.Information => "INFO",
                LogLevel.Warning => "WARN",
                LogLevel.Error => "ERROR",
                LogLevel.Critical => "CRIT",
                _ => "????",
            };

            // Shorten category: "MoriaMODCreator.Services.CategoryDataService" → "CategoryDataService"
            var shortCat = category.Contains('.') ? category[(category.LastIndexOf('.') + 1)..] : category;

            var message = $"{DateTime.Now:HH:mm:ss} [{level}] {shortCat}: {formatter(state, exception)}";
            if (exception != null)
                message += $"\n  {exception.GetType().Name}: {exception.Message}";

            lock (fileLock)
            {
                try { File.AppendAllText(filePath, message + "\n"); }
                catch { /* ignore file write failures */ }
            }
        }
    }
}
