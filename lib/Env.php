<?php
declare(strict_types=1);

/**
 * Env — reads the .env file that lives OUTSIDE the web root.
 *
 * The project root is the web root here, so a .env sitting next to the
 * code would be one .htaccess mistake away from being downloadable.
 * The file lives in /home/votolibre/config/peru2026/ instead.
 */
final class Env
{
    private const DEFAULT_PATH = '/home/votolibre/config/peru2026/.env';

    private static array $values = [];
    private static bool $loaded = false;

    public static function load(?string $path = null): void
    {
        if (self::$loaded) {
            return;
        }
        $path ??= getenv('APP_ENV_FILE') ?: self::DEFAULT_PATH;

        if (!is_readable($path)) {
            throw new RuntimeException('Environment file not readable');
        }
        foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            $line = trim($line);
            if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) {
                continue;
            }
            [$key, $value] = explode('=', $line, 2);
            self::$values[trim($key)] = trim($value, " \t\"'");
        }
        self::$loaded = true;
    }

    public static function get(string $key, ?string $default = null): ?string
    {
        self::load();
        return self::$values[$key] ?? $default;
    }

    /** Fails loudly at boot instead of silently later with an empty token. */
    public static function require(string $key): string
    {
        $value = self::get($key);
        if ($value === null || $value === '') {
            throw new RuntimeException("Missing required environment key: {$key}");
        }
        return $value;
    }
}
