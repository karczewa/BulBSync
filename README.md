# BulBSync

Sterowanie żarówkami **LSC Smart Connect** (i innymi żarówkami Tuya WiFi) z komputera, bez chmury, w sieci lokalnej.
Do tego **tryb ambient**: żarówki przejmują kolory z ekranu, np. podczas gry.

- **Sterowanie ręczne:** koło kolorów, jasność, biały z barwą (ciepła ↔ zimna), szybkie kolory i presety.
  Każda żarówka osobno albo **wszystkie naraz**. Karty pokazują stan i aktualny kolor każdej żarówki.
- **Ambient:** każda żarówka bierze kolor z wybranej strefy ekranu (lewa/prawa krawędź, środek, góra, dół, rogi, cały ekran).
  Masz regulację odświeżania (do 60/s), wygładzania, nasycenia, jasności min/max, progu czerni i wybór monitora,
  a także podgląd stref na żywo i licznik zmian wysłanych do każdej żarówki.
  Po zatrzymaniu żarówki wracają do stanu sprzed ambientu.
- **Skanowanie sieci:** jeśli router nada żarówce nowy adres IP, jeden przycisk znajdzie ją ponownie.
- Obsługuje protokół Tuya **3.5** (Twoje żarówki), a także 3.1–3.4. Wersja jest brana z `devices.json`.

## Instalacja (Windows)

1. Pobierz repo: **Code → Download ZIP** i rozpakuj (albo `git clone`).
2. Uruchom **`install.bat`**. Zainstaluje `tinytuya`, `mss`, `numpy`, `customtkinter`, `pillow` i `pyserial`,
   a opcjonalnie `dxcam`, czyli szybsze przechwytywanie ekranu na Windowsie.
3. Skopiuj **`devices.json`** (ten z `python -m tinytuya wizard`) do folderu BulBSync, obok `start.bat`.
4. Uruchom **`start.bat`**.

Jeśli wolisz konsolę:

```bash
python -m pip install -r requirements.txt
```

```bash
python -m bulbsync
```

> `devices.json` zawiera klucze żarówek. Jest w `.gitignore`, więc nie trafi do repo.
> Ustawienia aplikacji zapisują się w `settings.json` (też ignorowany).

## Ambient: wskazówki

- **Odświeżanie:** suwak sięga do 60/s. Kolor jest wysyłany tylko wtedy, gdy faktycznie się zmienił, więc przy
  spokojnym obrazie żarówki dostają mało poleceń. Ile żarówka naprawdę przyjmie, zależy od niej samej i od WiFi.
  Licznik „/s” przy każdej żarówce pokazuje, ile zmian faktycznie do niej poszło. Jeśli żarówka zaczyna się zacinać
  albo traci połączenie, zmniejsz odświeżanie.
- **Przechwytywanie:** jeśli zainstalowany jest `dxcam`, aplikacja używa DXGI, które jest szybsze i mniej obciąża procesor.
  W przeciwnym razie używa `mss`. Która metoda działa, widać w linii statusu ambientu.
- **Wygładzanie:** ok. 50% daje spokojne, płynne przejścia. 0% reaguje najszybciej, ale migocze przy dynamicznych scenach.
  Wygładzanie jest liczone w czasie, więc działa tak samo przy 10 i przy 60 klatkach/s.
- **Krzywa jasności:** jasność żarówki liczona jest z faktycznej ilości światła w strefie (z korekcją gammy ekranu),
  osobno od koloru. Przy 2.2 (domyślnie) żarówka świeci proporcjonalnie do światła z ekranu, więc ciemne sceny są
  naprawdę ciemne. Jeśli całość wydaje się za ciemna, zejdź do 1.6–1.8. 1.0 to jasne zachowanie starszej wersji.
  Procent przy każdej żarówce pokazuje jej bieżącą jasność.
- **Sposób liczenia koloru:** „Wyraziste kolory” daje pierwszeństwo nasyconym pikselom, więc czarne/szare tło nie zagłusza
  np. ognia czy neonu. „Średnia z ekranu” jest wierniejsza, ale bledsza.
- **Gry pełnoekranowe:** tryb „exclusive fullscreen” może blokować przechwytywanie. Ustaw w grze **okno bez ramek (borderless)**.
- W trybie ambient żarówki używają kanału DP 27 (tego samego co synchronizacja z muzyką w aplikacji), który przyjmuje szybkie zmiany.

## Pokrętło USB (opcjonalne)

Fizyczne pokrętło: kręcenie zmienia jasność, kliknięcie włącza i wyłącza światło.
Obudowa do druku 3D (krążek z obracaną pokrywą): [`hardware/knob/`](hardware/knob/README.md).
Części: **Raspberry Pi Pico H**, moduł enkodera **KY-040**, 5 przewodów żeńsko-żeńskich, kabel micro-USB **z transmisją danych**.

### Podłączenie

| KY-040 | Pico H: pin (fizyczny numer) | Podpis na spodzie Pico |
|---|---|---|
| `CLK` | pin **4** | GP2 |
| `DT` | pin **5** | GP3 |
| `SW` | pin **6** | GP4 |
| `GND` | pin **3** | GND |
| `+` | pin **36** | 3V3(OUT) |

```
            USB
      ┌─────┴─────┐
 GP0  1 ●         ● 40  VBUS
 GP1  2 ●         ● 39  VSYS
 GND  3 ■  ← GND  ■ 38  GND
 GP2  4 ●  ← CLK  ● 37  3V3_EN   ✗ NIE TEN
 GP3  5 ●  ← DT   ● 36  3V3(OUT) ← +
 GP4  6 ●  ← SW   ● 35  ...
      ...   (widok od góry, USB u góry)
```

- Piny liczone od **lewego górnego rogu przy USB** (1, 2, 3… w dół lewej strony; prawa strona od 40 u góry w dół).
- `+` podłącz do **3V3(OUT), pin 36**. Nie do pinu 37 (3V3_EN, wyłącza zasilanie) i nie do 5 V (VBUS/VSYS).
- Piny Pico H wystają od spodu. Na spodzie płytki przy każdym pinie jest podpis (GP2, GND, 3V3), więc łatwo sprawdzić.
- Jeśli kręcenie w prawo zmniejsza jasność, zamień przewody `CLK` i `DT`.

### Wgranie programu na Pico (jednorazowo)

1. Zainstaluj **Arduino IDE 2**.
2. *File → Preferences → Additional boards manager URLs* wklej:
   `https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json`
3. *Tools → Board → Boards Manager*, wyszukaj **pico**, zainstaluj **Raspberry Pi Pico/RP2040/RP2350** (autor: Earle F. Philhower).
4. Otwórz `firmware/bulbsync_knob/bulbsync_knob.ino`.
5. *Tools → Board → Raspberry Pi Pico/RP2040/RP2350 → Raspberry Pi Pico*.
6. **Za pierwszym razem:** przytrzymaj przycisk **BOOTSEL** na Pico, podłącz kabel USB, puść przycisk. Potem kliknij **Upload** (strzałka).
   Kolejne wgrania działają już bez BOOTSEL.
7. Test: *Tools → Serial Monitor*, prędkość **115200**. Co sekundę powinno pojawiać się `BULBSYNC-KNOB 1`,
   a przy kręceniu i klikaniu `+`, `-`, `CLICK`. Dioda na Pico mignie przy każdym ruchu.
   **Zamknij Serial Monitor** przed uruchomieniem BulBSync, bo port może być otwarty tylko w jednym programie naraz.

### Obsługa

| Ruch | Normalnie | W trakcie ambientu |
|---|---|---|
| Obrót | jasność ±5% na ząbek (szybkie kręcenie: ±10%); kręcenie w górę włącza wyłączone światło | jasność maksymalna ambientu |
| Obrót z wciśniętą gałką | kolor: odcień, biały: barwa (ciepła ↔ zimna) | jasność minimalna ambientu |
| Kliknięcie | włącz / wyłącz | zatrzymaj ambient |
| Przytrzymanie (0,7 s) | start ambientu | zatrzymaj ambient |

Aplikacja sama znajduje pokrętło (port Raspberry Pi, który się przedstawi) i łączy się ponownie po odłączeniu kabla.
Status i ostatnią akcję widać na pasku bocznym. Tam też wybierasz, czym steruje pokrętło: wszystkimi żarówkami albo jedną.
Gdyby automatyczne wykrywanie zawiodło, wpisz port w `settings.json`: `"knob": {"port": "COM5"}`.

Jeśli jeden ząbek zmienia jasność dwa razy (albo trzeba kręcić o dwa ząbki), zmień w programie płytki
`TRANSITIONS_PER_DETENT` z 4 na 2 i wgraj ponownie.

## Gdy coś nie działa

| Objaw | Co zrobić |
|---|---|
| „brak połączenia” przy żarówce | Kliknij **Skanuj sieć**, bo IP mogło się zmienić. Najlepiej ustaw w routerze rezerwację DHCP (stałe IP) po adresie MAC żarówki. |
| Błąd 901/905, timeout | Zamknij aplikację LSC / Smart Life na telefonie i ewentualnie inne programy (np. ScreenSync). Żarówka obsługuje tylko jedno połączenie lokalne naraz. |
| Błąd 914 / zły klucz | Żarówka była parowana ponownie, więc ma nowy klucz. Uruchom `python -m tinytuya wizard` jeszcze raz i podmień `devices.json`. |
| Brak `devices.json` | Skopiuj go do folderu BulBSync (obok `start.bat`). |

## Testy

```bash
python -m pytest
```

## Struktura

| Plik | Co robi |
|---|---|
| `bulbsync/gui.py` | okno: strony Sterowanie i Ambient |
| `bulbsync/widgets.py` | koło kolorów, suwaki z gradientem, podgląd stref ekranu |
| `bulbsync/theme.py` | kolory interfejsu |
| `bulbsync/bulb.py` | wątek na każdą żarówkę: stałe połączenie, scalanie poleceń, ponawianie po błędzie |
| `bulbsync/ambient.py` | przechwytywanie ekranu i liczenie koloru dla stref |
| `bulbsync/color.py` | konwersje kolorów i formaty danych Tuya (DP 24 / DP 27) |
| `bulbsync/config.py` | wczytywanie `devices.json` i `settings.json` |
| `bulbsync/knob.py` | pokrętło USB: wyszukiwanie i połączenie z płytką, co robi obrót i kliknięcie |
| `firmware/bulbsync_knob/` | program na Raspberry Pi Pico (Arduino) |
