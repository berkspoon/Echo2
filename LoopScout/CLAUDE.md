# LoopScout

## Quick Reference
- **Platform**: iOS (primary), Android (testing)
- **Language**: Dart 3.x
- **UI Framework**: Flutter 3.x with Cupertino widgets
- **Architecture**: MVVM with Riverpod
- **Minimum iOS Deployment**: 16.0
- **Minimum Android SDK**: 21
- **State Management**: flutter_riverpod
- **Maps**: flutter_map (OpenStreetMap tiles)
- **Routing Engine**: OSRM (Open Source Routing Machine)
- **Local Storage**: Hive
- **GPS**: geolocator + custom Kalman filter

## Project Purpose
LoopScout is a trail-first running route planner for iPhone. Users can:
1. Draw routes by tracing their finger on a map (draw-to-snap)
2. Enter a target distance and get trail-heavy loop/out-and-back suggestions
3. See accurate distance and elevation profiles
4. Save and organize routes

## Architecture Rules
- **MVVM pattern**: Screens (views) → Providers (view models) → Services (business logic) → Models (data)
- **Riverpod providers** live in `lib/providers/`. Use `@riverpod` annotation (code generation) for new providers.
- **Services** are singleton classes injected via Riverpod. They handle API calls, GPS, routing, and storage.
- **Models** are immutable data classes using `freezed` for code generation.
- **Screens** go in `lib/screens/`. Each screen is a StatelessWidget that reads providers.
- **Reusable widgets** go in `lib/widgets/`.
- **Cupertino-first**: Use CupertinoApp, CupertinoPageScaffold, CupertinoNavigationBar, etc. This app targets iPhone users.

## File Naming Conventions
- Snake_case for all file names: `route_creation_provider.dart`
- Suffix screens with `_screen.dart`: `map_screen.dart`
- Suffix widgets with `_widget.dart`: `elevation_profile_widget.dart`
- Suffix providers with `_provider.dart`: `route_creation_provider.dart`
- Suffix services with `_service.dart`: `routing_service.dart`
- Suffix models with `_model.dart`: `route_model.dart`

## Key Packages
```yaml
dependencies:
  flutter_riverpod: ^2.5.0
  riverpod_annotation: ^2.3.0
  flutter_map: ^6.1.0
  latlong2: ^0.9.0
  geolocator: ^12.0.0
  hive: ^2.2.3
  hive_flutter: ^1.1.0
  http: ^1.2.0
  freezed_annotation: ^2.4.0
  json_annotation: ^4.8.0
  path_provider: ^2.1.0
  uuid: ^4.2.0

dev_dependencies:
  build_runner: ^2.4.0
  freezed: ^2.4.0
  json_serializable: ^6.7.0
  riverpod_generator: ^2.4.0
  flutter_test:
    sdk: flutter
```

## Important Rules
1. **Never use `setState`** — all state flows through Riverpod providers.
2. **No Google Maps dependency** — we use flutter_map with OSM tiles to avoid API key costs and get better trail data.
3. **All HTTP calls go through services** — screens and providers never make direct HTTP requests.
4. **Cupertino widgets only** — no Material widgets (no Scaffold, AppBar, etc.). Use CupertinoPageScaffold, CupertinoNavigationBar, CupertinoButton, etc.
5. **Immutable models** — use freezed for all data models. No mutable state outside of providers.
6. **Test on Android emulator** — iOS builds go through Codemagic CI only. Don't assume iOS simulator access.

## OSRM API Reference
- **Match (snap to road)**: `GET /match/v1/foot/{coords}?overview=full&geometries=geojson`
- **Route (A to B)**: `GET /route/v1/foot/{coords}?overview=full&geometries=geojson&steps=true`
- **Public server**: `https://router.project-osrm.org`
- Coordinates format: `{lon},{lat};{lon},{lat}`

## OSM Overpass API Reference
- **Endpoint**: `https://overpass-api.de/api/interpreter`
- **Trail query example**: Fetch trails within radius of a point, filtered by highway=path|track|footway|cycleway
