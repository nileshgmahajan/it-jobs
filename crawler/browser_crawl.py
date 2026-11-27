"""Jya companies cha job-board (API) sapadla nahi, tyanchi career page robot browser (Chromium) madhe ughadto,
JavaScript load zalyavar jobs shodhto. Jobs milale nahit tar page 'monitor' karto ani badalla tar alert deto."""
import asyncio, hashlib, json, os, re, time
from urllib.parse import urljoin
import requests
import crawl

D, NOW = crawl.D, crawl.NOW
CFG = {"workers": 4, "per_company_sec": 80, "deadline_min": 120, "max_jobs": 100}
JOBWORD = re.compile(r"\b(engineer|developer|manager|analyst|consultant|architect|designer|specialist|lead|director|intern|"
                     r"associate|scientist|executive|officer|sales|support|tester|qa|devops|administrator|head|president|trainee|"
                     r"programmer|sde|recruiter|writer|marketing|product|technician|representative|advisor|coordinator|operations|researcher)\b", re.I)
JOBHREF = re.compile(r"(/jobs?[/?]|/careers?/|/openings?|/positions?|/vacanc|/requisition|job[_-]?id|/postings?/|/opportunit|/apply/|/role)", re.I)
TITLE = ("title", "jobTitle", "job_title", "positionTitle", "postingTitle", "requisitionTitle", "jobName", "name", "text")
URLK = ("url", "applyUrl", "apply_url", "jobUrl", "job_url", "canonicalPositionUrl", "externalPath", "absolute_url", "link", "hostedUrl")
LOCK = ("location", "locations", "city", "jobLocation", "primaryLocation", "locationsText", "locationName", "office")

def pick(d, keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (str, int)) and str(v).strip(): return str(v).strip()
        if isinstance(v, list) and v and isinstance(v[0], str): return ", ".join(v[:2])
        if isinstance(v, dict):
            for kk in ("name", "city", "label", "text"):
                if isinstance(v.get(kk), str): return v[kk]
    return ""

def jobs_in_json(obj):
    """Kuthlyahi JSON madhe 'jobs sarkhi list' shodhto."""
    best, stack = [], [obj]
    while stack:
        x = stack.pop()
        if isinstance(x, list):
            ds = [i for i in x if isinstance(i, dict)]
            if len(ds) >= 3 and len(ds) >= 0.8 * len(x):
                rows = [(pick(i, TITLE), pick(i, URLK), pick(i, LOCK)) for i in ds]
                good = [r for r in rows if 4 <= len(r[0]) <= 150 and (r[1] or r[2])]
                wordy = sum(1 for r in good if JOBWORD.search(r[0]))
                if len(good) >= 3 and len(good) >= 0.7 * len(ds) and wordy >= 0.4 * len(good) and len(good) > len(best): best = good
            stack += x[:300]
        elif isinstance(x, dict):
            stack += list(x.values())
    return best

def dom_jobs(links):
    seen, out = set(), []
    for href, text in links:
        t = (text or "").strip()
        if 5 <= len(t) <= 120 and JOBWORD.search(t) and JOBHREF.search(href) and (href, t) not in seen:
            seen.add((href, t)); out.append((t, href, ""))
    return out if len(out) >= 3 else []

def digest(text):
    t = re.sub(r"\s+", " ", re.sub(r"\d+", "", text.lower()))[:30000]
    return hashlib.sha1(t.encode()).hexdigest()[:16]

async def scan(ctx, c):
    """-> (status, [(title, url, loc)], extra)   status: jobs | watch | failed"""
    site = (c.get("site") or "").rstrip("/")
    urls = list(dict.fromkeys(u for u in [c.get("careers"), site + "/careers", site] if u and u.startswith("http")))
    err = "no url"
    for u in urls[:3]:
        page, found = await ctx.new_page(), []
        async def on_resp(r):
            try:
                if "json" in (r.headers.get("content-type") or "") and r.request.resource_type in ("xhr", "fetch"):
                    rows = jobs_in_json(await r.json())
                    if rows: found.append(rows)
            except Exception: pass
        page.on("response", on_resp)
        try:
            resp = await page.goto(u, wait_until="domcontentloaded", timeout=30000)
            if resp and resp.status >= 400: raise Exception(f"http {resp.status}")
            try: await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception: pass
            for _ in range(2):
                await page.mouse.wheel(0, 4000); await page.wait_for_timeout(1000)
            await page.wait_for_timeout(1500)
            if found:
                return "jobs", [(t, urljoin(u, l) if l else u, loc) for t, l, loc in max(found, key=len)], ""
            links = await page.eval_on_selector_all("a[href]", "els=>els.map(a=>[a.href,(a.innerText||'').trim().split('\\n')[0]])")
            jobs = dom_jobs(links)
            if jobs: return "jobs", jobs, ""
            return "watch", [], digest(await page.inner_text("body"))
        except Exception as e:
            err = str(e)[:80]
        finally:
            await page.close()
    return "failed", [], err

async def crawl_all(todo, scanner, deadline):
    sem, res = asyncio.Semaphore(CFG["workers"]), {}
    async def one(c):
        async with sem:
            if time.time() > deadline: return
            try: res[c["id"]] = await asyncio.wait_for(scanner(c), CFG["per_company_sec"])
            except Exception as e: res[c["id"]] = ("failed", [], str(e)[:80] or "timeout")
    await asyncio.gather(*(one(c) for c in todo))
    return res

def merge(state, todo, res):
    oldj = {j["uid"]: j for j in state.get("jobs", [])}
    by_c = {}
    for j in state.get("jobs", []): by_c.setdefault(j["cid"], []).append(j)
    cs, out, new, changed = state.get("companies", {}), [], [], []
    for c in todo:
        cid, r = c["id"], res.get(c["id"])
        st = cs.setdefault(cid, {})
        if r is None: out += by_c.get(cid, []); continue  # velet pohochla nahi, pudhchya run madhe
        status, items, extra = r
        st["checked"] = NOW.isoformat()
        if status == "failed":
            st["status"], st["error"] = "failed", extra; out += by_c.get(cid, []); continue
        st.pop("error", None)
        if status == "jobs":
            first = not st.get("had_jobs"); st.update(status="jobs", had_jobs=True, hash=""); st.pop("pending", None)
            for t, url, loc in items:
                if crawl.CFG["india_only"] and loc and not any(k in loc.lower() for k in crawl.INDIA): continue
                uid = f"{cid}:" + hashlib.sha1(f"{url}|{t}".encode()).hexdigest()[:12]
                if any(j["uid"] == uid for j in out[-CFG["max_jobs"]:]): continue
                o = oldj.get(uid); lv, ex = crawl.classify(t)
                rec = {"level": lv, "exp": ex, "uid": uid, "cid": cid, "company": c["name"], "type": c["type"], "title": t, "location": loc, "url": url,
                       "posted": "", "first_seen": o["first_seen"] if o else NOW.isoformat(), "baseline": o["baseline"] if o else first}
                out.append(rec)
                if not o and not first: new.append(rec)
        else:  # watch: page baghto, jobs vachta ale nahit
            st["status"], h = "watch", extra
            if not st.get("hash"): st["hash"] = h
            elif h != st["hash"]:
                if st.get("pending") == h:  # donda same navin hash = khara badal, rotating content nahi
                    st["hash"], st["changed"] = h, NOW.isoformat(); st.pop("pending"); changed.append(c)
                else: st["pending"] = h
            else: st.pop("pending", None)
    return out, cs, new, changed

def tg(text):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=15,
                      json={"chat_id": chat, "text": text, "disable_web_page_preview": True})

def main():
    from playwright.async_api import async_playwright
    comps, ats = crawl.load(D / "companies.json", []), crawl.load(D / "ats.json", {})
    state = crawl.load(D / "jobs_web.json", {"jobs": [], "companies": {}})
    todo = [c for c in comps if c["id"] in ats and not ats[c["id"]].get("ats") and (c.get("careers") or c.get("site"))]
    todo.sort(key=lambda c: state["companies"].get(c["id"], {}).get("checked", ""))
    print("companies to scan:", len(todo))
    async def blk(route):
        if route.request.resource_type in ("image", "media", "font"): await route.abort()
        else: await route.continue_()
    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch()
            ctx = await b.new_context(locale="en-IN", viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
            await ctx.route("**/*", blk)
            res = await crawl_all(todo, lambda c: scan(ctx, c), time.time() + CFG["deadline_min"] * 60)
            await b.close(); return res
    res = asyncio.run(go())
    out, cs, new, changed = merge(state, todo, res)
    json.dump({"updated": NOW.isoformat(), "companies": cs, "jobs": out}, open(D / "jobs_web.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    n = {}
    for c in todo: n[cs[c["id"]].get("status", "pending")] = n.get(cs[c["id"]].get("status", "pending"), 0) + 1
    print(f"scanned={len(res)} jobs={len(out)} new={len(new)} page_changes={len(changed)} status={n}")
    for i in range(0, min(len(changed), 40), 20):
        tg("🔔 Careers page badalla (navin job asu shakte):\n" + "\n".join(f"• {c['name']}: {c.get('careers') or c.get('site')}" for c in changed[i:i + 20]))
    try: crawl.notify(new)
    except Exception as e: print("notify failed:", e)

if __name__ == "__main__":
    main()
