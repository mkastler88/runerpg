# Prüfbericht: Thrones of Britannia (Datensatz aus früherem Chat)

Stand: 3. Nov 2026. Geprüft wurden `thrones_of_britannia_kanka_de.json`, die zwei CSV-Dateien und das Briefing.

## Ergebnis in Kürze

Der Datensatz ist in sich stimmig und deckt sich mit den Quellen im Projekt. Eine Abweichung (Schreibweise „Finngaill“) und mehrere nicht prüfbare Punkte sind unten aufgeführt.

## Was geprüft wurde und stimmt

| Prüfung | Ergebnis |
|---|---|
| Zählungen (63 Provinzen, 229 Städte, 53 Königreiche, 67 Fraktionen, 6 Kulturen, 10 Charaktere, 649 Verbindungen) | stimmen mit dem `meta`-Block überein |
| Provinzen und Städte gegen honga.net (`regions.mhtml`) | **identisch**: alle 63 Provinzen, alle 229 Städte, Stadtzahl und Zuordnung je Provinz |
| Duplikate, unbekannte Verweise, Symmetrien (Stadt ↔ Provinz, Stadt ↔ Königreich, Königreich ↔ Fraktion) | keine Fehler |
| Kultur von Stadt, Königreich, Fraktion | durchgehend konsistent |
| Verbindungen (649): Typen, Quellen, Ziele, Duplikate | alle Ziele vorhanden, keine Doppelten |
| 10 spielbare Fraktionen und ihre Anführer gegen Total War Wiki | identisch |
| 57 Nebenfraktionen und ihre Kulturgruppen gegen Total War Wiki | bis auf 1 Schreibweise identisch (siehe unten) |
| 53 Königreiche gegen die Beschriftungen der Fraktionskarte | 53 von 53 vorhanden, keine fehlt oder ist überzählig |
| CSV-Dateien gegen JSON (Provinz, Königreich, Fraktion, Kultur, Sicherheit je Stadt) | keine Abweichung |
| „19 geteilte Provinzen“ aus dem Briefing | nachgerechnet: exakt diese 19 |
| Summe der Städte der Königreiche | 229 |

## Abweichung

* **Finngaill / Fingaill:** Das Total War Wiki schreibt die Wikinger-Nebenfraktion „**Fingaill**“, der Datensatz „**Finngaill**“. Offen, welche Schreibweise gelten soll (die irische Form lautet Fionngaill).

## Nicht eigenständig prüfbar

* **Zuordnung Stadt → Fraktion (195 „hoch“):** stammt aus den Farben der Fraktionskarte. Die Stadtnamen auf der Karte sind zu klein, um sie hier neu zuverlässig auszulesen. Die 53 Königreiche passen zur Karte.
* **34 Städte „mittel“:** geografisch und aus dem Spielwissen geprüft, keine Auffälligkeit. Beispiele: Cork und Cloyne bei Myrrborg, Aberteifi und Dinefwr bei Seisilwig, Wareham und Watchet bei West Seaxe, Menevia bei Dewet, Maldon und Tilbury bei East Engle. Die Städte tragen in Kanka das Tag „Zuordnung unsicher“.
* **Vasallen von West Seaxe** (Cent, Cerneu, Defena, Gliwissig, Gwent, Suth Seaxe): stammt laut Briefing aus der Wiki-Infobox, die im Projekt nicht liegt. Nicht überprüfbar.
* **Fraktionen ohne Städte auf der Startkarte (14):** aus der Karte abgeleitet, plausibel.

## Hinweise zu den Texten

Die Beschreibungen sind Übersetzungen und Zusammenfassungen von Wiki-Texten und lesen sich gut. Einzelne historische Ungenauigkeiten stammen aus den Quelltexten und wurden nicht verändert, zum Beispiel: Alfred folgt seinem Bruder „im folgenden Jahr“ (tatsächlich 871), Flann Sinna folgt „seinem Vater 877“ (sein Vater starb 862), „Burghead“ steht im Wiki für Burgred (der Text vermerkt das). Für ein Rollenspiel ist das unkritisch.

## Hinweise zum Import

* Drei Namen kommen in mehreren Eintragsarten vor (Hlymrekr, Vedrafjordr, Veisafjordr: Provinz, Stadt, Fraktion). Das ist in Kanka unkritisch; intern haben sie unterschiedliche Schlüssel.
* Die Kulturen sind als Völker (Races) angelegt: Name = Kultur („Gälen“), Typ = Kulturgruppe („Gälische Königreiche“).
