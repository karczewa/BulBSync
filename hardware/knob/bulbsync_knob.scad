// BulBSync Knob – obudowa krążka (Raspberry Pi Pico H + moduł KY-040 + przewody dupont, bez lutowania)
//
// Części (zmienna `part`):
//   "base"      podstawa (stoi na biurku): Pico, słupki pod płytkę enkodera, słupki na obciążnik, otwór USB
//   "plate"     płytka, do której przykręca się enkoder (nakrętka na tulei), przykręcana do podstawy
//   "cap"       obracana pokrywa z ryflowaniem, nasadzana na oś enkodera
//   "test"      mały element próbny: otwór na tuleję enkodera + piasta z otworem na oś (drukuj najpierw!)
//   "assembly"  podgląd całości (nie do druku)
//   "section"   przekrój całości (nie do druku)
//
// Eksport STL z linii poleceń, np.:  openscad -D 'part="cap"' -o cap.stl bulbsync_knob.scad
// Wszystkie wymiary w mm. Najpierw zmierz swój KY-040 i popraw sekcję [KY-040].

part = "assembly";

/* [Ogólne] */
D = 86;              // średnica krążka
wall = 2.4;          // grubość ścianek
floor_t = 3;         // grubość dna podstawy
base_h = 12;         // wysokość nieruchomej podstawy (widoczny dolny pas)
gap = 0.6;           // szczelina między podstawą a pokrywą
$fn = 120;

/* [KY-040 – zmierz swój moduł!] */
ky_pcb = [19, 26, 1.6];    // płytka: szerokość, długość, grubość
ky_enc_from_edge = 8;      // od osi enkodera do krótkiej krawędzi płytki BEZ pinów
ky_under = 3;              // luz pod płytką (wystające lutowania)
ky_support = true;         // listwy podpierające płytkę od spodu (przy wciskaniu nacisk idzie na nie)
ky_support_x = 8.3;        // odległość listew od osi (omijają lutowania nóżek enkodera)
enc_body_h = 6.5;          // wysokość korpusu enkodera nad płytką (do miejsca, gdzie zaczyna się tuleja)
bushing_d = 7;             // średnica tulei z gwintem (zwykle M7)
bushing_h = 7;             // wysokość tulei nad korpusem
shaft_above_bushing = 12;  // ile osi wystaje ponad tuleję
bushing_threaded = false;  // true: tuleja z gwintem, enkoder przykręcany nakrętką do płytki
                           // false: tuleja gładka – płytkę KY-040 trzyma gniazdo w podstawie, a płytka mocująca dociska korpus enkodera
nut_h = 2;                 // grubość nakrętki (tylko gdy bushing_threaded = true)
ky_cradle = true;          // ścianki wzdłuż płytki KY-040 – nie pozwalają jej się obracać
ky_cradle_clear = 0.4;     // luz między płytką KY-040 a ściankami
ky_cradle_wall = 1.6;
ky_cradle_lip = 1.0;       // o ile ścianki wystają ponad płytkę KY-040
plate_press = 0.3;         // słupki niższe o tyle, żeby przykręcona płytka mocno docisnęła korpus enkodera

/* [Płytka mocująca enkoder] */
plate_t = 2.5;
plate_w = 14;              // szerokość płytki (wzdłuż osi Y)
pillar = 8;                // przekrój słupków
pillar_x = 17;             // odległość słupków od osi
bushing_clear = 0.4;       // luz otworu na tuleję

/* [Pokrywa] */
top_t = 3;                 // grubość wierzchu pokrywy
hub_d = 18;                // średnica piasty na oś
hub_len = 10;              // jak głęboko piasta nachodzi na oś
shaft_hole = 6.2;          // otwór na oś (dobrany pierścieniem próbnym nr 1) – pokrywa trzyma się na wcisk; za luźno -> zmniejsz o 0.05–0.1, za ciasno -> zwiększ
set_screw = false;         // true = śruba dociskowa M3 w piaście + okrągły otwór dostępowy w boku pokrywy
knurl_n = 72;              // liczba rowków ryflowania
knurl_depth = 0.7;
chamfer = 1.2;

/* [Raspberry Pi Pico H (leży do góry nogami, pinami do góry)] */
pico = [51, 21, 1];
pico_y = 9.5;              // odległość dłuższej krawędzi Pico od osi enkodera
pico_posts_h = 4;          // wysokość słupków pod Pico (pod nimi mieści się gniazdo USB)
usb_open = [13, 9];        // otwór na wtyczkę micro-USB (szer., wys.)
dupont_h = 14;             // wysokość wtyczki dupont
header_h = 2.5;            // plastikowa listwa pinów Pico

/* [Obciążnik: podkładki M10 nakładane na słupki] */
washer_post_d = 10;
washer_post_h = 14;
washer_pos = [[25, -17], [-25, -17]];

/* [Śruby M3] */
m3_hole = 3.4;
m3_tap = 3.0;              // otwór w słupku pod śrubę (przechodzi przez nakrętkę)
m3_nut_w = 5.5 + 0.4;      // rozmiar klucza nakrętki + luz
m3_nut_t = 2.4 + 0.4;

// ---------------------------------------------------------------------------
// Wysokości wynikające z wymiarów
ky_bottom   = floor_t + ky_under;
ky_top      = ky_bottom + ky_pcb[2];
plate_z0    = ky_top + enc_body_h;
plate_z1    = plate_z0 + plate_t;
bushing_top = ky_top + enc_body_h + bushing_h;
shaft_top   = bushing_top + shaft_above_bushing;
cap_ceiling = shaft_top + 0.5;
cap_top     = cap_ceiling + top_t;
cap_bottom  = base_h + gap;
hub_bottom  = cap_ceiling - hub_len;
nut_eff     = bushing_threaded ? nut_h : 0;
pillar_h    = bushing_threaded ? plate_z0 : plate_z0 - plate_press;
pico_z      = floor_t + pico_posts_h;            // dolna (elementowa) strona Pico
dupont_top  = pico_z + pico[2] + header_h + dupont_h + 4;   // +4 mm na zagięcie przewodów
usb_z       = pico_z - 1.4;                       // środek gniazda micro-USB
inner_r     = D / 2 - wall;

echo(str("Wysokość całkowita: ", cap_top, " mm, średnica: ", D, " mm"));
echo(str("Luz pod piastą (na wciśnięcie): ", hub_bottom - (plate_z1 + nut_eff), " mm"));
echo(str("Luz nad przewodami Pico: ", cap_ceiling - dupont_top, " mm"));
echo(str("Wystająca tuleja ponad płytką: ", bushing_top - plate_z1, " mm"));
assert(hub_bottom - (plate_z1 + nut_eff) >= 1.5, "Piasta pokrywy za nisko – za mało miejsca na wciśnięcie gałki");
assert(hub_bottom > bushing_top + 0.5, "Piasta pokrywy dotyka tulei enkodera");
assert(cap_ceiling - dupont_top >= 1, "Przewody na Pico nie mieszczą się pod pokrywą – zwiększ shaft_above_bushing lub zmniejsz pico_posts_h");
assert(!bushing_threaded || bushing_top - plate_z1 >= nut_h, "Tuleja za krótka na nakrętkę – zmniejsz plate_t");

// ---------------------------------------------------------------------------
module ring(r_out, r_in, h) {
  difference() { cylinder(r = r_out, h = h); translate([0, 0, -0.01]) cylinder(r = r_in, h = h + 0.02); }
}

module hex_nut_slot(w, t, extend) {
  // nakrętka leżąca płasko + kanał do wsunięcia w kierunku +X
  r = w / sqrt(3);
  union() {
    cylinder(r = r, h = t, $fn = 6, center = true);
    translate([extend / 2, 0, 0]) cube([extend, w, t], center = true);
  }
}

pico_holes = [for (sx = [-1, 1], sy = [0, 1]) [sx * 47 / 2, pico_y + 4.8 + sy * (pico[1] - 9.6)]];

module base() {
  difference() {
    union() {
      cylinder(r = D / 2, h = floor_t);
      // zewnętrzny pas z fazką na dole
      difference() {
        hull() {
          translate([0, 0, chamfer]) cylinder(r = D / 2, h = base_h - chamfer);
          cylinder(r = D / 2 - chamfer, h = base_h);
        }
        translate([0, 0, floor_t]) cylinder(r = inner_r, h = base_h);
      }
      // słupki pod płytkę enkodera
      for (sx = [-1, 1]) translate([sx * pillar_x - pillar / 2, -pillar / 2, 0]) cube([pillar, pillar, pillar_h]);
      // listwy podpierające płytkę KY-040
      if (ky_support) for (sx = [-1, 1])
        translate([sx * ky_support_x - 1, -(ky_pcb[1] - ky_enc_from_edge) + 2, 0])
          cube([2, ky_pcb[1] - 4, ky_bottom]);
      // gniazdo KY-040: ścianki wzdłuż dłuższych krawędzi (blokują obrót; przesunięcie blokuje tuleja w płytce)
      if (ky_cradle) for (sx = [-1, 1]) {
        cx = ky_pcb[0] / 2 + ky_cradle_clear;
        translate([sx > 0 ? cx : -cx - ky_cradle_wall, -(ky_pcb[1] - ky_enc_from_edge) + 1, 0])
          cube([ky_cradle_wall, ky_pcb[1] - 1, ky_top + ky_cradle_lip]);
      }
      // słupki pod Pico (z kołkami w otwory montażowe)
      for (p = pico_holes) translate(p) {
        cylinder(d = 4.6, h = pico_z);
        cylinder(d = 1.8, h = pico_z + pico[2] + 1.2, $fn = 24);
      }
      // słupki na podkładki (obciążnik)
      for (p = washer_pos) translate(p) cylinder(d = washer_post_d, h = floor_t + washer_post_h, $fn = 48);
    }
    // otwór na wtyczkę USB w ścianie (Pico leży gniazdem w stronę +X)
    translate([inner_r - 6, pico_y + pico[1] / 2 - usb_open[0] / 2, usb_z - usb_open[1] / 2])
      cube([D, usb_open[0], usb_open[1]]);
    // śruby + nakrętki M3 w słupkach
    for (sx = [-1, 1]) translate([sx * pillar_x, 0, 0]) {
      translate([0, 0, pillar_h - 9]) cylinder(d = m3_tap, h = 10, $fn = 24);
      translate([0, 0, pillar_h - 5]) rotate([0, 0, sx > 0 ? 0 : 180]) hex_nut_slot(m3_nut_w, m3_nut_t, pillar);
    }
  }
}

module plate() {
  difference() {
    translate([0, 0, plate_z0]) hull()
      for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * (pillar_x + pillar / 2 - 2), sy * (plate_w / 2 - 2), 0]) cylinder(r = 2, h = plate_t, $fn = 24);
    translate([0, 0, plate_z0 - 1]) cylinder(d = bushing_d + bushing_clear, h = plate_t + 2, $fn = 48);
    for (sx = [-1, 1]) translate([sx * pillar_x, 0, plate_z0 - 1]) cylinder(d = m3_hole, h = plate_t + 2, $fn = 24);
  }
}

module cap() {
  difference() {
    union() {
      difference() {
        translate([0, 0, cap_bottom]) hull() {
          cylinder(r = D / 2, h = cap_top - cap_bottom - chamfer);
          cylinder(r = D / 2 - chamfer, h = cap_top - cap_bottom);
        }
        translate([0, 0, cap_bottom - 0.01]) cylinder(r = inner_r, h = cap_ceiling - cap_bottom + 0.01);
        // ryflowanie
        for (i = [0 : knurl_n - 1]) rotate([0, 0, i * 360 / knurl_n])
          translate([D / 2, 0, cap_bottom + 2]) rotate([0, 0, 45])
            cube([knurl_depth * sqrt(2), knurl_depth * sqrt(2), cap_top - cap_bottom - 2 - chamfer - 1.5]);
      }
      // piasta
      translate([0, 0, hub_bottom]) cylinder(d = hub_d, h = cap_ceiling - hub_bottom + 0.01, $fn = 64);
    }
    // otwór na oś (nie na wylot)
    translate([0, 0, hub_bottom - 0.01]) cylinder(d = shaft_hole, h = hub_len, $fn = 48);
    translate([0, 0, hub_bottom - 0.01]) cylinder(d1 = shaft_hole + 1, d2 = shaft_hole, h = 0.6, $fn = 48);  // fazka wejścia
    if (set_screw) {
      sz = hub_bottom + hub_len / 2;
      // śruba dociskowa: otwór od boku piasty + kieszeń na nakrętkę wsuwaną od dołu
      translate([0, 0, sz]) rotate([0, 90, 0]) cylinder(d = m3_hole, h = D, $fn = 24);
      translate([5.6, 0, hub_bottom - 0.01]) hull() {
        translate([0, 0, 0]) rotate([0, 90, 0]) cylinder(r = m3_nut_w / sqrt(3), h = m3_nut_t, $fn = 6, center = true);
        translate([0, 0, sz - hub_bottom]) rotate([0, 90, 0]) cylinder(r = m3_nut_w / sqrt(3), h = m3_nut_t, $fn = 6, center = true);
      }
      // otwór dostępowy w boku pokrywy (na śrubę i klucz imbusowy / śrubokręt)
      translate([inner_r - 1, 0, sz]) rotate([0, 90, 0]) cylinder(d = 6.5, h = wall + 2, $fn = 32);
    }
  }
}

// Pierścienie próbne: otwory coraz większe, numer = liczba nacięć na brzegu.
test_holes = [6.2, 6.35, 6.5, 6.65];

module test_fit() {
  for (i = [0 : len(test_holes) - 1]) translate([i * 17, 0, 0]) difference() {
    cylinder(d = 14, h = 6, $fn = 64);
    translate([0, 0, -1]) cylinder(d = test_holes[i], h = 8, $fn = 48);
    translate([0, 0, -0.01]) cylinder(d1 = test_holes[i] + 0.8, d2 = test_holes[i], h = 0.4, $fn = 48);
    // nacięcia: 1, 2, 3 albo 4
    for (k = [0 : i]) rotate([0, 0, 90 + (k - i / 2) * 14]) translate([7, 0, -1]) cylinder(d = 1.6, h = 8, $fn = 12);
  }
}

// --- makiety elektroniki do podglądu -------------------------------------------
module ky040_mock() {
  color("darkslategray") translate([-ky_pcb[0] / 2, -(ky_pcb[1] - ky_enc_from_edge), ky_bottom]) cube(ky_pcb);
  color("silver") {
    translate([-6, -6, ky_top]) cube([12, 12, enc_body_h]);
    translate([0, 0, ky_top + enc_body_h]) cylinder(d = bushing_d, h = bushing_h);
    translate([0, 0, bushing_top]) cylinder(d = 6, h = shaft_above_bushing);
    if (bushing_threaded) translate([0, 0, plate_z1]) cylinder(d = 11, h = nut_h, $fn = 6);
  }
  color("black") translate([-6.5, -(ky_pcb[1] - ky_enc_from_edge) - 20, ky_bottom - 1]) cube([13, 20, 3.5]);
}
module pico_mock() {
  color("green") translate([-pico[0] / 2, pico_y, pico_z]) cube(pico);
  color("silver") translate([pico[0] / 2 - 5.5, pico_y + pico[1] / 2 - 4, pico_z - 2.6]) cube([6, 8, 2.6]);
  color("black") for (sy = [1.6, pico[1] - 1.6])
    translate([-pico[0] / 2 + 1, pico_y + sy - 1.3, pico_z + pico[2]]) cube([pico[0] - 2, 2.6, header_h + dupont_h]);
}

if (part == "base") base();
else if (part == "plate") translate([0, 0, -plate_z0]) plate();
else if (part == "cap") translate([0, 0, cap_top]) rotate([180, 0, 0]) cap();   // wierzchem do stołu
else if (part == "test") test_fit();
else if (part == "assembly" || part == "section") {
  difference() {
    union() {
      color("dimgray") base();
      color("lightgray") plate();
      color("#3a3a3a", 0.9) cap();
      ky040_mock();
      pico_mock();
    }
    if (part == "section") translate([-D, 0, -1]) cube([2 * D, D, 100]);
  }
}
