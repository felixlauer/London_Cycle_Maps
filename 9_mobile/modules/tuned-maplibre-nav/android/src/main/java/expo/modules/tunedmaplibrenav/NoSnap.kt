package expo.modules.tunedmaplibrenav

import org.maplibre.navigation.core.location.Location
import org.maplibre.navigation.core.routeprogress.RouteProgress
import org.maplibre.navigation.core.snap.Snap

/**
 * Identity snap — the puck keeps the measured position and heading.
 *
 * The default [org.maplibre.navigation.core.snap.SnapToRoute] projects the fix onto
 * the current step and replaces the bearing with the direction of the planned line
 * one metre ahead. On a bike that reads as the puck sliding along the drawn route
 * and fighting the real position whenever the rider leaves it, and as a map that
 * turns with the plan instead of with the rider. Route progress is computed from the
 * raw fix before snapping, so dropping the projection costs nothing.
 */
class NoSnap : Snap() {
  override fun getSnappedLocation(location: Location, routeProgress: RouteProgress): Location =
    location
}
