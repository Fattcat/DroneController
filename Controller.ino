// ============================================================
//  DRONE CONTROLLER - Arduino Nano
//  2x KY-023 Joystick + 4x Buttons
// ============================================================
//  ZAPOJENIE (Wiring):
//  ───────────────────────────────────────────────────────────
//  Ľavý joystick (KY-023 #1):
//    VCC → 5V
//    GND → GND
//    VRx → A0   (Yaw - otáčanie)
//    VRy → A1   (Throttle - výška)
//    SW  → D2   (Ľavé tlačidlo joysticku)
//
//  Pravý joystick (KY-023 #2):
//    VCC → 5V
//    GND → GND
//    VRx → A2   (Roll / Strafe)
//    VRy → A3   (Pitch - dopredu/dozadu)
//    SW  → D3   (Pravé tlačidlo joysticku)
//
//  Tlačidlá (INPUT_PULLUP - stlačené = LOW):
//    BTN1 (Rýchlosť +)  → D4
//    BTN2 (Rýchlosť -)  → D5
//    BTN3 (Boost)       → D6
//    BTN4 (Reset/Brzda) → D7
//
//  Výstup: Serial 115200 baud, formát:
//    LX:512,LY:512,RX:512,RY:512,LSW:0,RSW:0,B1:0,B2:0,B3:0,B4:0\n
// ============================================================

// --- Pin definície ---
const int PIN_LEFT_X  = A0;
const int PIN_LEFT_Y  = A1;
const int PIN_RIGHT_X = A2;
const int PIN_RIGHT_Y = A3;
const int PIN_LEFT_SW  = 2;
const int PIN_RIGHT_SW = 3;
const int PIN_BTN1 = 4;  // Rýchlosť +
const int PIN_BTN2 = 5;  // Rýchlosť -
const int PIN_BTN3 = 6;  // Boost / špeciálna akcia
const int PIN_BTN4 = 7;  // Reset / Brzda

// --- Kalibrácia stredov ---
int leftCenterX  = 512;
int leftCenterY  = 512;
int rightCenterX = 512;
int rightCenterY = 512;

// --- Dead zone (hodnoty bližšie k stredu ako toto sa ignorujú) ---
const int DEAD_ZONE = 30;

// --- Odoslanie rate ---
const unsigned long SEND_INTERVAL_MS = 20;  // 50 Hz
unsigned long lastSendTime = 0;

// --- Aplikuj dead zone a recentruj hodnotu ---
// Vstup: surová hodnota + kalibrovaný stred
// Výstup: hodnota 0–1023, kde 512 = stred
int applyDeadZone(int raw, int center) {
  int offset = raw - center;
  if (abs(offset) < DEAD_ZONE) return 512;
  // Remapuj tak, aby 512 bolo skutočný stred
  return constrain(512 + offset, 0, 1023);
}

// --- Kalibrácia joysticku ---
void calibrateJoysticks() {
  // Priemerujeme 20 odčítaní pri štarte (joysticky musia byť v strede!)
  long lx = 0, ly = 0, rx = 0, ry = 0;
  for (int i = 0; i < 20; i++) {
    lx += analogRead(PIN_LEFT_X);
    ly += analogRead(PIN_LEFT_Y);
    rx += analogRead(PIN_RIGHT_X);
    ry += analogRead(PIN_RIGHT_Y);
    delay(10);
  }
  leftCenterX  = lx / 20;
  leftCenterY  = ly / 20;
  rightCenterX = rx / 20;
  rightCenterY = ry / 20;
}

void setup() {
  Serial.begin(115200);

  // Tlačidlá: INPUT_PULLUP = stlačené = LOW, uvoľnené = HIGH
  pinMode(PIN_LEFT_SW,  INPUT_PULLUP);
  pinMode(PIN_RIGHT_SW, INPUT_PULLUP);
  pinMode(PIN_BTN1, INPUT_PULLUP);
  pinMode(PIN_BTN2, INPUT_PULLUP);
  pinMode(PIN_BTN3, INPUT_PULLUP);
  pinMode(PIN_BTN4, INPUT_PULLUP);

  // Kalibruj stredy - drž joysticky v neutrálnej polohe pri zapnutí!
  calibrateJoysticks();

  Serial.println("DRONE_CTRL_READY");
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendTime < SEND_INTERVAL_MS) return;
  lastSendTime = now;

  // --- Čítanie analógových hodnôt a aplikovanie kalibrácie + dead zone ---
  // BUG FIX: predtým sa posielali surové hodnoty bez použitia kalibrovaných stredov
  int lx = applyDeadZone(analogRead(PIN_LEFT_X),  leftCenterX);
  int ly = applyDeadZone(analogRead(PIN_LEFT_Y),  leftCenterY);
  int rx = applyDeadZone(analogRead(PIN_RIGHT_X), rightCenterX);
  int ry = applyDeadZone(analogRead(PIN_RIGHT_Y), rightCenterY);

  // --- Čítanie tlačidiel (LOW = stlačené → invertujeme na 1) ---
  int lsw = !digitalRead(PIN_LEFT_SW);
  int rsw = !digitalRead(PIN_RIGHT_SW);
  int b1  = !digitalRead(PIN_BTN1);
  int b2  = !digitalRead(PIN_BTN2);
  int b3  = !digitalRead(PIN_BTN3);
  int b4  = !digitalRead(PIN_BTN4);

  // --- Odoslanie dát cez Serial ---
  Serial.print("LX:");  Serial.print(lx);
  Serial.print(",LY:"); Serial.print(ly);
  Serial.print(",RX:"); Serial.print(rx);
  Serial.print(",RY:"); Serial.print(ry);
  Serial.print(",LSW:"); Serial.print(lsw);
  Serial.print(",RSW:"); Serial.print(rsw);
  Serial.print(",B1:"); Serial.print(b1);
  Serial.print(",B2:"); Serial.print(b2);
  Serial.print(",B3:"); Serial.print(b3);
  Serial.print(",B4:"); Serial.println(b4);
}
