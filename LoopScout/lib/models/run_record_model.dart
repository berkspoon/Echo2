import 'package:freezed_annotation/freezed_annotation.dart';

part 'run_record_model.freezed.dart';
part 'run_record_model.g.dart';

/// A recorded GPS run session.
@freezed
class RunRecordModel with _$RunRecordModel {
  const factory RunRecordModel({
    required String id,
    required DateTime startedAt,
    required DateTime endedAt,
    required double distanceMeters,
    required Duration duration,
    required List<GpsPointModel> gpsPoints,
    required List<SplitModel> splits,
    double? elevationGainMeters,
    String? routeId, // linked planned route, if any
  }) = _RunRecordModel;

  factory RunRecordModel.fromJson(Map<String, dynamic> json) =>
      _$RunRecordModelFromJson(json);
}

/// A single GPS reading during a run, after Kalman filtering.
@freezed
class GpsPointModel with _$GpsPointModel {
  const factory GpsPointModel({
    required double latitude,
    required double longitude,
    required double elevation,
    required DateTime timestamp,
    required double speedMps, // meters per second
  }) = _GpsPointModel;

  factory GpsPointModel.fromJson(Map<String, dynamic> json) =>
      _$GpsPointModelFromJson(json);
}

/// A per-mile (or per-km) split.
@freezed
class SplitModel with _$SplitModel {
  const factory SplitModel({
    required int splitNumber,
    required Duration duration,
    required double distanceMeters,
    required double paceSecondsPerKm,
    double? elevationChangeMeters,
  }) = _SplitModel;

  factory SplitModel.fromJson(Map<String, dynamic> json) =>
      _$SplitModelFromJson(json);
}
