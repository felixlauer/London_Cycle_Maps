package expo.modules.tunedmaplibrenav

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.transform
import org.maplibre.navigation.core.location.Location
import org.maplibre.navigation.core.location.engine.LocationEngine
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * Owns the heading the rider actually travels in, and screens obviously broken fixes.
 *
 * Position is passed through untouched — the puck is ground truth. Only [Location.bearing]
 * is rewritten, because Android hands out a course only while moving and the magnetometer
 * is only trustworthy while slow:
 *
 *  - above [GPS_MIN_SPEED_MS] the GPS course wins (fix bearing, else course over ground
 *    measured between fixes),
 *  - below [COMPASS_MAX_SPEED_MS] the compass wins,
 *  - in between the previous source is held, so a rider at traffic-light speed does not
 *    flip between the two every second.
 *
 * The result is smoothed circularly and rate-limited, otherwise the follow camera jitters
 * on every fix.
 */
class RiderLocationEngine(
  private val base: LocationEngine,
  private val compassHeading: () -> Float?,
) : LocationEngine {

  private enum class Source { GPS, COMPASS }

  private var source = Source.COMPASS

  /** Which sensor currently owns the bearing — reported with ride feedback. */
  @Volatile
  var puckSource: String = "compass"
    private set
  private var smoothed: Float? = null
  private var lastLat = Double.NaN
  private var lastLon = Double.NaN
  private var lastFixAt = 0L
  private var course: Float? = null
  private var consecutiveDrops = 0

  override fun listenToLocation(request: LocationEngine.Request): Flow<Location> =
    base.listenToLocation(request).transform { fix ->
      accept(fix)?.let { emit(it) }
    }

  override suspend fun getLastLocation(): Location? = base.getLastLocation()?.let { accept(it) }

  /** Returns the fix with a rider-true bearing, or null when the fix is not usable. */
  private fun accept(fix: Location): Location? {
    val now = fix.timeMilliseconds ?: System.currentTimeMillis()
    val dtSeconds = if (lastFixAt > 0L) (now - lastFixAt).coerceAtLeast(1L) / 1000.0 else 0.0
    val moved = if (lastLat.isNaN()) Double.NaN else distanceM(lastLat, lastLon, fix.latitude, fix.longitude)

    if (isJunk(fix, moved, dtSeconds)) {
      consecutiveDrops += 1
      // Never starve the engine: a run of poor fixes is still better than no progress.
      if (consecutiveDrops <= MAX_CONSECUTIVE_DROPS) return null
    }
    consecutiveDrops = 0

    if (!moved.isNaN() && moved >= COURSE_MIN_MOVE_M) {
      course = bearingBetween(lastLat, lastLon, fix.latitude, fix.longitude)
    }

    val speed = effectiveSpeed(fix, moved, dtSeconds)
    source = when {
      speed >= GPS_MIN_SPEED_MS -> Source.GPS
      speed <= COMPASS_MAX_SPEED_MS -> Source.COMPASS
      else -> source
    }
    puckSource = if (source == Source.GPS) "gps" else "compass"

    val compass = compassHeading()
    val target = when (source) {
      Source.GPS -> fix.bearing ?: course ?: compass
      Source.COMPASS -> compass ?: course ?: fix.bearing
    }

    lastLat = fix.latitude
    lastLon = fix.longitude
    lastFixAt = now

    if (target == null) return fix
    val bearing = smooth(target, if (dtSeconds > 0.0) dtSeconds else DEFAULT_DT_S)
    return fix.copy(bearing = bearing)
  }

  private fun isJunk(fix: Location, moved: Double, dtSeconds: Double): Boolean {
    val accuracy = fix.accuracyMeters
    if (accuracy != null && accuracy > MAX_ACCURACY_M) return true
    // Implausible jump: a bike does not cover 20 m/s, so this is a multipath spike.
    if (!moved.isNaN() && dtSeconds > 0.0 && moved / dtSeconds > MAX_IMPLIED_SPEED_MS) return true
    return false
  }

  private fun effectiveSpeed(fix: Location, moved: Double, dtSeconds: Double): Float {
    fix.speedMetersPerSeconds?.let { return it }
    if (!moved.isNaN() && dtSeconds > 0.0) return (moved / dtSeconds).toFloat()
    return 0f
  }

  /** Circular exponential smoothing with a slew limit, so the camera cannot spin. */
  private fun smooth(target: Float, dtSeconds: Double): Float {
    val previous = smoothed
    if (previous == null) {
      val first = normalize(target)
      smoothed = first
      return first
    }
    val maxStep = (MAX_SLEW_DEG_PER_S * dtSeconds).toFloat()
    val step = (signedDelta(target - previous) * SMOOTHING_ALPHA).coerceIn(-maxStep, maxStep)
    val next = normalize(previous + step)
    smoothed = next
    return next
  }

  private companion object {
    const val GPS_MIN_SPEED_MS = 3.0f
    const val COMPASS_MAX_SPEED_MS = 1.2f
    const val COURSE_MIN_MOVE_M = 8.0
    const val MAX_ACCURACY_M = 60.0f
    const val MAX_IMPLIED_SPEED_MS = 20.0
    const val MAX_CONSECUTIVE_DROPS = 4
    const val SMOOTHING_ALPHA = 0.35f
    const val MAX_SLEW_DEG_PER_S = 90.0
    const val DEFAULT_DT_S = 1.0
  }
}

private const val EARTH_RADIUS_M = 6_371_008.8

/** Signed shortest angular difference, in (-180, 180]. */
internal fun signedDelta(degrees: Float): Float {
  var d = (degrees + 180f) % 360f
  if (d < 0f) d += 360f
  return d - 180f
}

internal fun normalize(degrees: Float): Float {
  var d = degrees % 360f
  if (d < 0f) d += 360f
  return d
}

internal fun bearingBetween(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Float {
  val phi1 = Math.toRadians(lat1)
  val phi2 = Math.toRadians(lat2)
  val dLambda = Math.toRadians(lon2 - lon1)
  val y = sin(dLambda) * cos(phi2)
  val x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dLambda)
  return normalize(Math.toDegrees(atan2(y, x)).toFloat())
}

/** Equirectangular approximation — accurate well inside a metre at city scale. */
internal fun distanceM(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
  val meanLat = Math.toRadians((lat1 + lat2) / 2.0)
  val dx = Math.toRadians(lon2 - lon1) * cos(meanLat)
  val dy = Math.toRadians(lat2 - lat1)
  return hypot(dx, dy) * EARTH_RADIUS_M
}
