import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:loopscout/providers/route_creation_provider.dart';
import 'package:loopscout/widgets/drawing_toolbar_widget.dart';
import 'package:loopscout/widgets/distance_display_widget.dart';
import 'package:loopscout/theme/app_theme.dart';

/// The primary screen: map canvas with draw-to-snap route creation.
class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final MapController _mapController = MapController();

  // Default center — will be replaced by user's GPS location
  static const _defaultCenter = LatLng(40.0046, -75.3075); // Ardmore, PA area

  @override
  Widget build(BuildContext context) {
    final routeState = ref.watch(routeCreationProvider);

    return CupertinoPageScaffold(
      child: Stack(
        children: [
          // === Map layer ===
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: _defaultCenter,
              initialZoom: 14.0,
              onTap: _onMapTap,
              // Gesture handling changes based on drawing mode
              interactionOptions: InteractionOptions(
                flags: routeState.mode == DrawingMode.draw
                    ? InteractiveFlag.none // disable map gestures while drawing
                    : InteractiveFlag.all,
              ),
            ),
            children: [
              // OpenStreetMap tiles — free, no API key, great trail data
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.loopscout.app',
              ),

              // Snapped route polyline
              if (routeState.snappedPoints.isNotEmpty)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: routeState.snappedPoints,
                      strokeWidth: 4.0,
                      color: AppTheme.routeLine,
                    ),
                  ],
                ),

              // Live drawing preview (raw finger gesture, before snapping)
              if (routeState.drawnPoints.isNotEmpty)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: routeState.drawnPoints,
                      strokeWidth: 3.0,
                      color: AppTheme.routeLineDrawing.withOpacity(0.6),
                      isDotted: true,
                    ),
                  ],
                ),

              // Start/end markers
              if (routeState.snappedPoints.isNotEmpty)
                MarkerLayer(
                  markers: [
                    _buildMarker(
                      routeState.snappedPoints.first,
                      AppTheme.startMarker,
                      'S',
                    ),
                    if (routeState.snappedPoints.length > 1)
                      _buildMarker(
                        routeState.snappedPoints.last,
                        AppTheme.endMarker,
                        'E',
                      ),
                  ],
                ),
            ],
          ),

          // === Drawing gesture detector (overlay on map when in draw mode) ===
          if (routeState.mode == DrawingMode.draw)
            Positioned.fill(
              child: GestureDetector(
                onPanStart: _onDrawStart,
                onPanUpdate: _onDrawUpdate,
                onPanEnd: _onDrawEnd,
                behavior: HitTestBehavior.translucent,
              ),
            ),

          // === Distance display (top center) ===
          Positioned(
            top: MediaQuery.of(context).padding.top + 60,
            left: 16,
            right: 16,
            child: DistanceDisplayWidget(
              distanceMeters: routeState.distanceMeters,
              isLoading: routeState.isSnapping,
            ),
          ),

          // === Drawing toolbar (bottom) ===
          Positioned(
            bottom: MediaQuery.of(context).padding.bottom + 24,
            left: 16,
            right: 16,
            child: DrawingToolbarWidget(
              mode: routeState.mode,
              hasRoute: routeState.hasRoute,
              onModeChanged: (mode) {
                ref.read(routeCreationProvider.notifier).setMode(mode);
              },
              onUndo: () {
                ref.read(routeCreationProvider.notifier).undo();
              },
              onCloseLoop: () {
                ref.read(routeCreationProvider.notifier).closeLoop();
              },
              onClear: () {
                ref.read(routeCreationProvider.notifier).clearRoute();
              },
            ),
          ),

          // === Error banner ===
          if (routeState.error != null)
            Positioned(
              top: MediaQuery.of(context).padding.top + 120,
              left: 16,
              right: 16,
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.dangerRed.withOpacity(0.9),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  routeState.error!,
                  style: const TextStyle(
                    color: CupertinoColors.white,
                    fontSize: 14,
                  ),
                ),
              ),
            ),

          // === Snapping indicator ===
          if (routeState.isSnapping)
            const Positioned(
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              child: Center(
                child: CupertinoActivityIndicator(radius: 16),
              ),
            ),
        ],
      ),
    );
  }

  void _onMapTap(TapPosition tapPosition, LatLng point) {
    // Could be used for placing markers or selecting segments to erase
  }

  void _onDrawStart(DragStartDetails details) {
    final point = _screenToLatLng(details.localPosition);
    if (point != null) {
      ref.read(routeCreationProvider.notifier).addDrawnPoint(point);
    }
  }

  void _onDrawUpdate(DragUpdateDetails details) {
    final point = _screenToLatLng(details.localPosition);
    if (point != null) {
      ref.read(routeCreationProvider.notifier).addDrawnPoint(point);
    }
  }

  void _onDrawEnd(DragEndDetails details) {
    ref.read(routeCreationProvider.notifier).finishDrawingSegment();
  }

  /// Convert a screen position to a map LatLng coordinate.
  LatLng? _screenToLatLng(Offset screenPosition) {
    try {
      // flutter_map's camera provides point-to-latlng conversion
      final point = _mapController.camera.pointToLatLng(
        Point(screenPosition.dx, screenPosition.dy),
      );
      return point;
    } catch (_) {
      return null;
    }
  }

  Marker _buildMarker(LatLng point, Color color, String label) {
    return Marker(
      point: point,
      width: 28,
      height: 28,
      child: Container(
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(color: CupertinoColors.white, width: 2),
          boxShadow: [
            BoxShadow(
              color: color.withOpacity(0.3),
              blurRadius: 6,
              spreadRadius: 1,
            ),
          ],
        ),
        child: Center(
          child: Text(
            label,
            style: const TextStyle(
              color: CupertinoColors.white,
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ),
    );
  }
}
