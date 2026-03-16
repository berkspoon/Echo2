import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';
import 'package:loopscout/services/routing_service.dart';

/// Provides the RoutingService singleton.
final routingServiceProvider = Provider<RoutingService>((ref) {
  final service = RoutingService();
  ref.onDispose(() => service.dispose());
  return service;
});

/// The current drawing/editing mode for the map.
enum DrawingMode {
  pan,    // default — pan and zoom the map
  draw,   // finger drawing snaps to roads/trails
  erase,  // tap a segment to remove it
}

/// State for the route creation screen.
class RouteCreationState {
  final DrawingMode mode;
  final List<LatLng> drawnPoints;       // raw finger gesture points
  final List<LatLng> snappedPoints;     // OSRM-snapped route
  final double distanceMeters;
  final bool isSnapping;                // loading indicator
  final String? error;
  final List<RouteSuggestion> suggestions;

  const RouteCreationState({
    this.mode = DrawingMode.pan,
    this.drawnPoints = const [],
    this.snappedPoints = const [],
    this.distanceMeters = 0,
    this.isSnapping = false,
    this.error,
    this.suggestions = const [],
  });

  RouteCreationState copyWith({
    DrawingMode? mode,
    List<LatLng>? drawnPoints,
    List<LatLng>? snappedPoints,
    double? distanceMeters,
    bool? isSnapping,
    String? error,
    List<RouteSuggestion>? suggestions,
  }) {
    return RouteCreationState(
      mode: mode ?? this.mode,
      drawnPoints: drawnPoints ?? this.drawnPoints,
      snappedPoints: snappedPoints ?? this.snappedPoints,
      distanceMeters: distanceMeters ?? this.distanceMeters,
      isSnapping: isSnapping ?? this.isSnapping,
      error: error,
      suggestions: suggestions ?? this.suggestions,
    );
  }

  double get distanceMiles => distanceMeters / 1609.344;
  double get distanceKm => distanceMeters / 1000.0;
  bool get hasRoute => snappedPoints.isNotEmpty;
}

/// Manages the route creation workflow:
/// drawing → snapping → editing → saving.
class RouteCreationNotifier extends StateNotifier<RouteCreationState> {
  final RoutingService _routingService;
  final List<List<LatLng>> _undoStack = [];

  RouteCreationNotifier(this._routingService)
      : super(const RouteCreationState());

  /// Switch drawing mode.
  void setMode(DrawingMode mode) {
    state = state.copyWith(mode: mode);
  }

  /// Called continuously as the user drags their finger on the map.
  void addDrawnPoint(LatLng point) {
    state = state.copyWith(
      drawnPoints: [...state.drawnPoints, point],
    );
  }

  /// Called when the user lifts their finger — triggers snap-to-road.
  Future<void> finishDrawingSegment() async {
    if (state.drawnPoints.length < 2) return;

    // Save current state for undo
    _undoStack.add(List.from(state.snappedPoints));

    state = state.copyWith(isSnapping: true, error: null);

    try {
      final result = await _routingService.snapToRoute(state.drawnPoints);

      // Append snapped segment to existing route
      final combined = [
        ...state.snappedPoints,
        ...result.points,
      ];

      // Recalculate total distance
      final totalDistance = _calculatePolylineDistance(combined);

      state = state.copyWith(
        snappedPoints: combined,
        distanceMeters: totalDistance,
        drawnPoints: [], // clear raw drawing
        isSnapping: false,
      );
    } catch (e) {
      state = state.copyWith(
        isSnapping: false,
        error: 'Could not snap to route: ${e.toString()}',
      );
    }
  }

  /// Undo the last drawn segment.
  void undo() {
    if (_undoStack.isEmpty) return;
    final previous = _undoStack.removeLast();
    final distance = _calculatePolylineDistance(previous);
    state = state.copyWith(
      snappedPoints: previous,
      distanceMeters: distance,
      drawnPoints: [],
    );
  }

  /// Close the route as a loop back to the starting point.
  Future<void> closeLoop() async {
    if (state.snappedPoints.length < 2) return;

    state = state.copyWith(isSnapping: true, error: null);

    try {
      final result = await _routingService.getRoute(
        state.snappedPoints.last,
        state.snappedPoints.first,
      );

      final combined = [...state.snappedPoints, ...result.points];
      final totalDistance = _calculatePolylineDistance(combined);

      state = state.copyWith(
        snappedPoints: combined,
        distanceMeters: totalDistance,
        isSnapping: false,
      );
    } catch (e) {
      state = state.copyWith(
        isSnapping: false,
        error: 'Could not close loop: ${e.toString()}',
      );
    }
  }

  /// Clear the entire route.
  void clearRoute() {
    _undoStack.clear();
    state = const RouteCreationState();
  }

  /// Request trail-based route suggestions for a target distance.
  Future<void> suggestRoutes({
    required LatLng origin,
    required double targetDistanceMeters,
  }) async {
    state = state.copyWith(isSnapping: true, error: null);

    try {
      final suggestions = await _routingService.suggestLoopRoutes(
        origin: origin,
        targetDistanceMeters: targetDistanceMeters,
      );

      state = state.copyWith(
        suggestions: suggestions,
        isSnapping: false,
      );
    } catch (e) {
      state = state.copyWith(
        isSnapping: false,
        error: 'Could not generate suggestions: ${e.toString()}',
      );
    }
  }

  /// Apply a suggestion to the current route.
  void applySuggestion(RouteSuggestion suggestion) {
    _undoStack.add(List.from(state.snappedPoints));
    state = state.copyWith(
      snappedPoints: suggestion.points,
      distanceMeters: suggestion.distanceMeters,
      suggestions: [],
    );
  }

  /// Calculate the total distance of a polyline in meters.
  double _calculatePolylineDistance(List<LatLng> points) {
    const distance = Distance();
    double total = 0;
    for (int i = 0; i < points.length - 1; i++) {
      total += distance.as(LengthUnit.Meter, points[i], points[i + 1]);
    }
    return total;
  }
}

/// Provider for the route creation state.
final routeCreationProvider =
    StateNotifierProvider<RouteCreationNotifier, RouteCreationState>((ref) {
  final routingService = ref.watch(routingServiceProvider);
  return RouteCreationNotifier(routingService);
});
