#!/usr/bin/env python3
"""
run.py — Lanzador de SAT / TriageAI

Levanta el Backend (FastAPI + uvicorn, :8000) y el Frontend (http.server, :8080),
espera a que el backend responda y abre el navegador en
http://localhost:8080/index.html

Uso (desde la raíz del proyecto, donde están Backend/ y Frontend/):
    python run.py              # arranque normal
    python run.py --reload     # backend con autorecarga (desarrollo)
    python run.py --no-browser # no abrir el navegador

Ctrl+C detiene ambos procesos.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "Backend"
FRONTEND_DIR = ROOT / "Frontend"

BACKEND_PORT = 8000
FRONTEND_PORT = 8080
HTML_FILE = "index.html"  # login; redirige a triage.html o medico.html según el rol

# IMPORTANTE: el CORS del backend solo permite http://localhost:8080,
# por eso se usa "localhost" y no 127.0.0.1.
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}/{HTML_FILE}"
HEALTH_URL = f"http://localhost:{BACKEND_PORT}/api/health"


def find_python() -> str:
    """Usa el Python del venv (en Backend/ o en la raíz) si existe; si no, el actual."""
    candidates = []
    # El venv puede estar en Backend/ o en la raíz del proyecto, con nombre venv, .venv o env
    for base in (BACKEND_DIR, ROOT):
        for name in ("venv", ".venv", "env"):
            candidates.append(base / name / "Scripts" / "python.exe")  # Windows
            candidates.append(base / name / "bin" / "python")          # Linux / macOS
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_backend(timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def stop(proc: subprocess.Popen | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    print(f"  · Deteniendo {name}...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Lanza Backend + Frontend de SAT")
    parser.add_argument("--reload", action="store_true", help="uvicorn con --reload")
    parser.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    args = parser.parse_args()

    # ── Validaciones previas ──────────────────────────────────
    if not BACKEND_DIR.is_dir() or not FRONTEND_DIR.is_dir():
        print("✗ No encuentro las carpetas Backend/ y Frontend/. "
              "Ejecutá run.py desde la raíz del proyecto.")
        return 1
    if not (FRONTEND_DIR / HTML_FILE).exists():
        print(f"✗ No existe Frontend/{HTML_FILE}")
        return 1
    if not (BACKEND_DIR / ".env").exists():
        print("⚠ No hay Backend/.env — copiá .env.example a .env y completalo.")
    for port, name in ((BACKEND_PORT, "Backend"), (FRONTEND_PORT, "Frontend")):
        if port_in_use(port):
            print(f"✗ El puerto {port} ({name}) ya está en uso. Cerrá lo que lo ocupa e intentá de nuevo.")
            return 1

    python = find_python()
    print(f"Python: {python}\n")

    backend = frontend = None
    try:
        # ── 1. Backend ────────────────────────────────────────
        print(f"▶ Iniciando Backend  → http://localhost:{BACKEND_PORT}  (docs: /docs)")
        cmd = [python, "-m", "uvicorn", "app.main:app", "--port", str(BACKEND_PORT)]
        if args.reload:
            cmd.append("--reload")
        backend = subprocess.Popen(cmd, cwd=BACKEND_DIR)

        # ── 2. Frontend ───────────────────────────────────────
        print(f"▶ Iniciando Frontend → http://localhost:{FRONTEND_PORT}")
        frontend = subprocess.Popen(
            [python, "-m", "http.server", str(FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
        )

        # ── 3. Esperar al backend y abrir el navegador ────────
        print("⏳ Esperando a que el Backend esté listo (carga del modelo)...")
        if not wait_for_backend():
            if backend.poll() is not None:
                print("✗ El Backend se cerró al arrancar. Revisá el error de arriba.")
            else:
                print("✗ El Backend no respondió en 90 s.")
            return 1

        print(f"\n✓ Todo listo → {FRONTEND_URL}")
        print("  (Ctrl+C para detener todo)\n")
        if not args.no_browser:
            webbrowser.open(FRONTEND_URL)

        # ── 4. Mantener vivo hasta Ctrl+C o caída de un proceso ─
        while True:
            if backend.poll() is not None:
                print("\n✗ El Backend terminó inesperadamente.")
                return backend.returncode or 1
            if frontend.poll() is not None:
                print("\n✗ El Frontend terminó inesperadamente.")
                return frontend.returncode or 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nCerrando...")
        return 0
    finally:
        stop(frontend, "Frontend")
        stop(backend, "Backend")


if __name__ == "__main__":
    sys.exit(main())