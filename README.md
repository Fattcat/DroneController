# esp32-DroneController
Drone controller test

# 🚁 FPV Drone Simulator — Arduino + Python + HTML

Kompletný ovládač dronu s Arduino Nano, dvoma KY-023 joystickmi,
Python bridge serverom a 3D FPV simulátorom v prehliadači.

---

## 📁 Súbory

| Súbor | Popis |
|-------|-------|
| `arduino_controller.ino` | Sketch pre Arduino Nano |
| `server.py` | Python bridge: Serial → WebSocket |
| `drone_game.html` | 3D FPV hra (Three.js) |
| `requirements.txt` | Python závislosti |

---

## 🔌 Zapojenie (Wiring)

```
Ľavý KY-023:
  VCC  → 5V (Arduino)
  GND  → GND
  VRx  → A0   ← Yaw (otáčanie)
  VRy  → A1   ← Throttle (výška)
  SW   → D2   ← joystick tlačidlo

Pravý KY-023:
  VCC  → 5V
  GND  → GND
  VRx  → A2   ← Strafe/Roll
  VRy  → A3   ← Pitch (dopredu/dozadu)
  SW   → D3   ← joystick tlačidlo

Tlačidlá (INPUT_PULLUP — jeden pin na GND, druhý na DX):
  D4 → Rýchlosť +
  D5 → Rýchlosť −
  D6 → Turbo boost
  D7 → Brzda / stop
```

---

## 🛠️ Inštalácia

### 1. Arduino
```
1. Otvor Arduino IDE
2. Načítaj: arduino_controller.ino
3. Board: Arduino Nano
4. Processor: ATmega328P (Old Bootloader) alebo ATmega328P
5. Upload
```

### 2. Python
```bash
pip install flask flask-socketio pyserial eventlet
```

### 3. Spustenie
```bash
# Oba súbory musia byť v rovnakom priečinku!
python server.py
```
Potom otvor prehliadač: **http://localhost:5000**

---

## 🎮 Ovládanie

| Vstup | Akcia |
|-------|-------|
| Ľavý Joystick X | Yaw — otáčanie dronu |
| Ľavý Joystick Y | Throttle — výška (hore/dole) |
| Pravý Joystick X | Strafe — pohyb do strany |
| Pravý Joystick Y | Pitch — dopredu/dozadu |
| BTN 1 (D4) | Zvýšiť rýchlosť |
| BTN 2 (D5) | Znížiť rýchlosť |
| BTN 3 (D6) | Turbo boost |
| BTN 4 (D7) | Brzda |
| Ľavý joystick SW | (voľné) |
| Pravý joystick SW | (voľné) |

### Klávesnica (záloha bez Arduina)
```
W / S       → Pitch dopredu / dozadu
A / D       → Yaw vľavo / vpravo
Q / E       → Strafe vľavo / vpravo
Space       → Throttle hore
Shift       → Throttle dole
↑ / ↓       → Zvýš / Zníž základnú rýchlosť
X           → Brzda
```

---

## 🏁 Pravidlá hry

- Preleti 450-metrovú dráhu so **45 prekážkovými tyčami**
- Každá obídená tyč = **+15 bodov**
- Každý meter = **+0.4 bodu**
- Prežitý čas = **+1.5 bodu/s**
- Doletel do cieľa = **+500 bonusových bodov**
- Náraz do tyče alebo tvrdé pristátie = **GAME OVER**

---

## 🔧 Riešenie problémov

**Arduino sa nenájde automaticky:**
- Otvor `server.py` a nastav: `PORT_HINT = 'COM3'` (Windows) alebo `PORT_HINT = '/dev/ttyUSB0'` (Linux)

**Hra nefunguje bez servera:**
- Otvor `drone_game.html` priamo v prehliadači (dvojklik)
- Bude fungovať len s klávesnicou (Arduino nebude pripojené)

**Joysticky sú invertované:**
- V `server.py` zmeň znamienko: `ctrl.throttle = +mapJoy(d.LY)` (odstráň mínus)
- Alebo v Arduino skripte potočíme joystick

**Kalibrovaný stred je nesprávny:**
- Pri zapnutí Arduina drž joysticky v neutrálnej (strednej) polohe
- Arduino automaticky kalibruje stredy pri boote

---

## 🏗️ Architektúra

```
[Arduino Nano]
    ↓ Serial USB (115200 baud, 50 Hz)
[server.py — Python]
    ↓ WebSocket (Socket.IO)
[drone_game.html — Three.js]
    ↓ FPV render + fyzika + kolízie
[Prehliadač]
```
