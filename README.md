# IT Openings Portal (auto-updating)

Company chi navin job aapoaap dista: crawler dar 1 tasanni sarva companies chya job boards tapasto ani `data/jobs.json` update karto. Website (`index.html`) toch file vachte.

## Setup (ek vel, free)
1. github.com var free account -> **New repository** (Public), naav: `it-jobs`.
2. He sarve files (`.github` folder sahit) repo madhe upload kara.
3. `lists/` folder madhe tumchi 3 lists ya naavanni taka:
   `product.txt`, `service.txt`, `startup.txt`
   (Excel madhun 3 columns: S.No, Company, Link copy karun .txt madhe paste kara. `.csv` pan chalte.)
4. Repo **Settings -> Pages** -> Source: *Deploy from a branch* -> `main` / `(root)`.
5. Repo **Settings -> Actions -> General -> Workflow permissions** -> *Read and write*.
6. **Actions** tab -> *crawl-jobs* -> **Run workflow**. Pahilya veli 10-30 min lagtat.
7. Tumchi site: `https://<tumcha-username>.github.io/it-jobs/`

Pudhe te dar 1 tasanni swatah chalte. Navin job: **New** badge (24 tas), "Posted today/yesterday" ani date filter.

## He kase kam karte
- Company chya careers page madhun Greenhouse, Lever, Ashby, SmartRecruiters kinva Workday cha link shodhto (ek vel, `data/ats.json` madhe save hoto).
- Tya system chya public API kadun saglya jobs ghet. Pahilya run madhil jobs "baseline" (New nahi), nantarche navin = **New**.
- Default fakt India madhil jobs. Sarva jagatil hava asel tar `crawler/crawl.py` madhe `"india_only": False`.

## Maryada (pramanik)
- Jya companies chi career site swatachi (custom) aahe (ex. TCS, Infosys, Accenture, Amazon) tyanche jobs ya version madhe yet nahit. `data/jobs.json` madhil `stats` madhe `"none"` = ketki companies cover zali nahit te distat.
- Tyasathi company-wise adapter lihave lagtil (`FETCH` madhe navin function) kinva paid job-data API vapra.
- Pratyek company cha job lagech nahi, 3 tasanni kalto. `cron` `"0 */3 * * *"` badlun 1 tasanni karta yeil.
- Kahi companies cha ATS slug guess karun milto; chukicha match disla tar `data/ats.json` madhun to entry kadha.

## Notification (Telegram)
1. Telegram madhe **@BotFather** -> `/newbot` -> naav dya -> tumhala **token** milto.
2. Tumchya navin bot la ek message pathva ("hi").
3. Browser madhe ughada: `https://api.telegram.org/bot<TOKEN>/getUpdates` -> tyat `"chat":{"id":123456789` ha number = **chat id**.
4. GitHub repo -> **Settings -> Secrets and variables -> Actions**:
   - *Secrets*: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - *Variables* (optional): `ALERT_KEYWORDS` = `python,java,pune` (fakt he shabd asleli jobs cha alert; rikam theva = sarve)
5. Aata navin job aali ki mobile var Telegram message yeil: title, company, city, date-time ani apply link.
Pahilya run madhe alert yet nahit (to baseline aahe), fakt tyanantarchya navin jobs cha alert yeto.
Teams/friends sathi: Telegram **channel** banva, bot la admin kara, `TELEGRAM_CHAT_ID` = `@channelname`.

## Date ani vel
- Jithe company cha API job cha publish time deto (Lever, Ashby, SmartRecruiters, Greenhouse) tithe **Posted <date, time IST>**.
- Baki thikani (ex. Workday) **Detected <date, time IST>** = aaplya crawler la ti job pahilyanda keva disli.
