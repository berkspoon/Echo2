import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

/// Service for querying OpenStreetMap trail data via the Overpass API.
class TrailService {
  static const String _overpassUrl =
      'https://overpass-api.de/api/interpreter';

  final http.Client _client;

  TrailService({http.Client? client}) : _client = client ?? http.Client();

  /// Fetch trails and paths within [radiusMeters] of [center].
  /// Returns a list of trail segments with metadata.
  Future<List<TrailSegment>> fetchNearbyTrails({
    required LatLng center,
    double radiusMeters = 5000,
  }) async {
    final query = '''
[out:json][timeout:25];
(
  way["highway"="path"](around:$radiusMeters,${center.latitude},${center.longitude});
  way["highway"="footway"](around:$radiusMeters,${center.latitude},${center.longitude});
  way["highway"="track"](around:$radiusMeters,${center.latitude},${center.longitude});
  way["highway"="cycleway"](around:$radiusMeters,${center.latitude},${center.longitude});
  way["highway"="bridleway"](around:$radiusMeters,${center.latitude},${center.longitude});
);
out body geom;
''';

    final response = await _client.post(
      Uri.parse(_overpassUrl),
      body: {'data': query},
    );

    if (response.statusCode != 200) {
      throw TrailServiceException(
        'Overpass API failed: ${response.statusCode}',
      );
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final elements = data['elements'] as List<dynamic>;

    return elements
        .where((e) => e['type'] == 'way' && e['geometry'] != null)
        .map((e) => _parseTrailSegment(e as Map<String, dynamic>))
        .toList();
  }

  TrailSegment _parseTrailSegment(Map<String, dynamic> element) {
    final tags = element['tags'] as Map<String, dynamic>? ?? {};
    final geometry = element['geometry'] as List<dynamic>;

    final points = geometry
        .map((g) => LatLng(
              (g['lat'] as num).toDouble(),
              (g['lon'] as num).toDouble(),
            ))
        .toList();

    return TrailSegment(
      osmId: element['id'] as int,
      name: tags['name'] as String? ?? 'Unnamed trail',
      surface: tags['surface'] as String? ?? 'unknown',
      highway: tags['highway'] as String? ?? 'path',
      points: points,
    );
  }

  void dispose() {
    _client.close();
  }
}

/// A single trail/path segment from OSM.
class TrailSegment {
  final int osmId;
  final String name;
  final String surface; // e.g. 'gravel', 'dirt', 'paved', 'grass'
  final String highway; // e.g. 'path', 'footway', 'track', 'cycleway'
  final List<LatLng> points;

  const TrailSegment({
    required this.osmId,
    required this.name,
    required this.surface,
    required this.highway,
    required this.points,
  });

  /// Whether this is a natural/unpaved trail (what Melissa wants).
  bool get isTrail =>
      surface == 'gravel' ||
      surface == 'dirt' ||
      surface == 'ground' ||
      surface == 'grass' ||
      surface == 'earth' ||
      surface == 'sand' ||
      surface == 'mud' ||
      surface == 'unknown' && highway != 'cycleway';
}

class TrailServiceException implements Exception {
  final String message;
  TrailServiceException(this.message);

  @override
  String toString() => 'TrailServiceException: $message';
}
