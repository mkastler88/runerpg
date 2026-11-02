# Rune RPG auf Kanka: deutsche Regelinhalte per API

Die Inhalte kommen in **Etappen**, jede als eigene Datei in `data/`. Das Skript liest standardmäßig **alle** Dateien in `data/` (alphabetisch) und legt nur an, was in der Kampagne noch fehlt. Neue Etappe einspielen heißt also: neue Datei in `data/` kopieren und `import` erneut starten.

## Inhalt des Pakets

| Datei | Zweck |
|---|---|
| `kanka_import.py` | Import-Skript (nur Python 3.9+, keine weiteren Pakete) |
| `data/00_pilot_held.json` | Held-Pilot: Charakteristiken, 43 Fertigkeiten, 13 Gottheiten, Heldenerschaffung, Property Kit „Rune-Held“, Beispielheld Ragnar |
| `data/01_kap1_ausruestung.json` | Kapitel 1, Rest: 48 Waffen, 5 Rüstungen, 4 Schilde als Items, Property Kits „Rune-Waffe“ und „Rune-Rüstung“, Regel- und Tabellennotes |
| `data/02_kap2_kampf.json` | Kapitel 2: Kampf und weitere Regeln (27 Notes: Ablauf einer Runde, Initiative, Aktionen, Angriffe, Sonderfälle, Verletzungen, Heilung, Wettstreite) |
| `data/03_kap3_entwicklung.json` | Kapitel 3: Heldenentwicklung (Siegespunkte, Todesversicherung, Fertigkeiten steigern, Göttliche Gaben), 75 Göttliche Gaben und 15 Runenkräfte als Abilities, nach Schutzgott gruppiert, mit Gabentabelle |
| `data/04_kap4a_gegnersystem.json` | Kapitel 4, Teil A: Begegnungs-Referenz (Siegespunkte, Budget), Gegner erschaffen (Bedrohungsstufen, Mix, Foe-Maker-Tabelle, Fernkampfwerte, Macht), Property Kit „Rune-Gegner“ mit Formeln und drei Rechenbeispielen aus dem Buch |
| `data/05_kap4b_gegnergalerie.json` | Kapitel 4, Teil B: Gegnergalerie mit 31 Gegnertypen (Creatures mit Kit „Rune-Gegner“), 6 Gegnerfamilien (Races), Symbole, Benchmark, Referenztabelle, Regeln für eigene Kreaturen |
| `data/06_kap4c_gelaende_schwierigkeiten.json` | Kapitel 4, Teil C: 13 Geländemerkmale (Barrieren, Deckung, Schadensorte, Statisten, Ausgänge, Ebenen, Sicht, Fernbeschuss, rutschig, schräg, uneben, seltsame Magie, Karten) und Schwierigkeiten und Wurfarten (Standard, Vergleich, Singulär, Weak Link, Mehrfachwürfe, exotische Würfe, Den Göttern trotzen) |
| `data/07_kap4d_fallen_gefahren.json` | Kapitel 4, Teil D: Fallen und Gefahren (Schaden, Beeinträchtigung, Sticks, Sonderfälle) und 9 Fertigpakete (Säure, Hinterhalt, Ertrinken, Ausrüstungsschaden, Stürze, Feuer, Sich verirren, Greiferfallen, Tiere) |
| `data/08_kap4e_schaetze.json` | Kapitel 4, Teil E: Schätze (Kategorien A–F mit Zufallstabellen, Beute, Tränke, Talismane, Amulette, Ausrüstung und Potenz, Plündern, Machthelme) und 20 legendäre Gegenstände als Items |
| `data/09_einleitung.json` | Einleitung: Was ist Rune RPG, wichtige Begriffe, Die Welt von Rune, Grundregeln (Würfeln, Schwierigkeit, Triumph, Patzer), Spielbeispiel, Eigenarten des Spiels |
| `glossar.md` | Glossar Englisch → Deutsch (Zeilen mit „Vorschlag“ bitte prüfen) |
| `tests/mock_kanka.py` | Optional: lokaler Kanka-Nachbau zum Trockenlauf ohne echte Kampagne |

## Wichtig vorab

* **Immer erst in einer Testkampagne.** Kanka hat keinen Testmodus, und gelöschte Einträge lassen sich in Free-Kampagnen nicht wiederherstellen. Das Skript **löscht nie etwas**, es legt nur an oder aktualisiert.
* **Token niemals in Chats oder Dateien schreiben.** Das Skript liest ihn aus der Umgebungsvariable `KANKA_TOKEN` (oder aus `--token-file`). Liegt das Token in Projektdateien, erneuere es nach dem Pilot (Kanka: Profil → API).
* **Urheberrecht:** Das Regelwerk gehört Atlas Games. Halte die Kampagne privat, nicht im Marketplace teilen.
* **Free-Account:** höchstens 30 Anfragen pro Minute. Das Skript nutzt standardmäßig 25 und fängt Rate-Limits (HTTP 429) selbst ab.

## Ablauf

**1. Testkampagne anlegen** und die Kampagnen-ID aus der Adresse ablesen (`app.kanka.io/w/<ID>/…`).

**2. Zugangsdaten setzen** (nur für das aktuelle Terminal):

```bash
# macOS / Linux
export KANKA_TOKEN="…dein Token…"
export KANKA_CAMPAIGN_ID="12345"
```
```powershell
# Windows PowerShell
$env:KANKA_TOKEN = "…dein Token…"
$env:KANKA_CAMPAIGN_ID = "12345"
```

**3. Offline prüfen** (kein Netzwerk):

```bash
python3 kanka_import.py selftest    # Daten + Formeln gegen die Buchwerte (Ragnar)
python3 kanka_import.py plan        # zeigt, was noch fehlt (zieht bereits importierte Einträge ab), plus Laufzeit
```

**4. Import:**

```bash
python3 kanka_import.py import
python3 kanka_import.py verify      # liest Ragnars berechnete Werte aus Kanka und vergleicht mit dem Buch
```

Bricht der Import ab (Netz, Rate-Limit), einfach denselben Befehl erneut starten: Er macht anhand der Datei `kanka_map_<ID>.json` dort weiter. Diese Datei nicht löschen und nicht für eine andere Kampagne wiederverwenden (das Skript verweigert das).

**Aktualisieren:** `import` legt Neues an **und aktualisiert Geändertes**. Das Skript merkt sich in `kanka_map_<ID>.json` eine Prüfsumme je Eintrag und fasst nur an, was sich in den Daten geändert hat (siehe Abschnitt „Aktualisieren und Umbenennen“).

## Prüfliste in Kanka (bitte der Reihe nach)

1. **Hierarchie:** „Kapitel 1: Ein Held entsteht“ steht unter „Rune RPG: Regelwerk (Deutsch)“. Unter „Kampffertigkeiten“ usw. stehen die Fertigkeiten (zusammen 43).
2. **Verlinkung:** Öffne „Charakteristiken (Übersicht)“. Die Namen von Charakteristik und Schutzgott sind klickbare Verweise.
3. **Property Kit:** Unter „Property kits“ gibt es „Rune-Held“ mit rund 112 Properties (Abschnitte, Zahlen, Formeln).
4. **Ragnar:** Auf seiner Properties-Seite stehen die Formelwerte (z. B. Waffe1_INI 9, Absorption 6, Reaktion 5). `verify` prüft dasselbe automatisch.
5. **Kit anwenden:** Lege einen neuen Charakter an, wähle im Tab „Properties“ das Kit „Rune-Held“ und speichere. Die Properties erscheinen.
6. **Umlaute:** Rechnet z. B. `Absorption` korrekt, funktionieren Umlaute in Formeln (siehe unten, falls nicht).

## Wenn etwas nicht klappt

Der Pilot prüft diese Annahmen, die ich nicht vorab testen konnte (die Kanka-API ist von meiner Umgebung aus nicht erreichbar):

| Beobachtung | Mögliche Ursache | Was tun |
|---|---|---|
| Formeln zeigen `{Stärke}` oder bleiben Text | Umlaute in `{…}` werden nicht aufgelöst | **Neue** Testkampagne, Import mit `--ascii-names` (ä→ae, ö→oe, ü→ue, ß→ss) |
| Nur `Reaktion` rechnet nicht | `max()` nicht unterstützt (Kanka nennt nur `floor` und `ceil`) | Reaktion von Hand eintragen und mir Bescheid geben; ich ersetze die Formel |
| `Waffe…_FertWirksam` und Folgewerte falsch | Verkettete Verweise oder geschachtelte Klammern werden nicht aufgelöst | Bitte `verify`-Ausgabe schicken; ich vereinfache die Formel |
| Das Kit „Rune-Held“ hat keine Properties | Properties lassen sich auf Kits nicht über denselben Endpunkt setzen | Rückmeldung genügt; ich ändere den Weg |
| Verweise erscheinen als Text `[entity:…]` | Mention-Syntax weicht ab | Rückmeldung mit Beispiel |

`HTTP 422` bei einem Eintrag heißt, dass ein Feld abgelehnt wurde. Die Meldung steht in der Ausgabe, schick sie mir.

**Bereits geklärt:** `parent_id` erwartet die Entity-ID des Elternteils (im ersten Echtlauf per HTTP 422 gefunden, behoben).

## Bekannte Grenzen der Formeln

* **Bewegung:** rechnet 15 + 5 × Sprinten (richtig bis Sprinten 3; ab 4 gilt 30 + 10 je Punkt über 3).
* **Von Hand:** Trefferpunkte, Wundschwelle, Gesamtlast und Belastungsabzug sind Tabellenwerte und werden eingetragen (Tabellen stehen in den Notes „Trefferpunkte“, „Wundschwelle“, „Wichtige Zahlen und Formeln“).
* **Engagement** (für die Reaktion): ist als Auslegung umgesetzt (siehe Note „Übersetzungshinweise und Auffälligkeiten im Original“).
* Waffen sind im Pilot noch keine Items: Ihre Werte trägst du in den Waffenfeldern ein. Mit Kapitel 1 (Waffen/Rüstung) und Kapitel 4 werden sie später Items.

## Aktualisieren und Umbenennen

`python3 kanka_import.py import` gleicht die Daten in `data/` mit der Kampagne ab:

| Fall | Verhalten |
|---|---|
| Eintrag ist neu | wird angelegt |
| Eintrag hat sich in den Daten geändert (Name, Text, Tags, Properties …) | wird aktualisiert (1 Anfrage, plus 2 für die Properties) |
| Eintrag ist unverändert | wird übersprungen (0 Anfragen) |
| Property wurde umbenannt (`umbenennungen.json`) | die vorhandene Property wird **umbenannt**, nicht neu angelegt |
| Property steht in Kanka, aber nicht (mehr) in den Daten („verwaist“) | wird **gemeldet**, aber nicht gelöscht, außer mit `--prune` |

Optionen: `--update` erzwingt die Aktualisierung **aller** vorhandenen Einträge (auch unveränderter). `--no-update` legt nur Neues an und fasst Vorhandenes nie an. `--only <Schlüssel …>` beschränkt alles auf einzelne Einträge. `plan` zeigt vorher, was passieren würde (neu, zu aktualisieren, unverändert, Anfragen, Minuten).

* **Einmalig nach dem Wechsel auf diese Skriptversion:** Für bereits importierte Einträge ist noch keine Prüfsumme gespeichert, daher gelten sie alle als geändert und werden einmal vollständig synchronisiert (beim aktuellen Stand etwa 790 Anfragen, rund 32 Minuten). Danach kostet nur noch Geändertes Anfragen.
* **Umbenennungen von Properties:** In `umbenennungen.json` steht die Tabelle alt → neu. Dadurch behalten Kits, Beispielheld und Gegner ihre Werte, nur die Namen ändern sich. Benennst du später weitere Properties um, trägst du sie dort ein.
* **`--prune`** löscht Properties, die in den Daten nicht vorkommen. Das trifft auch Properties, die du selbst in Kanka angelegt hast. Erst `import` ohne `--prune` laufen lassen und die Meldung „verwaist“ lesen.
* Die internen Schlüssel der Einträge haben sich bei der Umbenennung nicht geändert; deshalb lässt sich eine bestehende Kampagne ohne Neuanlage aktualisieren. Wer es sauber möchte, importiert in eine frische Kampagne.

## Gruppenwerte der Gegner setzen

Die Gegner berechnen ihre Spielwerte aus den **Gruppenwerten deiner Helden** (Werte des Roll of Valor: der zweitschlechteste Wert jeder Spalte, Regeln in der Note „Spielwerte der Gegner berechnen“). Beim Import stehen **Beispielwerte** aus dem Regelbuch darin. Setze sie mit einem Aufruf für alle Gegner und das Kit:

```bash
python3 kanka_import.py gruppenwerte --init 10 --atk 12 --dfn 9 --dam 11 --abs 7 --hp 60 --res 4
```

Das sind etwa 64 Anfragen (3 Minuten). Wiederhole den Aufruf, wenn sich deine Gruppe verbessert. Die Beispielgegner aus dem Regelbeispiel bleiben unverändert (sie dienen der Prüfung mit `verify`). Die Bedrohungsstufe jedes Gegners stellst du in seinen Properties über **Bedrohung_Idx** ein (3 = schrecklich bis −3 = erbärmlich; Voreinstellung: ebenbürtig oder die maximale Stufe des Typs, falls niedriger).

## Umfang der Übersetzung

Übernommen werden die Einleitung und die Kapitel 1 bis 4 des Originals. Auf Wunsch entfallen „Recap: Designing Your Encounters“, „Quick ‘n’ Dirty Encounter Design“, Kapitel 5 bis 7, Anhang und Index. Die Kampagne hat dauerhaft einen Runner (Spielleiter), keinen Proxy, unbegrenzte Begegnungspunkte und Siegespunkte nach Ermessen. Entsprechende Regeln stehen als Referenz mit dem Tag „Referenz (Originalsystem, nicht angewandt)“.

## Was automatisch getestet wurde

* `selftest`: Struktur der Daten (eindeutige Schlüssel, Eltern vor Kindern, alle Verweise vorhanden, 43 Fertigkeiten) und **14 Formelwerte gegen die Beispielwerte des Buches** (Ragnar, S. 38–39).
* Der komplette Import wurde gegen den lokalen Nachbau getestet (Anlegen, Verlinken, Properties, Wiederaufnahme, `--update` ohne Dubletten, Rate-Limit, falscher Token, falsche Kampagne). **Das ersetzt nicht den Test gegen die echte Kanka-API.**
