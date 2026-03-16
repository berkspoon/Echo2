import 'package:flutter/cupertino.dart';
import 'package:loopscout/providers/route_creation_provider.dart';
import 'package:loopscout/theme/app_theme.dart';

/// Bottom toolbar for switching between pan/draw/erase modes
/// and accessing route actions (undo, close loop, clear).
class DrawingToolbarWidget extends StatelessWidget {
  final DrawingMode mode;
  final bool hasRoute;
  final ValueChanged<DrawingMode> onModeChanged;
  final VoidCallback onUndo;
  final VoidCallback onCloseLoop;
  final VoidCallback onClear;

  const DrawingToolbarWidget({
    super.key,
    required this.mode,
    required this.hasRoute,
    required this.onModeChanged,
    required this.onUndo,
    required this.onCloseLoop,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: CupertinoColors.white.withOpacity(0.95),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withOpacity(0.1),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          // Pan mode
          _ToolbarButton(
            icon: CupertinoIcons.hand_draw,
            label: 'Move',
            isActive: mode == DrawingMode.pan,
            onTap: () => onModeChanged(DrawingMode.pan),
          ),

          // Draw mode
          _ToolbarButton(
            icon: CupertinoIcons.pencil,
            label: 'Draw',
            isActive: mode == DrawingMode.draw,
            activeColor: AppTheme.accent,
            onTap: () => onModeChanged(DrawingMode.draw),
          ),

          // Erase mode
          _ToolbarButton(
            icon: CupertinoIcons.delete_left,
            label: 'Erase',
            isActive: mode == DrawingMode.erase,
            onTap: () => onModeChanged(DrawingMode.erase),
          ),

          // Divider
          Container(
            width: 1,
            height: 32,
            color: AppTheme.border,
          ),

          // Undo
          _ToolbarButton(
            icon: CupertinoIcons.arrow_uturn_left,
            label: 'Undo',
            isActive: false,
            enabled: hasRoute,
            onTap: onUndo,
          ),

          // Close loop
          _ToolbarButton(
            icon: CupertinoIcons.loop,
            label: 'Loop',
            isActive: false,
            enabled: hasRoute,
            onTap: onCloseLoop,
          ),

          // Clear
          _ToolbarButton(
            icon: CupertinoIcons.trash,
            label: 'Clear',
            isActive: false,
            enabled: hasRoute,
            activeColor: AppTheme.dangerRed,
            onTap: onClear,
          ),
        ],
      ),
    );
  }
}

class _ToolbarButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final bool enabled;
  final Color? activeColor;
  final VoidCallback onTap;

  const _ToolbarButton({
    required this.icon,
    required this.label,
    required this.isActive,
    this.enabled = true,
    this.activeColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = !enabled
        ? CupertinoColors.systemGrey4
        : isActive
            ? (activeColor ?? AppTheme.primary)
            : AppTheme.textSecondary;

    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: isActive
              ? (activeColor ?? AppTheme.primary).withOpacity(0.1)
              : null,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 22, color: color),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                fontSize: 10,
                fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
