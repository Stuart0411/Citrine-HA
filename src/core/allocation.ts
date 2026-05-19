import {
  DirectLimitsPolicy,
  EffectiveStationLimit,
  LoadPolicy,
  SiteBudgetPolicy,
  StationConfig,
} from '../types.js';

export function allocateSiteBudget(
  stations: StationConfig[],
  policy: SiteBudgetPolicy,
): EffectiveStationLimit[] {
  const overrideMap = new Map(policy.stationOverrides.map((override) => [override.stationId, override]));
  const weightedStations = stations.filter((station) => station.weight > 0);

  const totalWeight = weightedStations.reduce((acc, station) => acc + station.weight, 0);
  const fallbackWeight = totalWeight > 0 ? totalWeight : stations.length || 1;

  return stations.map((station) => {
    const explicit = overrideMap.get(station.stationId)?.maxWatts;
    const sharedCap = Math.floor((policy.siteBudgetWatts * station.weight) / fallbackWeight);
    const computed = explicit ?? sharedCap;
    const maxWatts = Math.max(0, Math.min(computed, station.maxWatts));

    return {
      stationId: station.stationId,
      tenantId: station.tenantId,
      protocol: station.protocol,
      maxWatts,
      evseId: station.evseId,
      connectorId: station.connectorId,
    };
  });
}

function buildGroupMembership(
  stations: StationConfig[],
  policy: DirectLimitsPolicy,
): Map<string, string[]> {
  const groupToStations = new Map<string, Set<string>>();

  for (const station of stations) {
    for (const groupId of station.groupIds ?? []) {
      const members = groupToStations.get(groupId) ?? new Set<string>();
      members.add(station.stationId);
      groupToStations.set(groupId, members);
    }
  }

  for (const group of policy.groups) {
    const members = groupToStations.get(group.groupId) ?? new Set<string>();
    for (const stationId of group.stationIds) {
      members.add(stationId);
    }

    groupToStations.set(group.groupId, members);
  }

  return new Map(
    Array.from(groupToStations.entries()).map(([groupId, members]) => [groupId, Array.from(members)]),
  );
}

export function allocateDirectLimits(
  stations: StationConfig[],
  policy: DirectLimitsPolicy,
): EffectiveStationLimit[] {
  const stationById = new Map(stations.map((station) => [station.stationId, station]));
  const effectiveByStation = new Map<string, number>();
  const groupMembership = buildGroupMembership(stations, policy);

  for (const groupLimit of policy.groupLimits) {
    const memberIds = groupMembership.get(groupLimit.groupId) ?? [];
    const members = memberIds
      .map((stationId) => stationById.get(stationId))
      .filter((station): station is StationConfig => Boolean(station));

    if (members.length === 0) {
      continue;
    }

    const weightedMembers = members.filter((station) => station.weight > 0);
    const totalWeight = weightedMembers.reduce((sum, station) => sum + station.weight, 0);
    const divisor = totalWeight > 0 ? totalWeight : members.length;

    for (const station of members) {
      const rawShare = totalWeight > 0
        ? Math.floor((groupLimit.maxWatts * station.weight) / divisor)
        : Math.floor(groupLimit.maxWatts / divisor);

      const clampedShare = Math.max(0, Math.min(rawShare, station.maxWatts));
      const existing = effectiveByStation.get(station.stationId);
      effectiveByStation.set(
        station.stationId,
        existing === undefined ? clampedShare : Math.min(existing, clampedShare),
      );
    }
  }

  for (const stationLimit of policy.stationLimits) {
    const station = stationById.get(stationLimit.stationId);
    if (!station) {
      continue;
    }

    const clamped = Math.max(0, Math.min(stationLimit.maxWatts, station.maxWatts));
    effectiveByStation.set(station.stationId, clamped);
  }

  return stations.map((station) => {
    const fallback =
      policy.defaultUnspecifiedWatts === undefined
        ? station.maxWatts
        : Math.max(0, Math.min(policy.defaultUnspecifiedWatts, station.maxWatts));

    const maxWatts = effectiveByStation.get(station.stationId) ?? fallback;

    return {
      stationId: station.stationId,
      tenantId: station.tenantId,
      protocol: station.protocol,
      maxWatts,
      evseId: station.evseId,
      connectorId: station.connectorId,
    };
  });
}

export function allocatePolicy(stations: StationConfig[], policy: LoadPolicy): EffectiveStationLimit[] {
  if (policy.mode === 'direct-limits') {
    return allocateDirectLimits(stations, policy);
  }

  return allocateSiteBudget(stations, policy);
}
