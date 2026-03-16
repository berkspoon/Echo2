import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

/// Service for snapping drawn gestures to roads/trails via OSRM
/// and generating route suggestions.
class RoutingService {
  static const String _baseUrl = 'https://router.project-osrm.org';

  final http.Client _client;

  RoutingService({http.Client? client}) : _client = client ?? http.Client();

  /// Snap a list of drawn points to the nearest road/trail network.
  /// Uses OSRM's "match" endpoint with the foot profile.
  /// Returns the snapped polyline as a list of LatLng points,
  /// along with the total distance in meters.
  Future<SnapResult> snapToRoute(List<LatLng> drawnPoints) async {
    if (drawnPoints.length < 2) {
      return SnapResult(points: drawnPoints, distanceMeters: 0);
    }

    // Sample points to stay within OSRM limits (max ~100 coords per request)
    final sampled = _samplePoints(drawnPoints, maxPoints: 80);

    final coords = sampled
        .map((p) => '${p.longitude},${p.latitude}')
        .join(';');

    final radiuses = List.filled(sampled.length, '25').join(';');

    final url = Uri.parse(
      '$_baseUrl/match/v1/foot/$coords'
      '?overview=full&geometries=geojson&radiuses=$radiuses',
    );

    final response = await _client.get(url);

    if (response.statusCode != 200) {
      throw RoutingException('OSRM match failed: ${response.statusCode}');
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final code = data['code'] as String?;

    if (code != 'Ok') {
      throw RoutingException('OSRM match error: $code');
    }

    final matchings = data['matchings'] as List<dynamic>;
    if (matchings.isEmpty) {
      return SnapResult(points: drawnPoints, distanceMeters: 0);
    }

    // Extract the snapped geometry from the first matching
    final geometry = matchings[0]['geometry'] as Map<String, dynamic>;
    final coordinates = geometry['coordinates'] as List<dynamic>;
    final distance = (matchings[0]['distance'] as num).toDouble();

    final snappedPoints = coordinates
        .map((c) => LatLng((c as List)[1].toDouble(), c[0].toDouble()))
        .toList();

    return SnapResult(points: snappedPoints, distanceMeters: distance);
  }

  /// Get a route between two points via OSRM's route endpoint.
  Future<SnapResult> getRoute(LatLng start, LatLng end) async {
    final coords = '${start.longitude},${start.latitude}'
        ';${end.longitude},${end.latitude}';

    final url = Uri.parse(
      '$_baseUrl/route/v1/foot/$coords'
      '?overview=full&geometries=geojson&steps=true',
    );

    final response = await _client.get(url);

    if (response.statusCode != 200) {
      throw RoutingException('OSRM route failed: ${response.statusCode}');
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final routes = data['routes'] as List<dynamic>;

    if (routes.isEmpty) {
      throw RoutingException('No route found');
    }

    final geometry = routes[0]['geometry'] as Map<String, dynamic>;
    final coordinates = geometry['coordinates'] as List<dynamic>;
    final distance = (routes[0]['distance'] as num).toDouble();

    final points = coordinates
        .map((c) => LatLng((c as List)[1].toDouble(), c[0].toDouble()))
        .toList();

    return SnapResult(points: points, distanceMeters: distance);
  }

  /// Generate a loop route of approximately [targetDistanceMeters]
  /// starting and ending at [origin].
  /// Returns multiple route options scored by trail percentage.
  Future<List<RouteSuggestion>> suggestLoopRoutes({
    required LatLng origin,
    required double targetDistanceMeters,
    int maxSuggestions = 3,
  }) async {
    // TODO: Implement trail-aware loop generation
    // Strategy:
    // 1. Query OSM Overpass for trails within radius
    // 2. Generate candidate waypoints along trails
    // 3. Build loop routes through OSRM
    // 4. Score by trail percentage and distance match
    // 5. Return top N suggestions

    // Placeholder — returns empty until implemented
    return [];
  }

  /// Downsample a point list to at most [maxPoints] while
  /// preserving the first and last point.
  List<LatLng> _samplePoints(List<LatLng> points, {int maxPoints = 80}) {
    if (points.length <= maxPoints) return points;

    final result = <LatLng>[points.first];
    final step = (points.length - 1) / (maxPoints - 1);

    for (int i = 1; i < maxPoints - 1; i++) {
      result.add(points[(i * step).round()]);
    }

    result.add(points.last);
    return result;
  }

  void dispose() {
    _client.close();
  }
}

/// Result of a snap or route operation.
class SnapResult {
  final List<LatLng> points;
  final double distanceMeters;

  const SnapResult({
    required this.points,
    required this.distanceMeters,
  });

  double get distanceMiles => distanceMeters / 1609.344;
  double get distanceKm => distanceMeters / 1000.0;
}

/// A suggested route with metadata.
class RouteSuggestion {
  final List<LatLng> points;
  final double distanceMeters;
  final double elevationGainMeters;
  final double trailPercentage;
  final String type; // 'loop', 'out_and_back', 'lollipop'

  const RouteSuggestion({
    required this.points,
    required this.distanceMeters,
    required this.elevationGainMeters,
    required this.trailPercentage,
    required this.type,
  });
}

class RoutingException implements Exception {
  final String message;
  RoutingException(this.message);

  @override
  String toString() => 'RoutingException: $message';
}
