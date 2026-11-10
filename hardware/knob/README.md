# Obudowa pokrętła (krążek)

Krążek Ø86 × 37 mm na **Raspberry Pi Pico H + moduł KY-040 + przewody dupont**, bez lutowania.
Kręcisz całą górną pokrywą, a klikasz, wciskając ją.

![Rozłożony model](preview_exploded.png)
![Strona z kablem USB](preview_usb_side.png)

## Pliki do druku (`stl/`)

| Plik | Co to | Orientacja | Uwagi |
|---|---|---|---|
| `knob_test.stl` | **element próbny**: otwór na tuleję enkodera + pierścień na oś | jak w pliku | **drukuj najpierw** (ok. 10 min) |
| `knob_base.stl` | podstawa: dno, ścianka z otworem USB, słupki | dnem do stołu | podpory niepotrzebne |
| `knob_plate.stl` | płytka, do której przykręca się enkoder | płasko | |
| `knob_cap.stl` | obracana pokrywa z ryflowaniem | **wierzchem do stołu** (tak jest w pliku) | wierzch wyjdzie gładki od stołu |

Sugerowane ustawienia: PLA/PETG, warstwa 0,2 mm, 3 obrysy, wypełnienie 15–20%, bez podpór.

## Najpierw: element próbny

1. **Płytka z otworem:** tuleja enkodera (gwint) ma wejść bez siłowania, a nakrętka ma się dać nakręcić od góry.
   Jeśli nie wchodzi, zwiększ `bushing_clear` (np. 0.6).
2. **Pierścień:** nasuń go na oś KY-040. Ma wejść z wyraźnym oporem i nie obracać się na osi.
   Jeśli jest za luźno, zmniejsz `shaft_hole` o 0.05–0.1. Jeśli nie wchodzi, zwiększ.
   Jeśli nie da się uzyskać pewnego trzymania, ustaw `set_screw = true`: w piaście będzie śruba dociskowa M3,
   a w boku pokrywy mały okrągły otwór, przez który się ją dokręca.

## Zmierz swój KY-040

Moduły różnią się między producentami. Zmierz suwmiarką i porównaj z sekcją `[KY-040]` na górze pliku `bulbsync_knob.scad`:

| Parametr | Domyślnie | Co zmierzyć |
|---|---|---|
| `ky_pcb` | 19 × 26 × 1,6 | szerokość, długość i grubość płytki |
| `ky_enc_from_edge` | 8 | od środka osi do krótkiej krawędzi płytki **bez** pinów |
| `enc_body_h` | 6,5 | od płytki do miejsca, gdzie zaczyna się gwintowana tuleja |
| `bushing_h` | 7 | wysokość gwintowanej tulei |
| `shaft_above_bushing` | 12 | ile osi wystaje ponad tuleję |

Jeśli coś się różni, zmień liczby w OpenSCAD (darmowy) i wygeneruj STL ponownie:
**F6** (render), potem **F7** (eksport STL). Wcześniej ustaw na górze pliku `part = "cap";` (albo `"base"`, `"plate"`, `"test"`).
Plik sam sprawdza, czy po zmianach wszystko się mieści, i wypisuje komunikat w konsoli, gdy coś koliduje.

## Potrzebne drobiazgi

- 2 × śruba **M3 × 10** + 2 × nakrętka M3 (płytka enkodera do słupków),
- nakrętka z kompletu KY-040 (na gwintowaną tuleję enkodera),
- podkładki **M10** jako obciążnik (nakładane na dwa słupki, do ok. 13 sztuk na słupek); możesz też przykleić klejem na gorąco inne ciężkie drobiazgi w wolnych miejscach na dnie,
- nóżki silikonowe albo mata antypoślizgowa na spód (żeby podstawa nie obracała się razem z pokrywą),
- (opcjonalnie, gdy `set_screw = true`) śruba M3 × 8 + nakrętka M3 do piasty.

## Składanie

1. **Nakrętki M3** wsuń w boczne kieszenie obu słupków.
2. **KY-040:** podłącz przewody dupont (zostaw je podłączone). Przełóż tuleję enkodera od spodu przez otwór w płytce
   i nakręć nakrętkę od góry. Piny modułu mają być skierowane w stronę słupków na podkładki (patrz podgląd).
3. **Płytkę z enkoderem** połóż na słupkach, tak żeby płytka KY-040 oparła się na dwóch listwach na dnie.
   Przykręć śrubami M3 × 10.
4. **Pico H** odwróć **do góry nogami** (pinami do góry), gniazdem USB w stronę otworu w ściance, i nałóż na cztery kołki.
   Podłącz przewody według schematu z głównego README (CLK → pin 4, DT → 5, SW → 6, GND → 3, + → 36).
   Pamiętaj, że po odwróceniu lewa i prawa strona Pico są zamienione. Kieruj się podpisami na spodzie płytki (GP2, GND, 3V3).
5. Ułóż przewody płasko, nałóż **podkładki** na słupki, przyklej **nóżki** pod spodem.
6. **Pokrywę** wciśnij na oś enkodera, aż piasta oprze się końcem osi o sufit pokrywy.
   Kliknięcie powinno być wyraźnie wyczuwalne, a pokrywa nie może ocierać o podstawę.
7. Podłącz kabel micro-USB przez otwór w podstawie.

Jeśli pokrywa ociera o podstawę, zwiększ `gap`. Jeśli kliknięcie nie działa (pokrywa opiera się, zanim zadziała przycisk),
sprawdź `shaft_above_bushing`: plik wypisuje „Luz pod piastą”, który powinien wynosić co najmniej 1,5 mm.
