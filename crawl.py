"""Pratyek company chya career page var kuthli job-board system (ATS) vaparli aahe te shodhto,
tithun jobs ghet aani navin jobs 'first_seen' sobat data/jobs.json madhe save karto."""
import json, os, re, pathlib, datetime as dt, concurrent.futures as cf
from urllib.parse import urlparse
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data"
CFG = {"india_only": True, "max_jobs_per_company": 150, "workers": 16, "timeout": 12, "retry_discovery_days": 14}
INDIA = ["india", "pune", "mumbai", "bengaluru", "bangalore", "hyderabad", "chennai", "delhi", "noida", "gurgaon",
         "gurugram", "kolkata", "ahmedabad", "nagpur", "nashik", "kochi", "coimbatore", "jaipur", "indore", "chandigarh",
         "thiruvananthapuram", "trivandrum", "mysuru", "vadodara", "bhubaneswar", "mohali", "thane", "kolhapur"]
H = {"User-Agent": "Mozilla/5.0 (compatible; JobWatch/1.0)"}
NOW = dt.datetime.now(dt.timezone.utc)
BAD = {"embed", "v1", "js", "api", "assets", "static", "oembed", "company", "jobs", "careers"}

def get(u):
    r = requests.get(u, headers=H, timeout=CFG["timeout"]); r.raise_for_status(); return r

def iso(v):
    if not v: return ""
    try:
        if isinstance(v, (int, float)): return dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc).isoformat()
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return ""

def f_greenhouse(s):
    return [dict(id=str(j["id"]), title=j["title"], loc=(j.get("location") or {}).get("name", ""),
                 url=j["absolute_url"], posted=iso(j.get("first_published")))
            for j in get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs").json()["jobs"]]

def f_lever(s):
    return [dict(id=j["id"], title=j["text"], loc=(j.get("categories") or {}).get("location") or "",
                 url=j["hostedUrl"], posted=iso(j.get("createdAt")))
            for j in get(f"https://api.lever.co/v0/postings/{s}?mode=json").json()]

def f_ashby(s):
    return [dict(id=j["id"], title=j["title"], loc=j.get("location") or "", url=j.get("jobUrl") or "",
                 posted=iso(j.get("publishedAt") or j.get("publishedDate")))
            for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{s}").json()["jobs"]]

def f_smart(s):
    out, off = [], 0
    while off < 300:
        c = get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=100&offset={off}").json().get("content", [])
        for j in c:
            l = j.get("location") or {}
            ctry = "India" if (l.get("country") or "").lower() == "in" else l.get("country")
            out.append(dict(id=j["id"], title=j["name"], loc=", ".join(x for x in [l.get("city"), ctry] if x),
                            url=f"https://jobs.smartrecruiters.com/{s}/{j['id']}", posted=iso(j.get("releasedDate"))))
        if len(c) < 100: break
        off += 100
    return out

def f_workday(s):
    t, wd, site = s.split("|")
    base, out, off = f"https://{t}.{wd}.myworkdayjobs.com", [], 0
    while off < CFG["max_jobs_per_company"]:
        r = requests.post(f"{base}/wday/cxs/{t}/{site}/jobs", headers=H, timeout=CFG["timeout"],
                          json={"appliedFacets": {}, "limit": 20, "offset": off,
                                "searchText": "India" if CFG["india_only"] else ""})
        r.raise_for_status()
        p = r.json().get("jobPostings", [])
        out += [dict(id=j["externalPath"], title=j["title"], loc=j.get("locationsText", ""),
                     url=f"{base}/{site}{j['externalPath']}", posted="") for j in p]
        if len(p) < 20: break
        off += 20
    return out

FETCH = {"greenhouse": f_greenhouse, "lever": f_lever, "ashby": f_ashby, "smartrecruiters": f_smart, "workday": f_workday}
RX = [("greenhouse", r"greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)"),
      ("lever", r"jobs\.lever\.co/([A-Za-z0-9_-]+)"), ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)"),
      ("smartrecruiters", r"smartrecruiters\.com/([A-Za-z0-9_-]+)")]

def find_ats(html):
    m = re.search(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Za-z]{2}/)?([A-Za-z0-9_-]+)", html)
    if m: return "workday", f"{m[1]}|{m[2]}|{m[3]}"
    for ats, rx in RX:
        for m in re.finditer(rx, html):
            if m[1].lower() not in BAD: return ats, m[1]
    return None

def discover(c):
    site = (c.get("site") or "").rstrip("/")
    pages = list(dict.fromkeys(u for u in [c.get("careers"), site, site + "/careers", site + "/jobs"] if u and u.startswith("http")))
    for u in pages:
        try:
            f = find_ats(get(u).text)
            if f: return f
        except Exception:
            pass
    dom = re.sub(r"^www\.", "", urlparse(site).netloc).split(".")[0] if site else ""
    base = re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", c["name"].lower()))
    for slug in dict.fromkeys(x for x in [base, dom] if x):  # last resort: guess the board name
        for ats in ("greenhouse", "lever", "ashby"):
            try:
                if FETCH[ats](slug): return ats, slug
            except Exception:
                pass
    return None

def work(c, info):
    try:
        if not info or (not info.get("ats") and (NOW - dt.datetime.fromisoformat(info["checked"])).days >= CFG["retry_discovery_days"]):
            f = discover(c)
            info = {"ats": f[0], "slug": f[1]} if f else {"ats": None, "checked": NOW.isoformat()}
        return c, info, (FETCH[info["ats"]](info["slug"]) if info.get("ats") else [])
    except Exception:
        return c, info or {}, None  # error: purane jobs tasech theva

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

def fmt_ist(s):
    return dt.datetime.fromisoformat(s).astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")

def notify(new):
    """Telegram var navin jobs cha message. Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. Optional: ALERT_KEYWORDS=python,java,pune"""
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    kws = [k.strip().lower() for k in os.environ.get("ALERT_KEYWORDS", "").split(",") if k.strip()]
    if kws: new = [j for j in new if any(k in f"{j['title']} {j['location']} {j['company']}".lower() for k in kws)]
    if not (tok and chat and new): return
    def send(t):
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=15,
                      json={"chat_id": chat, "text": t, "disable_web_page_preview": True})
    lines = [f"🆕 {j['title']}\n🏢 {j['company']} ({j['type']})\n📍 {j['location'] or '-'}\n"
             f"🕒 {'Posted' if j['posted'] else 'Detected'}: {fmt_ist(j['posted'] or j['first_seen'])}\n🔗 {j['url']}" for j in new[:60]]
    if len(new) > 60: lines.append(f"+{len(new)-60} ajun navin jobs, site var paha.")
    chunk = ""
    for l in lines:
        if len(chunk) + len(l) > 3500: send(chunk); chunk = ""
        chunk += l + "\n\n"
    if chunk: send(chunk)

def load(p, default):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return default

def main():
    comps = load(D / "companies.json", [])
    ats, old = load(D / "ats.json", {}), load(D / "jobs.json", {"jobs": []})
    oldj = {j["uid"]: j for j in old["jobs"]}
    by_c = {}
    for j in old["jobs"]: by_c.setdefault(j["cid"], []).append(j)
    out, new, stats = [], [], {}
    with cf.ThreadPoolExecutor(CFG["workers"]) as ex:
        for c, info, jobs in ex.map(lambda c: work(c, ats.get(c["id"])), comps):
            info = dict(info); info["crawled"] = ats.get(c["id"], {}).get("crawled", False)
            k = info.get("ats") or "none"; stats[k] = stats.get(k, 0) + 1
            if jobs is None:
                out += by_c.get(c["id"], []); ats[c["id"]] = info; continue
            first = not info["crawled"]
            sel = [j for j in jobs if not CFG["india_only"] or info["ats"] == "workday"
                   or any(x in j["loc"].lower() for x in INDIA)][:CFG["max_jobs_per_company"]]
            for j in sel:
                uid = f"{c['id']}:{j['id']}"; o = oldj.get(uid)
                rec = {"uid": uid, "cid": c["id"], "company": c["name"], "type": c["type"], "title": j["title"],
                       "location": j["loc"], "url": j["url"], "posted": j["posted"],
                       "first_seen": o["first_seen"] if o else NOW.isoformat(), "baseline": o["baseline"] if o else first}
                out.append(rec)
                if not o and not first: new.append(rec)
            info["crawled"] = True; ats[c["id"]] = info
    out.sort(key=lambda j: j["posted"] or j["first_seen"], reverse=True)
    json.dump({"updated": NOW.isoformat(), "stats": stats, "jobs": out}, open(D / "jobs.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(ats, open(D / "ats.json", "w"), separators=(",", ":"))
    print(f"companies={len(comps)} jobs={len(out)} new={len(new)} coverage={stats}")
    for j in new[:50]: print("NEW:", j["company"], "-", j["title"], "-", j["location"])
    try: notify(new)
    except Exception as e: print("notify failed:", e)

if __name__ == "__main__":
    main()
