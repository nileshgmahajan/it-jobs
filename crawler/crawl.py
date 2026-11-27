"""Pratyek company chya career page var kuthli job-board system (ATS) vaparli aahe te shodhto,
tithun jobs ghet aani navin jobs 'first_seen' sobat data/jobs.json madhe save karto."""
import html as htmllib, json, os, re, pathlib, datetime as dt, concurrent.futures as cf
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data"
CFG = {"india_only": True, "max_jobs_per_company": 150, "workers": 16, "timeout": 12, "retry_discovery_days": 14}
INDIA = ["india", "pune", "mumbai", "bengaluru", "bangalore", "hyderabad", "chennai", "delhi", "noida", "gurgaon",
         "gurugram", "kolkata", "ahmedabad", "nagpur", "nashik", "kochi", "coimbatore", "jaipur", "indore", "chandigarh",
         "thiruvananthapuram", "trivandrum", "mysuru", "vadodara", "bhubaneswar", "mohali", "thane", "kolhapur"]
H = {"User-Agent": "Mozilla/5.0 (compatible; JobWatch/1.0)", "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
NOW = dt.datetime.now(dt.timezone.utc)
BAD = {"embed", "v1", "js", "api", "assets", "static", "oembed", "company", "jobs", "careers", "www", "cdn", "static", "login"}

def get(u):
    r = requests.get(u, headers=H, timeout=CFG["timeout"]); r.raise_for_status(); return r

def iso(v):
    if not v: return ""
    try:
        if isinstance(v, (int, float)): return dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc).isoformat()
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return ""

SENIOR = re.compile(r"\b(senior|sr\.?|lead|principal|staff|manager|director|head|vp|vice president|architect|chief|distinguished|fellow|iii|iv|sde[- ]?(3|iii))\b", re.I)
FRESH = re.compile(r"\b(intern|interns|internship|trainee|trainees|fresher|freshers|graduate|graduates|campus|entry[- ]level|apprentice|apprenticeship|new grad|early career|early talent)\b", re.I)
JUNIOR = re.compile(r"\b(junior|jr\.?|associate|sde[- ]?(1|i)|(engineer|developer|analyst|consultant|scientist|designer|tester)[- ](1|i)|level[- ]?1|l1)\b", re.I)
MID = re.compile(r"\b(ii|sde[- ]?(2|ii)|(engineer|developer|analyst|consultant|scientist|designer)[- ](2|ii)|level[- ]?2|l2)\b", re.I)
YR1 = re.compile(r"(\d{1,2})\s*(?:\+|-|\u2013|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b[^.]{0,40}?experience", re.I)
YR2 = re.compile(r"experience[^.]{0,30}?(\d{1,2})\s*(?:\+|-|\u2013|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b", re.I)

def classify(title, desc=""):
    """-> (level, exp_text). level: fresher | junior | mid | senior | unknown.
    Title varun, ani description milali (Lever/Ashby/Workable) tar 'X years experience' varun."""
    t = title or ""
    d = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", desc or "")))[:8000]
    m = YR1.search(d) or YR2.search(d)
    yrs, exp = None, ""
    if m:
        yrs = int(m[1]); hi = int(m[2]) if m[2] else None
        exp = f"{yrs}-{hi} yrs" if hi and hi > yrs else (f"{yrs}+ yrs" if yrs else "0-1 yrs")
    if re.search(r"associate product manager|\bapm\b", t, re.I): return "junior", exp
    if SENIOR.search(t): return "senior", exp
    if FRESH.search(t): return "fresher", exp
    if yrs is not None: return ("fresher" if yrs <= 1 else "junior" if yrs <= 3 else "mid" if yrs <= 6 else "senior"), exp
    if MID.search(t): return "mid", exp
    if JUNIOR.search(t): return "junior", exp
    if re.search(r"\bfreshers?\b", d, re.I): return "fresher", exp
    return "unknown", exp

def f_greenhouse(s):
    return [dict(id=str(j["id"]), title=j["title"], loc=(j.get("location") or {}).get("name", ""),
                 url=j["absolute_url"], posted=iso(j.get("first_published")))
            for j in get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs").json()["jobs"]]

def f_lever(s):
    return [dict(id=j["id"], title=j["text"], loc=(j.get("categories") or {}).get("location") or "",
                 url=j["hostedUrl"], posted=iso(j.get("createdAt")), desc=j.get("descriptionPlain") or "")
            for j in get(f"https://api.lever.co/v0/postings/{s}?mode=json").json()]

def f_ashby(s):
    return [dict(id=j["id"], title=j["title"], loc=j.get("location") or "", url=j.get("jobUrl") or "",
                 posted=iso(j.get("publishedAt") or j.get("publishedDate")), desc=j.get("descriptionPlain") or "")
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

def f_workable(s):
    return [dict(id=str(j.get("shortcode") or j.get("id")), title=j["title"],
                 loc=", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x),
                 url=j.get("url") or f"https://apply.workable.com/{s}/j/{j.get('shortcode')}/",
                 posted=iso(j.get("published_on") or j.get("created_at")), desc=j.get("description") or "")
            for j in get(f"https://apply.workable.com/api/v1/widget/accounts/{s}?details=true").json().get("jobs", [])]

def f_recruitee(s):
    return [dict(id=str(o["id"]), title=o["title"], loc=o.get("location") or ", ".join(x for x in [o.get("city"), o.get("country")] if x),
                 url=o.get("careers_url") or f"https://{s}.recruitee.com", posted=iso(o.get("published_at") or o.get("created_at")))
            for o in get(f"https://{s}.recruitee.com/api/offers/").json().get("offers", [])]

def f_bamboo(s):
    out = []
    for j in get(f"https://{s}.bamboohr.com/careers/list").json().get("result", []):
        l = j.get("location") or {}
        out.append(dict(id=str(j["id"]), title=j["jobOpeningName"], loc=", ".join(x for x in [l.get("city"), l.get("state")] if x),
                        url=f"https://{s}.bamboohr.com/careers/{j['id']}", posted=""))
    return out

def f_breezy(s):
    return [dict(id=str(j["id"]), title=j["name"], loc=str((j.get("location") or {}).get("name") or ""),
                 url=j.get("url") or f"https://{s}.breezy.hr", posted=iso(j.get("published_date")))
            for j in get(f"https://{s}.breezy.hr/json").json()]

def f_personio(s):
    root = ET.fromstring(get(f"https://{s}.jobs.personio.de/xml").content)
    return [dict(id=p.findtext("id"), title=p.findtext("name") or "", loc=p.findtext("office") or "",
                 url=f"https://{s}.jobs.personio.de/job/{p.findtext('id')}", posted=iso(p.findtext("createdAt")))
            for p in root.iter("position")]

def f_jsonld(u):
    """Career page var Google-for-Jobs sathi JobPosting (schema.org) data aasel tar to vachto."""
    out = []
    for blk in re.findall(r'<script[^>]+ld\+json[^>]*>(.*?)</script>', get(u).text, re.S | re.I):
        try: stack = [json.loads(blk)]
        except Exception: continue
        while stack:
            x = stack.pop()
            if isinstance(x, list): stack += x
            elif isinstance(x, dict):
                t = x.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    loc = x.get("jobLocation"); loc = loc[0] if isinstance(loc, list) and loc else loc
                    a = loc.get("address", {}) if isinstance(loc, dict) else {}
                    a = a if isinstance(a, dict) else {}
                    c = a.get("addressCountry"); c = c.get("name") if isinstance(c, dict) else c
                    L = ", ".join(str(v) for v in [a.get("addressLocality"), a.get("addressRegion"), c] if v)
                    out.append(dict(id=str(x.get("url") or f"{x.get('title')}|{L}"), title=str(x.get("title", "")), loc=L,
                                    url=str(x.get("url") or u), posted=iso(x.get("datePosted"))))
                stack += [v for v in x.values() if isinstance(v, (dict, list))]
    return out

FETCH = {"greenhouse": f_greenhouse, "lever": f_lever, "ashby": f_ashby, "smartrecruiters": f_smart, "workday": f_workday, "workable": f_workable,
         "recruitee": f_recruitee, "bamboohr": f_bamboo, "breezy": f_breezy, "personio": f_personio, "jsonld": f_jsonld}
RX = [("greenhouse", r"greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)"),
      ("lever", r"jobs\.lever\.co/([A-Za-z0-9_-]+)"), ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)"),
      ("smartrecruiters", r"smartrecruiters\.com/([A-Za-z0-9_-]+)"),
      ("workable", r"apply\.workable\.com/([A-Za-z0-9_-]+)"), ("recruitee", r"([a-z0-9-]+)\.recruitee\.com"),
      ("bamboohr", r"([a-z0-9-]+)\.bamboohr\.com"), ("breezy", r"([a-z0-9-]+)\.breezy\.hr"),
      ("personio", r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)")]
SIGNS = ["icims.com", "taleo.net", "successfactors", "oraclecloud.com", "eightfold.ai", "phenom", "darwinbox", "keka.com",
         "zohorecruit", "zoho.com/recruit", "freshteam", "jobvite", "teamtailor", "comeet", "jazzhr", "applytojob",
         "naukri.com", "avature", "brassring", "cornerstone", "adp.com", "ultipro", "paylocity", "dayforce"]

def find_ats(html):
    m = re.search(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Za-z]{2}/)?([A-Za-z0-9_-]+)", html)
    if m: return "workday", f"{m[1]}|{m[2]}|{m[3]}"
    for ats, rx in RX:
        for m in re.finditer(rx, html):
            if m[1].lower() not in BAD: return ats, m[1]
    return None

def discover(c):
    """Return ((ats, slug) ya None, hint). hint = je system disla pan aaplyala adapter nahi."""
    site = (c.get("site") or "").rstrip("/")
    pages = list(dict.fromkeys(u for u in [c.get("careers"), site, site + "/careers", site + "/jobs"] if u and u.startswith("http")))
    hints = set()
    for u in pages:
        try: html = get(u).text
        except Exception: hints.add("unreachable"); continue
        f = find_ats(html)
        if f: return f, ""
        if "JobPosting" in html and "ld+json" in html: return ("jsonld", u), ""
        low = html.lower(); hints.update(x for x in SIGNS if x in low)
        if len(html) < 6000: hints.add("js-only?")
    dom = re.sub(r"^www\.", "", urlparse(site).netloc).split(".")[0] if site else ""
    base = re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", c["name"].lower()))
    for slug in dict.fromkeys(x for x in [base, dom] if x):  # last resort: guess the board name
        for ats in ("greenhouse", "lever", "ashby"):
            try:
                if FETCH[ats](slug): return (ats, slug), ""
            except Exception:
                pass
    return None, ",".join(sorted(hints)) or "custom"

def work(c, info):
    try:
        stale = info and not info.get("ats") and (info.get("v") != 2 or
                (NOW - dt.datetime.fromisoformat(info.get("checked", "2000-01-01T00:00:00+00:00"))).days >= CFG["retry_discovery_days"])
        if not info or stale:
            f, hint = discover(c)
            info = {"ats": f[0], "slug": f[1], "v": 2} if f else {"ats": None, "checked": NOW.isoformat(), "hint": hint, "v": 2}
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
    lvs = [k.strip().lower() for k in os.environ.get("ALERT_LEVELS", "").split(",") if k.strip()]
    if lvs: new = [j for j in new if j.get("level", "unknown") in lvs]
    if kws: new = [j for j in new if any(k in f"{j['title']} {j['location']} {j['company']}".lower() for k in kws)]
    if not (tok and chat and new): return
    def send(t):
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=15,
                      json={"chat_id": chat, "text": t, "disable_web_page_preview": True})
    lines = [f"🆕 {j['title']}{' 🎓 FRESHER' if j.get('level') == 'fresher' else ''}\n🏢 {j['company']} ({j['type']})\n📍 {j['location'] or '-'}\n"
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
    out, new, stats, hints = [], [], {}, {}
    with cf.ThreadPoolExecutor(CFG["workers"]) as ex:
        for c, info, jobs in ex.map(lambda c: work(c, ats.get(c["id"])), comps):
            info = dict(info); info["crawled"] = ats.get(c["id"], {}).get("crawled", False)
            k = info.get("ats") or "none"; stats[k] = stats.get(k, 0) + 1
            if k == "none":
                for h in (info.get("hint") or "custom").split(","): hints[h] = hints.get(h, 0) + 1
            if jobs is None:
                out += by_c.get(c["id"], []); ats[c["id"]] = info; continue
            first = not info["crawled"]
            sel = [j for j in jobs if not CFG["india_only"] or info["ats"] == "workday"
                   or any(x in j["loc"].lower() for x in INDIA)][:CFG["max_jobs_per_company"]]
            for j in sel:
                uid = f"{c['id']}:{j['id']}"; o = oldj.get(uid)
                lv, ex = classify(j["title"], j.get("desc", ""))
                rec = {"level": lv, "exp": ex, "uid": uid, "cid": c["id"], "company": c["name"], "type": c["type"], "title": j["title"],
                       "location": j["loc"], "url": j["url"], "posted": j["posted"],
                       "first_seen": o["first_seen"] if o else NOW.isoformat(), "baseline": o["baseline"] if o else first}
                out.append(rec)
                if not o and not first: new.append(rec)
            info["crawled"] = True; ats[c["id"]] = info
    out.sort(key=lambda j: j["posted"] or j["first_seen"], reverse=True)
    json.dump({"updated": NOW.isoformat(), "stats": stats, "hints": hints, "jobs": out}, open(D / "jobs.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(ats, open(D / "ats.json", "w"), separators=(",", ":"))
    print(f"companies={len(comps)} jobs={len(out)} new={len(new)} coverage={stats} hints={hints}")
    for j in new[:50]: print("NEW:", j["company"], "-", j["title"], "-", j["location"])
    try: notify(new)
    except Exception as e: print("notify failed:", e)

if __name__ == "__main__":
    main()
