import { AppConfig } from '../config.js';
import { EffectiveStationLimit, StationConfig } from '../types.js';

export class CitrineOsClient {
  constructor(private readonly config: AppConfig) {}

  private async postOcppAction(
    params: {
      version: '2.0.1' | '1.6';
      prefix: string;
      actionPath: string;
      stationId: string;
      tenantId: number;
    },
    payload: unknown,
  ): Promise<{ ok: boolean; status: number; body: unknown }> {
    const endpoint = `${this.config.citrineosBaseUrl}/ocpp/${params.version}/${params.prefix}/${params.actionPath}`;
    const query = new URLSearchParams({
      identifier: params.stationId,
      tenantId: String(params.tenantId),
    });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.config.applyTimeoutMs);

    try {
      const response = await fetch(`${endpoint}?${query.toString()}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      let body: unknown = undefined;
      try {
        body = await response.json();
      } catch {
        body = await response.text();
      }

      return {
        ok: response.ok,
        status: response.status,
        body,
      };
    } finally {
      clearTimeout(timeout);
    }
  }

  async sendSetChargingProfile(
    limit: EffectiveStationLimit,
    payload: unknown,
  ): Promise<{ ok: boolean; status: number; body: unknown }> {
    const version = limit.protocol === '2.0.1' ? '2.0.1' : '1.6';
    const prefix = limit.protocol === '2.0.1' ? this.config.citrineosOcpp2Prefix : this.config.citrineosOcpp16Prefix;

    return this.postOcppAction(
      {
        version,
        prefix,
        actionPath: 'setChargingProfile',
        stationId: limit.stationId,
        tenantId: limit.tenantId,
      },
      payload,
    );
  }

  async sendRemoteStartTransaction(
    station: StationConfig,
    request: { idToken: string; evseId?: number; connectorId?: number; remoteStartId?: number },
  ): Promise<{ ok: boolean; status: number; body: unknown }> {
    if (station.protocol === '2.0.1') {
      const payload = {
        remoteStartId: request.remoteStartId ?? Math.max(1, Math.floor(Date.now() / 1000)),
        idToken: {
          idToken: request.idToken,
          type: 'Central',
        },
        evseId: request.evseId,
      };

      return this.postOcppAction(
        {
          version: '2.0.1',
          prefix: this.config.citrineosOcpp2Prefix,
          actionPath: 'requestStartTransaction',
          stationId: station.stationId,
          tenantId: station.tenantId,
        },
        payload,
      );
    }

    const payload = {
      idTag: request.idToken,
      connectorId: request.connectorId ?? station.connectorId ?? 0,
    };

    return this.postOcppAction(
      {
        version: '1.6',
        prefix: this.config.citrineosOcpp16Prefix,
        actionPath: 'remoteStartTransaction',
        stationId: station.stationId,
        tenantId: station.tenantId,
      },
      payload,
    );
  }

  async sendRemoteStopTransaction(
    station: StationConfig,
    request: { transactionId: string | number },
  ): Promise<{ ok: boolean; status: number; body: unknown }> {
    if (station.protocol === '2.0.1') {
      const payload = {
        transactionId: String(request.transactionId),
      };

      return this.postOcppAction(
        {
          version: '2.0.1',
          prefix: this.config.citrineosOcpp2Prefix,
          actionPath: 'requestStopTransaction',
          stationId: station.stationId,
          tenantId: station.tenantId,
        },
        payload,
      );
    }

    const numericTransactionId = Number(request.transactionId);
    if (!Number.isFinite(numericTransactionId)) {
      throw new Error('transactionId must be numeric for OCPP 1.6 remote stop.');
    }

    const payload = {
      transactionId: Math.floor(numericTransactionId),
    };

    return this.postOcppAction(
      {
        version: '1.6',
        prefix: this.config.citrineosOcpp16Prefix,
        actionPath: 'remoteStopTransaction',
        stationId: station.stationId,
        tenantId: station.tenantId,
      },
      payload,
    );
  }

  async sendSetAvailability(
    station: StationConfig,
    request: { operationalStatus: 'Operative' | 'Inoperative'; evseId?: number; connectorId?: number },
  ): Promise<{ ok: boolean; status: number; body: unknown }> {
    if (station.protocol === '2.0.1') {
      const evseId = request.evseId ?? station.evseId;
      const connectorId = request.connectorId ?? station.connectorId;

      const payload: {
        operationalStatus: 'Operative' | 'Inoperative';
        evse?: { id: number; connectorId?: number };
      } = {
        operationalStatus: request.operationalStatus,
      };

      if (evseId !== undefined) {
        payload.evse = {
          id: evseId,
          connectorId,
        };
      }

      return this.postOcppAction(
        {
          version: '2.0.1',
          prefix: this.config.citrineosOcpp2Prefix,
          actionPath: 'changeAvailability',
          stationId: station.stationId,
          tenantId: station.tenantId,
        },
        payload,
      );
    }

    const payload = {
      connectorId: request.connectorId ?? station.connectorId ?? 0,
      type: request.operationalStatus,
    };

    return this.postOcppAction(
      {
        version: '1.6',
        prefix: this.config.citrineosOcpp16Prefix,
        actionPath: 'changeAvailability',
        stationId: station.stationId,
        tenantId: station.tenantId,
      },
      payload,
    );
  }
}
