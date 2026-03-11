"""
============================================================
  DRONE SIM - Python Bridge Server
  Číta dáta z Arduino (Serial) → posiela do prehliadača (WebSocket)
  Spúšťa HTTP server pre drone_game.html

  Inštalácia:
    pip install flask flask-socketio pyserial eventlet

  Spustenie:
    python server.py

  Potom otvor: http://localhost:5000
============================================================
"""

import os
import sys
import time
import threading
import serial
import serial.tools.list_ports
from flask import Flask, send_from_directory
from flask_socketio import SocketIO

# ─── Konfigurácia ────────────────────────────────────────────
BAUD_RATE    = 115200
PORT_HINT    = None   # Nastav na 'COM3' alebo '/dev/ttyUSB0' ak auto-detect nefunguje
SEND_RATE_HZ = 50     # Max. frekvencia odosielania do prehliadača
GAME_FILE    = "drone_game.html"  # Musí byť v rovnakom priečinku ako server.py

# ─── Flask + SocketIO setup ──────────────────────────────────
app = Flask(__name__, static_folder=".")
app.config["SECRET_KEY"] = "drone_fpv_2024"
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

# ─── Globálny stav ───────────────────────────────────────────
latest_ctrl = None
arduino_connected = False
connected_clients = 0


# ─── Pomocné funkcie ─────────────────────────────────────────
def find_arduino_port():
    """Automaticky nájde port Arduino / CH340 / CP210x."""
    if PORT_HINT:
        return PORT_HINT

    ports = serial.tools.list_ports.comports()
    ARDUINO_KEYWORDS = [
        "Arduino", "CH340", "CH341", "CP210", "USB Serial",
        "UART", "ttyUSB", "ttyACM", "usbmodem", "usbserial",
    ]
    for port in ports:
        desc = (port.description or "") + (port.manufacturer or "")
        if any(kw.lower() in desc.lower() for kw in ARDUINO_KEYWORDS):
            print(f"  ✅  Nájdený Arduino port: {port.device}  [{desc}]")
            return port.device

    # Fallback: prvý dostupný port
    if ports:
        print(f"  ⚠️   Arduino nenájdený - skúšam prvý port: {ports[0].device}")
        return ports[0].device

    return None


def parse_line(line: str) -> dict | None:
    """Parsuje riadok formátu  LX:512,LY:512,..."""
    try:
        parts = line.strip().split(",")
        if len(parts) < 10:
            return None
        data = {}
        for part in parts:
            if ":" not in part:
                return None
            k, v = part.split(":", 1)
            data[k.strip()] = int(v.strip())
        return data
    except Exception:
        return None


# ─── Sériový vlákno ──────────────────────────────────────────
def serial_thread():
    global latest_ctrl, arduino_connected
    min_interval = 1.0 / SEND_RATE_HZ
    last_emit = 0

    while True:
        port = find_arduino_port()
        if not port:
            print("  🔴  Arduino nenájdený. Retry o 5 sekúnd... (hra funguje len s klávesnicou)")
            time.sleep(5)
            continue

        try:
            ser = serial.Serial(port, BAUD_RATE, timeout=1.0)
            time.sleep(2.0)  # Arduino reset čas
            ser.reset_input_buffer()
            arduino_connected = True
            socketio.emit("arduino_status", {"connected": True})
            print(f"  🟢  Arduino pripojený na {port}")

            while True:
                try:
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="ignore")

                    if "DRONE_CTRL_READY" in line:
                        print("  🎮  Controller inicializovaný!")
                        continue

                    data = parse_line(line)
                    if data is None:
                        continue

                    latest_ctrl = data

                    # Throttle: emituj max. SEND_RATE_HZ krát za sekundu
                    now = time.monotonic()
                    if now - last_emit >= min_interval and connected_clients > 0:
                        socketio.emit("controller", data)
                        last_emit = now

                except serial.SerialException as e:
                    print(f"  ⚠️   Serial chyba: {e}")
                    break

        except serial.SerialException as e:
            print(f"  🔴  Nemôžem otvoriť {port}: {e}")

        arduino_connected = False
        socketio.emit("arduino_status", {"connected": False})
        time.sleep(3)


# ─── Flask routes ─────────────────────────────────────────────
@app.route("/")
def index():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), GAME_FILE)
    if not os.path.exists(html_path):
        return (
            f"<h2>Chyba: '{GAME_FILE}' nenájdený!</h2>"
            f"<p>Uisti sa, že {GAME_FILE} je v rovnakom priečinku ako server.py</p>",
            404,
        )
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), GAME_FILE)


@app.route("/status")
def status():
    return {
        "arduino": arduino_connected,
        "clients": connected_clients,
        "last_data": latest_ctrl,
    }


# ─── SocketIO udalosti ────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    global connected_clients
    connected_clients += 1
    print(f"  🌐  Prehliadač pripojený  (celkom: {connected_clients})")
    socketio.emit("arduino_status", {"connected": arduino_connected})


@socketio.on("disconnect")
def on_disconnect():
    global connected_clients
    connected_clients = max(0, connected_clients - 1)
    print(f"  🌐  Prehliadač odpojený  (celkom: {connected_clients})")


# ─── Hlavný vstup ─────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("=" * 56)
    print("  🚁  DRONE FPV SIM - Bridge Server")
    print("=" * 56)
    print(f"  Hra dostupná na:  http://localhost:5000")
    print(f"  Status API:       http://localhost:5000/status")
    print("=" * 56)

    # Spusti sériové vlákno
    t = threading.Thread(target=serial_thread, daemon=True)
    t.start()

    # Spusti web server
    try:
        socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n  👋  Server ukončený")
        sys.exit(0)
