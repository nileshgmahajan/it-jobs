"""Roj sakali Telegram var: gelya 24 tasat aalelya Fresher jobs cha summary.
Variable DIGEST_LEVELS (default: fresher). Udaharan: fresher,junior"""
import datetime as dt, json, os, pathlib
import requests

D = pathlib.Path(__file__).resolve().parent.parent / "data"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

def load(name):
    try: return json.load(open(D / name, encoding="utf-8")).get("jobs", [])
    except Exception: return []

def when(j): return dt.datetime.fromisoformat(j["posted"] or j["first_seen"])

def build(jobs, now, levels):
    rec = sorted([j for j in jobs if j.get("level") in levels and now - when(j) < dt.timedelta(hours=24)], key=when, reverse=True)
    prev = [j for j in jobs if j.get("level") in levels and dt.timedelta(hours=24) <= now - when(j) < dt.timedelta(hours=48)]
    by = {}
    for j in rec: by[j["type"]] = by.get(j["type"], 0) + 1
    head = f"🎓 {'/'.join(levels).title()} jobs, gelya 24 tasat: {len(rec)} (kal: {len(prev)})"
    if by: head += "\n" + " · ".join(f"{k}: {v}" for k, v in by.items())
    if not rec: return [head + "\nAaj navin job sapadli nahi."]
    lines = [f"• {j['title']}\n  {j['company']} · {j['location'] or '-'} · {when(j).astimezone(IST).strftime('%d %b, %I:%M %p')}\n  {j['url']}" for j in rec[:40]]
    if len(rec) > 40: lines.append(f"+{len(rec)-40} ajun, site var paha.")
    msgs, cur = [], head + "\n\n"
    for l in lines:
        if len(cur) + len(l) > 3500: msgs.append(cur); cur = ""
        cur += l + "\n\n"
    return msgs + [cur]

def main():
    levels = [x.strip().lower() for x in (os.environ.get("DIGEST_LEVELS") or "fresher").split(",") if x.strip()]
    msgs = build(load("jobs.json") + load("jobs_web.json"), dt.datetime.now(dt.timezone.utc), levels)
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    for m in msgs:
        print(m)
        if tok and chat:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=15,
                          json={"chat_id": chat, "text": m, "disable_web_page_preview": True})

if __name__ == "__main__":
    main()
