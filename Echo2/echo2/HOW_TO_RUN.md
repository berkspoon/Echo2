# How to Start/Restart the Echo 2.0 Server in VSCode

## Starting the server

1. **Open a terminal** in VSCode: press `Ctrl+`` (backtick) or go to **Terminal > New Terminal** in the menu
2. **Navigate to the app folder** by typing:
   ```
   cd Echo2/echo2
   ```
3. **Start the server** by typing:
   ```
   python -m uvicorn main:app --reload --port 8000
   ```
4. You'll see output like `Uvicorn running on http://127.0.0.1:8000` — that means it's working
5. **Open your browser** to http://localhost:8000

The `--reload` flag means the server auto-restarts when you save code changes. You should almost never need to manually restart.

## Stopping the server

- Click into the terminal where the server is running and press **Ctrl+C**

## Restarting the server (when things feel stuck)

1. **Ctrl+C** in the terminal to stop it
2. **(Optional) Clear Python cache** if you suspect stale code:
   ```
   rm -rf __pycache__ routers/__pycache__ db/__pycache__ models/__pycache__
   ```
3. Start it again:
   ```
   python -m uvicorn main:app --reload --port 8000
   ```

## If the port is stuck

Sometimes a killed server leaves a "zombie" process holding the port. Two options:

- **Use a different port**: `python -m uvicorn main:app --reload --port 8001` (then open http://localhost:8001)
- **Nuclear option**: Close VSCode entirely, reopen it, and start the server fresh

## Quick troubleshooting

| Symptom | Fix |
|---------|-----|
| `Address already in use` | Another server is running. Ctrl+C it first, or use a different port |
| Routes returning 404 or old behavior | Clear `__pycache__` folders (see above) and restart |
| Import errors on startup | Check the terminal output for the specific error message |
| Page shows JSON error instead of HTML | Server is running old code — restart it |
| Dashboard widgets show gray skeletons forever | The widget endpoints aren't loaded — restart the server |
