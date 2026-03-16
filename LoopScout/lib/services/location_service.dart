import 'dart:async';
import 'dart:math';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

/// Wraps Geolocator and applies Kalman filtering for smoother GPS tracks.
class LocationService {
  StreamSubscription<Position>? _positionSubscription;
  final _kalmanFilter = _GpsKalmanFilter();

  /// Request location permissions. Returns true if granted.
  Future<bool> requestPermission() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return false;

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    return permission == LocationPermission.whileInUse ||
        permission == LocationPermission.always;
  }

  /// Get the current position (single shot).
  Future<LatLng?> getCurrentPosition() async {
    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
      return LatLng(position.latitude, position.longitude);
    } catch (e) {
      return null;
    }
  }

  /// Start streaming GPS positions with Kalman filtering.
  /// [onPosition] is called with each filtered position.
  void startTracking({
    required void Function(FilteredPosition position) onPosition,
    int intervalMs = 1000,
  }) {
    _kalmanFilter.reset();

    _positionSubscription = Geolocator.getPositionStream(
      locationSettings: LocationSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 3, // minimum meters between updates
      ),
    ).listen((position) {
      final filtered = _kalmanFilter.process(
        latitude: position.latitude,
        longitude: position.longitude,
        accuracy: position.accuracy,
        altitude: position.altitude,
        timestamp: position.timestamp,
        speed: position.speed,
      );

      onPosition(filtered);
    });
  }

  /// Stop GPS tracking.
  void stopTracking() {
    _positionSubscription?.cancel();
    _positionSubscription = null;
  }

  void dispose() {
    stopTracking();
  }
}

/// A GPS position after Kalman filter smoothing.
class FilteredPosition {
  final double latitude;
  final double longitude;
  final double altitude;
  final double speedMps;
  final DateTime timestamp;
  final double estimatedAccuracy;

  const FilteredPosition({
    required this.latitude,
    required this.longitude,
    required this.altitude,
    required this.speedMps,
    required this.timestamp,
    required this.estimatedAccuracy,
  });

  LatLng toLatLng() => LatLng(latitude, longitude);
}

/// Simple 1D Kalman filter applied independently to lat/lng.
/// Reduces GPS zigzag — the #1 accuracy complaint about MapMyRun.
class _GpsKalmanFilter {
  double _latEstimate = 0;
  double _lngEstimate = 0;
  double _latVariance = 1e6; // high initial uncertainty
  double _lngVariance = 1e6;
  bool _initialized = false;

  // Process noise — how much we expect position to change per update.
  // Lower = smoother but laggier. Higher = more responsive but noisier.
  static const double _processNoise = 2.0;

  void reset() {
    _initialized = false;
    _latVariance = 1e6;
    _lngVariance = 1e6;
  }

  FilteredPosition process({
    required double latitude,
    required double longitude,
    required double accuracy,
    required double altitude,
    required DateTime timestamp,
    required double speed,
  }) {
    // Convert accuracy (meters) to approximate degrees variance
    final measurementVariance = pow(accuracy / 111000.0, 2).toDouble();

    if (!_initialized) {
      _latEstimate = latitude;
      _lngEstimate = longitude;
      _latVariance = measurementVariance;
      _lngVariance = measurementVariance;
      _initialized = true;
    } else {
      // Prediction step
      _latVariance += _processNoise * _processNoise / (111000.0 * 111000.0);
      _lngVariance += _processNoise * _processNoise / (111000.0 * 111000.0);

      // Update step (Kalman gain)
      final latGain = _latVariance / (_latVariance + measurementVariance);
      final lngGain = _lngVariance / (_lngVariance + measurementVariance);

      _latEstimate += latGain * (latitude - _latEstimate);
      _lngEstimate += lngGain * (longitude - _lngEstimate);

      _latVariance *= (1 - latGain);
      _lngVariance *= (1 - lngGain);
    }

    return FilteredPosition(
      latitude: _latEstimate,
      longitude: _lngEstimate,
      altitude: altitude,
      speedMps: speed,
      timestamp: timestamp,
      estimatedAccuracy: sqrt(_latVariance) * 111000.0,
    );
  }
}
