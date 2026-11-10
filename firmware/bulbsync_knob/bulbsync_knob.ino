// BulBSync Knob - pokrętło do sterowania światłem przez USB.
//
// Płytka: Raspberry Pi Pico / Pico H (rdzeń "Raspberry Pi Pico/RP2040" od Earle'a Philhowera).
// Enkoder: moduł KY-040 (obrót + przycisk w osi).
//
// Podłączenie (numery w nawiasach = fizyczne piny Pico, pin 1 to lewy górny róg przy USB):
//   KY-040 CLK -> GP2  (pin 4)
//   KY-040 DT  -> GP3  (pin 5)
//   KY-040 SW  -> GP4  (pin 6)
//   KY-040 GND -> GND  (pin 3)
//   KY-040 +   -> 3V3(OUT) (pin 36)   <- NIE pin 37 (3V3_EN) i NIE 5 V
//
// Protokół (tekst po USB, 115200, jedna wiadomość na linię):
//   "+" / "-"      obrót o jeden ząbek (w prawo / w lewo)
//   "P+" / "P-"    obrót o ząbek przy wciśniętej gałce
//   "CLICK"        krótkie kliknięcie (bez obracania w trakcie)
//   "HOLD"         przytrzymanie dłużej niż HOLD_MS (wysyłane od razu, bez czekania na puszczenie)
//   "BULBSYNC-KNOB 1"  przedstawienie się (co sekundę i w odpowiedzi na "?")

const int PIN_CLK = 2;
const int PIN_DT = 3;
const int PIN_SW = 4;

// Ile zmian stanu enkodera przypada na jeden wyczuwalny ząbek. KY-040 ma zwykle 4.
// Jeśli jeden ząbek daje dwa komunikaty, zmień na 2; jeśli trzeba kręcić o dwa ząbki - też spróbuj 2.
const int TRANSITIONS_PER_DETENT = 4;
// Odwróć kierunek, jeśli kręcenie w prawo zmniejsza jasność (albo zamień przewody CLK i DT).
const bool REVERSE = false;

const unsigned long DEBOUNCE_MS = 25;
const unsigned long HOLD_MS = 700;
const unsigned long HELLO_MS = 1000;

// Dekoder kwadraturowy: tablica przejść (poprzedni stan AB, nowy stan AB) -> krok.
// Niedozwolone przejścia (drgania styków) dają 0, więc enkoder nie "skacze".
const int8_t STEP[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};

uint8_t prevAB = 0;
int8_t acc = 0;

bool btnStable = HIGH;       // HIGH = puszczony (INPUT_PULLUP)
bool btnRaw = HIGH;
unsigned long btnRawChanged = 0;
unsigned long btnDownAt = 0;
bool turnedWhileDown = false;
bool holdSent = false;

unsigned long lastHello = 0;
unsigned long ledOffAt = 0;

uint8_t readAB() {
  return (digitalRead(PIN_CLK) << 1) | digitalRead(PIN_DT);
}

void blink() {
  digitalWrite(LED_BUILTIN, HIGH);
  ledOffAt = millis() + 30;
}

void send(const char *msg) {
  if (Serial) {  // nie blokuj, gdy aplikacja nie jest podłączona
    Serial.println(msg);
  }
  blink();
}

void setup() {
  pinMode(PIN_CLK, INPUT_PULLUP);
  pinMode(PIN_DT, INPUT_PULLUP);
  pinMode(PIN_SW, INPUT_PULLUP);  // KY-040 zwykle nie ma rezystora podciągającego na SW
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  prevAB = readAB();
}

void handleRotation() {
  uint8_t ab = readAB();
  if (ab == prevAB) return;
  acc += STEP[(prevAB << 2) | ab];
  prevAB = ab;
  int dir = 0;
  if (acc >= TRANSITIONS_PER_DETENT) dir = 1;
  if (acc <= -TRANSITIONS_PER_DETENT) dir = -1;
  if (dir == 0) return;
  acc = 0;
  if (REVERSE) dir = -dir;
  bool pressed = (btnStable == LOW);
  if (pressed) {
    turnedWhileDown = true;
    send(dir > 0 ? "P+" : "P-");
  } else {
    send(dir > 0 ? "+" : "-");
  }
}

void handleButton() {
  unsigned long now = millis();
  bool raw = digitalRead(PIN_SW);
  if (raw != btnRaw) {
    btnRaw = raw;
    btnRawChanged = now;
  }
  if (raw != btnStable && now - btnRawChanged >= DEBOUNCE_MS) {
    btnStable = raw;
    if (btnStable == LOW) {  // wciśnięty
      btnDownAt = now;
      turnedWhileDown = false;
      holdSent = false;
    } else {  // puszczony
      if (!turnedWhileDown && !holdSent) send("CLICK");
    }
  }
  if (btnStable == LOW && !holdSent && !turnedWhileDown && now - btnDownAt >= HOLD_MS) {
    holdSent = true;
    send("HOLD");
  }
}

void handleSerialInput() {
  while (Serial.available()) {
    int c = Serial.read();
    if (c == '?') {
      Serial.println("BULBSYNC-KNOB 1");
      lastHello = millis();
    }
  }
}

void loop() {
  handleRotation();
  handleButton();
  handleSerialInput();
  unsigned long now = millis();
  if (now - lastHello >= HELLO_MS) {
    lastHello = now;
    if (Serial) Serial.println("BULBSYNC-KNOB 1");
  }
  if (ledOffAt && (long)(now - ledOffAt) >= 0) {
    digitalWrite(LED_BUILTIN, LOW);
    ledOffAt = 0;
  }
}
