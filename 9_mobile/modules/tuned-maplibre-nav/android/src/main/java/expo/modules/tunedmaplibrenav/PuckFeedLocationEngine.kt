package expo.modules.tunedmaplibrenav

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.onEach
import org.maplibre.navigation.core.location.Location
import org.maplibre.navigation.core.location.engine.LocationEngine

/**
 * Fan-out wrapper: every accepted fix is shown on the puck *before* the navigation
 * engine may project it onto the route for progress.
 *
 * ProgressChangeListener is the wrong place to move the puck. The engine's location
 * there is optionally snapped, so the arrow would stick to the drawn line until the
 * off-route detector fires — a visualisation snap threshold the rider never asked for.
 */
class PuckFeedLocationEngine(
  private val inner: LocationEngine,
  private val onFix: (Location) -> Unit,
) : LocationEngine {

  override fun listenToLocation(request: LocationEngine.Request): Flow<Location> =
    inner.listenToLocation(request).onEach(onFix)

  override suspend fun getLastLocation(): Location? {
    val last = inner.getLastLocation()
    last?.let(onFix)
    return last
  }
}
