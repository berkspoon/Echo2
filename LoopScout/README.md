# LoopScout

A trail-first running route planner for iPhone, built with Flutter.

## What It Does

- **Draw-to-snap route creation**: Trace a route with your finger and it snaps to roads and trails
- **Distance-based trail suggestions**: Enter a target distance and get trail-heavy loop options
- **Accurate distance**: Calculated along actual path geometry, not point-to-point
- **Trail-first**: Uses OpenStreetMap data which has superior trail coverage

## Tech Stack

- **Language**: Dart (no JavaScript required)
- **Framework**: Flutter with Cupertino widgets (iOS look & feel)
- **Maps**: flutter_map with OpenStreetMap tiles
- **Route snapping**: OSRM (Open Source Routing Machine)
- **Trail data**: OpenStreetMap Overpass API
- **State management**: Riverpod
- **Local storage**: Hive
- **GPS**: geolocator with Kalman filter smoothing

## Development (Windows PC)

### Prerequisites
1. [Flutter SDK](https://flutter.dev/docs/get-started/install/windows)
2. [VS Code](https://code.visualstudio.com/) + Flutter extension
3. [Android Studio](https://developer.android.com/studio) (for Android emulator only)
4. [Claude Code](https://www.anthropic.com/claude-code) (optional, for AI-assisted coding)

### Getting Started
```bash
# Clone and enter the project
cd loopscout

# Install dependencies
flutter pub get

# Generate freezed/riverpod code
dart run build_runner build --delete-conflicting-outputs

# Run on Android emulator (daily development)
flutter run

# Run with hot reload
flutter run --debug
```

### iOS Builds (via Codemagic)
Since we're on Windows, iOS builds happen in the cloud:

1. Push to your Git repo
2. Codemagic detects the push and builds the iOS .ipa
3. The build is uploaded to TestFlight
4. Install on iPhone via TestFlight

See [codemagic.io](https://codemagic.io) for setup instructions.

## Project Structure
```
lib/
├── main.dart                  # App entry point
├── theme/
│   └── app_theme.dart         # Colors, typography, Cupertino theme
├── screens/
│   ├── map_screen.dart        # Main map canvas with draw-to-snap
│   ├── route_list_screen.dart # Saved routes list
│   └── settings_screen.dart   # App settings
├── widgets/
│   ├── drawing_toolbar_widget.dart      # Pan/Draw/Erase mode toolbar
│   ├── distance_display_widget.dart     # Route distance counter
│   ├── elevation_profile_widget.dart    # Elevation chart
│   └── distance_input_sheet_widget.dart # "Find a trail route" input
├── providers/
│   └── route_creation_provider.dart     # Route drawing state (Riverpod)
├── services/
│   ├── routing_service.dart   # OSRM snap-to-road/trail + suggestions
│   ├── location_service.dart  # GPS with Kalman filter
│   └── trail_service.dart     # OSM Overpass trail queries
├── models/
│   ├── route_model.dart       # Route + Waypoint data classes
│   └── run_record_model.dart  # GPS run recording data classes
└── utils/
    └── distance_utils.dart    # Distance/pace/duration formatters
```

## Architecture

MVVM with Riverpod:
- **Screens** → read providers, render Cupertino UI
- **Providers** → manage state, call services
- **Services** → handle APIs (OSRM, Overpass, GPS)
- **Models** → immutable data classes (freezed)

## License

Private project — built for Melissa.
