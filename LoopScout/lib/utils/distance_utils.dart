import 'package:latlong2/latlong.dart';

/// Utility functions for distance calculations on polylines.
class DistanceUtils {
  DistanceUtils._();

  static const _distance = Distance();

  /// Calculate total distance of a polyline in meters.
  static double polylineDistanceMeters(List<LatLng> points) {
    double total = 0;
    for (int i = 0; i < points.length - 1; i++) {
      total += _distance.as(LengthUnit.Meter, points[i], points[i + 1]);
    }
    return total;
  }

  /// Convert meters to miles.
  static double metersToMiles(double meters) => meters / 1609.344;

  /// Convert miles to meters.
  static double milesToMeters(double miles) => miles * 1609.344;

  /// Convert meters to kilometers.
  static double metersToKm(double meters) => meters / 1000.0;

  /// Format distance as a human-readable string.
  /// e.g. "3.42 mi" or "5.50 km"
  static String formatDistance(double meters, {bool useMiles = true}) {
    if (useMiles) {
      return '${metersToMiles(meters).toStringAsFixed(2)} mi';
    }
    return '${metersToKm(meters).toStringAsFixed(2)} km';
  }

  /// Format pace as min:sec per mile (or per km).
  static String formatPace(Duration duration, double meters,
      {bool useMiles = true}) {
    if (meters <= 0) return '--:--';

    final units = useMiles ? metersToMiles(meters) : metersToKm(meters);
    final secondsPerUnit = duration.inSeconds / units;
    final minutes = (secondsPerUnit / 60).floor();
    final seconds = (secondsPerUnit % 60).floor();

    final unit = useMiles ? '/mi' : '/km';
    return '${minutes.toString()}:${seconds.toString().padLeft(2, '0')}$unit';
  }

  /// Format duration as h:mm:ss or mm:ss.
  static String formatDuration(Duration duration) {
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);

    if (hours > 0) {
      return '$hours:${minutes.toString().padLeft(2, '0')}'
          ':${seconds.toString().padLeft(2, '0')}';
    }
    return '${minutes.toString()}:${seconds.toString().padLeft(2, '0')}';
  }
}
