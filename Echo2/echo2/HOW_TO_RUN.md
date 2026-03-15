# How to Start/Restart the Echo 2.0 Server in VSCode

## Starting the server (recommended: F5)

The easiest way — no terminal needed:

1. **Press F5** (or go to **Run > Start Debugging** in the menu)
2. VSCode will start the server automatically using the launch configuration
3. You'll see output in the Debug Console like `Uvicorn running on http://127.0.0.1:8000`
4. **Open your browser** to http://localhost:8000

This uses the `.vscode/launch.json` file which is already configured to run uvicorn with `--reload` on port 8000.

## Stopping the server

- **If started with F5:** Press **Shift+F5** or click the red square stop button in the debug toolbar
- **If started in terminal:** Click into the terminal and press **Ctrl+C**

## Restarting the server

1. **Stop it** (Shift+F5 or Ctrl+C)
2. **Start it again** (F5)

The `--reload` flag means the server auto-restarts when you save code changes, so you should rarely need to manually restart. But if things feel stuck, a stop + start usually fixes it.

## Alternative: terminal method

If F5 doesn't work for some reason, you can also start the server from a terminal:

1. **Open a terminal** in VSCode: press Ctrl+` (backtick) or go to **Terminal > New Terminal**
2. **Navigate to the app folder:**
   ```
   cd Echo2/echo2
   ```
3. **Start the server:**
   ```
   python -m uvicorn main:app --reload --port 8000
   ```

## If the port is stuck

Sometimes a killed server leaves a "zombie" process holding the port. Two options:

- **Change the port in launch.json:** Edit `.vscode/launch.json` and change `"8000"` to `"8001"`, then F5 again (open http://localhost:8001)
- **Nuclear option**: Close VSCode entirely, reopen it, and press F5

## Quick troubleshooting

| Symptom | Fix |
|---------|-----|
| `Address already in use` | Another server is running. Stop it first (Shift+F5), or change the port |
| Routes returning 404 or old behavior | Restart the server (Shift+F5 then F5) |
| Import errors on startup | Check the Debug Console for the specific error message |
| Page shows JSON error instead of HTML | Server is running old code — restart it |
| Dashboard widgets show gray skeletons forever | The widget endpoints aren't loaded — restart the server |
| F5 does nothing or shows "No debugger" | Make sure you have the Python extension installed in VSCode |
