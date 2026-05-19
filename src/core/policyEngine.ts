import { createHash, randomUUID } from 'node:crypto';
import { AppConfig } from '../config.js';
import { CitrineOsClient } from '../adapters/citrineosClient.js';
import { StateRepository } from '../storage/stateRepo.js';
import {
  EffectiveStationLimit,
  LoadPolicy,
  OutboxCommand,
  RuntimeState,
  SiteBudgetPolicy,
  StationConfig,
} from '../types.js';
import { allocatePolicy } from './allocation.js';
import { translateLimitToCommand } from './translator.js';

export class PolicyEngine {
  constructor(
    private readonly config: AppConfig,
    private readonly stateRepo: StateRepository,
    private readonly citrineClient: CitrineOsClient,
  ) {}

  get stations(): StationConfig[] {
    return this.config.stations;
  }

  computePolicyHash(policy: LoadPolicy): string {
    return createHash('sha256').update(JSON.stringify(policy)).digest('hex');
  }

  async applyPolicy(policy: LoadPolicy): Promise<RuntimeState> {
    const current = await this.stateRepo.getState();
    const policyHash = this.computePolicyHash(policy);

    if (current.runtime.desiredPolicy?.policyHash === policyHash) {
      return current.runtime;
    }

    const limits = allocatePolicy(this.config.stations, policy);
    await this.dispatchLimits(limits, policyHash);

    const nextRuntime: RuntimeState = {
      desiredPolicy: {
        policy,
        receivedAt: new Date().toISOString(),
        policyHash,
      },
      effectiveLimits: limits,
      fallbackActive: false,
      lastAppliedAt: new Date().toISOString(),
    };

    await this.stateRepo.setRuntime(nextRuntime);
    return nextRuntime;
  }

  async enforceFallbackIfStale(): Promise<RuntimeState | undefined> {
    const state = await this.stateRepo.getState();
    const desired = state.runtime.desiredPolicy;

    if (!desired) {
      return undefined;
    }

    const expiresAt =
      new Date(desired.receivedAt).getTime() + desired.policy.ttlSeconds * 1000;

    if (Date.now() < expiresAt || state.runtime.fallbackActive) {
      return undefined;
    }

    const fallbackPolicy: SiteBudgetPolicy = {
      mode: 'site-budget',
      idempotencyKey: `fallback-${Date.now()}`,
      sourceTimestamp: new Date().toISOString(),
      ttlSeconds: this.config.stalePolicySeconds,
      siteBudgetWatts: this.config.fallbackSiteCapWatts,
      stationOverrides: [],
    };

    const policyHash = this.computePolicyHash(fallbackPolicy);
    const limits = allocatePolicy(this.config.stations, fallbackPolicy);
    await this.dispatchLimits(limits, policyHash);

    const nextRuntime: RuntimeState = {
      desiredPolicy: {
        policy: fallbackPolicy,
        receivedAt: new Date().toISOString(),
        policyHash,
      },
      effectiveLimits: limits,
      fallbackActive: true,
      fallbackReason: 'Source policy is stale; safe fallback cap applied.',
      lastAppliedAt: new Date().toISOString(),
    };

    await this.stateRepo.setRuntime(nextRuntime);
    return nextRuntime;
  }

  async reconcile(): Promise<RuntimeState> {
    const state = await this.stateRepo.getState();
    if (!state.runtime.desiredPolicy) {
      return state.runtime;
    }

    const limits = allocatePolicy(this.config.stations, state.runtime.desiredPolicy.policy);
    await this.dispatchLimits(limits, state.runtime.desiredPolicy.policyHash);

    const nextRuntime: RuntimeState = {
      ...state.runtime,
      effectiveLimits: limits,
      lastAppliedAt: new Date().toISOString(),
    };

    await this.stateRepo.setRuntime(nextRuntime);
    return nextRuntime;
  }

  private async dispatchLimits(limits: EffectiveStationLimit[], policyHash: string): Promise<void> {
    for (const limit of limits) {
      const translated = translateLimitToCommand(limit);
      const command: OutboxCommand = {
        id: randomUUID(),
        policyHash,
        stationId: limit.stationId,
        protocol: limit.protocol,
        action: translated.action,
        payload: translated.payload,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        attempts: 0,
        status: 'pending',
      };

      await this.stateRepo.appendOutbox(command);

      command.status = 'sent';
      command.attempts += 1;
      command.updatedAt = new Date().toISOString();
      await this.stateRepo.updateOutbox(command);

      try {
        const response = await this.citrineClient.sendSetChargingProfile(limit, translated.payload);
        command.updatedAt = new Date().toISOString();
        command.response = response.body;
        command.status = response.ok ? 'accepted' : 'rejected';
      } catch (error) {
        command.updatedAt = new Date().toISOString();
        command.status = 'failed';
        command.error = error instanceof Error ? error.message : 'Unknown error while dispatching';
      }

      await this.stateRepo.updateOutbox(command);
    }
  }
}
