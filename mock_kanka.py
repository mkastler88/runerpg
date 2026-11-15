#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lokaler Kanka-Nachbau zum Testen des Import-Skripts ohne Netzwerk und ohne echte Kampagne.
Start:  python3 tests/mock_kanka.py [Port]      (Standard 8765, Token: TESTTOKEN)
Dann:   KANKA_TOKEN=TESTTOKEN KANKA_CAMPAIGN_ID=1 python3 kanka_import.py import --base-url http://127.0.0.1:8765/1.0 --rpm 6000 --yes
Simuliert außerdem einmalig ein Rate-Limit (HTTP 429) beim 7. Aufruf."""
import json, os, re, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kanka_import import eval_props  # gleiche Formelrechnung wie der Selbsttest

STATE = {"rels": [], "rel_id": 0, "members": [], "counter": 0, "eid": 1000, "objs": {}, "attrs": {}, "attr_id": 0, "calls": 0, "limited": False, "log": []}
LOCK = threading.Lock()
EP = ("tags", "notes", "abilities", "characters", "items", "creatures", "races", "locations", "organisations", "attribute_templates")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj=None, headers=None):
        b = json.dumps(obj if obj is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _handle(self, method):
        with LOCK:
            STATE["calls"] += 1
            if self.headers.get("Authorization") != "Bearer TESTTOKEN":
                return self._send(401, {"message": "Unauthenticated."})
            if STATE["calls"] == 7 and not STATE["limited"]:
                STATE["limited"] = True
                return self._send(429, {"message": "Too Many Attempts."}, {"Retry-After": "1"})
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            m = re.match(r"^/1\.0/campaigns/(\d+)/(.+)$", self.path)
            if not m: return self._send(404, {"message": "not found"})
            path, _, qs = m.group(2).partition("?")
            STATE["log"].append((method, path))
            mm = re.match(r"^(\w+)(?:/(\d+))?$", path)
            if mm and mm.group(1) in EP:
                ep, oid = mm.group(1), mm.group(2)
                if method == "GET" and not oid:
                    per = int(os.environ.get("MOCK_PER_PAGE", "20"))
                    page = int(re.search(r"page=(\d+)", qs).group(1)) if re.search(r"page=(\d+)", qs) else 1
                    allo = [o for o in STATE["objs"].values() if o["_ep"] == ep]
                    chunk = allo[(page - 1) * per: page * per]
                    out = [{k: v for k, v in o.items() if k != "_ep"} for o in chunk]
                    return self._send(200, {"data": out, "meta": {"current_page": page, "last_page": max(1, -(-len(allo) // per)), "per_page": per, "total": len(allo)}})
                if method == "DELETE" and oid:
                    STATE["objs"].pop(int(oid), None)
                    return self._send(200, {"message": "deleted"})
                if method in ("POST", "PUT", "PATCH") and body and body.get("parent_id") is not None:
                    if body["parent_id"] not in {o["id" if os.environ.get("MOCK_PARENT_MODE") == "id" else "entity_id"] for o in STATE["objs"].values() if o["_ep"] == ep}:
                        return self._send(422, {"code": 422, "error": "The selected parent id is invalid.",
                                                "fields": {"parent_id": ["The selected parent id is invalid."]}})
                if method in ("POST", "PUT", "PATCH") and body:
                    mode = os.environ.get("MOCK_LINK_MODE", "id")
                    for fld, target_ep in (("races", "races"), ("locations", "locations")):
                        for v in body.get(fld) or []:
                            ok = any(o["_ep"] == target_ep and o["id" if mode == "id" else "entity_id"] == v for o in STATE["objs"].values())
                            if not ok:
                                return self._send(422, {"code": 422, "error": "The selected %s is invalid." % fld, "fields": {fld: ["The selected %s is invalid." % fld]}})
                if method == "POST":
                    STATE["counter"] += 1; STATE["eid"] += 1
                    o = dict(body); o.update(id=STATE["counter"], entity_id=STATE["eid"], _ep=ep)
                    STATE["objs"][o["id"]] = o
                    return self._send(200, {"data": o})
                if method in ("PUT", "PATCH") and oid:
                    o = STATE["objs"].get(int(oid))
                    if not o: return self._send(404, {"message": "no"})
                    if method == "PUT": o.update(body)
                    else: o.update(body)
                    return self._send(200, {"data": o})
            mr = re.match(r"^entities/(\d+)/relations$", path)
            if mr and method == "POST":
                eids = {o["entity_id"] for o in STATE["objs"].values()}
                owner = int(mr.group(1))
                targets = body.get("targets") or [body.get("target_id")]
                if owner not in eids or body.get("owner_id") != owner or not body.get("relation") or any(t not in eids for t in targets):
                    return self._send(422, {"code": 422, "error": "invalid relation"})
                out = []
                for t in targets:
                    STATE["rel_id"] += 1
                    r = {"id": STATE["rel_id"], "owner_id": owner, "target_id": t, "relation": body["relation"]}
                    STATE["rels"].append(r); out.append(r)
                return self._send(200, {"data": out if body.get("targets") else out[0]})
            mm = re.match(r"^organisations/(\d+)/organisation_members$", path)
            if mm and method == "POST":
                orgs = {o["id"] for o in STATE["objs"].values() if o["_ep"] == "organisations"}
                chars = {o["id"] for o in STATE["objs"].values() if o["_ep"] == "characters"}
                if body.get("organisation_id") not in orgs or body.get("character_id") not in chars:
                    return self._send(422, {"code": 422, "error": "invalid member"})
                STATE["rel_id"] += 1; STATE["members"].append(dict(body, id=STATE["rel_id"]))
                return self._send(200, {"data": {"id": STATE["rel_id"]}})
            md = re.match(r"^entities/(\d+)/attributes/(\d+)$", path)
            if md and method == "DELETE":
                lst = STATE["attrs"].get(int(md.group(1)), [])
                STATE["attrs"][int(md.group(1))] = [a for a in lst if a["id"] != int(md.group(2))]
                return self._send(200, {"message": "deleted"})
            ma = re.match(r"^entities/(\d+)/attributes$", path)
            if ma:
                eid = int(ma.group(1)); lst = STATE["attrs"].setdefault(eid, [])
                if method == "GET":
                    props = [{"name": a["name"], "value": a["value"], "type_id": a["type_id"]} for a in lst]
                    try: res = eval_props(props)
                    except Exception: res = {}
                    out = []
                    for a in lst:
                        r = res.get(a["name"]); b = dict(a)
                        b["parsed"] = (str(int(r)) if isinstance(r, (int, float)) and float(r).is_integer() else str(r)) if r is not None else a["value"]
                        out.append(b)
                    return self._send(200, {"data": out})
                if method == "PATCH":
                    for a in body["attribute"]:
                        if a.get("id"):
                            for x in lst:
                                if x["id"] == a["id"]: x.update(a)
                        else:
                            STATE["attr_id"] += 1; b = dict(a); b["id"] = STATE["attr_id"]; lst.append(b)
                    return self._send(200, {"data": lst})
            return self._send(404, {"message": "unbekannter Pfad " + path})

    def do_GET(self):
        if self.path == "/debug":
            with LOCK:
                info = {"objekte": len(STATE["objs"]), "attribut_listen": {str(k): len(v) for k, v in STATE["attrs"].items() if len(v) > 100},
                        "doppelte_property_namen": sum(len(v) - len({a["name"] for a in v}) for v in STATE["attrs"].values()),
                        "anfragen": STATE["calls"], "relationen": len(STATE["rels"]), "mitglieder": len(STATE["members"])}
            return self._send(200, info)
        self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PUT(self): self._handle("PUT")
    def do_PATCH(self): self._handle("PATCH")
    def do_DELETE(self): self._handle("DELETE")


def serve(port=8765):
    srv = HTTPServer(("127.0.0.1", port), H)
    return srv


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print("Mock-Kanka läuft auf http://127.0.0.1:%d/1.0 (Token TESTTOKEN)" % port)
    serve(port).serve_forever()
