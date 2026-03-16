import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:loopscout/theme/app_theme.dart';
import 'package:loopscout/screens/map_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize Hive for local storage
  await Hive.initFlutter();

  // TODO: Register Hive adapters for Route, Waypoint, RunRecord models
  // Hive.registerAdapter(RouteModelAdapter());

  runApp(
    const ProviderScope(
      child: LoopScoutApp(),
    ),
  );
}

class LoopScoutApp extends StatelessWidget {
  const LoopScoutApp({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoApp(
      title: 'LoopScout',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const MapScreen(),
    );
  }
}
