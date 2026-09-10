import ExpoModulesCore

/**
 * Placeholder so the module autolinks on Apple platforms. Turn-by-turn runs on
 * Android only — JS renders the plan map instead of the nav view elsewhere.
 *
 * JS never mounts this view: `TBT_ENGINE` in src/navigation/useNavSession.ts
 * refuses to open a session without a real engine, and PlanMapScreen guards the
 * mount as well. Filling it in is beta 2 — the props and events must match
 * src/TunedMaplibreNav.types.ts exactly. See
 * 0_documentation/tasks/IOS_TESTFLIGHT_BETA1.md §6.
 */
public class TunedMaplibreNavModule: Module {
  public func definition() -> ModuleDefinition {
    Name("TunedMaplibreNav")

    View(TunedMaplibreNavView.self) {}
  }
}

public class TunedMaplibreNavView: ExpoView {}
