import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { StationConfig } from './types.js';

export interface AppConfig {
  port: number;
  webhookSharedSecret: string;
  citrineosBaseUrl: string;
  citrineosStationsUrl?: string;
  citrineosOcpp2Prefix: string;
  citrineosOcpp16Prefix: string;
  fallbackSiteCapWatts: number;
  stalePolicySeconds: number;
  applyTimeoutMs: number;
  stationDefaultTenantId: number;
  stationDefaultProtocol: '2.0.1' | '1.6';
  stationDefaultMaxWatts: number;
  stationDefaultWeight: number;
  stationDiscoveryTimeoutMs: number;
  stations: StationConfig[];
}

function parseNumber(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseProtocol(value: unknown): '2.0.1' | '1.6' | undefined {
  if (value === '2.0.1' || value === '1.6') {
    return value;
  }

  if (typeof value !== 'string') {
    return undefined;
  }

  if (value.includes('2.0.1')) {
    return '2.0.1';
  }

  if (value.includes('1.6')) {
    return '1.6';
  }

  return undefined;
}

function readNumericField(record: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }

  return undefined;
}

function readTextField(record: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      return value;
    }
  }

  return undefined;
}

function normalizeDiscoveredStations(data: unknown, config: Omit<AppConfig, 'stations'>): StationConfig[] {
  let stationList: unknown[] = [];

  if (Array.isArray(data)) {
    stationList = data;
  } else if (data && typeof data === 'object') {
    const objectData = data as Record<string, unknown>;
    const candidates = [objectData.stations, objectData.data, objectData.results];
    const found = candidates.find((candidate) => Array.isArray(candidate));
    if (Array.isArray(found)) {
      stationList = found;
    }
  }

  const stations: StationConfig[] = [];
  for (const item of stationList) {
    if (!item || typeof item !== 'object') {
      continue;
    }

    const record = item as Record<string, unknown>;
    const stationId = readTextField(record, ['stationId', 'identifier', 'chargePointId', 'id']);
    if (!stationId) {
      continue;
    }

    const discoveredProtocol = parseProtocol(
      readTextField(record, ['protocol', 'ocppVersion', 'ocppProtocol']),
    );

    const protocol = discoveredProtocol ?? config.stationDefaultProtocol;
    const tenantId =
      readNumericField(record, ['tenantId', 'tenant']) ?? config.stationDefaultTenantId;
    const maxWatts =
      readNumericField(record, ['maxWatts', 'maxPowerWatts']) ?? config.stationDefaultMaxWatts;
    const weight = readNumericField(record, ['weight']) ?? config.stationDefaultWeight;

    const evseId = readNumericField(record, ['evseId']);
    const connectorId = readNumericField(record, ['connectorId']);

    stations.push({
      stationId,
      protocol,
      tenantId,
      maxWatts,
      weight,
      evseId,
      connectorId,
    });
  }

  return stations;
}

async function discoverStations(config: Omit<AppConfig, 'stations'>): Promise<StationConfig[]> {
  if (!config.citrineosStationsUrl) {
    return [];
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.stationDiscoveryTimeoutMs);

  try {
    const response = await fetch(config.citrineosStationsUrl, {
      method: 'GET',
      signal: controller.signal,
      headers: { accept: 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Station discovery failed with status ${response.status}`);
    }

    const body = (await response.json()) as unknown;
    return normalizeDiscoveredStations(body, config);
  } finally {
    clearTimeout(timeout);
  }
}

function loadStations(): StationConfig[] {
  const stationFile = resolve(process.cwd(), 'config', 'stations.json');
  const fallbackFile = resolve(process.cwd(), 'config', 'stations.example.json');
  const filePath = existsSync(stationFile) ? stationFile : fallbackFile;

  if (!existsSync(filePath)) {
    return [];
  }

  const raw = readFileSync(filePath, 'utf-8');
  return JSON.parse(raw) as StationConfig[];
}

function persistStations(stations: StationConfig[]): void {
  const configDir = resolve(process.cwd(), 'config');
  const stationFile = resolve(configDir, 'stations.json');

  mkdirSync(configDir, { recursive: true });
  writeFileSync(stationFile, `${JSON.stringify(stations, null, 2)}\n`, 'utf-8');
}

export async function loadConfig(): Promise<AppConfig> {
  const baseConfig: Omit<AppConfig, 'stations'> = {
    port: parseNumber(process.env.PORT, 8095),
    webhookSharedSecret: process.env.WEBHOOK_SHARED_SECRET ?? 'replace-me',
    citrineosBaseUrl: process.env.CITRINEOS_BASE_URL ?? 'http://localhost:8080',
    citrineosStationsUrl: process.env.CITRINEOS_STATIONS_URL,
    citrineosOcpp2Prefix: process.env.CITRINEOS_OCPP2_PREFIX ?? 'smartcharging',
    citrineosOcpp16Prefix: process.env.CITRINEOS_OCPP16_PREFIX ?? 'smartcharging',
    fallbackSiteCapWatts: parseNumber(process.env.FALLBACK_SITE_CAP_WATTS, 11000),
    stalePolicySeconds: parseNumber(process.env.STALE_POLICY_SECONDS, 120),
    applyTimeoutMs: parseNumber(process.env.APPLY_TIMEOUT_MS, 25000),
    stationDefaultTenantId: parseNumber(process.env.STATION_DEFAULT_TENANT_ID, 1),
    stationDefaultProtocol: parseProtocol(process.env.STATION_DEFAULT_PROTOCOL) ?? '1.6',
    stationDefaultMaxWatts: parseNumber(process.env.STATION_DEFAULT_MAX_WATTS, 11000),
    stationDefaultWeight: parseNumber(process.env.STATION_DEFAULT_WEIGHT, 1),
    stationDiscoveryTimeoutMs: parseNumber(process.env.STATION_DISCOVERY_TIMEOUT_MS, 10000),
  };

  let stations = loadStations();

  try {
    const discovered = await discoverStations(baseConfig);
    if (discovered.length > 0) {
      stations = discovered;
      persistStations(discovered);
      console.log(`[startup] Discovered ${discovered.length} stations from CitrineOS and wrote config/stations.json`);
    }
  } catch (error) {
    console.warn('[startup] Station discovery failed; continuing with local station config.', error);
  }

  return {
    ...baseConfig,
    stations,
  };
}
