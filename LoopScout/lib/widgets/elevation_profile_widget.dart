import 'package:flutter/cupertino.dart';
import 'package:loopscout/theme/app_theme.dart';

/// Displays an elevation profile chart below the map for the current route.
/// TODO: Implement with CustomPainter drawing a filled area chart.
class ElevationProfileWidget extends StatelessWidget {
  final List<double> elevations; // elevation values along the route
  final double distanceMeters;

  const ElevationProfileWidget({
    super.key,
    required this.elevations,
    required this.distanceMeters,
  });

  @override
  Widget build(BuildContext context) {
    if (elevations.isEmpty) return const SizedBox.shrink();

    final minElev = elevations.reduce((a, b) => a < b ? a : b);
    final maxElev = elevations.reduce((a, b) => a > b ? a : b);
    final gainMeters = _calculateGain();

    return Container(
      height: 120,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CupertinoColors.white.withOpacity(0.95),
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withOpacity(0.06),
            blurRadius: 12,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header stats
          Row(
            children: [
              _StatChip(
                icon: CupertinoIcons.arrow_up_right,
                value: '${gainMeters.toStringAsFixed(0)} ft',
                label: 'Gain',
              ),
              const SizedBox(width: 16),
              _StatChip(
                icon: CupertinoIcons.arrow_up,
                value: '${(maxElev * 3.281).toStringAsFixed(0)} ft',
                label: 'Max',
              ),
              const SizedBox(width: 16),
              _StatChip(
                icon: CupertinoIcons.arrow_down,
                value: '${(minElev * 3.281).toStringAsFixed(0)} ft',
                label: 'Min',
              ),
            ],
          ),

          const SizedBox(height: 8),

          // Chart area
          Expanded(
            child: CustomPaint(
              size: Size.infinite,
              painter: _ElevationChartPainter(
                elevations: elevations,
                minElev: minElev,
                maxElev: maxElev,
              ),
            ),
          ),
        ],
      ),
    );
  }

  double _calculateGain() {
    double gain = 0;
    for (int i = 1; i < elevations.length; i++) {
      final diff = elevations[i] - elevations[i - 1];
      if (diff > 0) gain += diff;
    }
    return gain * 3.281; // meters to feet
  }
}

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String value;
  final String label;

  const _StatChip({
    required this.icon,
    required this.value,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: AppTheme.primary),
        const SizedBox(width: 3),
        Text(
          value,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: AppTheme.navy,
          ),
        ),
        const SizedBox(width: 2),
        Text(
          label,
          style: const TextStyle(
            fontSize: 10,
            color: AppTheme.textSecondary,
          ),
        ),
      ],
    );
  }
}

class _ElevationChartPainter extends CustomPainter {
  final List<double> elevations;
  final double minElev;
  final double maxElev;

  _ElevationChartPainter({
    required this.elevations,
    required this.minElev,
    required this.maxElev,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (elevations.length < 2) return;

    final range = maxElev - minElev;
    if (range == 0) return;

    final path = Path();
    final fillPath = Path();

    for (int i = 0; i < elevations.length; i++) {
      final x = (i / (elevations.length - 1)) * size.width;
      final y = size.height - ((elevations[i] - minElev) / range) * size.height;

      if (i == 0) {
        path.moveTo(x, y);
        fillPath.moveTo(x, size.height);
        fillPath.lineTo(x, y);
      } else {
        path.lineTo(x, y);
        fillPath.lineTo(x, y);
      }
    }

    // Close fill path
    fillPath.lineTo(size.width, size.height);
    fillPath.close();

    // Draw filled area
    final fillPaint = Paint()
      ..color = const Color(0xFF2A9D8F).withOpacity(0.15)
      ..style = PaintingStyle.fill;
    canvas.drawPath(fillPath, fillPaint);

    // Draw line
    final linePaint = Paint()
      ..color = const Color(0xFF2A9D8F)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round;
    canvas.drawPath(path, linePaint);
  }

  @override
  bool shouldRepaint(covariant _ElevationChartPainter oldDelegate) {
    return oldDelegate.elevations != elevations;
  }
}
