#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rune RPG -> Kanka: Import der deutschen Regelinhalte per Kanka-API.

Befehle (import legt Neues an und aktualisiert Geändertes; Gelöschtes bleibt, außer mit --prune für Properties):
  selftest   Prüft Daten und rechnet die Property-Formeln lokal gegen die Buchwerte (Ragnar). Kein Netzwerk.
  plan       Zeigt, was angelegt würde, und schätzt die Laufzeit. Kein Netzwerk.
  import     Legt Tags, Einträge und Properties in Kanka an (nie löschen).
  verify     Liest die Beispielwerte (Ragnar, Beispielgegner) aus Kanka und vergleicht sie mit dem Buch.
  pull       Liest Änderungen aus Kanka (Texte, neue und gelöschte Einträge) und führt sie mit den Datendateien zusammen (Bericht; mit --apply schreiben).
  gruppenwerte  Setzt die Heldengruppen-Werte (Roll of Valor) in allen Gegnern: --init --atk --dfn --dam --abs --hp --res

Zugangsdaten (nie in Dateien oder Chats schreiben):
  KANKA_TOKEN         Persönliches Zugriffstoken (Kanka: Profil > API)
  KANKA_CAMPAIGN_ID   ID der (Test-)Kampagne
Nur Python 3.9+, keine weiteren Pakete.
"""
import argparse, datetime, difflib, glob, hashlib, html as htmllib, json, math, os, re, shutil, sys, time, unicodedata, urllib.error, urllib.request
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://api.kanka.io/1.0"
ENDPOINT = {"note": "notes", "ability": "abilities", "character": "characters", "item": "items", "creature": "creatures", "race": "races", "location": "locations", "organisation": "organisations",
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
    data = {"meta": {}, "tags": [], "entities": [], "relations": [], "members": []}
    tagkeys = set()
    for path in paths:
        part = json.load(open(path, encoding="utf-8"))
        if not isinstance(part, dict) or "entities" not in part:
            print("Hinweis: %s enthält keine Einträge (\"entities\") und wird übersprungen. "
                  "Gehört sie nicht in data\\? (umbenennungen.json liegt neben dem Skript.)" % os.path.basename(path))
            continue
        data["meta"].setdefault("dateien", []).append(os.path.basename(path))
        for t in part.get("tags", []):
            if t["key"] not in tagkeys:
                tagkeys.add(t["key"]); data["tags"].append(t)
        for _e in part["entities"]:
            _e["_file"] = path
        data["entities"] += part["entities"]
        data["relations"] += part.get("relations", [])
        data["members"] += part.get("members", [])
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
        for fld in ("races", "locations"):
            for k in e.get(fld, []):
                if k not in allkeys:
                    errors.append("Unbekannter Schlüssel %s in %s.%s" % (k, e["key"], fld))
    seen_rel = set()
    for r in data.get("relations", []):
        for side in ("from", "to"):
            if r[side] not in allkeys:
                errors.append("Verbindung mit unbekanntem Schlüssel (%s): %s" % (side, r[side]))
        rk = (r["from"], r["relation"], r["to"])
        if rk in seen_rel:
            errors.append("Doppelte Verbindung: %s -> %s (%s)" % (r["from"], r["to"], r["relation"]))
        seen_rel.add(rk)
    for m in data.get("members", []):
        for side in ("organisation", "character"):
            if m[side] not in allkeys:
                errors.append("Mitglied mit unbekanntem Schlüssel (%s): %s" % (side, m[side]))
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
    for k in ("title", "races", "locations"):
        if e.get(k):
            core[k] = e[k]
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
        if rec is not None and rec.get("remote_deleted") and not args.update:
            same.append(e)      # in Kanka gelöscht (siehe pull); wird nicht neu angelegt oder aktualisiert
        elif rec is None:
            new.append(e)
        elif args.update or (not args.no_update and rec.get("hash") != ehash(e)):
            changed.append(e)
        else:
            same.append(e)
    return new, changed, same


def pending_links(data, state):
    """Noch nicht angelegte Verbindungen (gruppiert je Besitzer und Text) und Mitglieder."""
    rel_state = (state or {}).get("relations", {})
    mem_state = (state or {}).get("members", {})
    groups = {}
    for r in data.get("relations", []):
        if "%s|%s|%s" % (r["from"], r["relation"], r["to"]) in rel_state:
            continue
        groups.setdefault((r["from"], r["relation"], r.get("attitude")), []).append(r["to"])
    members = [m for m in data.get("members", []) if "%s|%s" % (m["organisation"], m["character"]) not in mem_state]
    return groups, members


def plan_counts(data, mapping=None, args=None, state=None):
    """Zählt Anfragen. Pass 2 (Verlinkung) ist nur nötig, wenn ein Verweis beim Anlegen noch nicht bekannt ist.
    Rückgabe: Tags, Anlegen, Verlinken, Properties (neu), Aktualisieren, Properties (Aktualisieren, je 2 Anfragen), unverändert,
    Verbindungs-Anfragen (gebündelt), Mitglieder-Anfragen."""
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
    groups, members = pending_links(data, state)
    return n_tags, len(new), n_ph2, n_props, len(changed), n_upd_props, len(same), len(groups), len(members)


def cmd_plan(args):
    data = load_data(data_files(args), args.ascii_names)
    cid = (args.campaign or os.environ.get("KANKA_CAMPAIGN_ID", "")).strip()
    mapping, pstate = {}, {}
    mp_path = args.map or os.path.join(HERE, "kanka_map_%s.json" % cid)
    if cid and os.path.exists(mp_path):
        pstate = json.load(open(mp_path, encoding="utf-8"))
        mapping = pstate.get("items", {})
        print("Zuordnungsdatei gefunden: %d Einträge sind schon in Kampagne %s." % (len(mapping), cid))
    n_tags, n_create, n_ph2, n_props, n_upd, n_upd_props, n_same, n_rel, n_mem = plan_counts(data, mapping, args, pstate)
    total = n_tags + n_create + n_ph2 + n_props + n_upd + 2 * n_upd_props + n_rel + n_mem
    print("Dateien: %s" % ", ".join(data["meta"].get("dateien", [])))
    print("Geplante Anfragen:")
    print("  Tags anlegen:                 %d" % n_tags)
    print("  Neue Einträge anlegen:        %d" % n_create)
    print("  Verlinkungen (Pass 2):        %d" % n_ph2)
    print("  Properties neuer Einträge:    %d" % n_props)
    print("  Geänderte Einträge aktualisieren: %d (Properties dazu: %d × 2 Anfragen)" % (n_upd, n_upd_props))
    print("  Unverändert (übersprungen):   %d" % n_same)
    print("  Verbindungen (gebündelt):     %d Anfragen" % n_rel)
    print("  Mitglieder (Organisationen):  %d" % n_mem)
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

    n_tags, n_create, n_ph2, n_props, n_upd, n_upd_props, n_same, n_rel, n_mem = plan_counts(data, mp, args, state)
    total = n_tags + n_create + n_ph2 + n_props + n_upd + 2 * n_upd_props + n_rel + n_mem
    print("Kampagne %s: %d neu, %d zu aktualisieren, %d unverändert; Verbindungen: %d Anfragen, Mitglieder: %d." % (cid, n_create, n_upd, n_same, n_rel, n_mem))
    print("Ca. %d Anfragen, etwa %.0f Minuten bei %d/min." % (total, total / args.rpm, args.rpm))
    if not args.yes:
        if input("Fortfahren? (ja/nein) ").strip().lower() not in ("ja", "j", "y", "yes"):
            print("Abgebrochen."); return 0

    def parent_id(e):
        mode = state.get("parent_mode", {}).get(e["kind"], "entity_id")
        return mp[e["parent"]]["entity_id" if mode == "entity_id" else "id"]

    def link_fields(e, mode):
        out = {}
        for fld in ("races", "locations"):
            if e.get(fld):
                out[fld] = [mp[k]["id" if mode == "id" else "entity_id"] for k in e[fld]]
        return out

    def send(method, path, payload, e):
        """Sendet einen Eintrag; bei 422 wegen races/locations oder parent_id wird die jeweils andere ID-Art versucht."""
        try:
            return api.call(method, path, payload)
        except ApiError as ex:
            msg = str(ex)
            if method == "PUT" and "404" in msg:
                return None      # Eintrag wurde in Kanka gelöscht
            if "422" not in msg:
                raise
            if (e.get("races") or e.get("locations")) and ("races" in msg or "locations" in msg) and state.get("link_mode", "id") == "id":
                state["link_mode"] = "entity_id"
                payload.update(link_fields(e, "entity_id"))
                print("  Hinweis: races/locations erwarten offenbar Entity-IDs; wechsle und versuche es erneut.", flush=True)
                save()
                return api.call(method, path, payload)
            modes = state.setdefault("parent_mode", {})
            if e.get("parent") and "parent_id" in msg and modes.get(e["kind"], "entity_id") == "entity_id":
                modes[e["kind"]] = "id"
                payload["parent_id"] = parent_id(e)
                print("  Hinweis: parent_id erwartet bei %s offenbar die Objekt-ID; wechsle und versuche es erneut." % e["kind"], flush=True)
                save()
                return api.call(method, path, payload)
            raise

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
            if e.get("title"): payload["title"] = e["title"]
            if e["kind"] in ("note", "ability", "location") and e.get("parent"):
                payload["parent_id"] = parent_id(e)   # Kanka erwartet die Entity-ID des Elternteils
            if e["kind"] != "property_kit":
                payload["tags"] = [mp[t]["id"] for t in e["tags"]]
            payload.update(link_fields(e, state.get("link_mode", "id")))
            ep = ENDPOINT[e["kind"]]
            if exists:
                if send("PUT", "%s/%s" % (ep, mp[e["key"]]["id"]), payload, e) is None:
                    mp[e["key"]]["remote_deleted"] = True
                    save(); print("In Kanka gelöscht, übersprungen:", e["name"], "(mit `pull --drop-deleted` aus den Daten entfernen)", flush=True)
                    continue
                print("Aktualisiert:", e["name"], flush=True)
            else:
                r = send("POST", ep, payload, e)["data"]
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
        # 5) Verbindungen (gebündelt je Besitzer und Text) und Mitglieder von Organisationen
        groups, members = pending_links(data, state)
        rel_state = state.setdefault("relations", {})
        mem_state = state.setdefault("members", {})
        for (frm, text, att), tos in groups.items():
            owner = mp[frm]["entity_id"]
            tids = [mp[t]["entity_id"] for t in tos]
            body = {"relation": text, "owner_id": owner}
            if att is not None:
                body["attitude"] = att
            if len(tids) == 1:
                body["target_id"] = tids[0]
            else:
                body["targets"] = tids
            resp = api.call("POST", "entities/%s/relations" % owner, body)
            rdata = resp.get("data", resp) if isinstance(resp, dict) else resp
            by_target = {}
            if isinstance(rdata, list):
                by_target = {x.get("target_id"): x.get("id") for x in rdata if isinstance(x, dict)}
            elif isinstance(rdata, dict) and "id" in rdata:
                by_target = {rdata.get("target_id"): rdata["id"]}
            for t, tid in zip(tos, tids):
                rel_state["%s|%s|%s" % (frm, text, t)] = by_target.get(tid, True)
            save()
            print("Verbindung: %s -[%s]-> %d Ziel(e)" % (key_name(data, frm), text, len(tos)), flush=True)
        for m in members:
            oid, cidx = mp[m["organisation"]]["id"], mp[m["character"]]["id"]
            r = api.call("POST", "organisations/%s/organisation_members" % oid,
                         {"organisation_id": oid, "character_id": cidx, "role": m.get("role", "")})
            rd = r.get("data", r) if isinstance(r, dict) else {}
            mem_state["%s|%s" % (m["organisation"], m["character"])] = rd.get("id", True) if isinstance(rd, dict) else True
            save()
            print("Mitglied: %s in %s (%s)" % (key_name(data, m["character"]), key_name(data, m["organisation"]), m.get("role", "")), flush=True)
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


# ------------------------------------------------------------------ Pull: Änderungen aus Kanka zurückholen
PULL_KINDS = [("tag", "tags"), ("race", "races"), ("location", "locations"), ("organisation", "organisations"), ("character", "characters"),
              ("note", "notes"), ("ability", "abilities"), ("item", "items"), ("creature", "creatures"), ("property_kit", "attribute_templates")]
PARENT_FIELDS = {"location": ("parent_id", "parent_location_id", "location_id"), "note": ("parent_id", "note_id"), "ability": ("parent_id", "ability_id"),
                 "race": ("parent_id", "race_id"), "organisation": ("parent_id", "organisation_id"), "item": ("parent_id", "item_id"),
                 "creature": ("parent_id", "creature_id"), "character": (), "property_kit": ()}
ENT_RAW = re.compile(r"\[entity:(\d+)(?:\|([^\]]*))?\]")
A_TAG = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S)


def slugify(s):
    s = s.replace("Æ", "Ae").replace("æ", "ae").replace("Ð", "D").replace("ð", "d").replace("Þ", "Th").replace("þ", "th")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "eintrag"


def fetch_all(api, ep):
    out, page = [], 1
    while True:
        r = api.call("GET", "%s?page=%d" % (ep, page))
        out += r.get("data", [])
        last = (r.get("meta") or {}).get("last_page", 1)
        if page >= last or not r.get("data"):
            break
        page += 1
    return out


def mentions_to_refs(text, ent2key, key2name):
    """Kanka-Verweise ([entity:ID|Alias] oder <a>-Links auf Entities) in unsere {{ref:schlüssel|Alias}} zurückrechnen."""
    text = text or ""

    def ref(k, label):
        if label and label != key2name.get(k):
            return "{{ref:%s|%s}}" % (k, label)
        return "{{ref:%s}}" % k

    def raw(m):
        k = ent2key.get(int(m.group(1)))
        return ref(k, (m.group(2) or "").strip()) if k else m.group(0)

    def anchor(m):
        attrs = m.group(1)
        mm = re.search(r"\[entity:(\d+)", attrs) or re.search(r'data-entity-id="(\d+)"', attrs) or re.search(r"/entities/(\d+)", attrs)
        k = ent2key.get(int(mm.group(1))) if mm else None
        return ref(k, re.sub(r"<[^>]+>", "", m.group(2)).strip()) if k else m.group(0)

    return A_TAG.sub(anchor, ENT_RAW.sub(raw, text)).strip()


def canon(text):
    """Vergleichsform: Verweise ohne Alias, Entities aufgelöst, Leerraum vereinheitlicht."""
    t = re.sub(r"\{\{ref:([^}|]+)(?:\|[^}]*)?\}\}", lambda m: "@@%s@@" % m.group(1), text or "")
    t = htmllib.unescape(t)
    t = re.sub(r"<br\s*/?>", "<br>", t)
    t = re.sub(r"\s+", " ", t)
    return re.sub(r">\s+<", "><", t).strip()


def canon_text(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", canon(text))).strip()


def snippet(a, b, w=60):
    """Kurze Gegenüberstellung der ersten abweichenden Stelle (reiner Text)."""
    a, b = canon_text(a), canon_text(b)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            return "…%s[%s → %s]%s…" % (a[max(0, i1 - 25):i1], a[i1:i2][:w], b[j1:j2][:w], a[i2:i2 + 25])
    return ""


def cmd_pull(args):
    """Liest Einträge aus Kanka, vergleicht sie mit den Datendateien und schreibt (mit --apply) die Änderungen zurück."""
    creds = get_credentials(args)
    if not creds:
        return 2
    token, cid = creds
    data = load_data(data_files(args), False)
    map_path = args.map or os.path.join(HERE, "kanka_map_%s.json" % cid)
    if not os.path.exists(map_path):
        print("Keine Zuordnungsdatei gefunden:", map_path); return 2
    state = json.load(open(map_path, encoding="utf-8"))
    mp = state["items"]
    api = Api(token, cid, args.base_url, args.rpm)
    ents = {e["key"]: e for e in data["entities"]}
    ep_of = dict(PULL_KINDS)

    # Fernstand lesen
    try:
        remote = {k: fetch_all(api, ep) for k, ep in PULL_KINDS}
    except ApiError as ex:
        print("ABBRUCH:", ex); return 1
    print("Gelesen: " + ", ".join("%s %d" % (ep, len(remote[k])) for k, ep in PULL_KINDS))

    by_id, by_ent = {}, {}                       # (kind, id) -> key ; entity_id -> key
    for key, rec in mp.items():
        by_id[(rec.get("kind"), rec["id"])] = key
        if rec.get("entity_id"):
            by_ent[rec["entity_id"]] = key
    key2name = {k: e["name"] for k, e in ents.items()}

    # Eltern-ID-Art anhand bekannter Einträge erkennen (Entity-ID oder Objekt-ID)
    votes = {"entity_id": 0, "id": 0}
    for kind, objs in remote.items():
        for r in objs:
            key = by_id.get((kind, r["id"]))
            e = ents.get(key) if key else None
            if not e or not e.get("parent") or e["parent"] not in mp:
                continue
            for f in PARENT_FIELDS.get(kind, ()):
                v = r.get(f)
                if v:
                    if v == mp[e["parent"]].get("entity_id"): votes["entity_id"] += 1
                    elif v == mp[e["parent"]]["id"]: votes["id"] += 1
                    break
    pmode = "id" if votes["id"] > votes["entity_id"] else "entity_id"

    def remote_parent(kind, r):
        """Liefert (Schlüssel des Elterneintrags oder None, Rohwert). Rohwert None = kein Elternteil."""
        for f in PARENT_FIELDS.get(kind, ()):
            v = r.get(f)
            if v:
                k = (by_ent.get(v) or by_id.get((kind, v))) if pmode == "entity_id" else (by_id.get((kind, v)) or by_ent.get(v))
                return k, v
        return None, None

    tag_names = {t["id"]: t.get("name", "") for t in remote["tag"]}
    new_tags = []                                # (key, id, entity_id, name)
    tag_key = {rec["id"]: k for k, rec in mp.items() if rec.get("kind") == "tag"}
    used_keys = set(mp) | set(ents)

    def keys_for_tags(ids):
        out = []
        for i in ids or []:
            if i not in tag_key:
                k = "tag.kanka.%s" % slugify(tag_names.get(i, str(i)))
                while k in used_keys: k += "-2"
                used_keys.add(k); tag_key[i] = k
                tobj = next((t for t in remote["tag"] if t["id"] == i), {})
                new_tags.append((k, i, tobj.get("entity_id"), tag_names.get(i, str(i))))
            out.append(tag_key[i])
        return out

    changed, formal, conflicts, unchanged = [], [], [], 0
    seen_remote = set()
    for kind, objs in remote.items():
        if kind == "tag":
            continue
        for r in objs:
            key = by_id.get((kind, r["id"]))
            if not key or key not in ents:
                continue
            seen_remote.add(key)
            e = ents[key]
            diffs = {}
            if (r.get("name") or "").strip() != (e["name"] or "").strip(): diffs["name"] = r.get("name")
            if (r.get("type") or "").strip() != (e.get("type") or "").strip(): diffs["type"] = (r.get("type") or "").strip() or None
            if kind == "character" and (r.get("title") or "").strip() != (e.get("title") or "").strip(): diffs["title"] = (r.get("title") or "").strip()
            new_entry = mentions_to_refs(r.get("entry"), by_ent, key2name)
            only_formal = False
            if canon(new_entry) != canon(e["entry"]):
                if canon_text(new_entry) == canon_text(e["entry"]):
                    only_formal = True
                else:
                    diffs["entry"] = new_entry
            if set(keys_for_tags(r.get("tags"))) != set(e["tags"]):
                diffs["tags"] = keys_for_tags(r.get("tags"))
            if any(f in r for f in PARENT_FIELDS.get(kind, ())):      # nur vergleichen, wenn Kanka das Feld überhaupt liefert
                pk, raw = remote_parent(kind, r)
                if raw is not None and pk is None:
                    diffs["parent"] = ("?", raw)                          # Elternteil ist (noch) unbekannt, z. B. ein neuer Eintrag
                elif pk != (e.get("parent") or None):
                    diffs["parent"] = pk
            if diffs:
                local_changed = bool(mp[key].get("hash")) and mp[key]["hash"] != ehash(e)
                (conflicts if local_changed else changed).append((key, e, r, diffs))
            elif only_formal:
                formal.append(key)
            else:
                unchanged += 1

    deleted = [k for k, rec in mp.items() if rec.get("kind") in ep_of and rec["kind"] != "tag" and k in ents and k not in seen_remote and (not rec.get("remote_deleted") or args.drop_deleted)]
    new_objs = []
    for kind, objs in remote.items():
        if kind == "tag":
            continue
        for r in objs:
            if (kind, r["id"]) not in by_id:
                new_objs.append((kind, r))

    # ---------- Bericht
    print("\nVergleich mit den Datendateien (Eltern-ID-Art: %s):" % pmode)
    print("  unverändert:          %d" % unchanged)
    print("  nur formal geändert:  %d (HTML-Umformung durch Kanka, wird nicht übernommen)" % len(formal))
    print("  inhaltlich geändert:  %d" % len(changed))
    print("  Konflikte (auch lokal seit dem Import geändert): %d" % len(conflicts))
    print("  neu in Kanka:         %d" % len(new_objs))
    print("  in Kanka gelöscht:    %d" % len(deleted))

    def show(title, items, limit):
        if not items: return
        print("\n" + title)
        for key, e, r, diffs in items[:limit]:
            fl = ", ".join(diffs)
            print("  %-34s %s  [%s]" % (key[:34], e["name"][:40], fl))
            if "entry" in diffs:
                sn = snippet(e["entry"], diffs["entry"])
                if sn: print("      Text: %s" % sn)
            for f in ("name", "type", "title"):
                if f in diffs: print("      %s: %r → %r" % (f, e.get(f), diffs[f]))
            if "parent" in diffs:
                print("      Eltern: %r → %r" % (e.get("parent"), diffs["parent"] if not isinstance(diffs["parent"], tuple) else "(neuer Eintrag)"))
            if "tags" in diffs:
                print("      Tags: %s → %s" % (sorted(e["tags"]), sorted(diffs["tags"])))
        if len(items) > limit: print("  … und %d weitere (--alle zeigt alle)" % (len(items) - limit))
    lim = 10 ** 6 if args.alle else 25
    show("Inhaltlich geändert:", changed, lim)
    show("KONFLIKTE (lokal und in Kanka geändert; Standard: %s gewinnt):" % ("Kanka" if args.prefer == "kanka" else "lokal"), conflicts, lim)
    if new_objs:
        print("\nNeu in Kanka:")
        for kind, r in new_objs[:lim]:
            print("  %-13s %s" % (kind, r.get("name")))
    if deleted:
        print("\nIn Kanka gelöscht (noch in den Dateien):")
        for k in deleted[:lim]: print("  %-34s %s" % (k[:34], key2name[k]))
    if not args.apply:
        print("\nNichts geändert. Mit --apply werden die Änderungen in die Datendateien geschrieben (vorher Sicherung nach backup\\).")
        return 0

    # ---------- Anwenden
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(HERE, "backup", "data_%s" % stamp)
    _n = 2
    while os.path.exists(bdir):                      # mehrere Sicherungen in derselben Sekunde
        bdir = os.path.join(HERE, "backup", "data_%s_%d" % (stamp, _n)); _n += 1
    os.makedirs(os.path.dirname(bdir), exist_ok=True)
    shutil.copytree(os.path.join(HERE, "data"), bdir)
    shutil.copy2(map_path, os.path.join(bdir, os.path.basename(map_path)))
    print("\nSicherung: %s" % bdir)

    todo = [(k, e, r, d) for k, e, r, d in changed]
    todo += [(k, e, r, d) for k, e, r, d in conflicts if args.prefer == "kanka"]
    skipped = len(conflicts) if args.prefer == "local" else 0
    by_file, pending_parents = {}, []
    for key, e, r, diffs in todo:
        by_file.setdefault(e["_file"], []).append((key, diffs))
    for path, items in by_file.items():
        raw = json.load(open(path, encoding="utf-8"))
        idx = {x["key"]: x for x in raw["entities"]}
        for key, diffs in items:
            x = idx[key]
            for f, v in diffs.items():
                if f == "parent" and isinstance(v, tuple):
                    pending_parents.append((key, x, v[1], path))
                elif f == "parent":
                    x["parent"] = v
                else:
                    x[f] = v
            mp[key]["hash"] = ehash(x)
        json.dump(raw, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("Aktualisiert: %s (%d Einträge)" % (os.path.basename(path), len(items)))

    # neue Einträge
    if new_objs or new_tags:
        out_path = os.path.join(HERE, "data", "90_aus_kanka.json")
        out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {"meta": {"ausschnitt": "In Kanka angelegte Einträge (per pull übernommen)"}, "tags": [], "entities": []}
        newkey = {}
        for kind, r in new_objs:
            k = "kanka.%s.%s" % (kind, slugify(r.get("name") or str(r["id"])))
            while k in used_keys: k += "-2"
            used_keys.add(k); newkey[(kind, r["id"])] = k
            by_id[(kind, r["id"])] = k
            if r.get("entity_id"): by_ent[r["entity_id"]] = k
        for k, tid, teid, tname in new_tags:
            out["tags"].append({"key": k, "name": tname})
            mp[k] = {"id": tid, "entity_id": teid, "kind": "tag"}
        # Eltern zuerst
        newkeys_set = set(newkey.values())

        def depth(kind, r, d=0):
            pk, raw = remote_parent(kind, r)
            if pk in newkeys_set and d < 20:
                for kk, rr in new_objs:
                    if newkey[(kk, rr["id"])] == pk:
                        return 1 + depth(kk, rr, d + 1)
            return 0
        order = sorted(new_objs, key=lambda t: (depth(*t), [x[0] for x in PULL_KINDS].index(t[0])))
        for kind, r in order:
            k = newkey[(kind, r["id"])]
            ent_dict = {"key": k, "kind": kind, "name": r.get("name"), "type": (r.get("type") or None), "parent": remote_parent(kind, r)[0],
                        "tags": keys_for_tags(r.get("tags")), "entry": mentions_to_refs(r.get("entry"), by_ent, key2name)}
            if kind == "character" and r.get("title"): ent_dict["title"] = r["title"]
            for fld, kn in (("races", "race"), ("locations", "location")):
                keys = [x for x in ((by_id.get((kn, i)) or by_ent.get(i)) for i in (r.get(fld) or [])) if x]
                if keys: ent_dict[fld] = keys
            if r.get("entity_id"):
                try:
                    attrs = api.call("GET", "entities/%s/attributes" % r["entity_id"]).get("data", [])
                except ApiError:
                    attrs = []
                props = [{"name": a["name"], "value": a.get("value") if a.get("value") is not None else "", "type_id": a.get("type_id", 1),
                          **({"is_pinned": True} if a.get("is_pinned") else {})} for a in attrs]
                if props: ent_dict["properties"] = props
            out["entities"].append(ent_dict)
            mp[k] = {"id": r["id"], "entity_id": r.get("entity_id"), "kind": kind, "hash": ehash(ent_dict)}
        json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("Neu übernommen: %d Einträge, %d Tags → data\\90_aus_kanka.json" % (len(order), len(new_tags)))
        for key, x, rawv, path in pending_parents:
            pk = by_ent.get(rawv) or by_id.get((mp[key]["kind"], rawv))
            if pk:
                raw = json.load(open(path, encoding="utf-8"))
                for y in raw["entities"]:
                    if y["key"] == key:
                        y["parent"] = pk; mp[key]["hash"] = ehash(y)
                json.dump(raw, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            else:
                print("  Hinweis: Elternteil von %s unbekannt, unverändert gelassen." % key)

    # gelöschte Einträge
    if deleted:
        if args.drop_deleted:
            dropped = []
            for k in deleted:
                dep = [x["key"] for x in ents.values() if x.get("parent") == k or k in x.get("races", []) or k in x.get("locations", []) or ("{{ref:%s" % k) in x["entry"]]
                dep += ["Verbindung" for r in data.get("relations", []) if k in (r["from"], r["to"])] + ["Mitglied" for m in data.get("members", []) if k in (m["organisation"], m["character"])]
                if dep:
                    print("  nicht entfernt (wird noch verwendet von %s): %s" % (", ".join(dep[:3]), k)); continue
                path = ents[k]["_file"]
                raw = json.load(open(path, encoding="utf-8"))
                raw["entities"] = [x for x in raw["entities"] if x["key"] != k]
                json.dump(raw, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                mp.pop(k, None); dropped.append(k)
            print("Aus den Dateien entfernt: %d von %d gelöschten Einträgen" % (len(dropped), len(deleted)))
        else:
            for k in deleted: mp[k]["remote_deleted"] = True
            print("Als „in Kanka gelöscht“ vermerkt (bleiben in den Dateien; `import` überspringt sie). Zum Entfernen: pull --apply --drop-deleted")
    json.dump(state, open(map_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nFertig. %d Anfragen gesendet.%s" % (api.count, " %d Konflikte blieben lokal (--prefer local)." % skipped if skipped else ""))
    return 0


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["selftest", "plan", "import", "verify", "gruppenwerte", "pull"])
    ap.add_argument("--data", nargs="+", help="Datendatei(en) (JSON); Standard: alle Dateien in data/")
    ap.add_argument("--campaign", help="Kampagnen-ID (sonst KANKA_CAMPAIGN_ID)")
    ap.add_argument("--token-file", help="Datei mit dem Token (sonst KANKA_TOKEN)")
    ap.add_argument("--rpm", type=int, default=25, help="Anfragen pro Minute (Free: max. 30, Subscriber: max. 90)")
    ap.add_argument("--ascii-names", action="store_true", help="Umlaute in Property-Namen ersetzen (ä→ae, ö→oe, ü→ue, ß→ss)")
    ap.add_argument("--update", action="store_true", help="import: ALLE vorhandenen Einträge erzwungen aktualisieren (sonst nur geänderte)")
    ap.add_argument("--no-update", dest="no_update", action="store_true", help="import: nur neue Einträge anlegen, vorhandene nie anfassen")
    ap.add_argument("--apply", action="store_true", help="pull: Änderungen aus Kanka in die Datendateien schreiben (vorher Sicherung nach backup\\)")
    ap.add_argument("--prefer", choices=["kanka", "local"], default="kanka", help="pull: wer bei Konflikten gewinnt (Standard: kanka)")
    ap.add_argument("--drop-deleted", dest="drop_deleted", action="store_true", help="pull --apply: in Kanka gelöschte Einträge auch aus den Datendateien entfernen")
    ap.add_argument("--alle", action="store_true", help="pull: alle Unterschiede anzeigen, nicht nur die ersten 25")
    ap.add_argument("--prune", action="store_true", help="import: Properties löschen, die in Kanka stehen, aber nicht in den Daten (Vorsicht bei eigenen Properties)")
    ap.add_argument("--yes", action="store_true", help="Rückfrage vor dem Import überspringen")
    ap.add_argument("--map", help="Pfad der Zuordnungsdatei")
    ap.add_argument("--only", nargs="+", help="import: nur diese Schlüssel bearbeiten (z. B. mit --update einzelne Einträge aktualisieren)")
    ap.add_argument("--base-url", default=BASE_URL, help="API-Basis-URL (nur für Tests ändern)")
    ap.add_argument("--show", help="plan: Schlüssel eines Eintrags im Detail anzeigen")
    for _n, _a in GRP_NAMES:
        ap.add_argument("--" + _a, type=int, help="gruppenwerte: Gruppenwert " + _n)
    a = ap.parse_args()
    sys.exit({"selftest": cmd_selftest, "plan": cmd_plan, "import": cmd_import, "verify": cmd_verify, "gruppenwerte": cmd_gruppenwerte, "pull": cmd_pull}[a.command](a))


if __name__ == "__main__":
    main()
