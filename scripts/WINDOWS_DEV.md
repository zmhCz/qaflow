# Windows local dev

Start everything:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

Stop everything:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1
```

Check status:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\status-dev.ps1
```

Notes:

- `start-dev.ps1` will auto-download a portable Redis package into `.runtime/redis`.
- Backend runs with `daphne` so WebSocket endpoints can work in local development.
- Celery runs with `-P solo` for Windows compatibility.
- Runtime artifacts are written to `.runtime/` and `logs/`.
