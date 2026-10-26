د Telegram Bot د Render لپاره

فایلونه:
- bot.py: ستاسو اصلي فایل
- database.py: SQLite ډیټابېس او د اډمین/چینل عملیات
- styles.py: د متن سټایلونه او د پاڼو جوړول
- requirements.txt: د Python کتابتونونه

Render:
1) دا ZIP په خپل Android موبایل کې خلاص کړئ.
2) ټول څلور فایلونه GitHub Repository ته پورته کړئ (د ZIP فایل پخپله د Python کوډ په توګه مه اجرا کوئ).
3) په Render کې New + > Background Worker که د قیمت برخه کې وړیا نه وي، د وړیا پلان لپاره یې مه ټاکئ.
4) د Build Command: pip install -r requirements.txt
5) د Start Command: python bot.py
6) Environment Variables:
   BOT_TOKEN = د BotFather څخه خپل پټ Token
   OWNER_ID = 8062657182 (که دا ستاسو Telegram ID وي؛ که نه، خپل سم عددي ID ولیکئ)
   DB_PATH = font_style_bot.sqlite3

مهم:
- د Render د فایل‌سیستم SQLite ډیټابېس د وړیا Web Service په بیا جوړېدو/بیا چالانېدو کې له منځه تللی شي؛ دایمي معلوماتو لپاره persistent disk یا بهرنی ډیټابېس ته اړتیا وي.
- دا ZIP د موجود bot.py پر بنسټ د اړینو فایلونو جوړ شوی نسخه ده؛ ځکه اصلي database.py او styles.py نه وو، د دوی دقیق اصلي چلند تضمین کېدای نه شي.
- د کوډ له چلولو مخکې ټیسټ وکړئ. BOT_TOKEN په عام GitHub Repository کې مه اچوئ.
