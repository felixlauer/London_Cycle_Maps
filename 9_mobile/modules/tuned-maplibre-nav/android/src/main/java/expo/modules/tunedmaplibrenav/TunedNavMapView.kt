package expo.modules.tunedmaplibrenav

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import expo.modules.kotlin.AppContext
import expo.modules.kotlin.viewevent.EventDispatcher
import expo.modules.kotlin.views.ExpoView
import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.location.LocationComponent
import org.maplibre.android.location.LocationComponentActivationOptions
import org.maplibre.android.location.LocationComponentOptions
import org.maplibre.android.location.OnCameraTrackingChangedListener
import org.maplibre.android.location.modes.CameraMode
import org.maplibre.android.location.modes.RenderMode
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.navigation.core.location.Location
import org.maplibre.navigation.core.location.replay.ReplayRouteLocationEngine
import org.maplibre.navigation.core.location.toAndroidLocation
import org.maplibre.navigation.core.milestone.Milestone
import org.maplibre.navigation.core.milestone.MilestoneEventListener
import org.maplibre.navigation.core.milestone.VoiceInstructionMilestone
import org.maplibre.navigation.core.models.DirectionsResponse
import org.maplibre.navigation.core.models.DirectionsRoute
import org.maplibre.navigation.core.navigation.AndroidMapLibreNavigation
import org.maplibre.navigation.core.navigation.MapLibreNavigation
import org.maplibre.navigation.core.navigation.MapLibreNavigationOptions
import org.maplibre.navigation.core.routeprogress.ProgressChangeListener
import org.maplibre.navigation.core.routeprogress.RouteProgress
import org.maplibre.navigation.location.gms.GoogleLocationEngine

/**
 * In-process MapLibre navigation map. Tuned owns all chrome in React Native —
 * this view is map + engine only (puck, camera, route line, voice, progress events).
 *
 * Route geometry authority is the Tuned line passed in [routeGeoJson]; the engine's
 * DirectionsRoute is the same path (BYOR) and drives progress and voice.
 *
 * The puck is never snapped to that line (see [NoSnap]) and deviation is judged by
 * [RouteDeviationTracker] rather than the SDK detector, so the rider sees their real
 * position and heading while only the line and the instructions react.
 */
@SuppressLint("ViewConstructor")
class TunedNavMapView(context: Context, appContext: AppContext) : ExpoView(context, appContext) {

  private val onNavReady by EventDispatcher<Map<String, Any?>>()
  private val onRouteProgress by EventDispatcher<Map<String, Any?>>()
  private val onOffRoute by EventDispatcher<Map<String, Any?>>()
  private val onRouteRejoined by EventDispatcher<Map<String, Any?>>()
  private val onArrival by EventDispatcher<Map<String, Any?>>()
  private val onTrackingChanged by EventDispatcher<Map<String, Any?>>()
  private val onNavError by EventDispatcher<Map<String, Any?>>()

  private val mapView: MapView
  private var mapLibreMap: MapLibreMap? = null
  private var style: Style? = null
  private var locationComponent: LocationComponent? = null

  private var navigation: MapLibreNavigation? = null
  private var replayEngine: ReplayRouteLocationEngine? = null
  private var riderEngine: RiderLocationEngine? = null
  private var compass: CompassHeadingTracker? = null
  private var voice: NavVoice? = null
  private val deviation = RouteDeviationTracker()

  private var route: DirectionsRoute? = null
  private var navigationRunning = false
  private var arrivalSent = false
  private var lastProgressAt = 0L
  private var lastStepKey = -1
  private var lastFollowCamera = Int.MIN_VALUE
  private var lastFollowRender = Int.MIN_VALUE
  private var lastFollowZoom = Double.NaN
  private var lastFixSpeed = 0f
  private var trackingUser = true
  private var styleReady = false
  private var distanceFromRoute = 0.0
  private var zoomedOutForSpeed = false
  private var lastOffRouteEmitAt = 0L
  private var lastImperativeAnnouncement: String? = null
  private var resumeSpeakRunnable: Runnable? = null

  private val mainHandler = Handler(Looper.getMainLooper())

  // Props
  private var themeMode: String = "dark"
  private var simulate: Boolean = false
  private var rerouting: Boolean = false
  private var cyclewaysVisible: Boolean = true
  private var cameraMode: String = "follow"
  private var routeGeoJson: String = EMPTY_FC
  private var trafficGeoJson: String = EMPTY_FC
  private var cyclewayGeoJson: String = EMPTY_FC
  private var initialLatitude: Double? = null
  private var initialLongitude: Double? = null
  private var initialBearing: Double = 0.0
  private var muted: Boolean = false

  init {
    try {
      MapLibre.getInstance(context.applicationContext)
    } catch (e: Exception) {
      Log.w(TAG, "MapLibre.getInstance: ${e.message}")
    }
    mapView = MapView(context)
    addView(mapView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
    mapView.onCreate(null)
    mapView.getMapAsync { map ->
      mapLibreMap = map
      map.uiSettings.isCompassEnabled = false
      map.uiSettings.isLogoEnabled = false
      map.uiSettings.isAttributionEnabled = false
      map.uiSettings.isRotateGesturesEnabled = true
      map.uiSettings.isTiltGesturesEnabled = true
      applyStyle()
    }
  }

  // ---------------------------------------------------------------- props

  fun setThemeMode(value: String) {
    if (themeMode == value) return
    themeMode = value
    if (mapLibreMap != null) applyStyle()
  }

  fun setSimulate(value: Boolean) {
    simulate = value
  }

  fun setMuted(value: Boolean) {
    muted = value
    voice?.muted = value
  }

  fun setRerouting(value: Boolean) {
    if (rerouting == value) return
    rerouting = value
    applyRouteLineColors()
    if (value) {
      // Maneuver cues are stale until the new line lands; say why it went quiet.
      cancelResumeSpeak()
      voice?.stopSpeaking()
      voice?.speak(context.getString(R.string.tuned_nav_rerouting_announcement))
    }
  }

  fun setCyclewaysVisible(value: Boolean) {
    if (cyclewaysVisible == value) return
    cyclewaysVisible = value
    style?.getLayer(LAYER_CYCLE)?.setProperties(
      PropertyFactory.visibility(if (value) Property.VISIBLE else Property.NONE),
    )
  }

  fun setRouteGeoJson(value: String) {
    routeGeoJson = value.ifBlank { EMPTY_FC }
    (style?.getSource(SOURCE_ROUTE) as? GeoJsonSource)?.setGeoJson(routeGeoJson)
    // Deviation is measured against the line the rider can actually see.
    deviation.setRoute(routeGeoJson)
    distanceFromRoute = 0.0
  }

  fun setTrafficGeoJson(value: String) {
    trafficGeoJson = value.ifBlank { EMPTY_FC }
    (style?.getSource(SOURCE_TRAFFIC) as? GeoJsonSource)?.setGeoJson(trafficGeoJson)
  }

  fun setCyclewayGeoJson(value: String) {
    cyclewayGeoJson = value.ifBlank { EMPTY_FC }
    (style?.getSource(SOURCE_CYCLE) as? GeoJsonSource)?.setGeoJson(cyclewayGeoJson)
  }

  fun setInitialLatitude(value: Double?) {
    initialLatitude = value
  }

  fun setInitialLongitude(value: Double?) {
    initialLongitude = value
  }

  fun setInitialBearing(value: Double) {
    initialBearing = value
  }

  /** Camera intent from JS: "follow" tracks the puck, "overview" frames the whole line. */
  fun setCameraMode(value: String) {
    cameraMode = value
    applyCameraMode()
  }

  /** Bumped by JS to re-apply the same camera mode (e.g. recenter tap while following). */
  fun setCameraNonce(@Suppress("UNUSED_PARAMETER") value: Int) {
    applyCameraMode()
  }

  fun setDirectionsJson(json: String) {
    if (json.isBlank()) return
    val parsed = try {
      DirectionsResponse.fromJson(json).routes.firstOrNull()
    } catch (e: Exception) {
      Log.e(TAG, "Failed to parse DirectionsResponse", e)
      onNavError(mapOf("message" to (e.message ?: "Could not read route")))
      null
    } ?: return

    val wasReroute = navigationRunning
    route = parsed
    arrivalSent = false
    lastStepKey = -1
    lastOffRouteEmitAt = 0L
    // A fresh line ends the previous off-route episode.
    deviation.reset()
    if (wasReroute) {
      // Same session, new path. Google / Apple / Waze all speak the next action
      // the moment the replacement lands, not after the next 400 m milestone.
      replayEngine?.assign(parsed)
      navigation?.startNavigation(parsed)
      scheduleResumeSpeak(pickResumeAnnouncement(parsed))
    } else {
      maybeStartNavigation()
    }
  }

  // ---------------------------------------------------------------- map setup

  private fun styleUrl(): String = if (themeMode == "light") {
    context.getString(R.string.tuned_nav_map_style_light)
  } else {
    context.getString(R.string.tuned_nav_map_style_dark)
  }

  private fun applyStyle() {
    val map = mapLibreMap ?: return
    styleReady = false
    map.setStyle(Style.Builder().fromUri(styleUrl())) { loaded ->
      style = loaded
      styleReady = true
      addRouteLayers(loaded)
      activateLocationComponent(loaded)
      applyInitialCamera()
      applyCameraMode()
      maybeStartNavigation()
    }
  }

  private fun addRouteLayers(target: Style) {
    target.addSource(GeoJsonSource(SOURCE_ROUTE, routeGeoJson))
    target.addSource(GeoJsonSource(SOURCE_TRAFFIC, trafficGeoJson))
    target.addSource(GeoJsonSource(SOURCE_CYCLE, cyclewayGeoJson))

    target.addLayer(
      LineLayer(LAYER_ROUTE_CASING, SOURCE_ROUTE).withProperties(
        PropertyFactory.lineColor(CASING_COLOR),
        PropertyFactory.lineWidth(ROUTE_CASING_WIDTH),
        PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
        PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
      ),
    )
    target.addLayer(
      LineLayer(LAYER_ROUTE_CORE, SOURCE_ROUTE).withProperties(
        PropertyFactory.lineColor(if (rerouting) REROUTE_COLOR else ROUTE_COLOR),
        PropertyFactory.lineWidth(ROUTE_CORE_WIDTH),
        PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
        PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
      ),
    )
    // Overlays carry their planning-map colour per feature so nav matches the planner.
    target.addLayer(
      LineLayer(LAYER_CYCLE, SOURCE_CYCLE).withProperties(
        PropertyFactory.lineColor(Expression.get(PROP_COLOR)),
        PropertyFactory.lineWidth(ROUTE_CORE_WIDTH),
        PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
        PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
        PropertyFactory.visibility(if (cyclewaysVisible) Property.VISIBLE else Property.NONE),
      ),
    )
    target.addLayer(
      LineLayer(LAYER_TRAFFIC, SOURCE_TRAFFIC).withProperties(
        PropertyFactory.lineColor(Expression.get(PROP_COLOR)),
        PropertyFactory.lineWidth(ROUTE_CORE_WIDTH),
        PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
        PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
      ),
    )
  }

  private fun applyRouteLineColors() {
    val core = style?.getLayer(LAYER_ROUTE_CORE) ?: return
    core.setProperties(
      PropertyFactory.lineColor(if (rerouting) REROUTE_COLOR else ROUTE_COLOR),
    )
    style?.getLayer(LAYER_CYCLE)?.setProperties(
      PropertyFactory.lineOpacity(if (rerouting) 0.35f else 1f),
    )
    style?.getLayer(LAYER_TRAFFIC)?.setProperties(
      PropertyFactory.lineOpacity(if (rerouting) 0.35f else 1f),
    )
  }

  @SuppressLint("MissingPermission")
  private fun activateLocationComponent(target: Style) {
    val map = mapLibreMap ?: return
    val component = map.locationComponent
    try {
      component.activateLocationComponent(
        LocationComponentActivationOptions
          .builder(context, target)
          // Puck is fed from GPS (PuckFeedLocationEngine), never from snapped
          // progress, so the arrow stays on the rider while guidance uses the line.
          .useDefaultLocationEngine(false)
          .locationComponentOptions(
            LocationComponentOptions.builder(context)
              // SDK default 1.1: interpolate between GPS samples so 1 Hz fixes
              // still look like motion. 0 made every update a teleport.
              .trackingAnimationDurationMultiplier(1.1f)
              .compassAnimationEnabled(true)
              .accuracyAnimationEnabled(false)
              .pulseEnabled(false)
              .build(),
          )
          .build(),
      )
      component.isLocationComponentEnabled = true
      component.renderMode = RenderMode.NORMAL
      component.addOnCameraTrackingChangedListener(object : OnCameraTrackingChangedListener {
        override fun onCameraTrackingDismissed() {
          if (!trackingUser) return
          trackingUser = false
          onTrackingChanged(mapOf("tracking" to false))
        }

        override fun onCameraTrackingChanged(currentMode: Int) {
          val tracking = currentMode != CameraMode.NONE
          if (tracking == trackingUser) return
          trackingUser = tracking
          onTrackingChanged(mapOf("tracking" to tracking))
        }
      })
      locationComponent = component
      lastFollowCamera = Int.MIN_VALUE
      lastFollowRender = Int.MIN_VALUE
      lastFollowZoom = Double.NaN
      applyFollowModes()
    } catch (e: Exception) {
      Log.e(TAG, "activateLocationComponent failed", e)
      onNavError(mapOf("message" to (e.message ?: "Location layer failed")))
    }
  }

  private fun applyInitialCamera() {
    val map = mapLibreMap ?: return
    val lat = initialLatitude ?: return
    val lon = initialLongitude ?: return
    map.cameraPosition = CameraPosition.Builder()
      .target(LatLng(lat, lon))
      .zoom(FOLLOW_ZOOM)
      .tilt(FOLLOW_TILT)
      .bearing(initialBearing)
      .build()
  }

  /**
   * Follow camera + puck render, switched on speed so standing still is not stuck
   * on 1 Hz GPS bearings.
   *
   * Stopped: LocationComponent reads the magnetometer itself (TRACKING_COMPASS /
   * RenderMode.COMPASS) at sensor rate. Moving: GPS course with interpolated
   * positions (TRACKING_GPS / RenderMode.GPS).
   */
  private fun applyFollowModes() {
    val component = locationComponent ?: return
    if (cameraMode == "overview") {
      lastFollowCamera = CameraMode.NONE
      component.cameraMode = CameraMode.NONE
      showRouteOverview()
      return
    }

    val useCompass = shouldFollowCompass()
    val hasSensor = compass?.hasReliableHeading == true
    val camera = when {
      !hasSensor -> CameraMode.TRACKING_GPS_NORTH
      useCompass -> CameraMode.TRACKING_COMPASS
      else -> CameraMode.TRACKING_GPS
    }
    val render = when {
      !hasSensor -> RenderMode.NORMAL
      useCompass -> RenderMode.COMPASS
      else -> RenderMode.GPS
    }
    val zoom = if (zoomedOutForSpeed) FOLLOW_ZOOM_FAST else FOLLOW_ZOOM
    if (camera == lastFollowCamera && render == lastFollowRender && zoom == lastFollowZoom) {
      return
    }
    lastFollowCamera = camera
    lastFollowRender = render
    lastFollowZoom = zoom
    try {
      component.renderMode = render
      component.setCameraMode(
        camera,
        CAMERA_TRANSITION_MS,
        zoom,
        null,
        FOLLOW_TILT,
        null,
      )
    } catch (e: Exception) {
      Log.w(TAG, "applyFollowModes failed: ${e.message}")
      lastFollowCamera = Int.MIN_VALUE
      lastFollowRender = Int.MIN_VALUE
      lastFollowZoom = Double.NaN
      return
    }
    if (!trackingUser) {
      trackingUser = true
      onTrackingChanged(mapOf("tracking" to true))
    }
  }

  /** Same hysteresis as RiderLocationEngine: GPS course above 3 m/s, compass below 1.2. */
  private fun shouldFollowCompass(): Boolean {
    val speed = lastFixSpeed
    if (speed >= FOLLOW_GPS_MIN_MS) return false
    if (speed <= FOLLOW_COMPASS_MAX_MS) return true
    return lastFollowRender == RenderMode.COMPASS || lastFollowRender == Int.MIN_VALUE
  }

  private fun applyCameraMode() {
    applyFollowModes()
  }

  private fun showRouteOverview() {
    val map = mapLibreMap ?: return
    val bounds = routeBounds() ?: return
    map.animateCamera(
      CameraUpdateFactory.newLatLngBounds(
        bounds,
        OVERVIEW_PAD_H,
        OVERVIEW_PAD_TOP,
        OVERVIEW_PAD_H,
        OVERVIEW_PAD_BOTTOM,
      ),
      OVERVIEW_MS,
    )
  }

  /** Bounds straight from the Tuned line JSON — no geojson model dependency. */
  private fun routeBounds(): LatLngBounds? {
    return try {
      val features = JSONObject(routeGeoJson).optJSONArray("features") ?: return null
      var minLat = Double.MAX_VALUE
      var maxLat = -Double.MAX_VALUE
      var minLon = Double.MAX_VALUE
      var maxLon = -Double.MAX_VALUE
      var seen = 0
      for (i in 0 until features.length()) {
        val coords = features.optJSONObject(i)
          ?.optJSONObject("geometry")
          ?.optJSONArray("coordinates") ?: continue
        for (j in 0 until coords.length()) {
          val pair = coords.opt(j) as? JSONArray ?: continue
          val lon = pair.optDouble(0, Double.NaN)
          val lat = pair.optDouble(1, Double.NaN)
          if (lon.isNaN() || lat.isNaN()) continue
          seen += 1
          if (lat < minLat) minLat = lat
          if (lat > maxLat) maxLat = lat
          if (lon < minLon) minLon = lon
          if (lon > maxLon) maxLon = lon
        }
      }
      if (seen < 2) return null
      LatLngBounds.from(maxLat, maxLon, minLat, minLon)
    } catch (e: Exception) {
      Log.w(TAG, "routeBounds failed: ${e.message}")
      null
    }
  }

  /**
   * Heading available -> chevron. Stopped uses the compass; moving uses GPS course.
   * No heading -> plain circle, north-up.
   */
  private fun applyPuckMode(@Suppress("UNUSED_PARAMETER") hasHeading: Boolean) {
    applyFollowModes()
  }

  // ---------------------------------------------------------------- engine

  private fun maybeStartNavigation() {
    if (navigationRunning || !styleReady) return
    val activeRoute = route ?: return

    val tracker = compass ?: CompassHeadingTracker(context) { hasHeading ->
      mainHandler.post { applyPuckMode(hasHeading) }
    }.also {
      compass = it
      if (isAttachedToWindow) it.start()
    }

    val innerEngine = if (simulate) {
      ReplayRouteLocationEngine().also {
        replayEngine = it
        it.assign(activeRoute)
      }
    } else {
      try {
        RiderLocationEngine(
          GoogleLocationEngine(context.applicationContext, Looper.getMainLooper()),
        ) { tracker.headingDegrees }.also { riderEngine = it }
      } catch (e: Exception) {
        Log.w(TAG, "GoogleLocationEngine unavailable: ${e.message}")
        onNavError(mapOf("message" to "Location services unavailable"))
        return
      }
    }
    // Puck + deviation see the raw fix. The engine may still project for step
    // progress; that must not move the arrow.
    val engine = PuckFeedLocationEngine(innerEngine) { loc ->
      mainHandler.post { onRawFix(loc) }
    }

    // Snapping off: the puck is the measured position, so the map never argues with
    // the rider. Deviation is judged by RouteDeviationTracker, and Tuned Flask owns
    // replanning, so the SDK detector would only be a second, blunter opinion.
    val options = MapLibreNavigationOptions.Builder()
      .withEnableOffRouteDetection(false)
      .withEnableFasterRouteDetection(false)
      .withSnapToRoute(false)
      .build()

    val nav = AndroidMapLibreNavigation(
      context = context.applicationContext,
      options = options,
      locationEngine = engine,
      snapEngine = NoSnap(),
    )
    navigation = nav
    voice = NavVoice(context).also { it.muted = muted }

    nav.addProgressChangeListener(progressListener)
    nav.addMilestoneEventListener(milestoneListener)
    nav.startNavigation(activeRoute)
    navigationRunning = true
    onNavReady(mapOf("ready" to true))
  }

  private val progressListener = object : ProgressChangeListener {
    override fun onProgressChange(location: Location, routeProgress: RouteProgress) {
      handleProgress(location, routeProgress)
    }
  }

  private val milestoneListener = object : MilestoneEventListener {
    override fun onMilestoneEvent(
      routeProgress: RouteProgress,
      instruction: String?,
      milestone: Milestone,
    ) {
      if (milestone !is VoiceInstructionMilestone) return
      // Cues belong to the line being replaced — speaking them would send the rider
      // to a turn that is about to disappear.
      if (rerouting) return
      val announcement = (if (milestone.announcement.isNullOrBlank()) instruction else milestone.announcement)
        ?.trim().orEmpty()
      if (announcement.isEmpty()) return
      // The post-reroute resume already spoke this; do not say it twice.
      if (announcement == lastImperativeAnnouncement) {
        lastImperativeAnnouncement = null
        return
      }
      voice?.speak(announcement)
    }
  }

  /**
   * Fix-quality extras carried alongside progress so a ride report can be judged
   * later: a tap logged on a 40 m fix means something very different from one on
   * a 4 m fix. Everything here is already on the Android fix — no new sensors.
   */
  @Suppress("DEPRECATION")
  private fun fixQuality(location: Location): Map<String, Any?> {
    val fix = try {
      location.toAndroidLocation()
    } catch (e: Exception) {
      Log.w(TAG, "toAndroidLocation failed: ${e.message}")
      null
    }
    val modern = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
    return mapOf(
      "altitude" to fix?.takeIf { it.hasAltitude() }?.altitude,
      "hAccuracyM" to fix?.takeIf { it.hasAccuracy() }?.accuracy,
      "vAccuracyM" to fix
        ?.takeIf { modern && it.hasVerticalAccuracy() }
        ?.verticalAccuracyMeters,
      "speedAccuracyMps" to fix
        ?.takeIf { modern && it.hasSpeedAccuracy() }
        ?.speedAccuracyMetersPerSecond,
      "bearingAccuracyDeg" to fix
        ?.takeIf { modern && it.hasBearingAccuracy() }
        ?.bearingAccuracyDegrees,
      // Fix time, not "now" — a stale fix is visible in the gap.
      "gpsEpochMs" to (location.timeMilliseconds ?: fix?.time),
      "mocked" to when {
        fix == null -> null
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> fix.isMock
        else -> fix.isFromMockProvider
      },
      // Reported in addition to the GPS course, not instead of it.
      "compassHeadingDeg" to compass?.headingDegrees,
      "puckSource" to if (simulate) "replay" else riderEngine?.puckSource,
    )
  }

  private fun handleProgress(location: Location, progress: RouteProgress) {
    val now = System.currentTimeMillis()
    applySpeedZoom(location.speedMetersPerSeconds ?: 0f)

    val legProgress = progress.currentLegProgress
    val stepKey = progress.legIndex * 1000 + progress.stepIndex
    val stepChanged = stepKey != lastStepKey
    if (!stepChanged && now - lastProgressAt < PROGRESS_THROTTLE_MS) return
    lastProgressAt = now
    lastStepKey = stepKey

    // stepIndex is the step being ridden; the maneuver ahead starts the next one.
    val hasUpcomingStep = legProgress.upComingStep != null
    val lastLeg = progress.legIndex >= progress.directionsRoute.legs.size - 1
    val upcomingLegIndex = when {
      hasUpcomingStep -> progress.legIndex
      lastLeg -> progress.legIndex
      else -> progress.legIndex + 1
    }
    val upcomingStepIndex = when {
      hasUpcomingStep -> progress.stepIndex + 1
      lastLeg -> progress.stepIndex
      else -> 0
    }

    onRouteProgress(
      mapOf(
        "legIndex" to progress.legIndex,
        "stepIndex" to progress.stepIndex,
        "upcomingLegIndex" to upcomingLegIndex,
        "upcomingStepIndex" to upcomingStepIndex,
        "distanceRemaining" to progress.distanceRemaining,
        "durationRemaining" to progress.durationRemaining,
        "stepDistanceRemaining" to legProgress.currentStepProgress.distanceRemaining,
        "fractionTraveled" to progress.fractionTraveled,
        "latitude" to location.latitude,
        "longitude" to location.longitude,
        "speed" to (location.speedMetersPerSeconds ?: 0f),
        "bearing" to (location.bearing ?: 0f),
        "distanceFromRoute" to distanceFromRoute,
        "hasHeading" to (compass?.hasReliableHeading == true),
      ) + fixQuality(location),
    )

    if (!arrivalSent && progress.distanceRemaining <= ARRIVAL_RADIUS_M) {
      arrivalSent = true
      onArrival(mapOf("arrived" to true))
    }
  }

  /** GPS (or replay) fix — puck and off-route live here, not on snapped progress. */
  private fun onRawFix(location: Location) {
    lastFixSpeed = location.speedMetersPerSeconds ?: 0f
    applySpeedZoom(lastFixSpeed)
    applyFollowModes()
    locationComponent?.forceLocationUpdate(location.toAndroidLocation())
    evaluateDeviation(location, System.currentTimeMillis())
  }

  /** Every fix is checked, not just the throttled ones, so the timer stays honest. */
  private fun evaluateDeviation(location: Location, now: Long) {
    val result = deviation.update(location.latitude, location.longitude, now) ?: return
    distanceFromRoute = result.distanceM
    if (result.entered) {
      lastOffRouteEmitAt = now
      onOffRoute(
        mapOf(
          "latitude" to location.latitude,
          "longitude" to location.longitude,
          "distanceFromRoute" to result.distanceM,
        ),
      )
    } else if (result.rejoined) {
      lastOffRouteEmitAt = 0L
      onRouteRejoined(
        mapOf(
          "latitude" to location.latitude,
          "longitude" to location.longitude,
          "distanceFromRoute" to result.distanceM,
        ),
      )
    } else if (
      result.offRoute &&
      !rerouting &&
      now - lastOffRouteEmitAt >= OFF_ROUTE_REPEAT_MS
    ) {
      // `entered` fires once per episode. A rider who stays on a different street
      // never rejoins, so JS would never start another replan without this nudge.
      lastOffRouteEmitAt = now
      onOffRoute(
        mapOf(
          "latitude" to location.latitude,
          "longitude" to location.longitude,
          "distanceFromRoute" to result.distanceM,
        ),
      )
    }
  }

  /** Pull the camera back at speed so the rider sees further ahead. */
  private fun applySpeedZoom(speed: Float) {
    if (cameraMode == "overview") return
    val shouldZoomOut = if (zoomedOutForSpeed) {
      speed > SPEED_ZOOM_EXIT_MS
    } else {
      speed > SPEED_ZOOM_ENTER_MS
    }
    if (shouldZoomOut == zoomedOutForSpeed) return
    zoomedOutForSpeed = shouldZoomOut
    applyFollowModes()
  }

  private fun cancelResumeSpeak() {
    resumeSpeakRunnable?.let { mainHandler.removeCallbacks(it) }
    resumeSpeakRunnable = null
  }

  private fun scheduleResumeSpeak(text: String?) {
    val clean = text?.trim().orEmpty()
    if (clean.isEmpty()) return
    lastImperativeAnnouncement = clean
    cancelResumeSpeak()
    val r = Runnable {
      resumeSpeakRunnable = null
      // QUEUE_ADD so this follows "Rerouting" if it is still speaking.
      voice?.speak(clean, flush = false)
    }
    resumeSpeakRunnable = r
    mainHandler.postDelayed(r, RESUME_SPEAK_DELAY_MS)
  }

  /**
   * Cue the rider would hear now on the new line. Google, Apple and Waze all
   * speak the next action immediately after "Recalculating", with the distance
   * if the turn is not yet under the wheel. MapLibre's milestone often skips
   * the entry cue because remaining is already ~1 m below `distanceAlongGeometry`.
   */
  private fun pickResumeAnnouncement(route: DirectionsRoute): String? {
    val step = route.legs.firstOrNull()?.steps?.firstOrNull() ?: return null
    val voices = step.voiceInstructions.orEmpty().filter { !it.announcement.isNullOrBlank() }
    if (voices.isEmpty()) {
      return step.maneuver.instruction?.trim()?.takeIf { it.isNotEmpty() }
    }
    val rem = step.distance
    return voices
      .filter { it.distanceAlongGeometry <= rem + RESUME_DISTANCE_SLACK_M }
      .maxByOrNull { it.distanceAlongGeometry }
      ?.announcement
      ?: voices.last().announcement
  }

  private fun stopNavigation() {
    cancelResumeSpeak()
    lastImperativeAnnouncement = null
    val nav = navigation ?: return
    try {
      nav.removeProgressChangeListener(progressListener)
      nav.removeMilestoneEventListener(milestoneListener)
      nav.stopNavigation()
      nav.onDestroy()
    } catch (e: Exception) {
      Log.w(TAG, "stopNavigation: ${e.message}")
    }
    navigation = null
    replayEngine?.onStop()
    replayEngine = null
    riderEngine = null
    navigationRunning = false
  }

  // ---------------------------------------------------------------- lifecycle

  override fun onAttachedToWindow() {
    super.onAttachedToWindow()
    mapView.onStart()
    mapView.onResume()
    compass?.start()
  }

  override fun onDetachedFromWindow() {
    compass?.stop()
    cancelResumeSpeak()
    voice?.stopSpeaking()
    mapView.onPause()
    mapView.onStop()
    super.onDetachedFromWindow()
  }

  fun destroy() {
    mainHandler.removeCallbacksAndMessages(null)
    stopNavigation()
    compass?.stop()
    compass = null
    voice?.release()
    voice = null
    try {
      mapView.onDestroy()
    } catch (e: Exception) {
      Log.w(TAG, "mapView.onDestroy: ${e.message}")
    }
  }

  private companion object {
    const val TAG = "TunedNavMapView"
    const val EMPTY_FC = """{"type":"FeatureCollection","features":[]}"""

    const val SOURCE_ROUTE = "tuned-nav-route"
    const val SOURCE_TRAFFIC = "tuned-nav-traffic"
    const val SOURCE_CYCLE = "tuned-nav-cycle"
    const val LAYER_ROUTE_CASING = "tuned-nav-route-casing"
    const val LAYER_ROUTE_CORE = "tuned-nav-route-core"
    const val LAYER_TRAFFIC = "tuned-nav-traffic-line"
    const val LAYER_CYCLE = "tuned-nav-cycle-line"
    const val PROP_COLOR = "color"

    // Planning-map parity (RouteOverlayLayers ROUTE_CASING/CORE widths).
    const val ROUTE_CASING_WIDTH = 13f
    const val ROUTE_CORE_WIDTH = 5f
    const val CASING_COLOR = "#FFFFFF"
    const val ROUTE_COLOR = "#FF0061"
    const val REROUTE_COLOR = "#9AA3B2"

    const val FOLLOW_ZOOM = 16.4
    // Held until well below the entry speed so the zoom cannot oscillate.
    const val FOLLOW_ZOOM_FAST = 15.6
    const val SPEED_ZOOM_ENTER_MS = 6.5f
    const val SPEED_ZOOM_EXIT_MS = 4.5f
    const val FOLLOW_TILT = 45.0
    /** Short — LocationComponent interpolates between fixes; this is only mode/zoom changes. */
    const val CAMERA_TRANSITION_MS = 350L
    const val FOLLOW_GPS_MIN_MS = 3.0f
    const val FOLLOW_COMPASS_MAX_MS = 1.2f
    const val OVERVIEW_MS = 700
    const val OVERVIEW_PAD_H = 60
    const val OVERVIEW_PAD_TOP = 240
    const val OVERVIEW_PAD_BOTTOM = 260

    const val ARRIVAL_RADIUS_M = 25.0
    const val PROGRESS_THROTTLE_MS = 900L
    /** While still off-route, re-emit so JS can replan after cooldown without a rejoin. */
    const val OFF_ROUTE_REPEAT_MS = 5_000L
    /** Let "Rerouting" finish, then speak the new next-turn (Google / Apple / Waze). */
    const val RESUME_SPEAK_DELAY_MS = 280L
    const val RESUME_DISTANCE_SLACK_M = 12.0
  }
}
