package expo.modules.tunedmaplibrenav

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * Exposes the in-process MapLibre navigation map. All turn-by-turn chrome lives
 * in React Native, so the module is view-only — no Activity, no vendor UI.
 */
class TunedMaplibreNavModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("TunedMaplibreNav")

    View(TunedNavMapView::class) {
      Events(
        "onNavReady",
        "onRouteProgress",
        "onOffRoute",
        "onRouteRejoined",
        "onArrival",
        "onTrackingChanged",
        "onNavError",
      )

      Prop("directionsJson") { view: TunedNavMapView, json: String ->
        view.setDirectionsJson(json)
      }
      Prop("routeGeoJson") { view: TunedNavMapView, json: String ->
        view.setRouteGeoJson(json)
      }
      Prop("trafficGeoJson") { view: TunedNavMapView, json: String ->
        view.setTrafficGeoJson(json)
      }
      Prop("cyclewayGeoJson") { view: TunedNavMapView, json: String ->
        view.setCyclewayGeoJson(json)
      }
      Prop("themeMode") { view: TunedNavMapView, mode: String ->
        view.setThemeMode(mode)
      }
      Prop("simulate") { view: TunedNavMapView, simulate: Boolean ->
        view.setSimulate(simulate)
      }
      Prop("muted") { view: TunedNavMapView, muted: Boolean ->
        view.setMuted(muted)
      }
      Prop("rerouting") { view: TunedNavMapView, rerouting: Boolean ->
        view.setRerouting(rerouting)
      }
      Prop("cyclewaysVisible") { view: TunedNavMapView, visible: Boolean ->
        view.setCyclewaysVisible(visible)
      }
      Prop("cameraMode") { view: TunedNavMapView, mode: String ->
        view.setCameraMode(mode)
      }
      Prop("cameraNonce") { view: TunedNavMapView, nonce: Int ->
        view.setCameraNonce(nonce)
      }
      Prop("initialLatitude") { view: TunedNavMapView, value: Double? ->
        view.setInitialLatitude(value)
      }
      Prop("initialLongitude") { view: TunedNavMapView, value: Double? ->
        view.setInitialLongitude(value)
      }
      Prop("initialBearing") { view: TunedNavMapView, value: Double ->
        view.setInitialBearing(value)
      }

      OnViewDestroys { view: TunedNavMapView ->
        view.destroy()
      }
    }
  }
}
