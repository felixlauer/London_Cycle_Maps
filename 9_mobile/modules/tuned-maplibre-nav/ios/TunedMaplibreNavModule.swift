import ExpoModulesCore

/**
 * Placeholder so the module autolinks on Apple platforms. Turn-by-turn runs on
 * Android only — JS renders the plan map instead of the nav view elsewhere.
 */
public class TunedMaplibreNavModule: Module {
  public func definition() -> ModuleDefinition {
    Name("TunedMaplibreNav")

    View(TunedMaplibreNavView.self) {}
  }
}

public class TunedMaplibreNavView: ExpoView {}
