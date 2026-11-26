"""lists/product.txt, service.txt, startup.txt (ya .csv) -> data/companies.json
Format: Excel madhun 3 columns copy karun paste kara: S.No <tab> Company <tab> Link"""
import csv, json, re, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = [("Product", "product", False), ("Service", "service", False), ("Startup", "startup", True)]
SUF = re.compile(r"\b(inc|ltd|limited|llc|plc|pvt|private|corporation|corp|se|sa|ag|group|technologies|technology|software|systems|global|services|holdings)\b", re.I)

def nkey(n):
    return re.sub(r"[^a-z0-9]", "", SUF.sub("", re.sub(r"\(.*?\)", "", n).lower())) or n.lower()

def url_of(u):
    u = u.strip().replace("\u2011", "-").replace("\u2010", "-")
    return u if u.startswith("http") else "https://" + u

def host(u):
    return re.sub(r"^www\.", "", u.split("//")[-1].split("/")[0].lower())

def parse_txt(path):
    rows, pend = [], None
    for raw in open(path, encoding="utf-8", errors="ignore"):
        line = raw.rstrip("\r\n")
        if not line.strip() or ("\t" not in line and re.fullmatch(r"\s*\d+\s*", line)):
            continue  # blank or Excel row-number noise
        parts = [p.strip() for p in line.split("\t")]
        if parts[0].isdigit():
            if pend is not None: rows.append(pend)
            pend = [p for p in parts[1:] if p]
        elif pend is not None and not line.lstrip().startswith(("S. No", "FOLLOW")):
            pend.append(line.strip())  # name/link wrapped on next lines
    if pend is not None: rows.append(pend)
    return rows

def parse_csv(path):
    out = []
    for r in csv.reader(open(path, encoding="utf-8", errors="ignore")):
        r = [x.strip() for x in r if x.strip()]
        if len(r) >= 3 and r[0].isdigit(): out.append(r[1:])
    return out

def parse(path):
    rows = parse_csv(path) if path.suffix == ".csv" else parse_txt(path)
    return [(re.sub(r"\s*\(.*?\)", "", " ".join(r[0].split())).strip() or r[0], url_of(r[-1])) for r in rows if len(r) >= 2 and "." in r[-1]]

def main():
    comps, by_n, by_h = [], {}, {}
    for typ, stem, is_careers in SOURCES:
        p = next((q for q in (ROOT/"lists"/f"{stem}.txt", ROOT/"lists"/f"{stem}.csv") if q.exists()), None)
        if not p: print("missing list:", stem); continue
        n0 = len(comps)
        for name, url in parse(p):
            c = by_n.get(nkey(name)) or by_h.get(host(url))
            if not c:
                c = {"name": name, "type": typ, "site": "", "careers": "", "tags": []}; comps.append(c)
            by_n.setdefault(nkey(name), c); by_h.setdefault(host(url), c)
            if typ not in c["tags"]: c["tags"].append(typ)
            if is_careers: c["careers"] = c["careers"] or url
            else: c["site"] = c["site"] or url
        print(f"{stem}: {len(comps)-n0} new companies")
    seen = {}
    for c in comps:
        if not c["site"] and c["careers"]: c["site"] = "https://" + host(c["careers"])
        c["id"] = re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-") or "co"
        k = seen[c["id"]] = seen.get(c["id"], 0) + 1
        if k > 1: c["id"] += f"-{k}"
    comps.sort(key=lambda c: c["name"].lower())
    (ROOT/"data").mkdir(exist_ok=True)
    json.dump(comps, open(ROOT/"data"/"companies.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("total unique companies:", len(comps))

if __name__ == "__main__":
    main()
