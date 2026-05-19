import type { Express, Request, Response } from 'express';
import { z } from 'zod';
import { CitrineOsClient } from '../adapters/citrineosClient.js';
import { PolicyEngine } from '../core/policyEngine.js';
import { StateRepository } from '../storage/stateRepo.js';
import { StationConfig } from '../types.js';

const policySchema = z.object({
  mode: z.literal('site-budget').default('site-budget'),
  idempotencyKey: z.string().min(8),
  sourceTimestamp: z.string().datetime(),
  ttlSeconds: z.number().int().min(10).max(3600),
  siteBudgetWatts: z.number().int().min(0),
  stationOverrides: z
    .array(
      z.object({
        stationId: z.string().min(1),
        maxWatts: z.number().int().min(0).optional(),
      }),
    )
    .default([]),
});

const directPolicySchema = z.object({
  mode: z.literal('direct-limits').default('direct-limits'),
  idempotencyKey: z.string().min(8),
  sourceTimestamp: z.string().datetime(),
  ttlSeconds: z.number().int().min(10).max(3600),
  stationLimits: z
    .array(
      z.object({
        stationId: z.string().min(1),
        maxWatts: z.number().int().min(0),
      }),
    )
    .default([]),
  groups: z
    .array(
      z.object({
        groupId: z.string().min(1),
        stationIds: z.array(z.string().min(1)).min(1),
      }),
    )
    .default([]),
  groupLimits: z
    .array(
      z.object({
        groupId: z.string().min(1),
        maxWatts: z.number().int().min(0),
      }),
    )
    .default([]),
  defaultUnspecifiedWatts: z.number().int().min(0).optional(),
});

const remoteStartSchema = z.object({
  stationId: z.string().min(1),
  idToken: z.string().min(1),
  evseId: z.number().int().min(0).optional(),
  connectorId: z.number().int().min(0).optional(),
  remoteStartId: z.number().int().min(1).optional(),
});

const remoteStopSchema = z.object({
  stationId: z.string().min(1),
  transactionId: z.union([z.string().min(1), z.number().int().min(0)]).optional(),
});

const setAvailabilitySchema = z.object({
  stationId: z.string().min(1),
  operationalStatus: z.enum(['Operative', 'Inoperative']),
  evseId: z.number().int().min(0).optional(),
  connectorId: z.number().int().min(0).optional(),
});

let nextTransactionId = 1;
const stationLastTransactionId = new Map<string, number>();

function allocateTransactionId(stationId: string): number {
  const transactionId = nextTransactionId;
  nextTransactionId += 1;
  stationLastTransactionId.set(stationId, transactionId);
  return transactionId;
}

function getLatestTransactionId(stationId: string): number | undefined {
  return stationLastTransactionId.get(stationId);
}

function rejectUnauthorized(request: Request, response: Response, sharedSecret: string): boolean {
  const provided = request.header('x-shared-secret');
  if (!provided || provided !== sharedSecret) {
    response.status(401).json({ error: 'Unauthorized webhook request.' });
    return true;
  }

  return false;
}

export function registerRoutes(
  app: Express,
  engine: PolicyEngine,
  stateRepository: StateRepository,
  sharedSecret: string,
  citrineClient: CitrineOsClient,
): void {
  function findStation(stationId: string): StationConfig | undefined {
    return engine.stations.find((station) => station.stationId === stationId);
  }

  app.get('/health', (_request, response) => {
    response.json({ status: 'ok' });
  });

  app.get('/api/v1/stations', (_request, response) => {
    response.json({ stations: engine.stations });
  });

  app.post('/api/v1/policies/site-budget', async (request, response) => {
    if (rejectUnauthorized(request, response, sharedSecret)) {
      return;
    }

    const parsed = policySchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: parsed.error.flatten() });
      return;
    }

    const runtime = await engine.applyPolicy(parsed.data);
    response.status(202).json({
      message: 'Policy accepted and apply flow started.',
      runtime,
    });
  });

  app.post('/api/v1/policies/direct-limits', async (request, response) => {
    if (rejectUnauthorized(request, response, sharedSecret)) {
      return;
    }

    const parsed = directPolicySchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: parsed.error.flatten() });
      return;
    }

    const runtime = await engine.applyPolicy(parsed.data);
    response.status(202).json({
      message: 'Direct limits accepted and apply flow started.',
      runtime,
    });
  });

  app.post('/api/v1/policies/reconcile', async (request, response) => {
    if (rejectUnauthorized(request, response, sharedSecret)) {
      return;
    }

    const runtime = await engine.reconcile();
    response.status(202).json({ message: 'Reconciliation triggered.', runtime });
  });

  app.post('/api/v1/operations/remote-start', async (request, response) => {
    if (rejectUnauthorized(request, response, sharedSecret)) {
      return;
    }

    const parsed = remoteStartSchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: parsed.error.flatten() });
      return;
    }

    const station = findStation(parsed.data.stationId);
    if (!station) {
      response.status(404).json({ error: `Station ${parsed.data.stationId} is not configured.` });
      return;
    }

    const transactionId = allocateTransactionId(station.stationId);
    const remoteStartRequest = {
      ...parsed.data,
      remoteStartId: parsed.data.remoteStartId ?? transactionId,
    };

    try {
      const result = await citrineClient.sendRemoteStartTransaction(station, remoteStartRequest);
      response.status(result.ok ? 202 : 502).json({
        message: result.ok ? 'Remote start request dispatched.' : 'Remote start dispatch rejected by CitrineOS.',
        stationId: station.stationId,
        protocol: station.protocol,
        transactionId,
        remoteStartId: remoteStartRequest.remoteStartId,
        status: result.status,
        body: result.body,
      });
    } catch (error) {
      response.status(500).json({
        error: error instanceof Error ? error.message : 'Failed to dispatch remote start request.',
      });
    }
  });

  app.post('/api/v1/operations/remote-stop', async (request, response) => {
    if (rejectUnauthorized(request, response, sharedSecret)) {
      return;
    }

    const parsed = remoteStopSchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: parsed.error.flatten() });
      return;
    }

    const station = findStation(parsed.data.stationId);
    if (!station) {
      response.status(404).json({ error: `Station ${parsed.data.stationId} is not configured.` });
      return;
    }

    const transactionId = parsed.data.transactionId ?? getLatestTransactionId(station.stationId);
    if (transactionId === undefined) {
      response.status(400).json({
        error: `No known transaction id for station ${station.stationId}. Start a session first or provide transactionId.`,
      });
      return;
    }

    try {
      const result = await citrineClient.sendRemoteStopTransaction(station, { transactionId });
      response.status(result.ok ? 202 : 502).json({
        message: result.ok ? 'Remote stop request dispatched.' : 'Remote stop dispatch rejected by CitrineOS.',
        stationId: station.stationId,
        protocol: station.protocol,
        transactionId,
        status: result.status,
        body: result.body,
      });
    } catch (error) {
      response.status(500).json({
        error: error instanceof Error ? error.message : 'Failed to dispatch remote stop request.',
      });
    }
  });

  app.post('/api/v1/operations/set-availability', async (request, response) => {
    if (rejectUnauthorized(request, response, sharedSecret)) {
      return;
    }

    const parsed = setAvailabilitySchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: parsed.error.flatten() });
      return;
    }

    const station = findStation(parsed.data.stationId);
    if (!station) {
      response.status(404).json({ error: `Station ${parsed.data.stationId} is not configured.` });
      return;
    }

    try {
      const result = await citrineClient.sendSetAvailability(station, parsed.data);
      response.status(result.ok ? 202 : 502).json({
        message: result.ok ? 'Set availability request dispatched.' : 'Set availability rejected by CitrineOS.',
        stationId: station.stationId,
        protocol: station.protocol,
        status: result.status,
        body: result.body,
      });
    } catch (error) {
      response.status(500).json({
        error: error instanceof Error ? error.message : 'Failed to dispatch set availability request.',
      });
    }
  });

  app.get('/api/v1/state', async (_request, response) => {
    const state = await stateRepository.getState();
    response.json(state);
  });
}
