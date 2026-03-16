import 'package:flutter/cupertino.dart';

/// LoopScout color palette and theme configuration.
class AppTheme {
  AppTheme._();

  // Brand colors
  static const Color primary = Color(0xFF2A9D8F);       // Teal
  static const Color primaryDark = Color(0xFF1F7A6E);
  static const Color accent = Color(0xFFE76F51);         // Warm orange
  static const Color navy = Color(0xFF1B2A4A);
  static const Color background = Color(0xFFF8F9FA);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color textPrimary = Color(0xFF1A1A2E);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color border = Color(0xFFE5E7EB);
  static const Color trailGreen = Color(0xFF4CAF50);
  static const Color roadGray = Color(0xFF9E9E9E);
  static const Color dangerRed = Color(0xFFEF4444);

  // Map-specific colors
  static const Color routeLine = Color(0xFF2A9D8F);
  static const Color routeLineDrawing = Color(0xFFE76F51);
  static const Color trailHighlight = Color(0xFF4CAF50);
  static const Color startMarker = Color(0xFF2A9D8F);
  static const Color endMarker = Color(0xFFE76F51);

  static const CupertinoThemeData light = CupertinoThemeData(
    primaryColor: primary,
    primaryContrastingColor: CupertinoColors.white,
    barBackgroundColor: surface,
    scaffoldBackgroundColor: background,
    textTheme: CupertinoTextThemeData(
      primaryColor: primary,
      textStyle: TextStyle(
        fontFamily: '.SF Pro Text',
        fontSize: 16,
        color: textPrimary,
      ),
      navTitleTextStyle: TextStyle(
        fontFamily: '.SF Pro Display',
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: textPrimary,
      ),
      navLargeTitleTextStyle: TextStyle(
        fontFamily: '.SF Pro Display',
        fontSize: 34,
        fontWeight: FontWeight.w700,
        color: textPrimary,
      ),
    ),
  );
}
