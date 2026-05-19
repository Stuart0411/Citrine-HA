import express from 'express';
import { loadConfig } from './config.js';
import { registerRoutes } from './api/routes.js';
import { StateRepository } from './storage/stateRepo.js';
import { CitrineOsClient } from './adapters/citrineosClient.js';
import { PolicyEngine } from './core/policyEngine.js';

async function main(): Promise<void> {
  const config = await loadConfig();
  const app = express();
  app.use(express.json({ limit: '1mb' }));

  const stateRepository = new StateRepository();
  const citrineClient = new CitrineOsClient(config);
  const engine = new PolicyEngine(config, stateRepository, citrineClient);

  registerRoutes(app, engine, stateRepository, config.webhookSharedSecret, citrineClient);

  setInterval(async () => {
    try {
      const fallback = await engine.enforceFallbackIfStale();
      if (fallback) {
        // Keep this log high-signal for ops visibility.
        console.warn('[fallback] Applied stale-policy fallback cap', fallback.fallbackReason);
      }
    } catch (error) {
      console.error('[fallback] Failed to evaluate stale-policy fallback', error);
    }
  }, 15000);

  app.listen(config.port, () => {
    console.log(`Load-management bridge listening on :${config.port}`);
    console.log(`Configured stations: ${config.stations.length}`);
  });
}

main().catch((error) => {
  console.error('Fatal startup error', error);
  process.exit(1);
});
