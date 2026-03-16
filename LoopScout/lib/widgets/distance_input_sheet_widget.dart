import 'package:flutter/cupertino.dart';
import 'package:loopscout/theme/app_theme.dart';

/// Bottom sheet where the user enters a target distance
/// to get trail-based route suggestions.
class DistanceInputSheet extends StatefulWidget {
  final void Function(double distanceMiles) onSubmit;

  const DistanceInputSheet({super.key, required this.onSubmit});

  @override
  State<DistanceInputSheet> createState() => _DistanceInputSheetState();
}

class _DistanceInputSheetState extends State<DistanceInputSheet> {
  final _controller = TextEditingController();
  double _sliderValue = 5.0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        top: 20,
        left: 24,
        right: 24,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      decoration: const BoxDecoration(
        color: CupertinoColors.systemBackground,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Handle bar
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: CupertinoColors.systemGrey4,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Title
          const Text(
            'Find a trail route',
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: AppTheme.navy,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Enter how far you want to run and we\u2019ll suggest trail-heavy loops nearby.',
            style: TextStyle(
              fontSize: 14,
              color: AppTheme.textSecondary,
            ),
          ),
          const SizedBox(height: 24),

          // Distance display
          Center(
            child: Text(
              '${_sliderValue.toStringAsFixed(1)} miles',
              style: const TextStyle(
                fontSize: 36,
                fontWeight: FontWeight.w700,
                color: AppTheme.primary,
              ),
            ),
          ),
          const SizedBox(height: 8),

          // Slider
          CupertinoSlider(
            value: _sliderValue,
            min: 1.0,
            max: 50.0,
            divisions: 98, // 0.5 mile increments
            activeColor: AppTheme.primary,
            onChanged: (value) {
              setState(() {
                _sliderValue = value;
              });
            },
          ),

          // Min/max labels
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('1 mi', style: TextStyle(fontSize: 12, color: AppTheme.textSecondary)),
                Text('50 mi', style: TextStyle(fontSize: 12, color: AppTheme.textSecondary)),
              ],
            ),
          ),
          const SizedBox(height: 8),

          // Or type it in
          Row(
            children: [
              const Text(
                'Or type exact: ',
                style: TextStyle(fontSize: 14, color: AppTheme.textSecondary),
              ),
              SizedBox(
                width: 80,
                child: CupertinoTextField(
                  controller: _controller,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  placeholder: 'e.g. 18',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 16),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                  onChanged: (value) {
                    final parsed = double.tryParse(value);
                    if (parsed != null && parsed >= 1 && parsed <= 50) {
                      setState(() => _sliderValue = parsed);
                    }
                  },
                ),
              ),
              const SizedBox(width: 6),
              const Text(
                'miles',
                style: TextStyle(fontSize: 14, color: AppTheme.textSecondary),
              ),
            ],
          ),
          const SizedBox(height: 24),

          // Submit button
          CupertinoButton.filled(
            borderRadius: BorderRadius.circular(12),
            onPressed: () {
              widget.onSubmit(_sliderValue);
              Navigator.of(context).pop();
            },
            child: const Text(
              'Find Trail Routes',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
