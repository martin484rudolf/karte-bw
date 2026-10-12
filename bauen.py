#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baut die klickbaren Volt-Karten für den Haiilo-Hub.

Aufruf:   python bauen.py ebenen.json          (alle Ebenen)
          python bauen.py ebenen.json bw       (nur eine Ebene)

Je Ebene entstehen  <ziel>/index.html  und – falls noch nicht vorhanden –
<ziel>/links.json als Gerüst. Eine vorhandene links.json wird nie überschrieben;
fehlende Schlüssel werden ergänzt.

Quelle der Grenzen: Verwaltungsgebiete 1:250 000 (VG250) des Bundesamtes für
Kartographie und Geodäsie, Datenlizenz Deutschland – Namensnennung 2.0.
"""
import json, math, sys, os, re
from pathlib import Path
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, box
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

# ---------------------------------------------------------------- Geometrie --

WGS84_ZU_UTM32 = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)


def nach_utm32(geom):
    return shp_transform(lambda x, y, z=None: WGS84_ZU_UTM32.transform(x, y), geom)


def lade_quelle(pfad):
    """AGS -> (name, bezeichnung, geometrie in UTM32). Mehrfach vorkommende AGS
    werden zusammengefasst (Konstanz liegt in VG250 zweigeteilt vor)."""
    rohdaten = json.load(open(pfad, encoding="utf-8"))
    gesammelt = {}
    for f in rohdaten["features"]:
        p = f["properties"]
        ags = str(p.get("AGS") or p.get("ARS") or "")
        if not ags:
            continue
        g = shape(f["geometry"])
        if ags in gesammelt:
            gesammelt[ags]["teile"].append(g)
        else:
            gesammelt[ags] = {
                "name": p.get("GEN", ""),
                "bez": p.get("BEZ", ""),
                "teile": [g],
            }
    for ags, e in gesammelt.items():
        e["geom"] = nach_utm32(unary_union(e["teile"]))
        del e["teile"]
    return gesammelt


def ohne_loecher(geom, hoechstflaeche=float("inf")):
    """Löcher schließen. Beim Vereinigen der Kreise bleiben in VG250 haarfeine
    Schlitze zwischen benachbarten Flächen stehen – die sollen den Umriss nicht
    durchlöchern."""
    def eins(p):
        ringe = [r for r in p.interiors if Polygon(r).area > hoechstflaeche]
        return Polygon(p.exterior, ringe)
    if geom.geom_type == "Polygon":
        return eins(geom)
    return MultiPolygon([eins(g) for g in geom.geoms if g.geom_type == "Polygon"])


def saeubern(geom, mindestflaeche):
    """Winzige Splitter (Exklaven von wenigen Hektar) weglassen."""
    if geom.geom_type == "Polygon":
        return geom
    teile = [g for g in geom.geoms if g.area >= mindestflaeche]
    if not teile:
        teile = [max(geom.geoms, key=lambda g: g.area)]
    return MultiPolygon(teile) if len(teile) > 1 else teile[0]


# ------------------------------------------------------------------- Pfade ---

def pfad_d(geom, nach_px, stellen=1):
    """Shapely-Geometrie -> SVG-Pfad in Bildkoordinaten, ohne Doppelpunkte."""
    stuecke = []

    def ring(koords):
        punkte = []
        for x, y in koords:
            px, py = nach_px(x, y)
            px, py = round(px, stellen), round(py, stellen)
            if punkte and punkte[-1] == (px, py):
                continue
            punkte.append((px, py))
        if len(punkte) > 2 and punkte[0] == punkte[-1]:
            punkte.pop()
        if len(punkte) < 3:
            return
        stuecke.append(
            "M" + "L".join(f"{x},{y}" for x, y in punkte) + "Z"
        )

    polys = geom.geoms if geom.geom_type in ("MultiPolygon", "GeometryCollection") else [geom]
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        ring(p.exterior.coords)
        for loch in p.interiors:
            ring(loch.coords)
    return "".join(stuecke)


# ---------------------------------------------------------------- Beschriftung

# Breite je Zeichen in Vielfachen der Schriftgröße, für Ubuntu Medium geschätzt.
_SCHMAL = "iljtIf.,;:'|!()[]-/ "
_BREIT = "mwMWQ@"


def textbreite(s):
    b = 0.0
    for c in s:
        if c in _SCHMAL:
            b += 0.30
        elif c in _BREIT:
            b += 0.86
        elif c.isupper() or c in "ÄÖÜ":
            b += 0.64
        elif c.isdigit():
            b += 0.55
        else:
            b += 0.53
    return b


def umbrueche(name, maximal_zeilen=3):
    """Alle sinnvollen Aufteilungen eines Namens auf 1..n Zeilen."""
    teile = []
    for wort in name.split(" "):
        stuecke = re.split(r"(?<=-)", wort)
        teile.extend([s for s in stuecke if s])
    ergebnis = []
    n = len(teile)

    def rekursiv(start, aktuell):
        if len(aktuell) > maximal_zeilen:
            return
        if start == n:
            if aktuell:
                ergebnis.append(list(aktuell))
            return
        for ende in range(start + 1, n + 1):
            stueck = "".join(teile[start:ende])
            if not stueck.endswith("-"):
                stueck = " ".join(
                    w for w in " ".join(teile[start:ende]).split(" ") if w
                )
            aktuell.append(stueck.replace("- ", "-").strip())
            rekursiv(ende, aktuell)
            aktuell.pop()

    rekursiv(0, [])
    return ergebnis


def beste_schrift(name, radius, stufen):
    """Erste Schriftgröße aus `stufen`, in der der Name in einen Kreis mit
    radius passt – samt der dafür nötigen Zeilenaufteilung. Feste Stufen statt
    stufenlos skalierter Schrift: sonst steht neben 19 pt ein 9-pt-Name und das
    Kartenbild wird unruhig."""
    varianten = umbrueche(name)
    for fs in stufen:
        passend = [
            z for z in varianten
            if fs <= 2 * radius / math.hypot(
                max(textbreite(y) for y in z), 1.06 * len(z))
        ]
        if passend:
            return fs, min(passend, key=len)
    return None, min(varianten, key=len)


def ankerpunkt(geom):
    """Punkt mit möglichst großem Abstand zum Rand (Pol der Unzugänglichkeit),
    samt diesem Abstand. Gitter mit Verfeinerung – robust auch bei Löchern."""
    teil = max(geom.geoms, key=lambda g: g.area) if geom.geom_type == "MultiPolygon" else geom
    rand = teil.boundary
    x0, y0, x1, y1 = teil.bounds
    schritt = max((x1 - x0), (y1 - y0)) / 12
    besser = (None, -1)
    bereich = (x0, y0, x1, y1)
    for _ in range(5):
        bx0, by0, bx1, by1 = bereich
        y = by0
        while y <= by1:
            x = bx0
            while x <= bx1:
                from shapely.geometry import Point

                p = Point(x, y)
                if teil.contains(p):
                    d = p.distance(rand)
                    if d > besser[1]:
                        besser = ((x, y), d)
                x += schritt
            y += schritt
        if besser[0] is None:
            from shapely.geometry import Point

            p = teil.representative_point()
            return (p.x, p.y), p.distance(rand)
        cx, cy = besser[0]
        bereich = (cx - schritt, cy - schritt, cx + schritt, cy + schritt)
        schritt /= 3
    return besser


def faerben(flaechen, anzahl=4):
    """Greedy-Färbung, damit benachbarte Flächen verschiedene Töne bekommen."""
    schluessel = list(flaechen)
    nachbarn = {k: set() for k in schluessel}
    for i, a in enumerate(schluessel):
        ga = flaechen[a]["geom"]
        for b in schluessel[i + 1:]:
            gb = flaechen[b]["geom"]
            if ga.distance(gb) < 60:  # 60 m Toleranz: Grenze berührt
                nachbarn[a].add(b)
                nachbarn[b].add(a)
    farbe = {}
    while len(farbe) < len(schluessel):
        offen = [k for k in schluessel if k not in farbe]
        # DSATUR: zuerst die Fläche mit den meisten schon gefärbten Nachbarn
        k = max(offen, key=lambda k: (
            len({farbe[n] for n in nachbarn[k] if n in farbe}), len(nachbarn[k])))
        belegt = {farbe[n] for n in nachbarn[k] if n in farbe}
        frei = [c for c in range(anzahl) if c not in belegt]
        farbe[k] = frei[0] if frei else anzahl - 1
    konflikte = sum(
        1 for a in schluessel for b in nachbarn[a] if farbe[a] == farbe[b]
    ) // 2
    if konflikte:
        print(f"   Hinweis: {konflikte} gleichfarbige Nachbarschaften")
    return farbe


# ------------------------------------------------------------------- Vorlage --

VORLAGE = Path(__file__).with_name("vorlage.html")


def schreibe_html(ziel, titel, aria, daten):
    html = VORLAGE.read_text(encoding="utf-8")
    html = html.replace("{{TITEL}}", titel).replace("{{ARIA}}", aria)
    html = html.replace(
        "{{DATEN}}", json.dumps(daten, ensure_ascii=False, separators=(",", ":"))
    )
    Path(ziel, "index.html").write_text(html, encoding="utf-8")


def schreibe_links(ziel, flaechen_namen, nachbar_namen, vorgaben):
    pfad = Path(ziel, "links.json")
    if pfad.exists():
        vorhanden = json.loads(pfad.read_text(encoding="utf-8"))
    else:
        vorhanden = {
            "hinweis": "Adressen der Haiilo-Seiten eintragen. Leere Adresse = Fläche nicht anklickbar.",
            "ziel": "_blank",
            "flaechen": {},
            "nachbarn": {},
        }
    vorhanden.setdefault("flaechen", {})
    vorhanden.setdefault("nachbarn", {})
    for k, name in flaechen_namen.items():
        e = vorhanden["flaechen"].setdefault(k, {"name": name, "url": ""})
        e.setdefault("name", name)
        e.setdefault("url", vorgaben.get(k, ""))
        if not e["url"]:
            e["url"] = vorgaben.get(k, "")
    for k, name in nachbar_namen.items():
        e = vorhanden["nachbarn"].setdefault(k, {"name": name, "url": ""})
        e.setdefault("url", "")
    pfad.write_text(
        json.dumps(vorhanden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# -------------------------------------------------------------------- Ebene ---

def baue_ebene(cfg, quelle):
    name = cfg["name"]
    ziel = Path(cfg["ziel"])
    ziel.mkdir(parents=True, exist_ok=True)

    breite = cfg.get("breite", 1000)
    rand = cfg.get("rand", 60)          # Rand in Bildpunkten
    toleranz = cfg.get("toleranz", 150)  # Vereinfachung in Metern
    mindest = cfg.get("mindestflaeche", 2.0e5)

    # Flächen der Ebene
    flaechen = {
        ags: dict(e) for ags, e in quelle.items()
        if ags.startswith(cfg["praefix"]) and len(ags) == len(cfg["beispiel_ags"])
        and (not cfg.get("nur") or ags in cfg["nur"])
    }
    if not flaechen:
        raise SystemExit(f"Ebene {name}: keine Flächen gefunden")

    umriss = ohne_loecher(unary_union([e["geom"] for e in flaechen.values()]))
    umriss = saeubern(umriss.simplify(toleranz, preserve_topology=True), mindest * 20)

    for e in flaechen.values():
        e["geom"] = saeubern(
            e["geom"].simplify(toleranz, preserve_topology=True), mindest
        )

    ganzes = unary_union([e["geom"] for e in flaechen.values()])

    # Bildmaßstab aus der Ausdehnung der Ebene
    x0, y0, x1, y1 = ganzes.bounds
    nutz = breite - 2 * rand
    skala = (x1 - x0) / nutz
    hoehe = round((y1 - y0) / skala + 2 * rand)

    def nach_px(x, y):
        return (x - x0) / skala + rand, (y1 - y) / skala + rand

    # Umland
    umland_kasten = box(
        x0 - 0.75 * (x1 - x0), y0 - 0.40 * (y1 - y0),
        x1 + 0.75 * (x1 - x0), y1 + 0.40 * (y1 - y0),
    )
    nachbar_praefixe = cfg.get("nachbarn", {})
    nachbarn = []
    verbraucht = set(flaechen)
    for key, bez in nachbar_praefixe.items():
        teile = [
            e["geom"] for ags, e in quelle.items()
            if ags.startswith(bez["praefix"]) and ags not in flaechen
        ]
        if not teile:
            continue
        verbraucht |= {ags for ags in quelle if ags.startswith(bez["praefix"])}
        g = unary_union(teile).simplify(toleranz * 3, preserve_topology=True)
        g = g.intersection(umland_kasten).difference(ganzes)
        if g.is_empty:
            continue
        g = saeubern(g, mindest * 50)
        (ax, ay), r = ankerpunkt(g)
        bx, by = nach_px(ax, ay)
        nachbarn.append({
            "key": key, "v": bez["name"], "d": pfad_d(g, nach_px),
            "bx": round(bx, 1), "by": round(by, 1),
        })

    # Staatsgebiet als ruhige Grundfläche unter allem
    land = unary_union([
        e["geom"].simplify(toleranz * 8, preserve_topology=True)
        for e in quelle.values()
    ]).intersection(umland_kasten)
    land = saeubern(ohne_loecher(land, mindest * 500), mindest * 200)

    # Farbtöne
    farbe = faerben(flaechen)

    # Flächen samt Beschriftung
    stufen = cfg.get("schrift_stufen", [14, 11])
    eintraege, aussen = [], []
    for ags in sorted(flaechen):
        e = flaechen[ags]
        (ax, ay), r_m = ankerpunkt(e["geom"])
        lx, ly = nach_px(ax, ay)
        r_px = r_m / skala
        fs, zeilen = beste_schrift(e["name"], r_px, stufen)
        satz = {
            "ags": ags, "name": e["name"], "bez": e["bez"],
            "d": pfad_d(e["geom"], nach_px), "c": farbe[ags],
            "lx": round(lx, 1), "ly": round(ly, 1),
        }
        if fs:
            satz["fs"] = fs
            satz["lines"] = zeilen
        else:
            satz["fs"] = cfg.get("schrift_aussen", stufen[-1])
            satz["lines"] = [e["name"]]
            satz["aussen"] = True
            aussen.append(satz)
        eintraege.append(satz)

    # Außenbeschriftung in die Randspalte links oder rechts legen
    from shapely.geometry import LineString
    gx0, gy0, gx1, gy1 = ganzes.bounds
    for s in aussen:
        # waagrechte Linie durch den Ankerpunkt: wo verlässt sie die Ebene?
        y_m = y1 - (s["ly"] - rand) * skala
        schnitt = ganzes.intersection(LineString([(gx0 - 1, y_m), (gx1 + 1, y_m)]))
        if schnitt.is_empty:
            links_px, rechts_px = s["lx"], s["lx"]
        else:
            sx0, _, sx1, _ = schnitt.bounds
            links_px = nach_px(sx0, y_m)[0]
            rechts_px = nach_px(sx1, y_m)[0]
        s["_l"], s["_r"] = links_px - 12, rechts_px + 12
        s["seite"] = "l" if (s["lx"] - links_px) <= (rechts_px - s["lx"]) else "r"

    abstand = cfg.get("schrift_aussen", stufen[-1]) * 1.5
    for seite in ("l", "r"):
        gruppe = sorted([s for s in aussen if s["seite"] == seite], key=lambda s: s["ly"])
        y = None
        for s in gruppe:
            y = s["ly"] if y is None else max(s["ly"], y + abstand)
            s["tx"] = round(max(8, s["_l"]) if seite == "l" else min(breite - 8, s["_r"]), 1)
            s["ty"] = round(y, 1)
            del s["_l"], s["_r"]
        # von unten nachziehen, falls aus dem Bild gelaufen
        grenze = hoehe - rand * 0.3
        ueber = (gruppe[-1]["ty"] - grenze) if gruppe else 0
        if ueber > 0:
            for s in reversed(gruppe):
                s["ty"] = round(min(s["ty"], grenze), 1)
                grenze = s["ty"] - abstand

    # Bildausschnitt so weit aufziehen, dass die Außenbeschriftung hineinpasst
    fx0, fx1 = 0.0, float(breite)
    for s in aussen:
        br = textbreite(s["lines"][0]) * s["fs"] + 6
        fx0 = min(fx0, s["tx"] - br if s["seite"] == "l" else fx0)
        fx1 = max(fx1, s["tx"] + br if s["seite"] == "r" else fx1)

    daten = {
        "w": breite, "h": hoehe,
        "frame": [round(fx0, 1), 0, round(fx1 - fx0, 1), hoehe],
        "land": pfad_d(land, nach_px),
        "rahmen": pfad_d(umriss, nach_px),
        "nb": nachbarn,
        "g": eintraege,
    }

    schreibe_html(ziel, cfg["titel"], cfg["aria"], daten)
    # gleichnamige Flächen (Stadt- und Landkreis) in der Linkdatei unterscheiden
    doppelt = {
        s["name"] for s in eintraege
        if sum(1 for t in eintraege if t["name"] == s["name"]) > 1
    }
    schreibe_links(
        ziel,
        {s["ags"]: (f'{s["name"]} ({s["bez"]})' if s["name"] in doppelt else s["name"])
         for s in eintraege},
        {n["key"]: n["v"] for n in nachbarn},
        cfg.get("vorgaben", {}),
    )

    groesse = os.path.getsize(Path(ziel, "index.html"))
    print(f"{name}: {len(eintraege)} Flächen, {len(nachbarn)} Nachbarn, "
          f"{len(aussen)} Außenbeschriftungen, {breite}x{hoehe} px, "
          f"{groesse/1024:.0f} KB")
    for s in aussen:
        print(f"   außen: {s['name']}")


def main():
    cfg_pfad = sys.argv[1] if len(sys.argv) > 1 else "ebenen.json"
    nur = sys.argv[2] if len(sys.argv) > 2 else None
    cfg = json.loads(Path(cfg_pfad).read_text(encoding="utf-8"))
    quelle = lade_quelle(cfg["quelle"])
    print(f"Quelle: {len(quelle)} Gebiete")
    for ebene in cfg["ebenen"]:
        if nur and ebene["name"] != nur:
            continue
        baue_ebene(ebene, quelle)


if __name__ == "__main__":
    main()
