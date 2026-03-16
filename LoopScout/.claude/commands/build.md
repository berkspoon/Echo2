---
description: Build the Flutter project and report errors
---

Run `flutter build apk --debug` to verify the project compiles.
If there are errors, fix them. Focus on:
- Import paths
- Missing generated files (run `dart run build_runner build` first)
- Type mismatches
- Null safety issues

After fixing, run the build again to confirm it passes.
