<?php
declare(strict_types=1);

require __DIR__ . '/vendor/autoload.php';

use Aws\BedrockAgent\BedrockAgentClient;
use Aws\S3\S3Client;
use Aws\Exception\AwsException;
use GuzzleHttp\Promise\Utils;

header('Content-Type: application/json; charset=utf-8');

// =========================
// Config
// =========================

// compras
#$KB_ID = "B0J6EB9XUO";
#$DS_ID = "WKSWJ0IDZB";

// destino (BDA)
#$BUCKET_BDA = "miu-documentos-compras-bedrock-procesing";


// produccion
$KB_ID = "ZLSIIBQ6B3";
$DS_ID = "4FQEKRDVOD";

// destino (BDA)
$BUCKET_BDA = "miu-documentos-bedrock-procesing";


$REGION = 'us-west-2';
$TARGET_PHRASE = 'no text content found in the files';
$TZ_GT = new DateTimeZone('America/Guatemala');

// =========================
// Load .env
// =========================
$envFile = __DIR__ . '/.env';
// $envFile = '/home/desait/.env';

if (!file_exists($envFile)) {
    throw new RuntimeException("Archivo .env no encontrado en: {$envFile}");
}
$env = parse_ini_file($envFile);

$AWS_REGION = $env['AWS_REGION'] ?? $REGION;
$AWS_KEY    = $env['AWS_ACCESS_KEY_ID'] ?? null;
$AWS_SECRET = $env['AWS_SECRET_ACCESS_KEY'] ?? null;

if (!$AWS_KEY || !$AWS_SECRET) {
    throw new RuntimeException("Credenciales AWS incompletas en .env");
}

// =========================
// AWS Clients
// =========================
$bedrock = new BedrockAgentClient([
    'region'      => $AWS_REGION,
    'version'     => 'latest',
    'credentials' => ['key' => $AWS_KEY, 'secret' => $AWS_SECRET],
    'suppress_php_deprecation_warning' => true,
]);

$s3 = new S3Client([
    'region'      => $AWS_REGION,
    'version'     => 'latest',
    'credentials' => ['key' => $AWS_KEY, 'secret' => $AWS_SECRET],
    'suppress_php_deprecation_warning' => true,
]);

// =========================
// Helpers
// =========================
function endsWith(string $haystack, string $needle): bool {
    $len = strlen($needle);
    if ($len === 0) return true;
    return substr($haystack, -$len) === $needle;
}

function normalizeFailureReasons(array $failureReasons): array {
    $out = [];
    foreach ($failureReasons as $r) {
        if (is_string($r)) {
            $s = trim($r);
            if ($s !== '' && $s[0] === '[' && substr($s, -1) === ']') {
                $parsed = json_decode($s, true);
                if (is_array($parsed)) {
                    foreach ($parsed as $x) {
                        if (is_string($x)) $out[] = $x;
                    }
                    continue;
                }
            }
            $out[] = $r;
        } else {
            $out[] = (string)$r;
        }
    }
    return $out;
}

function extractS3Uris(string $text): array {
    preg_match_all('/s3:\/\/[^\s,\]]+/i', $text, $m);
    return $m[0] ?? [];
}

function dedupePreserveOrder(array $arr): array {
    $seen = [];
    $out = [];
    foreach ($arr as $v) {
        if (!isset($seen[$v])) {
            $seen[$v] = true;
            $out[] = $v;
        }
    }
    return $out;
}

function parseS3Uri(string $uri): array {
    if (stripos($uri, 's3://') !== 0) {
        throw new RuntimeException("Invalid S3 URI: {$uri}");
    }
    $noScheme = substr($uri, 5);
    $pos = strpos($noScheme, '/');
    if ($pos === false) return [$noScheme, ''];
    return [substr($noScheme, 0, $pos), substr($noScheme, $pos + 1)];
}

function toN8nPath(string $bucket, string $key): string {
    // Formato como tu imagen: /bucket/key
    return '/' . $bucket . '/' . $key;
}

function listLatestJobSummary(BedrockAgentClient $bedrock, string $kbId, string $dsId): ?array {
    $resp = $bedrock->listIngestionJobs([
        'knowledgeBaseId' => $kbId,
        'dataSourceId'    => $dsId,
        'sortBy'          => ['attribute' => 'STARTED_AT', 'order' => 'DESCENDING'],
        'maxResults'      => 1,
    ]);
    return $resp['ingestionJobSummaries'][0] ?? null;
}

function pickLatestFinishedJobId(BedrockAgentClient $bedrock, string $kbId, string $dsId): array {
    $nextToken = null;
    do {
        $params = [
            'knowledgeBaseId' => $kbId,
            'dataSourceId'    => $dsId,
            'sortBy'          => ['attribute' => 'STARTED_AT', 'order' => 'DESCENDING'],
            'maxResults'      => 50,
        ];
        if ($nextToken) $params['nextToken'] = $nextToken;

        $resp = $bedrock->listIngestionJobs($params);
        foreach ($resp['ingestionJobSummaries'] ?? [] as $j) {
            if (($j['status'] ?? '') !== 'IN_PROGRESS') {
                return [$j['ingestionJobId'], $j['status']];
            }
        }
        $nextToken = $resp['nextToken'] ?? null;
    } while ($nextToken);

    return [null, null];
}

// =========================
// Main
// =========================
try {
    $latest = listLatestJobSummary($bedrock, $KB_ID, $DS_ID);
    if (!$latest) {
        echo json_encode(['total' => 0, 'items' => [], 'error' => 'No ingestion jobs found'], JSON_UNESCAPED_SLASHES);
        exit;
    }

    // Si el último está IN_PROGRESS, agarrar el más reciente terminado
    if (($latest['status'] ?? '') === 'IN_PROGRESS') {
        [$jobId, $pickedStatus] = pickLatestFinishedJobId($bedrock, $KB_ID, $DS_ID);
        if (!$jobId) {
            echo json_encode(['total' => 0, 'items' => [], 'error' => 'Latest job IN_PROGRESS and no finished job found'], JSON_UNESCAPED_SLASHES);
            exit;
        }
    } else {
        $jobId = $latest['ingestionJobId'];
        $pickedStatus = $latest['status'];
    }

    $job = $bedrock->getIngestionJob([
        'knowledgeBaseId' => $KB_ID,
        'dataSourceId'    => $DS_ID,
        'ingestionJobId'  => $jobId,
    ])['ingestionJob'] ?? [];

    $warnings = normalizeFailureReasons($job['failureReasons'] ?? []);

    // 1) PDFs “no text content found”
    $pdfUris = [];
    foreach ($warnings as $w) {
        if (stripos($w, $TARGET_PHRASE) !== false) {
            foreach (extractS3Uris($w) as $uri) {
                if (endsWith(strtolower($uri), '.pdf')) {
                    $pdfUris[] = $uri;
                }
            }
        }
    }
    $pdfUris = dedupePreserveOrder($pdfUris);

    // 2) Async checks:
    //    A) metadata exists in ORIGIN (required)
    //    B) pdf exists in BDA (must NOT exist)
    $metaPromises = [];
    $bdaPdfPromises = [];
    $map = []; // idx => ['originBucket','key','pdfUri']

    foreach ($pdfUris as $i => $pdfUri) {
        [$originBucket, $key] = parseS3Uri($pdfUri);
        $idx = (string)$i;

        $map[$idx] = [
            'pdfUri' => $pdfUri,
            'originBucket' => $originBucket,
            'key' => $key,
        ];

        $metaPromises[$idx] = $s3->headObjectAsync([
            'Bucket' => $originBucket,
            'Key'    => $key . '.metadata.json',
        ]);

        $bdaPdfPromises[$idx] = $s3->headObjectAsync([
            'Bucket' => $BUCKET_BDA,
            'Key'    => $key, // misma key
        ]);
    }

    $metaSettled  = Utils::settle($metaPromises)->wait();
    $bdaSettled   = Utils::settle($bdaPdfPromises)->wait();

    $items = [];

    foreach ($map as $idx => $info) {
        $originBucket = $info['originBucket'];
        $key          = $info['key'];

        // A) metadata en origen debe existir
        if (($metaSettled[$idx]['state'] ?? '') !== 'fulfilled') {
            continue;
        }

        // B) si PDF YA existe en BDA -> excluir
        if (($bdaSettled[$idx]['state'] ?? '') === 'fulfilled') {
            continue;
        }

        // Si rechazó por 404/NoSuchKey -> perfecto (NO existe en BDA)
        $reason = $bdaSettled[$idx]['reason'] ?? null;
        if ($reason instanceof AwsException) {
            $code   = (string)$reason->getAwsErrorCode();
            $status = (int)$reason->getStatusCode();

            if (!($status === 404 || $code === 'NotFound' || $code === 'NoSuchKey')) {
                echo json_encode([
                    'total' => 0,
                    'items' => [],
                    'error' => 'S3 headObject on BDA failed (non-404)',
                    'details' => [
                        'bda_bucket' => $BUCKET_BDA,
                        'key' => $key,
                        'aws_error_code' => $code,
                        'status_code' => $status,
                        'message' => $reason->getMessage(),
                    ],
                ], JSON_UNESCAPED_SLASHES);
                exit;
            }
        }

        // ? Construir los 4 links en formato n8n
        $items[] = [
            'src'      => toN8nPath($originBucket, $key),
            'src_meta' => toN8nPath($originBucket, $key . '.metadata.json'),
            'dst'      => toN8nPath($BUCKET_BDA, $key),
            'dst_meta' => toN8nPath($BUCKET_BDA, $key . '.metadata.json'),
        ];
    }

    echo json_encode([
        'total' => count($items),
        'items' => $items,
        'job'   => [
            'ingestionJobId' => $jobId,
            'pickedStatus'   => $pickedStatus,
            'generatedAtGT'  => (new DateTime('now', $TZ_GT))->format('Y-m-d H:i:s'),
        ],
    ], JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
    echo json_encode([
        'total' => 0,
        'items' => [],
        'error' => 'Unhandled exception',
        'message' => $e->getMessage(),
    ], JSON_UNESCAPED_SLASHES);
}
