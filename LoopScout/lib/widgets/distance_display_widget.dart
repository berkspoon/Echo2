import 'package:flutter/cupertino.dart';
import 'package:loopscout/theme/app_theme.dart';

/// Displays the current route distance at the top of the map.
/// Shows miles as the primary unit with km as secondary.
class DistanceDisplayWidget extends StatelessWidget {
  final double distanceMeters;
  final bool isLoading;

  const DistanceDisplayWidget({
    super.key,
    required this.distanceMeters,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    if (distanceMeters == 0 && !isLoading) {
      return const SizedBox.shrink();
    }

    final miles = distanceMeters / 1609.344;
    final km = distanceMeters / 1000.0;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: CupertinoColors.white.withOpacity(0.95),
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withOpacity(0.08),
            blurRadius: 16,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (isLoading) ...[
            const CupertinoActivityIndicator(radius: 8),
            const SizedBox(width: 10),
          ],

          // Primary: miles
          Text(
            miles.toStringAsFixed(2),
            style: const TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w700,
              color: AppTheme.navy,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(width: 4),
          const Text(
            'mi',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w500,
              color: AppTheme.textSecondary,
            ),
          ),

          // Divider
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 12),
            width: 1,
            height: 24,
            color: AppTheme.border,
          ),

          // Secondary: km
          Text(
            km.toStringAsFixed(2),
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w500,
              color: AppTheme.textSecondary,
            ),
          ),
          const SizedBox(width: 3),
          const Text(
            'km',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w400,
              color: AppTheme.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}
