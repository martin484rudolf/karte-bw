# Volt-Karte Baden-Württemberg

Klickbare Karte der 44 Stadt- und Landkreise in Baden-Württemberg für den
Volt-Hub in Haiilo. Jeder Kreis kann auf den Hub der dortigen Volt-Gruppe
zeigen, auf eine Kreiskarte mit den Gemeinden oder auf eine beliebige andere
Seite.

- `index.html` – die Karte, zum Einbetten im Haiilo-Widget (iFrame)
- `links.json` – die Adressen: je Kreis eine, dazu die drei Nachbarländer
- `bauen.py`, `vorlage.html`, `ebenen.json`, `quellen/` – der Bausatz, mit dem
  die Karte erzeugt wird; auf Vercel wird davon nichts ausgeliefert

## Adressen eintragen

In `links.json` beim passenden Eintrag die Adresse zwischen die
Anführungszeichen bei `"url"` setzen. Leer = Fläche nicht anklickbar; auf der
Karte steht dann im Tooltip „Seite folgt".

`"ziel": "_blank"` öffnet die Links in einem neuen Tab, `"_top"` im
Haiilo-Fenster selbst.

Die Datei wird beim Aufruf der Seite nachgeladen, nicht fest eingebaut: eine
geänderte Adresse ist nach dem nächsten Deploy sofort wirksam, ohne dass die
Karte neu gebaut werden muss. Gleiches gilt umgekehrt – `bauen.py`
überschreibt eine vorhandene `links.json` nicht, sondern ergänzt nur fehlende
Einträge.

## Karte neu bauen

```
pip install shapely pyproj
python bauen.py ebenen.json
```

`ebenen.json` beschreibt, was gebaut wird: Zuschnitt (`praefix` – `08` ist
Baden-Württemberg), Breite, Vereinfachung der Grenzen in Metern, Schriftgrößen,
die hervorgehobenen Nachbarn und voreingetragene Adressen. Für eine Kreiskarte
mit Gemeinden wird eine zweite Ebene mit dem Gemeinde-Datensatz und dem
Präfix des Kreises ergänzt.

Das Skript projiziert nach UTM 32N (EPSG:25832), vereinfacht die Grenzen,
sucht für jede Fläche den Punkt mit dem größten Abstand zum Rand, setzt die
Beschriftung so groß, wie sie dort hineinpasst, legt zu kleine Flächen an den
Rand und färbt benachbarte Kreise nach dem Vier-Farben-Satz unterschiedlich
ein.

## Quellen und Lizenz

Verwaltungsgrenzen: Verwaltungsgebiete 1:250 000 (VG250) des Bundesamtes für
Kartographie und Geodäsie, Datenlizenz Deutschland – Namensnennung 2.0
(`www.govdata.de/dl-de/by-2-0`). Bei Veröffentlichung ist die Quelle zu nennen.

Farben und Schrift nach dem Volt-Corporate-Design (Purple 502379, Yellow
FDC220, Blue 82D0F4, Green 1BBE6F, Schrift Ubuntu).
