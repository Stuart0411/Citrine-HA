import { resolve } from 'node:path';
import { OutboxCommand, RuntimeState } from '../types.js';
import { readJsonFile, writeJsonFile } from './jsonStore.js';

interface PersistedState {
  runtime: RuntimeState;
  outbox: OutboxCommand[];
}

const DEFAULT_STATE: PersistedState = {
  runtime: {
    effectiveLimits: [],
    fallbackActive: false,
  },
  outbox: [],
};

export class StateRepository {
  private readonly filePath = resolve(process.cwd(), 'data', 'state.json');

  async getState(): Promise<PersistedState> {
    return readJsonFile(this.filePath, DEFAULT_STATE);
  }

  async setRuntime(runtime: RuntimeState): Promise<void> {
    const state = await this.getState();
    state.runtime = runtime;
    await writeJsonFile(this.filePath, state);
  }

  async appendOutbox(command: OutboxCommand): Promise<void> {
    const state = await this.getState();
    state.outbox.push(command);
    await writeJsonFile(this.filePath, state);
  }

  async updateOutbox(command: OutboxCommand): Promise<void> {
    const state = await this.getState();
    state.outbox = state.outbox.map((existing) => (existing.id === command.id ? command : existing));
    await writeJsonFile(this.filePath, state);
  }
}
