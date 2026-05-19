import { EffectiveStationLimit } from '../types.js';

interface OcppEnvelope {
  action: 'SetChargingProfile';
  payload: unknown;
}

function buildOcpp2SetChargingProfile(limit: EffectiveStationLimit): OcppEnvelope {
  const profileId = Math.max(1, Math.floor(Date.now() / 1000));

  return {
    action: 'SetChargingProfile',
    payload: {
      evseId: limit.evseId ?? 0,
      chargingProfile: {
        id: profileId,
        stackLevel: 10,
        chargingProfilePurpose: 'ChargingStationMaxProfile',
        chargingProfileKind: 'Absolute',
        chargingSchedule: [
          {
            id: profileId,
            chargingRateUnit: 'W',
            chargingSchedulePeriod: [
              {
                startPeriod: 0,
                limit: limit.maxWatts,
              },
            ],
          },
        ],
      },
    },
  };
}

function buildOcpp16SetChargingProfile(limit: EffectiveStationLimit): OcppEnvelope {
  const profileId = Math.max(1, Math.floor(Date.now() / 1000));

  return {
    action: 'SetChargingProfile',
    payload: {
      connectorId: limit.connectorId ?? 0,
      csChargingProfiles: {
        chargingProfileId: profileId,
        stackLevel: 10,
        chargingProfilePurpose: 'ChargePointMaxProfile',
        chargingProfileKind: 'Absolute',
        chargingSchedule: {
          chargingRateUnit: 'W',
          chargingSchedulePeriod: [
            {
              startPeriod: 0,
              limit: limit.maxWatts,
            },
          ],
        },
      },
    },
  };
}

export function translateLimitToCommand(limit: EffectiveStationLimit): OcppEnvelope {
  if (limit.protocol === '2.0.1') {
    return buildOcpp2SetChargingProfile(limit);
  }

  return buildOcpp16SetChargingProfile(limit);
}
