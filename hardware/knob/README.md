# Obudowa pokrętła (krążek)

Krążek Ø86 × 33,5 mm na **Raspberry Pi Pico H + moduł KY-040 + przewody dupont**, bez lutowania i bez śrub.
Kręcisz zewnętrznym pierścieniem, klikasz przyciskiem na środku.

![Rozłożony model](preview_exploded.png)
![Strona z kablem USB](preview_usb_side.png)

## Jak to działa

- **Pierścień** leży całym obwodem na górnej krawędzi podstawy (zakładka), więc się nie kiwa.
- **Przycisk** (Ø40 mm) jest wciśnięty na oś enkodera. Ma stożkową krawędź szerszą od spodu, więc nie wyjdzie górą
  i przytrzymuje pierścień. Trzy ukryte wpusty w otworze pierścienia obracają przycisk, a z nim oś.
- Wnętrze podstawy jest od góry całkowicie otwarte, więc Pico wkłada się bez przeszkód.

## Pliki do druku (`stl/`)

| Plik | Co to | Orientacja |
|---|---|---|
| `knob_base.stl` | podstawa: dno, ścianka z otworem USB, słupki, gniazdo enkodera | dnem do stołu |
| `knob_plate.stl` | płytka dociskająca enkoder, wciskana na kołki | płasko |
| `knob_cap.stl` | obrotowy pierścień z ryflowaniem | **wierzchem do stołu** (tak jest w pliku) |
| `knob_button.stl` | przycisk na środek | **wierzchem do stołu** (tak jest w pliku) |
| `knob_test.stl` | pierścienie próbne do dobrania otworu na oś | jak w pliku |

Sugerowane ustawienia: PLA/PETG, warstwa 0,2 mm, 3 obrysy, wypełnienie 15–20%, bez podpór.

## Wymiary KY-040

Model jest ustawiony pod **Okystar KY-040 (HW-040)**: gładka tuleja bez gwintu, nacięty wałek. Dla innego modułu
popraw sekcję `[KY-040]` na górze pliku `bulbsync_knob.scad`:

| Parametr | Okystar KY-040 | Co zmierzyć |
|---|---|---|
| `ky_pcb` | 18,5 × 26 × 1,6 | szerokość, długość i grubość płytki |
| `ky_enc_from_edge` | 9 | od środka osi do krótkiej krawędzi płytki **bez** pinów |
| `enc_body_h` | 5,75 | od płytki do miejsca, gdzie zaczyna się tuleja |
| `bushing_h` | 7 | wysokość tulei |
| `shaft_above_bushing` | 8,6 | ile osi wystaje ponad tuleję |
| `shaft_hole` | 6,2 | otwór na oś, dobrany pierścieniem próbnym nr 1 |

Po zmianie liczb w OpenSCAD: ustaw `part = "cap";` (albo `"base"`, `"plate"`, `"button"`), **F6**, potem **F7** (eksport STL).
Plik sam sprawdza, czy wszystko się mieści.

## Potrzebne drobiazgi

- podkładki **M10** jako obciążnik (na dwa słupki) albo inne ciężkie drobiazgi przyklejone na dnie,
- nóżki silikonowe albo mata antypoślizgowa na spód (żeby podstawa nie obracała się razem z pierścieniem).

## Składanie

1. **KY-040:** podłącz przewody dupont. Włóż moduł w gniazdo na środku podstawy: płytka na czterech podkładkach,
   między dwiema ściankami, osią do góry.
2. **Płytkę mocującą** nałóż otworem na tuleję enkodera i wciśnij na kołki na słupkach.
3. **Pico H** odwróć do góry nogami (pinami do góry), gniazdem USB w stronę otworu w ściance, i nałóż na cztery kołki.
   Podłącz przewody według podpisów na spodzie płytki (CLK → GP2, DT → GP3, SW → GP4, GND → GND, + → 3V3).
4. Ułóż przewody **jak najniżej i z dala od środka**, nałóż podkładki, przyklej nóżki.
5. **Przycisk włóż w pierścień od spodu** (trzy rowki przycisku trafiają na trzy wpusty w otworze pierścienia).
6. Nałóż pierścień z przyciskiem na podstawę i **wciśnij środek przycisku na oś** do oporu.
7. Podłącz kabel micro-USB.

## Dopasowanie

| Objaw | Co zmienić |
|---|---|
| Pierścień obraca się ciężko albo ociera bokiem | zwiększ `lap_clear` (np. 0.45); pomaga też odrobina smaru albo grafitu z ołówka na krawędzi podstawy |
| Pierścień ma luz na boki | zmniejsz `lap_clear` (np. 0.2) |
| Przycisk wystaje ponad pierścień albo unosi pierścień | zmniejsz `btn_roof` o tyle, ile wystaje |
| Przycisk jest wyraźnie niżej niż pierścień | zwiększ `btn_roof` |
| Przycisk ociera o otwór | zwiększ `btn_gap` |
| Przycisk za luźny lub za ciasny na osi | `shaft_hole` (±0,05–0,1) |

Opcje: `plate_fix = "screws"` (płytka na śruby M3 zamiast kołków), `bushing_threaded = true` (enkoder z gwintem i nakrętką),
`button_d` (średnica przycisku).
