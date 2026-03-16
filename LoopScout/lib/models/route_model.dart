import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:latlong2/latlong.dart';

part 'route_model.freezed.dart';
part 'route_model.g.dart';

/// A saved route with its waypoints and metadata.
@freezed
class RouteModel with _$RouteModel {
  const factory RouteModel({
    required String id,
    required String name,
    required DateTime createdAt,
    required double distanceMeters,
    required double elevationGainMeters,
    required List<WaypointModel> waypoints,
    @Default(0.0) double trailPercentage,
    String? notes,
  }) = _RouteModel;

  factory RouteModel.fromJson(Map<String, dynamic> json) =>
      _$RouteModelFromJson(json);
}

/// A single point along a route.
@freezed
class WaypointModel with _$WaypointModel {
  const factory WaypointModel({
    required double latitude,
    required double longitude,
    @Default(0.0) double elevation,
  }) = _WaypointModel;

  factory WaypointModel.fromJson(Map<String, dynamic> json) =>
      _$WaypointModelFromJson(json);
}

/// Extension to convert between WaypointModel and LatLng.
extension WaypointLatLng on WaypointModel {
  LatLng toLatLng() => LatLng(latitude, longitude);
}

extension LatLngWaypoint on LatLng {
  WaypointModel toWaypoint({double elevation = 0.0}) =>
      WaypointModel(
        latitude: latitude,
        longitude: longitude,
        elevation: elevation,
      );
}
