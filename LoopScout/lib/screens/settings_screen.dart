import 'package:flutter/cupertino.dart';
import 'package:loopscout/theme/app_theme.dart';

/// App settings: distance units, map style, etc.
/// TODO: Implement with Hive-backed preferences.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        middle: Text('Settings'),
      ),
      child: SafeArea(
        child: CupertinoListSection.insetGrouped(
          header: const Text('PREFERENCES'),
          children: [
            CupertinoListTile(
              title: const Text('Distance Unit'),
              additionalInfo: const Text('Miles'),
              trailing: const CupertinoListTileChevron(),
              onTap: () {
                // TODO: Distance unit picker
              },
            ),
            CupertinoListTile(
              title: const Text('Route Preference'),
              additionalInfo: const Text('Trails First'),
              trailing: const CupertinoListTileChevron(),
              onTap: () {
                // TODO: Route preference picker (trails first, roads ok, etc.)
              },
            ),
            CupertinoListTile(
              title: const Text('Map Style'),
              additionalInfo: const Text('OpenStreetMap'),
              trailing: const CupertinoListTileChevron(),
              onTap: () {
                // TODO: Map tile source picker
              },
            ),
          ],
        ),
      ),
    );
  }
}
