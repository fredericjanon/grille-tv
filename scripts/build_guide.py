#!/usr/bin/env python3
"""Construit data/guide.json à partir du flux XMLTV public xmltvfr.fr.

- Ne garde que les chaînes de la liste CHANNELS (bouquet Free, plan de service d'août 2026).
- Classe chaque programme dans une des 9 catégories de l'application.
- Ajoute des visuels (affiche / fond) via TMDB si la variable TMDB_API_KEY est définie,
  sinon utilise l'image du flux quand il en fournit une.

Uniquement la bibliothèque standard de Python.
"""
import difflib
import gzip
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "guide.json")
ART_CACHE = os.path.join(ROOT, "data", "art-cache.json")

# Adresse du flux. À corriger via la variable GitHub FEED_URL si elle change.
DEFAULT_FEEDS = [
    "https://xmltvfr.fr/xmltv/xmltv.xml.gz",
    "https://xmltvfr.fr/xmltv/xmltv.zip",
    "https://xmltvfr.fr/xmltv/xmltv.xml",
]
PARIS = ZoneInfo("Europe/Paris")
DAYS_BEFORE, DAYS_AFTER = 1, 8
TMDB_MAX_LOOKUPS = int(os.environ.get("TMDB_MAX_LOOKUPS", "300"))
TMDB_RETRY_NULL_DAYS = 14

# (clé, numéro Free, nom affiché, identifiants XMLTV possibles, catégorie par défaut)
CHANNELS = [
    ("tf1", 1, "TF1", ["TF1.fr"], "mag"),
    ("f2", 2, "France 2", ["France2.fr"], "mag"),
    ("f3", 3, "France 3", ["France3.fr"], "mag"),
    ("f4", 4, "France 4", ["France4.fr"], "mag"),
    ("f5", 5, "France 5", ["France5.fr"], "doc"),
    ("m6", 6, "M6", ["M6.fr"], "mag"),
    ("arte", 7, "Arte", ["Arte.fr"], "doc"),
    ("lcp", 8, "LCP", ["LaChaineParlementaire.fr", "LCP.fr"], "info"),
    ("w9", 9, "W9", ["W9.fr"], "musique"),
    ("tmc", 10, "TMC", ["TMC.fr"], "mag"),
    ("tfx", 11, "TFX", ["NT1.fr", "TFX.fr"], "show"),
    ("gulli", 12, "Gulli", ["Gulli.fr"], "jeune"),
    ("bfm", 13, "BFM TV", ["BFMTV.fr"], "info"),
    ("cnews", 14, "CNews", ["CNews.fr"], "info"),
    ("lci", 15, "LCI", ["LCI.fr"], "info"),
    ("fi", 16, "franceinfo", ["FranceInfo.fr"], "info"),
    ("cstar", 17, "CStar", ["CStar.fr"], "musique"),
    ("t18", 18, "T18", ["T18.fr"], "serie"),
    ("novo19", 19, "NOVO19", ["NOVO19.fr"], "serie"),
    ("tf1sf", 20, "TF1 Séries Films", ["TF1SeriesFilms.fr"], "serie"),
    ("equipe", 21, "L'Équipe", ["LEquipe21.fr", "LEquipe.fr"], "sport"),
    ("sixter", 22, "6ter", ["6ter.fr"], "serie"),
    ("rmcs", 23, "RMC Story", ["Numero23.fr", "RMCStory.fr"], "show"),
    ("rmcd", 24, "RMC Découverte", ["RMCDecouverte.fr"], "doc"),
    ("rmcl", 25, "RMC Life", ["RMCLife.fr"], "mag"),
    ("tv5", 27, "TV5 Monde", ["TV5Monde.fr"], "mag"),
    ("pp", 28, "Paris Première", ["ParisPremiere.fr"], "mag"),
    ("rtl9", 29, "RTL9", ["RTL9.fr"], "film"),
    ("canal", 40, "Canal+", ["CanalPlus.fr"], "film"),
]


def norm(s):
    s = unicodedata.normalize("NFD", s or "").lower()
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


# ---------- Catégories ----------
RULES = [
    ("sport", ("sport", "football", "rugby", "tennis", "cyclisme", "basket", "handball", "formule 1")),
    ("musique", ("musique", "concert", "clip", "opera", "danse", "spectacle musical")),
    ("jeune", ("jeunesse", "enfant", "dessin anime", "dessins animes", "youth", "children")),
    ("film", ("film", "telefilm", "cinema", "long metrage", "court metrage")),
    ("serie", ("serie", "feuilleton", "soap", "sitcom")),
    ("info", ("journal", "info", "actualit", "meteo", "politique", "debat")),
    ("doc", ("documentaire", "docu", "reportage", "histoire", "decouverte", "nature", "science", "societe")),
    ("show", ("divertissement", "jeu", "reality", "telerealite", "variete", "humour", "quiz", "spectacle", "cuisine", "talent")),
    ("mag", ("magazine", "talk", "emission", "culture", "sante", "consommation", "art")),
]


def classify(cats, default):
    text = " | ".join(norm(c) for c in cats)
    for key, words in RULES:
        if any(w in text for w in words):
            return key
    return default


# ---------- Téléchargement ----------
def download(urls, dest):
    last = None
    for url in urls:
        try:
            print("Téléchargement :", url, flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "grille-tv/1.0 (usage personnel)"})
            with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            if os.path.getsize(dest) > 1000:
                return url
            last = "fichier trop petit"
        except Exception as e:  # noqa: BLE001
            last = e
            print("  échec :", e, flush=True)
    raise SystemExit("Aucune adresse de flux ne répond (%s). Définissez la variable FEED_URL." % last)


def open_xml(path):
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic[:2] == b"\x1f\x8b":
        return gzip.open(path, "rb")
    if magic[:2] == b"PK":
        z = zipfile.ZipFile(path)
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        return z.open(name)
    return open(path, "rb")


def parse_time(s):
    s = (s or "").strip()
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M %z", "%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            d = datetime.strptime(s, fmt)
            return int((d if d.tzinfo else d.replace(tzinfo=PARIS)).timestamp())
        except ValueError:
            continue
    return None


def episode_label(el):
    for e in el.findall("episode-num"):
        if e.get("system") == "xmltv_ns" and e.text:
            parts = e.text.split(".")
            try:
                season = int(parts[0].split("/")[0]) + 1 if parts[0].strip() else None
                ep = int(parts[1].split("/")[0]) + 1 if len(parts) > 1 and parts[1].strip() else None
            except ValueError:
                continue
            if season and ep:
                return "Saison %d · épisode %d" % (season, ep)
            if ep:
                return "Épisode %d" % ep
    return ""


GENERIC = {"film", "serie", "telefilm", "feuilleton", "cinema", "long metrage", "court metrage", "serie tv"}


def feed_extra(el, cats):
    """Année, réalisateur, acteurs, pays, genre et public du flux XMLTV."""
    x = {}
    cr = el.find("credits")
    if cr is not None:
        d = [(e.text or "").strip() for e in cr.findall("director") if (e.text or "").strip()]
        a = [(e.text or "").strip() for e in cr.findall("actor") if (e.text or "").strip()]
        if d:
            x["d"] = d[:2]
        if a:
            x["a"] = a[:8]
    y = (el.findtext("date") or "")[:4]
    if y.isdigit():
        x["y"] = int(y)
    co = [(c.text or "").strip() for c in el.findall("country") if (c.text or "").strip()]
    if co:
        x["co"] = [COUNTRIES.get(c.upper(), c) if len(c) == 2 else c for c in co[:2]]
    rt = el.find("rating/value")
    if rt is not None and (rt.text or "").strip():
        x["r"] = rt.text.strip()
    g = [c for c in cats if c and norm(c) not in GENERIC]
    if g:
        x["g"] = g[:2]
    return x


def read_feed(path, wanted, t_min, t_max):
    """wanted : dict id_xmltv -> clé de chaîne."""
    progs = {k: [] for k in wanted.values()}
    names = {}
    with open_xml(path) as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag == "channel":
                cid = el.get("id")
                if cid in wanted:
                    names[cid] = (el.findtext("display-name") or "").strip()
                el.clear()
            elif el.tag == "programme":
                cid = el.get("channel")
                if cid in wanted:
                    s, e = parse_time(el.get("start")), parse_time(el.get("stop"))
                    if s and e and e > t_min and s < t_max and e > s:
                        title = (el.findtext("title") or "").strip()
                        if title:
                            sub = (el.findtext("sub-title") or "").strip()
                            icon = el.find("icon")
                            progs[wanted[cid]].append({
                                "s": s, "e": e, "title": title,
                                "desc": " ".join((el.findtext("desc") or "").split()),
                                "cats": [c.text or "" for c in el.findall("category")],
                                "ep": episode_label(el) or (sub if sub and len(sub) < 60 else ""),
                                "img": icon.get("src") if icon is not None and icon.get("src") else "",
                                "year": (el.findtext("date") or "")[:4],
                                "x": feed_extra(el, [c.text or "" for c in el.findall("category")]),
                            })
                el.clear()
    return progs, names


# ---------- TMDB (visuels, optionnel) ----------
def tmdb_get(url, key):
    headers = {"Accept": "application/json", "User-Agent": "grille-tv/1.0"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    else:
        url += "&api_key=" + urllib.parse.quote(key)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "2")) + 1)
                continue
            raise
    return None


COUNTRIES = {"FR": "France", "US": "États-Unis", "GB": "Royaume-Uni", "DE": "Allemagne", "IT": "Italie",
             "ES": "Espagne", "CA": "Canada", "BE": "Belgique", "JP": "Japon", "KR": "Corée du Sud",
             "CH": "Suisse", "AU": "Australie", "IE": "Irlande", "SE": "Suède", "DK": "Danemark"}


def tmdb_art(title, kind, year, key):
    q = {"query": title, "language": "fr-FR", "include_adult": "false"}
    if kind == "movie" and year.isdigit():
        q["year"] = year
    data = tmdb_get("https://api.themoviedb.org/3/search/%s?%s" % (kind, urllib.parse.urlencode(q)), key)
    want = norm(title)
    for r in (data or {}).get("results", [])[:5]:
        names = [r.get("title"), r.get("original_title"), r.get("name"), r.get("original_name")]
        best = max((difflib.SequenceMatcher(None, want, norm(n)).ratio() for n in names if n), default=0)
        if best < 0.85:
            continue
        det = tmdb_get("https://api.themoviedb.org/3/%s/%s?language=fr-FR&append_to_response=credits" % (kind, r["id"]), key) or r
        credits = det.get("credits") or {}
        x = {}
        date = det.get("release_date") or det.get("first_air_date") or ""
        if date[:4].isdigit():
            x["y"] = int(date[:4])
        if det.get("genres"):
            x["g"] = [g["name"] for g in det["genres"]][:3]
        codes = [c.get("iso_3166_1") for c in det.get("production_countries", [])] or det.get("origin_country") or []
        if codes:
            x["co"] = [COUNTRIES.get(c, c) for c in codes][:2]
        dirs = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        if dirs:
            x["d"] = dirs[:2]
        creators = [c["name"] for c in det.get("created_by", []) if c.get("name")]
        if creators:
            x["cr"] = creators[:2]
        cast = [c["name"] for c in credits.get("cast", []) if c.get("name")]
        if cast:
            x["a"] = cast[:8]
        if det.get("vote_average") and det.get("vote_count", 0) >= 20:
            x["n"] = round(det["vote_average"], 1)
        return {
            "p": "https://image.tmdb.org/t/p/w500" + r["poster_path"] if r.get("poster_path") else "",
            "b": "https://image.tmdb.org/t/p/w780" + r["backdrop_path"] if r.get("backdrop_path") else "",
            "x": x,
            "ov": (det.get("overview") or "").strip(),
        }
    return None


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main():
    now = int(time.time())
    today = datetime.now(PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    t_min = int((today - timedelta(days=DAYS_BEFORE)).timestamp())
    t_max = int((today + timedelta(days=DAYS_AFTER)).timestamp())

    feeds = [os.environ["FEED_URL"]] if os.environ.get("FEED_URL") else DEFAULT_FEEDS
    tmp = tempfile.mkdtemp()
    try:
        src = download(feeds, os.path.join(tmp, "feed"))
        wanted = {}
        for key, _n, _name, ids, _d in CHANNELS:
            for i in ids:
                wanted[i] = key
        progs, _names = read_feed(os.path.join(tmp, "feed"), wanted, t_min, t_max)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    tmdb_key = os.environ.get("TMDB_API_KEY", "").strip()
    cache = load_json(ART_CACHE, {})
    lookups = 0
    channels, missing, total = [], [], 0
    pending = []  # (start, programme) pour prioriser les visuels des prochains jours
    for key, num, name, _ids, default in CHANNELS:
        lst = sorted(progs.get(key, []), key=lambda p: p["s"])
        if not lst:
            missing.append(name)
            continue
        clean = []
        for p in lst:  # supprime les chevauchements
            if clean and p["s"] < clean[-1]["e"]:
                if p["s"] <= clean[-1]["s"]:
                    continue
                clean[-1]["e"] = p["s"]
            p["cat"] = classify(p["cats"], default)
            p["bg"] = ""
            clean.append(p)
        pending += [p for p in clean if p["cat"] in ("film", "serie")]
        channels.append({"id": key, "n": num, "name": name, "p": clean})
        total += len(clean)

    if tmdb_key:
        for p in sorted(pending, key=lambda p: abs(p["s"] - now)):
            kind = "movie" if p["cat"] == "film" else "tv"
            ck = kind + "|" + norm(p["title"])
            hit = cache.get(ck)
            fresh = hit and (hit.get("art") or now - hit.get("t", 0) < TMDB_RETRY_NULL_DAYS * 86400)
            if not fresh:
                if lookups >= TMDB_MAX_LOOKUPS:
                    continue
                try:
                    art = tmdb_art(p["title"], kind, p["year"], tmdb_key)
                except Exception as e:  # noqa: BLE001
                    print("TMDB :", e)
                    continue
                hit = cache[ck] = {"t": now, "art": art}
                lookups += 1
                time.sleep(0.05)
            art = hit.get("art") if hit else None
            if art:
                if art.get("p") or art.get("b"):
                    p["img"], p["bg"] = art.get("p", ""), art.get("b", "")
                filled = False
                for k, v in (art.get("x") or {}).items():
                    if not p["x"].get(k):
                        p["x"][k] = v
                        filled = True
                if filled or art.get("p") or art.get("b"):
                    p["x"]["s"] = "t"
                if len(p["desc"]) < 40 and art.get("ov"):
                    p["desc"] = art["ov"]
        print("TMDB : %d recherches" % lookups)
        os.makedirs(os.path.dirname(ART_CACHE), exist_ok=True)
        with open(ART_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))

    out = {
        "generated": datetime.now(PARIS).isoformat(timespec="minutes"),
        "source": src,
        "tmdb": bool(tmdb_key),
        "last": max(p["e"] for c in channels for p in c["p"]) if channels else 0,
        "channels": [
            {"id": c["id"], "n": c["n"], "name": c["name"], "p": [
                [p["s"], p["e"], p["title"], p["desc"][:600], p["cat"], p["ep"], p["img"], p["bg"],
                 (p["x"] if p["cat"] in ("film", "serie") and p["x"] else 0)] for p in c["p"]
            ]} for c in channels
        ],
    }
    if not channels:
        raise SystemExit("Aucune chaîne trouvée dans le flux : identifiants à vérifier.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("OK : %d chaînes, %d programmes -> %s (%.1f Ko)" % (len(channels), total, OUT, os.path.getsize(OUT) / 1024))
    if missing:
        print("Chaînes absentes du flux :", ", ".join(missing))


if __name__ == "__main__":
    sys.exit(main())
