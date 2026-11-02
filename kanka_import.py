#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rune RPG -> Kanka: Import der deutschen Regelinhalte per Kanka-API.

Befehle (import legt Neues an und aktualisiert Geändertes; Gelöschtes bleibt, außer mit --prune für Properties):
  selftest   Prüft Daten und rechnet die Property-Formeln lokal gegen die Buchwerte (Ragnar). Kein Netzwerk.
  plan       Zeigt, was angelegt würde, und schätzt die Laufzeit. Kein Netzwerk.
  import     Legt Tags, Einträge und Properties in Kanka an (nie löschen).
  verify     Liest die Beispielwerte (Ragnar, Beispielgegner) aus Kanka und vergleicht sie mit dem Buch.
  gruppenwerte  Setzt die Heldengruppen-Werte (Roll of Valor) in allen Gegnern: --init --atk --dfn --dam --abs --hp --res

Zugangsdaten (nie in Dateien oder Chats schreiben):
  KANKA_TOKEN         Persönliches Zugriffstoken (Kanka: Profil > API)
  KANKA_CAMPAIGN_ID   ID der (Test-)Kampagne
Nur Python 3.9+, keine weiteren Pakete.
"""
import argparse, glob, hashlib, json, math, os, re, sys, time, urllib.error, urllib.request
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://api.kanka.io/1.0"
ENDPOINT = {"note": "notes", "ability": "abilities", "character": "characters", "item": "items", "creature": "creatures", "race": "races",
            "property_kit": "attribute_templates", "tag": "tags"}
REF_RE = re.compile(r"\{\{ref:([^}|]+)(?:\|([^}]+))?\}\}")
BRACE_RE = re.compile(r"\{([^{}]+)\}")


# ------------------------------------------------------------------ Hilfsfunktionen
def ascii_name(s):
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


def data_files(args):
    """Standard: alle Dateien data/*.json in alphabetischer Reihenfolge (z. B. 00_..., 01_...)."""
    return args.data or sorted(glob.glob(os.path.join(HERE, "data", "*.json")))


def load_data(paths, ascii_names=False):
    """Lädt eine oder mehrere Datendateien und führt sie zusammen (Tags eindeutig, Einträge in Dateireihenfolge)."""
    if isinstance(paths, str):
        paths = [paths]
    data = {"meta": {}, "tags": [], "entities": []}
    tagkeys = set()
    for path in paths:
        part = json.load(open(path, encoding="utf-8"))
        data["meta"].setdefault("dateien", []).append(os.path.basename(path))
        for t in part.get("tags", []):
            if t["key"] not in tagkeys:
                tagkeys.add(t["key"]); data["tags"].append(t)
        data["entities"] += part["entities"]
    if ascii_names:
        for e in data["entities"]:
            for pr in e.get("properties", []):
                pr["name"] = ascii_name(pr["name"])
                pr["value"] = BRACE_RE.sub(lambda m: "{" + ascii_name(m.group(1)) + "}", pr["value"])
            if e.get("expected"):
                e["expected"] = {ascii_name(k): v for k, v in e["expected"].items()}
    return data


def read_token(args):
    tok = os.environ.get("KANKA_TOKEN", "").strip()
    if not tok and args.token_file:
        parts = open(args.token_file, encoding="utf-8").read().split()
        tok = max(parts, key=len) if parts else ""
    return tok


# ------------------------------------------------------------------ Formeln lokal rechnen
SAFE = re.compile(r"^[0-9a-z_\s+\-*/().,]*$")
FUNCS = {"floor": math.floor, "ceil": math.ceil, "max": max, "min": min}


def eval_props(props):
    """Rechnet alle Properties (Zahlen, Formeln) lokal aus. Gibt dict name->Zahl/None zurück."""
    raw = {p["name"]: p["value"] for p in props if p["type_id"] in (1, 6)}
    cache, stack = {}, []

    def val(name):
        if name in cache:
            return cache[name]
        if name not in raw:
            raise KeyError("Unbekannte Property in Formel: {%s}" % name)
        if name in stack:
            raise ValueError("Zirkelbezug: " + " -> ".join(stack + [name]))
        stack.append(name)
        expr = raw[name].strip()
        if expr == "":
            res = None
        else:
            sub = BRACE_RE.sub(lambda m: "(%s)" % val(m.group(1)), expr)
            names = set(re.findall(r"[a-z_]+", sub))
            if not names <= set(FUNCS) or not SAFE.match(sub):
                res = None          # Text, kein Rechenausdruck
            else:
                res = eval(sub, {"__builtins__": {}}, FUNCS)
        stack.pop()
        cache[name] = res
        return res

    return {n: val(n) for n in raw}


# ------------------------------------------------------------------ Selbsttest
def cmd_selftest(args):
    data = load_data(data_files(args), args.ascii_names)
    ents, errors = data["entities"], []
    keys = {t["key"] for t in data["tags"]}
    seen = set()
    for e in ents:
        if e["key"] in seen or e["key"] in keys:
            errors.append("Doppelter Schlüssel: %s (liegt in data/ noch eine alte oder doppelte Datei, z. B. pilot_held.json neben 00_pilot_held.json?)" % e["key"])
        seen.add(e["key"])
        if e.get("parent") and e["parent"] not in seen:
            errors.append("Elternteil kommt nach Kind (oder fehlt): %s -> %s" % (e["key"], e["parent"]))
    allkeys = seen
    for e in ents:
        for m in REF_RE.finditer(e["entry"]):
            if m.group(1) not in allkeys:
                errors.append("Unbekannter Verweis {{ref:%s}} in %s" % (m.group(1), e["key"]))
        for t in e["tags"]:
            if t not in keys:
                errors.append("Unbekannter Tag %s in %s" % (t, e["key"]))
    abil = [e for e in ents if e["kind"] == "ability" and e["key"].startswith("ab.") and not e["key"].startswith("ab.g.")]
    if abil:
        print("Fertigkeiten (ohne Gruppen): %d (erwartet 43)" % len(abil))
        if len(abil) != 43:
            errors.append("Anzahl Fertigkeiten != 43")
    for e in ents:
        if e.get("properties"):
            names = [p["name"] for p in e["properties"]]
            dup = {n for n in names if names.count(n) > 1 and n}
            if dup:
                errors.append("Doppelte Property-Namen in %s: %s" % (e["key"], sorted(dup)))
    checked = 0
    for e in ents:
        if not e.get("expected"):
            continue
        try:
            res = eval_props(e["properties"])
        except (KeyError, ValueError) as ex:
            errors.append("%s: %s" % (e["key"], ex))
            continue
        print("\nFormelprüfung %s (Buchwerte):" % e["name"])
        for name, exp in e["expected"].items():
            got = res.get(name)
            ok = got is not None and abs(got - exp) < 1e-9
            checked += 1
            print("  %-16s erwartet %-4s berechnet %-6s %s" % (name, exp, got, "OK" if ok else "FEHLER"))
            if not ok:
                errors.append("%s: %s erwartet %s, berechnet %s" % (e["key"], name, exp, got))
    # Formel-Referenzen im Kit
    kits = [e for e in ents if e["kind"] == "property_kit"]
    for kit in kits:
        kn = {p["name"] for p in kit["properties"]}
        for p in kit["properties"]:
            for m in BRACE_RE.finditer(p["value"]):
                if m.group(1) not in kn:
                    errors.append("Kit %s: {%s} in %s nicht definiert" % (kit["key"], m.group(1), p["name"]))
    print("\nDateien: %s" % ", ".join(data["meta"].get("dateien", [])))
    print("Einträge: %d, Tags: %d, Kits: %d, geprüfte Buchwerte: %d" % (len(ents), len(data["tags"]), len(kits), checked))
    if errors:
        print("\nFEHLER:")
        for x in errors:
            print(" -", x)
        return 1
    print("Selbsttest bestanden.")
    return 0


# ------------------------------------------------------------------ Plan
def ehash(e):
    """Prüfsumme des Soll-Inhalts eines Eintrags (zur Erkennung von Änderungen)."""
    core = {k: e.get(k) for k in ("kind", "name", "type", "parent", "tags", "entry", "properties")}
    return hashlib.sha1(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def load_renames():
    """Property-Umbenennungen (alt -> neu) aus umbenennungen.json. Damit werden vorhandene Properties umbenannt statt neu angelegt."""
    path = os.path.join(HERE, "umbenennungen.json")
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8")).get("properties", {})


def classify(data, mapping, args):
    """Teilt die Einträge in neu / geändert / unverändert (nach Zuordnungsdatei und Prüfsumme)."""
    new, changed, same = [], [], []
    for e in data["entities"]:
        if args.only and e["key"] not in args.only:
            continue
        rec = mapping.get(e["key"])
        if rec is None:
            new.append(e)
        elif args.update or (not args.no_update and rec.get("hash") != ehash(e)):
            changed.append(e)
        else:
            same.append(e)
    return new, changed, same


def plan_counts(data, mapping=None, args=None):
    """Zählt Anfragen. Pass 2 (Verlinkung) ist nur nötig, wenn ein Verweis beim Anlegen noch nicht bekannt ist.
    Rückgabe: Tags, Anlegen, Verlinken, Properties (neu), Aktualisieren, Properties (Aktualisieren, je 2 Anfragen), unverändert."""
    mapping = mapping or {}
    known = set(mapping) | {t["key"] for t in data["tags"]}
    n_tags = sum(1 for t in data["tags"] if t["key"] not in mapping)
    if args is None:
        args = argparse.Namespace(only=None, update=False, no_update=False)
    new, changed, same = classify(data, mapping, args)
    n_ph2 = n_props = 0
    for e in new:
        if e.get("properties"):
            n_props += 1
        if any(m.group(1) not in known for m in REF_RE.finditer(e["entry"])):
            n_ph2 += 1
        known.add(e["key"])
    n_upd_props = sum(1 for e in changed if e.get("properties"))
    return n_tags, len(new), n_ph2, n_props, len(changed), n_upd_props, len(same)


def cmd_plan(args):
    data = load_data(data_files(args), args.ascii_names)
    cid = (args.campaign or os.environ.get("KANKA_CAMPAIGN_ID", "")).strip()
    mapping = {}
    mp_path = args.map or os.path.join(HERE, "kanka_map_%s.json" % cid)
    if cid and os.path.exists(mp_path):
        mapping = json.load(open(mp_path, encoding="utf-8")).get("items", {})
        print("Zuordnungsdatei gefunden: %d Einträge sind schon in Kampagne %s." % (len(mapping), cid))
    n_tags, n_create, n_ph2, n_props, n_upd, n_upd_props, n_same = plan_counts(data, mapping, args)
    total = n_tags + n_create + n_ph2 + n_props + n_upd + 2 * n_upd_props
    print("Dateien: %s" % ", ".join(data["meta"].get("dateien", [])))
    print("Geplante Anfragen:")
    print("  Tags anlegen:                 %d" % n_tags)
    print("  Neue Einträge anlegen:        %d" % n_create)
    print("  Verlinkungen (Pass 2):        %d" % n_ph2)
    print("  Properties neuer Einträge:    %d" % n_props)
    print("  Geänderte Einträge aktualisieren: %d (Properties dazu: %d × 2 Anfragen)" % (n_upd, n_upd_props))
    print("  Unverändert (übersprungen):   %d" % n_same)
    print("  Summe:                        %d Anfragen, bei %d/min etwa %.0f Minuten" % (total, args.rpm, total / args.rpm))
    if args.show:
        e = next((x for x in data["entities"] if x["key"] == args.show), None)
        if not e:
            print("Schlüssel nicht gefunden:", args.show); return 1
        print("\n--- %s (%s) ---" % (e["key"], e["kind"]))
        print("name:", e["name"], "| type:", e["type"], "| parent:", e["parent"], "| tags:", e["tags"])
        print("entry (Pass 1):\n", REF_RE.sub(lambda m: m.group(2) or key_name(data, m.group(1)), e["entry"])[:1500])
        if e.get("properties"):
            print("\nProperties (%d):" % len(e["properties"]))
            for p in e["properties"][:25]:
                print("  [%s] %s = %s" % (p["type_id"], p["name"], p["value"]))
    return 0


def key_name(data, key):
    for e in data["entities"]:
        if e["key"] == key:
            return e["name"]
    return key


# ------------------------------------------------------------------ API
class ApiError(Exception):
    pass


class Api:
    def __init__(self, token, campaign, base, rpm):
        self.token, self.cid, self.base, self.rpm = token, campaign, base.rstrip("/"), rpm
        self.times, self.count = deque(), 0

    def _throttle(self):
        now = time.time()
        while self.times and now - self.times[0] > 60:
            self.times.popleft()
        if len(self.times) >= self.rpm:
            wait = 60 - (now - self.times[0]) + 0.5
            if wait > 0:
                time.sleep(wait)
        self.times.append(time.time())

    def call(self, method, path, body=None, retries=5):
        url = "%s/campaigns/%s/%s" % (self.base, self.cid, path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(retries):
            self._throttle()
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": "Bearer " + self.token, "Accept": "application/json",
                "Content-Type": "application/json", "User-Agent": "rune-kanka-import/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self.count += 1
                    txt = r.read().decode("utf-8")
                    return json.loads(txt) if txt.strip() else {}
            except urllib.error.HTTPError as ex:
                msg = ex.read().decode("utf-8", errors="replace")[:600]
                if ex.code == 429:
                    wait = int(ex.headers.get("Retry-After", "65") or 65)
                    print("  Rate-Limit (429), warte %ds ..." % wait, flush=True)
                    time.sleep(wait + 1)
                    continue
                if ex.code >= 500:
                    print("  Serverfehler %d, neuer Versuch ..." % ex.code, flush=True)
                    time.sleep(5 * (attempt + 1))
                    continue
                raise ApiError("%s %s -> HTTP %d: %s" % (method, path, ex.code, msg.replace(self.token, "***")))
            except urllib.error.URLError as ex:
                print("  Netzwerkfehler (%s), neuer Versuch ..." % ex.reason, flush=True)
                time.sleep(5 * (attempt + 1))
        raise ApiError("%s %s: zu viele Fehlversuche" % (method, path))


# ------------------------------------------------------------------ Import
def render(entry, data, mapping, final):
    def sub(m):
        key, alias = m.group(1), m.group(2)
        if final and key in mapping:
            return "[entity:%s%s]" % (mapping[key]["entity_id"], "|" + alias if alias else "")
        return alias or key_name(data, key)
    return REF_RE.sub(sub, entry)


def all_refs_known(entry, mapping):
    return all(m.group(1) in mapping for m in REF_RE.finditer(entry))


def get_credentials(args):
    """Liest Token und Kampagnen-ID und sagt genau, was fehlt. Gibt (token, cid) oder None zurück."""
    token = read_token(args)
    cid = (args.campaign or os.environ.get("KANKA_CAMPAIGN_ID", "")).strip().strip('"').strip("'")
    missing = []
    if not token:
        missing.append("Token (KANKA_TOKEN oder --token-file)")
    if not cid:
        missing.append("Kampagnen-ID (KANKA_CAMPAIGN_ID oder --campaign)")
    if missing:
        print("Es fehlt: " + " und ".join(missing) + ".")
        print("Gefundene KANKA-Variablen in diesem Fenster: %s" % (", ".join(sorted(k for k in os.environ if k.upper().startswith("KANKA"))) or "keine"))
        print("Hinweis: $env:-Variablen gelten nur im selben PowerShell-Fenster, in dem sie gesetzt wurden.")
        print("Alternativ ohne Variablen:  python kanka_import.py import --campaign 12345 --token-file C:\\Pfad\\token.txt")
        return None
    if not cid.isdigit():
        print("Die Kampagnen-ID muss eine Zahl sein (aus der Adresse app.kanka.io/w/<ID>/...), gefunden: %r" % cid)
        return None
    return token, cid


def cmd_import(args):
    creds = get_credentials(args)
    if not creds:
        return 2
    token, cid = creds
    data = load_data(data_files(args), args.ascii_names)
    if cmd_selftest_quiet(data):
        print("Selbsttest fehlgeschlagen, bitte zuerst `selftest` ausführen."); return 2
    map_path = args.map or os.path.join(HERE, "kanka_map_%s.json" % cid)
    state = json.load(open(map_path, encoding="utf-8")) if os.path.exists(map_path) else {"campaign": cid, "items": {}}
    if str(state.get("campaign")) != str(cid):
        print("Die Zuordnungsdatei gehört zu einer anderen Kampagne. Abbruch."); return 2
    mp = state["items"]
    api = Api(token, cid, args.base_url, args.rpm)

    def save():
        json.dump(state, open(map_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n_tags, n_create, n_ph2, n_props, n_upd, n_upd_props, n_same = plan_counts(data, mp, args)
    total = n_tags + n_create + n_ph2 + n_props + n_upd + 2 * n_upd_props
    print("Kampagne %s: %d neu, %d zu aktualisieren, %d unverändert." % (cid, n_create, n_upd, n_same))
    print("Ca. %d Anfragen, etwa %.0f Minuten bei %d/min." % (total, total / args.rpm, args.rpm))
    if not args.yes:
        if input("Fortfahren? (ja/nein) ").strip().lower() not in ("ja", "j", "y", "yes"):
            print("Abgebrochen."); return 0

    try:
        # 1) Tags
        for t in data["tags"]:
            if t["key"] in mp:
                continue
            r = api.call("POST", "tags", {"name": t["name"]})["data"]
            mp[t["key"]] = {"id": r["id"], "entity_id": r.get("entity_id"), "kind": "tag"}
            save(); print("Tag:", t["name"], flush=True)

        # 2) Einträge (Pass 1)
        new_e, changed_e, _same = classify(data, mp, args)
        todo = {e["key"] for e in new_e + changed_e}
        touched, phase2 = [], []
        for e in data["entities"]:
            if e["key"] not in todo:
                continue
            exists = e["key"] in mp
            final = all_refs_known(e["entry"], mp)
            payload = {"name": e["name"], "entry": render(e["entry"], data, mp, final)}
            if e.get("type"): payload["type"] = e["type"]
            if e["kind"] in ("note", "ability") and e.get("parent"):
                payload["parent_id"] = mp[e["parent"]]["entity_id"]   # Kanka erwartet die Entity-ID des Elternteils
            if e["kind"] != "property_kit":
                payload["tags"] = [mp[t]["id"] for t in e["tags"]]
            ep = ENDPOINT[e["kind"]]
            if exists:
                api.call("PUT", "%s/%s" % (ep, mp[e["key"]]["id"]), payload)
                print("Aktualisiert:", e["name"], flush=True)
            else:
                r = api.call("POST", ep, payload)["data"]
                mp[e["key"]] = {"id": r["id"], "entity_id": r.get("entity_id"), "kind": e["kind"]}
                save(); print("Angelegt:", e["name"], flush=True)
            touched.append((e, exists))
            if REF_RE.search(e["entry"]) and not final:
                phase2.append(e)

        # 3) Verlinkungen (Pass 2)
        for e in phase2:
            api.call("PATCH", "%s/%s" % (ENDPOINT[e["kind"]], mp[e["key"]]["id"]),
                     {"entry": render(e["entry"], data, mp, True)})
            print("Verlinkt:", e["name"], flush=True)

        # 4) Properties (mit Umbenennen vorhandener Properties) und Prüfsumme
        renames = load_renames()
        reverse = {}
        for old_n, new_n in renames.items():
            reverse.setdefault(new_n, []).append(old_n)
        orphans_total, orphan_entries = 0, 0
        for e, exists in touched:
            props = e.get("properties")
            if props:
                eid = mp[e["key"]]["entity_id"]
                existing = {}
                if exists:
                    for a in api.call("GET", "entities/%s/attributes" % eid).get("data", []):
                        existing[a["name"]] = a["id"]
                used, attrs, renamed = set(), [], 0
                for i, pr in enumerate(props):
                    a = {"name": pr["name"], "value": pr["value"], "type_id": pr["type_id"], "default_order": i,
                         "is_private": False, "is_pinned": bool(pr.get("is_pinned"))}
                    if pr["name"] in existing:
                        a["id"] = existing[pr["name"]]; used.add(pr["name"])
                    else:
                        for old_n in reverse.get(pr["name"], []):
                            if old_n in existing and old_n not in used:
                                a["id"] = existing[old_n]; used.add(old_n); renamed += 1   # alte Property wird umbenannt
                                break
                    attrs.append(a)
                api.call("PATCH", "entities/%s/attributes" % eid, {"attribute": attrs})
                print("Properties (%d%s): %s" % (len(attrs), ", %d umbenannt" % renamed if renamed else "", e["name"]), flush=True)
                orphans = [n for n in existing if n not in used and n not in {a["name"] for a in attrs}]
                if orphans:
                    orphans_total += len(orphans); orphan_entries += 1
                    if args.prune:
                        for n in orphans:
                            api.call("DELETE", "entities/%s/attributes/%s" % (eid, existing[n]))
                        print("   gelöscht (verwaist): %s" % ", ".join(orphans[:8]) + (" …" if len(orphans) > 8 else ""), flush=True)
                    else:
                        print("   verwaist (nicht in den Daten): %s" % ", ".join(orphans[:8]) + (" …" if len(orphans) > 8 else ""), flush=True)
            mp[e["key"]]["hash"] = ehash(e)
            save()
        if orphans_total and not args.prune:
            print("\nHinweis: %d verwaiste Properties in %d Einträgen (nicht in den Daten). Mit --prune werden sie gelöscht; "
                  "eigene Properties, die du selbst in Kanka angelegt hast, würden dabei ebenfalls gelöscht." % (orphans_total, orphan_entries))
    except ApiError as ex:
        save()
        print("\nABBRUCH:", ex)
        print("Der Stand ist in %s gesichert; ein erneuter Aufruf macht dort weiter." % map_path)
        return 1
    save()
    print("\nFertig. %d Anfragen gesendet. Nächster Schritt: `verify`." % api.count)
    return 0


def cmd_selftest_quiet(data):
    import io, contextlib, tempfile
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp, ensure_ascii=False); tmp.close()
    ns = argparse.Namespace(data=[tmp.name], ascii_names=False)
    with contextlib.redirect_stdout(io.StringIO()):
        rc = cmd_selftest(ns)
    os.unlink(tmp.name)
    return rc


# ------------------------------------------------------------------ Verify
def cmd_verify(args):
    creds = get_credentials(args)
    if not creds:
        return 2
    token, cid = creds
    data = load_data(data_files(args), args.ascii_names)
    map_path = args.map or os.path.join(HERE, "kanka_map_%s.json" % cid)
    if not os.path.exists(map_path):
        print("Keine Zuordnungsdatei gefunden:", map_path); return 2
    mp = json.load(open(map_path, encoding="utf-8"))["items"]
    api = Api(token, cid, args.base_url, args.rpm)
    bad = 0
    for e in data["entities"]:
        if not e.get("expected") or e.get("local_only") or e["key"] not in mp:
            continue
        attrs = {a["name"]: a for a in api.call("GET", "entities/%s/attributes" % mp[e["key"]]["entity_id"]).get("data", [])}
        print("\nPrüfung %s (Kanka-Werte gegen Buch):" % e["name"])
        for name, exp in e["expected"].items():
            a = attrs.get(name)
            got = (a.get("parsed") if a and a.get("parsed") not in (None, "") else (a or {}).get("value"))
            try:
                ok = abs(float(str(got).strip()) - exp) < 1e-9
            except (ValueError, TypeError):
                ok = False
            bad += 0 if ok else 1
            print("  %-16s Buch %-4s Kanka %-14s %s" % (name, exp, got, "OK" if ok else "ABWEICHUNG"))
    if bad:
        print("\n%d Abweichung(en). Hinweise: Rechnet Kanka Formeln nicht, siehe README (Abschnitt „Wenn Formeln nicht rechnen“)." % bad)
        return 1
    print("\nAlle geprüften Werte stimmen mit dem Buch überein.")
    return 0


# ------------------------------------------------------------------ Gruppenwerte setzen
GRP_NAMES = [("G_INIT", "init"), ("G_ATK", "atk"), ("G_DFN", "dfn"), ("G_DAM", "dam"), ("G_ABS", "abs"), ("G_HP", "hp"), ("G_RES", "res")]


def cmd_gruppenwerte(args):
    """Setzt die Gruppenwerte (Roll of Valor) in allen Gegnern und im Kit „Rune-Gegner“ auf die Werte deiner Heldengruppe."""
    vals = {n: getattr(args, a) for n, a in GRP_NAMES}
    if any(v is None for v in vals.values()):
        print("Bitte alle sieben Werte angeben: --init --atk --dfn --dam --abs --hp --res"); return 2
    creds = get_credentials(args)
    if not creds:
        return 2
    token, cid = creds
    data = load_data(data_files(args), args.ascii_names)
    map_path = args.map or os.path.join(HERE, "kanka_map_%s.json" % cid)
    if not os.path.exists(map_path):
        print("Keine Zuordnungsdatei gefunden:", map_path); return 2
    mp = json.load(open(map_path, encoding="utf-8"))["items"]
    targets = [e for e in data["entities"] if e.get("properties") and e["key"] in mp and not e["key"].startswith("ex.")
               and any(pr["name"] == "G_INIT" for pr in e["properties"])]
    print("Setze Gruppenwerte %s in %d Einträgen (%d Anfragen, etwa %.0f Minuten)." % (vals, len(targets), 2 * len(targets), 2 * len(targets) / args.rpm))
    if not args.yes and input("Fortfahren? (ja/nein) ").strip().lower() not in ("ja", "j", "y", "yes"):
        print("Abgebrochen."); return 0
    api = Api(token, cid, args.base_url, args.rpm)
    try:
        for e in targets:
            eid = mp[e["key"]]["entity_id"]
            ids = {a["name"]: a["id"] for a in api.call("GET", "entities/%s/attributes" % eid).get("data", [])}
            attrs = [{"id": ids[n], "name": n, "value": str(v), "type_id": 6} for n, v in vals.items() if n in ids]
            api.call("PATCH", "entities/%s/attributes" % eid, {"attribute": attrs})
            print("Gruppenwerte gesetzt:", e["name"], flush=True)
    except ApiError as ex:
        print("\nABBRUCH:", ex); return 1
    print("\nFertig. %d Anfragen gesendet." % api.count)
    return 0


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["selftest", "plan", "import", "verify", "gruppenwerte"])
    ap.add_argument("--data", nargs="+", help="Datendatei(en) (JSON); Standard: alle Dateien in data/")
    ap.add_argument("--campaign", help="Kampagnen-ID (sonst KANKA_CAMPAIGN_ID)")
    ap.add_argument("--token-file", help="Datei mit dem Token (sonst KANKA_TOKEN)")
    ap.add_argument("--rpm", type=int, default=25, help="Anfragen pro Minute (Free: max. 30, Subscriber: max. 90)")
    ap.add_argument("--ascii-names", action="store_true", help="Umlaute in Property-Namen ersetzen (ä→ae, ö→oe, ü→ue, ß→ss)")
    ap.add_argument("--update", action="store_true", help="import: ALLE vorhandenen Einträge erzwungen aktualisieren (sonst nur geänderte)")
    ap.add_argument("--no-update", dest="no_update", action="store_true", help="import: nur neue Einträge anlegen, vorhandene nie anfassen")
    ap.add_argument("--prune", action="store_true", help="import: Properties löschen, die in Kanka stehen, aber nicht in den Daten (Vorsicht bei eigenen Properties)")
    ap.add_argument("--yes", action="store_true", help="Rückfrage vor dem Import überspringen")
    ap.add_argument("--map", help="Pfad der Zuordnungsdatei")
    ap.add_argument("--only", nargs="+", help="import: nur diese Schlüssel bearbeiten (z. B. mit --update einzelne Einträge aktualisieren)")
    ap.add_argument("--base-url", default=BASE_URL, help="API-Basis-URL (nur für Tests ändern)")
    ap.add_argument("--show", help="plan: Schlüssel eines Eintrags im Detail anzeigen")
    for _n, _a in GRP_NAMES:
        ap.add_argument("--" + _a, type=int, help="gruppenwerte: Gruppenwert " + _n)
    a = ap.parse_args()
    sys.exit({"selftest": cmd_selftest, "plan": cmd_plan, "import": cmd_import, "verify": cmd_verify, "gruppenwerte": cmd_gruppenwerte}[a.command](a))


if __name__ == "__main__":
    main()
