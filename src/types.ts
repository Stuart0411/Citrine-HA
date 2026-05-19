export type OcppProtocol = '2.0.1' | '1.6';

export interface StationConfig {
  stationId: string;
  protocol: OcppProtocol;
  tenantId: number;
  maxWatts: number;
  weight: number;
  groupIds?: string[];
  evseId?: number;
  connectorId?: number;
}

export interface StationOverride {
  stationId: string;
  maxWatts?: number;
}

export interface BasePolicy {
  idempotencyKey: string;
  sourceTimestamp: string;
  ttlSeconds: number;
}

export interface SiteBudgetPolicy extends BasePolicy {
  mode: 'site-budget';
  siteBudgetWatts: number;
  stationOverrides: StationOverride[];
}

export interface StationLimitInput {
  stationId: string;
  maxWatts: number;
}

export interface StationGroupInput {
  groupId: string;
  stationIds: string[];
}

export interface GroupLimitInput {
  groupId: string;
  maxWatts: number;
}

export interface DirectLimitsPolicy extends BasePolicy {
  mode: 'direct-limits';
  stationLimits: StationLimitInput[];
  groups: StationGroupInput[];
  groupLimits: GroupLimitInput[];
  defaultUnspecifiedWatts?: number;
}

export type LoadPolicy = SiteBudgetPolicy | DirectLimitsPolicy;

export interface EffectiveStationLimit {
  stationId: string;
  tenantId: number;
  protocol: OcppProtocol;
  maxWatts: number;
  evseId?: number;
  connectorId?: number;
}

export interface DesiredPolicySnapshot {
  policy: LoadPolicy;
  receivedAt: string;
  policyHash: string;
}

export type CommandStatus = 'pending' | 'sent' | 'accepted' | 'rejected' | 'failed';

export interface OutboxCommand {
  id: string;
  policyHash: string;
  stationId: string;
  protocol: OcppProtocol;
  action: 'SetChargingProfile';
  payload: unknown;
  createdAt: string;
  updatedAt: string;
  attempts: number;
  status: CommandStatus;
  response?: unknown;
  error?: string;
}

export interface RuntimeState {
  desiredPolicy?: DesiredPolicySnapshot;
  effectiveLimits: EffectiveStationLimit[];
  fallbackActive: boolean;
  fallbackReason?: string;
  lastAppliedAt?: string;
}
