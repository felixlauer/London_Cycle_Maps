package expo.modules.tunedmaplibrenav

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min

/**
 * Decides when the rider has genuinely left the route.
 *
 * The SDK's own detector fires on a bare radius plus a timer, which on a bike triggers
 * while filtering past a queue or crossing a wide junction, and it offers no way back
 * once it has fired. This tracker measures the perpendicular distance to the drawn line
 * and applies the hysteresis competitors use:
 *
 *  - beyond [ENTER_M] starts a candidate,
 *  - a candidate is confirmed after [ENTER_MS] still out,
 *  - beyond [HARD_M] confirms at once (a deliberate turn away),
 *  - back inside [EXIT_M] for [EXIT_MS] ends the episode so a replan in
 *    flight can be abandoned, without a single GPS blip cancelling it.
 *
 *  [resetEpisode] clears the latch without dropping the line, so a rider who
 *  stays off-route after a failed replan can enter again without first
 *  coming back inside [EXIT_M].
 */
class RouteDeviationTracker {

  data class Result(
    val distanceM: Double,
    val offRoute: Boolean,
    val entered: Boolean,
    val rejoined: Boolean,
  )

  private var lats = DoubleArray(0)
  private var lons = DoubleArray(0)
  private var cursor = 0
  private var offRoute = false
  private var candidateSince = NO_CANDIDATE
  private var rejoinSince = NO_CANDIDATE

  val hasRoute: Boolean get() = lats.size >= 2

  /** Load the line the rider is meant to follow, as a GeoJSON FeatureCollection string. */
  fun setRoute(geoJson: String) {
    val lat = ArrayList<Double>()
    val lon = ArrayList<Double>()
    try {
      val features = JSONObject(geoJson).optJSONArray("features")
      if (features != null) {
        for (i in 0 until features.length()) {
          val coords = features.optJSONObject(i)
            ?.optJSONObject("geometry")
            ?.optJSONArray("coordinates") ?: continue
          for (j in 0 until coords.length()) {
            val pair = coords.opt(j) as? JSONArray ?: continue
            val x = pair.optDouble(0, Double.NaN)
            val y = pair.optDouble(1, Double.NaN)
            if (x.isNaN() || y.isNaN()) continue
            lat.add(y)
            lon.add(x)
          }
        }
      }
    } catch (_: Exception) {
      // A malformed line simply means no deviation checks.
    }
    lats = lat.toDoubleArray()
    lons = lon.toDoubleArray()
    reset()
  }

  /** Clear episode state — called on a new route so a stale candidate cannot fire. */
  fun reset() {
    cursor = 0
    resetEpisode()
  }

  /**
   * Drop the current off-route latch, keep the line. The next fix can enter
   * again even if the rider never came back inside [EXIT_M].
   */
  fun resetEpisode() {
    offRoute = false
    candidateSince = NO_CANDIDATE
    rejoinSince = NO_CANDIDATE
  }

  fun update(lat: Double, lon: Double, nowMs: Long): Result? {
    if (!hasRoute) return null
    val distance = distanceToRoute(lat, lon)

    if (!offRoute) {
      if (distance >= HARD_M) return confirm(distance)
      if (distance >= ENTER_M) {
        if (candidateSince == NO_CANDIDATE) {
          candidateSince = nowMs
        } else if (nowMs - candidateSince >= ENTER_MS) {
          return confirm(distance)
        }
      } else if (distance < EXIT_M) {
        candidateSince = NO_CANDIDATE
      }
      return Result(distance, offRoute = false, entered = false, rejoined = false)
    }

    if (distance < EXIT_M) {
      if (rejoinSince == NO_CANDIDATE) rejoinSince = nowMs
      if (nowMs - rejoinSince >= EXIT_MS) {
        offRoute = false
        candidateSince = NO_CANDIDATE
        rejoinSince = NO_CANDIDATE
        return Result(distance, offRoute = false, entered = false, rejoined = true)
      }
      return Result(distance, offRoute = true, entered = false, rejoined = false)
    }
    rejoinSince = NO_CANDIDATE
    return Result(distance, offRoute = true, entered = false, rejoined = false)
  }

  private fun confirm(distance: Double): Result {
    offRoute = true
    candidateSince = NO_CANDIDATE
    rejoinSince = NO_CANDIDATE
    return Result(distance, offRoute = true, entered = true, rejoined = false)
  }

  /**
   * Perpendicular distance to the nearest segment, searched in a window around the last
   * match so cost does not grow with route length. A window miss (reroute, tunnel exit,
   * teleport) falls back to a full scan.
   */
  private fun distanceToRoute(lat: Double, lon: Double): Double {
    val windowed = scan(lat, lon, max(0, cursor - WINDOW_BACK), min(lats.size - 1, cursor + WINDOW_AHEAD))
    if (windowed.first <= WINDOW_TRUST_M) {
      cursor = windowed.second
      return windowed.first
    }
    val full = scan(lat, lon, 0, lats.size - 1)
    cursor = full.second
    return full.first
  }

  /** Returns the best distance in [from, to] and the index of the segment that produced it. */
  private fun scan(lat: Double, lon: Double, from: Int, to: Int): Pair<Double, Int> {
    var best = Double.MAX_VALUE
    var bestIndex = from
    for (i in from until to) {
      val d = segmentDistanceM(lat, lon, lats[i], lons[i], lats[i + 1], lons[i + 1])
      if (d < best) {
        best = d
        bestIndex = i
      }
    }
    if (best == Double.MAX_VALUE && lats.isNotEmpty()) {
      val i = from.coerceIn(0, lats.size - 1)
      return Pair(distanceM(lat, lon, lats[i], lons[i]), i)
    }
    return Pair(best, bestIndex)
  }

  private companion object {
    const val NO_CANDIDATE = -1L
    const val ENTER_M = 22.0
    const val ENTER_MS = 2_500L
    const val HARD_M = 50.0
    const val EXIT_M = 12.0
    const val EXIT_MS = 1_000L
    const val WINDOW_BACK = 120
    const val WINDOW_AHEAD = 900
    const val WINDOW_TRUST_M = 200.0
  }
}

/** Point-to-segment distance, projected locally so the maths stays in metres. */
internal fun segmentDistanceM(
  lat: Double,
  lon: Double,
  aLat: Double,
  aLon: Double,
  bLat: Double,
  bLon: Double,
): Double {
  val scale = Math.cos(Math.toRadians(lat))
  val px = (lon - aLon) * scale
  val py = lat - aLat
  val vx = (bLon - aLon) * scale
  val vy = bLat - aLat
  val lengthSq = vx * vx + vy * vy
  val t = if (lengthSq <= 0.0) 0.0 else ((px * vx + py * vy) / lengthSq).coerceIn(0.0, 1.0)
  val dx = px - vx * t
  val dy = py - vy * t
  return Math.toRadians(Math.hypot(dx, dy)) * 6_371_008.8
}
