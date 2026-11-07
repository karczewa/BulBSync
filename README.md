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
2. Uruchom **`install.bat`**. Zainstaluje `tinytuya`, `mss`, `numpy`, `customtkinter` i `pillow`,
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
- **Sposób liczenia koloru:** „Wyraziste kolory” daje pierwszeństwo nasyconym pikselom, więc czarne/szare tło nie zagłusza
  np. ognia czy neonu. „Średnia z ekranu” jest wierniejsza, ale bledsza.
- **Gry pełnoekranowe:** tryb „exclusive fullscreen” może blokować przechwytywanie. Ustaw w grze **okno bez ramek (borderless)**.
- W trybie ambient żarówki używają kanału DP 27 (tego samego co synchronizacja z muzyką w aplikacji), który przyjmuje szybkie zmiany.

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
