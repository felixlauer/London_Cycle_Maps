import React from 'react';
import { LineLayer, ShapeSource } from '@rnmapbox/maps';
import type { RouteLeg } from '../api/route';
import { pathToLineGeoJSON } from '../lib/coords';
import { routeColors } from '../theme/tokens';
import { LINE_EMISSIVE } from './styles';

type Props = {
  routeLegs: RouteLeg[];
  activeLegIndex: number;
  onSelectLeg: (index: number) => void;
};

/**
 * Multi-via legs — web MultiLegRouteLayers.
 * Active: full opacity; inactive safest 0.4; invisible hit for tap.
 */
export function MultiLegRouteLayers({
  routeLegs,
  activeLegIndex,
  onSelectLeg,
}: Props) {
  return (
    <>
      {(routeLegs || []).map((leg, i) => {
        const active = i === activeLegIndex;
        const safest = leg?.safest;
        const safeGeo = pathToLineGeoJSON(safest?.path, { leg: i, kind: 'safe' });
        const hitGeo = pathToLineGeoJSON(safest?.path, { leg: i, kind: 'hit' });

        return (
          <React.Fragment key={`leg-${i}`}>
            {safeGeo && safest?.path && safest.path.length > 1 ? (
              <ShapeSource id={`safe-${i}`} shape={safeGeo}>
                <LineLayer
                  id={`safe-${i}-casing`}
                  style={{
                    lineColor: '#ffffff',
                    lineWidth: active ? 13 : 10,
                    lineOpacity: active ? 1 : 0.4,
                    lineCap: 'round',
                    lineJoin: 'round',
                    ...LINE_EMISSIVE,
                  }}
                />
                <LineLayer
                  id={`safe-${i}-line`}
                  style={{
                    lineColor: routeColors.profile,
                    lineWidth: active ? 5 : 4,
                    lineOpacity: active ? 1 : 0.4,
                    lineCap: 'round',
                    lineJoin: 'round',
                    ...LINE_EMISSIVE,
                  }}
                />
              </ShapeSource>
            ) : null}

            {!active && hitGeo && safest?.path && safest.path.length > 1 ? (
              <ShapeSource
                id={`safe-${i}-hit`}
                shape={hitGeo}
                hitbox={{ width: 44, height: 44 }}
                onPress={() => onSelectLeg(i)}
              >
                <LineLayer
                  id={`safe-${i}-hit`}
                  style={{
                    lineColor: '#000000',
                    lineWidth: 18,
                    lineOpacity: 0,
                    lineCap: 'round',
                    lineJoin: 'round',
                  }}
                />
              </ShapeSource>
            ) : null}
          </React.Fragment>
        );
      })}
    </>
  );
}
