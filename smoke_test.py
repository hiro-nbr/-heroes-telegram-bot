# -*- coding: utf-8 -*-
"""تست عملکردی بخش‌های مختلف ربات (بدون نیاز به توکن واقعی)."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import bot  # noqa: E402

results = []

def check(name, condition):
    results.append((name, bool(condition)))
    print(("✅" if condition else "❌") + " " + name)

# ۱) ایمپورت موفق
check("import bot", True)

# ۲) ساختار کارمندها
check("تیم ۱۲۵ نفره کامل است (۵ پایه + ۱۰۰ اضافه از employees.py)",
      len(bot.EMPLOYEES) == 125 and len(bot.EXTRA_EMPLOYEES) == 100)
check("هیرو اولین کارمند است و چت ساده‌ی خودمونی دارد",
      list(bot.EMPLOYEES)[0] == "hiro"
      and bot.EMPLOYEES["hiro"]["name"] == "هیرو"
      and "چت" in bot.EMPLOYEES["hiro"]["role"])
check("هر کارمند پرامپت و نقش دارد",
      all(all(k in e for k in ("name", "role", "emoji", "duty", "system_prompt"))
          for e in bot.EMPLOYEES.values()))
check("پرامپت‌ها فارسی و کامل هستند",
      all(len(e["system_prompt"]) > 100 for e in bot.EMPLOYEES.values()))

# ۳) حافظه‌ی گفتگو (دیتابیس SQL)
for leftover in ("test_memory.db", "test_mig.json", "test_mig.json.bak"):
    if os.path.exists(leftover):
        os.remove(leftover)
s = bot.SQLStore("test_memory.db", context_max_messages=bot.CONTEXT_MAX_MESSAGES)
s.append(1, "manager", "user", "سلام")
s.append(1, "manager", "assistant", "سلام! چطور کمک کنم؟")
check("ذخیره و خواندن حافظه در دیتابیس SQL", len(s.get_history(1, "manager")) == 2)
for i in range(160):
    s.append(1, "manager", "user", f"msg{i}")
hist = s.get_history(1, "manager")
check("حافظه بلندمدت شد: ۱۵۰ پیام قبلی را یادش می‌ماند (قبلاً فقط ۲۰ پیام بود)",
      len(hist) == bot.CONTEXT_MAX_MESSAGES and "msg20" in [m["content"] for m in hist])
check("هیچ پیامی از بین نمی‌رود (بایگانی کامل در دیتابیس)",
      "سلام" in [m["content"] for m in s.get_all(1, "manager")])
# ── چت جدید (نشست‌ها): حافظه از نو، بایگانی حفظ ──
s.append(1, "writer", "user", "پیام چت قدیمی")
s.append(1, "writer", "assistant", "جواب چت قدیمی")
s.new_chat(1, "writer")
s.append(1, "writer", "user", "پیام چت جدید")
check("چت جدید: حافظه‌ی گفتگو از نو شروع می‌شود",
      [m["content"] for m in s.get_history(1, "writer")] == ["پیام چت جدید"])
check("چت جدید: بایگانی چت‌های قبلی حفظ می‌شود",
      "جواب چت قدیمی" in [m["content"] for m in s.get_all(1, "writer")])
s.append(1, "writer", "assistant", "جواب چت جدید")
s.delete_last(1, "writer", "assistant")
check("پاسخ دوباره: آخرین جواب برداشته می‌شود",
      [m["content"] for m in s.get_history(1, "writer")][-1] == "پیام چت جدید")
s.clear(1)
import json as _json
with open("test_mig.json", "w", encoding="utf-8") as f:
    _json.dump({"55": {"manager": [{"role": "user", "content": "پیام قدیمی"}]}}, f, ensure_ascii=False)
s.migrate_json("test_mig.json", None)
check("انتقال خودکار فایل‌های JSON قدیمی به دیتابیس",
      "پیام قدیمی" in [m["content"] for m in s.get_all(55, "manager")]
      and os.path.exists("test_mig.json.bak") and not os.path.exists("test_mig.json"))
s.clear(1)
s.clear(55)
check("پاک کردن حافظه از دیتابیس", s.get_history(1, "manager") == [] and s.overview(1) == [])
s.close()   # بستن اتصال دیتابیس تا ویندوز اجازه‌ی حذف فایل را بدهد
if os.path.exists("test_memory.db"):
    os.remove("test_memory.db")
if os.path.exists("test_mig.json.bak"):
    os.remove("test_mig.json.bak")

# ۴) کیبوردها
check("منوی اصلی ۷ دکمه دارد (هیرو، تیم، گفتگو، تسک، هیستوری، پاک کردن، دعوت دوستان)",
      len(bot.main_menu().inline_keyboard) == 7
      and bot.main_menu().inline_keyboard[0][0].callback_data == "chat:hiro"
      and bot.main_menu().inline_keyboard[-1][0].callback_data == "invite")
tk = bot.employee_keyboard("chat")
total_pages = -(-len(bot.EMPLOYEES) // 20)   # ۲۰ نفر در هر صفحه
first_page_rows = -(-min(len(bot.EMPLOYEES), 20) // 2) + 2   # ردیف‌های اعضا + ناوبری + منو
check("کیبورد صفحه‌بندی‌شده‌ی کارمندها درست است",
      len(tk.inline_keyboard) == first_page_rows and "بعدی" in tk.inline_keyboard[-2][-1].text)
check("کال‌بک دیتای دکمه‌ها درست است",
      tk.inline_keyboard[0][0].callback_data == "chat:" + list(bot.EMPLOYEES)[0])
kp = bot.employee_keyboard("chat", total_pages - 1)
check("صفحه‌ی آخر کیبورد آخرین عضو و دکمه‌ی قبلی را دارد",
      kp.inline_keyboard[0][0].callback_data == "chat:" + list(bot.EMPLOYEES)[(total_pages - 1) * 20]
      and "قبلی" in kp.inline_keyboard[-2][0].text)

# ۵) متن‌ها
wt = bot.welcome_text()
pages = bot.team_pages()
check("متن خوش‌آمد تعداد اعضا را نشان می‌دهد و امکانات ویژه را معرفی می‌کند",
      str(len(bot.EMPLOYEES)) in wt and "🔁 پاسخ دوباره" in wt)
check("Markdown → HTML تلگرام (پررنگ/کد)",
      bot.md_to_html("**سلام** `code`") == "<b>سلام</b> <code>code</code>")
check("امنیت: HTML خام در جواب‌ها escape می‌شود",
      bot.md_to_html("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;")
check("دکمه‌های زیر هر جواب: پاسخ دوباره، چت جدید و امتیاز 👍/👎",
      bot.answer_keyboard("manager").inline_keyboard[0][0].callback_data == "regen:manager"
      and bot.answer_keyboard("manager").inline_keyboard[0][1].callback_data == "newchat:manager"
      and bot.answer_keyboard("manager").inline_keyboard[1][0].callback_data == "rate:up:manager"
      and bot.answer_keyboard("manager").inline_keyboard[1][1].callback_data == "rate:down:manager")
check("دکمه‌ی توقف پاسخ فعال است", "⏹" in bot.stop_keyboard().inline_keyboard[0][0].text)
check("پاسخ زنده (استریم)، دستور /new و منوی دستورات آماده‌اند",
      callable(bot.stream_answer) and callable(bot.cmd_new) and callable(bot.post_init))
check("معرفی تیم همه‌ی اعضا را پوشش می‌دهد",
      all(e["name"] in "\n".join(pages) for e in bot.EMPLOYEES.values()))
check("پیام‌های معرفی تیم زیر محدودیت ۴۰۹۶ کاراکتر تلگرام هستند",
      all(len(p) <= 4096 for p in pages))

# ۶) چت هیستوری — دیتابیس (همان SQLStore)
if os.path.exists("test_history.db"):
    os.remove("test_history.db")
h = bot.SQLStore("test_history.db")
h.add(42, "manager", "user", "سلام <b>تست</b>")
h.add(42, "manager", "assistant", "سلام!")
h.add(43, "manager", "user", "کاربر دیگر")
check("بایگانی برای هر کاربر جدا است",
      len(h.get_all(42, "manager")) == 2 and len(h.get_all(43, "manager")) == 1)
for i in range(30):
    h.add(42, "manager", "user", f"پیام{i}")
check("بایگانی سقف پیام ندارد و همه حفظ می‌شود", len(h.get_all(42, "manager")) == 32)
check("فهرست گفتگوها تعداد پیام‌ها را درست نشان می‌دهد (به تفکیک چت)",
      h.overview(42)[0][0] == "manager" and h.overview(42)[0][2] == 32)
h.clear(42)
check("پاک کردن بایگانی یک کاربر کار می‌کند",
      h.get_all(42, "manager") == [] and len(h.get_all(43, "manager")) == 1)
h.clear(43)
h.close()
if os.path.exists("test_history.db"):
    os.remove("test_history.db")

# ۶٫۵) کاربران، امتیازها و آمار (مود استارتاپ)
if os.path.exists("test_users.db"):
    os.remove("test_users.db")
u = bot.SQLStore("test_users.db")
check("ثبت پروفایل کاربر جدید", u.touch_user(77, "هیراد") is True and u.user_info(77) is not None)
u.touch_user(77, "هیراد")
check("کاربر تکراری دوباره ثبت نمی‌شود", u.user_info(77)["name"] == "هیراد")
u.incr_user(77)
u.incr_user(77)
check("شمارنده‌ی پیام کاربر کار می‌کند", u.user_info(77)["msg_count"] == 2)
u.add(77, "manager", "user", "امروز")
check("پیام‌های امروز شمرده می‌شود", u.messages_today(77) == 1)
u.add_rating(77, "manager", 1)
u.add_rating(77, "writer", -1)
check("ثبت رأی 👍/👎 و جمع‌بندی درست", u.rating_summary() == (1, 1))
check("شمارش کل کاربران و پیام‌ها", u.count_users() == 1 and u.count_messages() >= 1)
check("فهرست کاربران برای برادکست", u.all_user_ids() == ["77"])
check("کارمند موردعلاقه پیدا می‌شود", u.fav_employee(77) == "manager")
u.touch_user(88, "دوست", referred_by="77")
check("رفرال ثبت می‌شود و شمارنده‌ی دعوت بالا می‌رود",
      u.user_info(88)["referred_by"] == "77" and u.invited_count(77) == 1)
u.touch_user(88, "دوست", referred_by="999")
check("رفرال بعد از ثبت اولیه تغییر نمی‌کند", u.user_info(88)["referred_by"] == "77")
check("پرمشغله‌ترین کارمندها درست است", u.top_employees(5) == [("manager", 1)])
u.close()
if os.path.exists("test_users.db"):
    os.remove("test_users.db")
check("تنظیمات استارتاپ (ظرفیت روزانه، ادمین، متن ظرفیت) موجود است",
      bot.FREE_DAILY_LIMIT > 0 and isinstance(bot.ADMIN_IDS, list)
      and callable(bot._is_admin) and "ظرفیت" in bot.limit_text())
check("دستورهای /stats و /admin و /broadcast آماده‌اند",
      all(callable(getattr(bot, f"cmd_{c}")) for c in ("stats", "admin", "broadcast")))
check("لینک دعوت رفرال درست ساخته می‌شود",
      bot.invite_link("mybot", 123) == "https://t.me/mybot?start=ref123")

# ۶٫۶) گیمیفیکیشن — XP، سطح، استریک و لیدربرد
import time as _t
if os.path.exists("test_game.db"):
    os.remove("test_game.db")
g = bot.SQLStore("test_game.db")
g.touch_user(10, "کاربر ده")
g.award_xp(10, 30)
check("XP ثبت می‌شود", g.user_info(10)["xp"] == 30)
g.award_xp(10, bot.XP_PER_REFERRAL)
check("پاداش رفرال به XP اضافه می‌شود", g.user_info(10)["xp"] == 55)
check("سطح از XP درست حساب می‌شود",
      bot.level_from_xp(0)[0] == 1 and bot.level_from_xp(55)[0] == 2
      and bot.level_from_xp(99999)[2] is None)
check("نوار پیشرفت درست است",
      bot.progress_bar(25) == "▰▰▱▱▱" and bot.progress_bar(50) == "▱▱▱▱▱"
      and bot.progress_bar(99999) == "▰▰▰▰▰")
st, changed = g.bump_streak(10)
check("اولین فعالیت، استریک ۱ می‌شود", st == 1 and changed is True)
st2, changed2 = g.bump_streak(10)
check("فعالیت دوم در همان روز، استریک را خراب نمی‌کند", (st2, changed2) == (1, False))
yesterday = _t.strftime("%Y-%m-%d", _t.localtime(_t.time() - 86400))
g._conn.execute("UPDATE users SET last_day = ? WHERE user_id = '10'", (yesterday,))
g._conn.commit()
st3, _ = g.bump_streak(10)
check("فعالیت در روز بعد، استریک را بالا می‌برد", st3 == 2)
g.touch_user(20, "کاربر بیست")
g.award_xp(20, 200)
board = g.leaderboard(10)
check("لیدربرد بر اساس XP مرتب می‌شود", board[0][0] == "20" and board[0][2] == 200 and len(board) == 2)
check("رتبه‌ی کاربران در لیدربرد", g.user_rank(10) == 2 and g.user_rank(20) == 1)
g.add(10, "manager", "user", "پیام امروز")
chart = bot.weekly_chart(g.weekly_activity())
check("نمودار هفتگی ادمین ساخته می‌شود", "▇" in chart and "1" in chart)
check("دستور /top و ثابت‌های گیمیفیکیشن آماده‌اند",
      callable(bot.cmd_top) and bot.XP_PER_MESSAGE > 0 and bot.XP_WELCOME_BONUS > 0 and len(bot.LEVELS) >= 4)

# ۶٫۷) حالت خودکار — بدون انتخاب کارمند، مدیر تیم بهترین نفر را وصل می‌کند
check("مود خودکار روشن و مسیریاب آفلاین آماده است", bot.AUTO_ROUTE is True and callable(bot.keyword_route))
routed = bot.keyword_route("یک ایده‌ی بازاریابی برای اینستاگرام می‌خواهم")
check("مسیریاب آفلاین کلیدواژه‌ی فارسی را می‌فهمد", routed in bot.EMPLOYEES)
check("مسیریاب برای پیام نامربوط None برمی‌گرداند", bot.keyword_route("زرتشت زرزر") is None)
check("مسیریاب هوشمند (مدیر تیم) آماده است", callable(bot.ai_route))
check("پنل جلسه‌ی فوری ۳ نفره است و مدیر پروژه در آن هست",
      len(bot.meeting_panel("شعر و ترانه")) == 3 and "manager" in bot.meeting_panel("شعر و ترانه"))
check("استارتر پک سه سؤال آماده می‌سازد",
      len(bot.starter_questions("manager")) == 3
      and bot.EMPLOYEES["manager"]["name"] in bot.starter_questions("manager")[0]
      and bot.starter_questions("nobody") == [])
if os.path.exists("test_exp.db"):
    os.remove("test_exp.db")
e = bot.SQLStore("test_exp.db")
first_emp = list(bot.EMPLOYEES)[0]
e.add(77, first_emp, "user", "سلام چطور کتاب بنویسم؟")
e.add(77, first_emp, "assistant", "با نوشتن روزانه شروع کن")
txt = bot.export_text(77, first_emp, e)
check("خروجی گفتگو شامل نام کارمند و متن پیام‌ها است",
      "سلام چطور کتاب بنویسم؟" in txt and "نوشتن روزانه" in txt and "👤" in txt)
e.close()
if os.path.exists("test_exp.db"):
    os.remove("test_exp.db")
check("پیام صوتی، جلسه‌ی فوری و خروجی فایل آماده‌اند",
      callable(bot.handle_voice) and callable(bot.cmd_meeting) and callable(bot.cmd_export)
      and bot.WHISPER_MODEL)

# ۶٫۸) قفل تخصص — هر کار فقط دستِ متخصصِ خودش است
check("کد پایتون فقط دست بهراد است",
      bot.skill_owner("یه کد پایتون برام بنویس") == ("developer", "کدنویسی و برنامه‌نویسی"))
check("سناریو فقط دست نگار است",
      bot.skill_owner("سناریوی یه ویدیو بنویس") == ("scenario_writer", "سناریو و فیلمنامه"))
check("کمپین تبلیغاتی فقط دست ساراست", bot.skill_owner("کمپین تبلیغاتی بچین")[0] == "marketer")
check("کد تخفیف فریب قفل را نمی‌دهد",
      bot.skill_owner("یه سناریو بنویس براش کد تخفیف")[0] == "scenario_writer")
check("پیام عادی قفل نمی‌خورد", bot.skill_owner("سلام خوبی؟ چه خبر") is None)
check("نگار حق کد دادن ندارد ولی بهراد دارد",
      bot.skill_owner("پایتون بنویس برام")[0] == "developer"
      and bot.skill_owner("پایتون بنویس برام")[0] != "scenario_writer")
check("قفل تخصص برای هسته‌ی تیم تنظیم شده",
      {"developer", "scenario_writer", "marketer", "manager"} <= set(bot.EXCLUSIVE_SKILLS))
g.close()
if os.path.exists("test_game.db"):
    os.remove("test_game.db")

# ۷) چت هیستوری — توابع ربات (با بایگانی واقعی bot.archive)
uid = 999999
bot.archive.clear(uid)
bot.archive.add(uid, "manager", "user", "سلام <b>تست</b> تلگرام")
bot.archive.add(uid, "manager", "assistant", "سلام! چه کمکی می‌توانم بکنم؟")
ov = bot.history_overview_text(uid)
kbh = bot.history_keyboard(uid)
hp = bot.history_pages(uid, "manager", 1)
check("فهرست چت هیستوری کاربر ساخته می‌شود", "چت هیستوری تو" in ov and "1 گفتگو" in ov)
check("کیبورد هیستوری دکمه‌ی گفتگو را دارد (با شماره‌ی چت)", kbh.inline_keyboard[0][0].callback_data == "hview:manager:1:0")
check("تاریخچه با نام فرستنده و فرمت امن HTML نمایش داده می‌شود",
      len(hp) == 1 and "👤 شما" in hp[0] and "&lt;b&gt;" in hp[0])
check("صفحات تاریخچه زیر سقف ۴۰۹۶ کاراکتر تلگرام هستند", all(len(p) <= 4096 for p in hp))
for i in range(25):   # ۲۵ گفتگوی دیگر برای تست صفحه‌بندی فهرست
    bot.archive.add(uid, f"emp{i}", "user", f"پیام {i}")
kbh2 = bot.history_keyboard(uid)
nav_rows = [r for r in kbh2.inline_keyboard
            if any(b.callback_data and b.callback_data.startswith("hpage:") for b in r)]
check("فهرست هیستوری ۲۰ گفتگو در هر صفحه با دکمه‌ی بعدی صفحه‌بندی می‌شود",
      len(kbh2.inline_keyboard[0]) == 2 and nav_rows and "بعدی" in nav_rows[0][-1].text)
check("پاک کردن یک گفتگو از بایگانی کار می‌کند",
      (bot.archive.clear(uid, "manager"), bot.archive.get_all(uid, "manager") == [])[1])
bot.archive.clear(uid)
check("پاک کردن کل بایگانی کاربر کار می‌کند", bot.archive.overview(uid) == [])
check("کاربر بدون سابقه پیام راهنمای چت هیستوری می‌گیرد",
      "هنوز گفتگویی ثبت نشده" in bot.history_overview_text(uid)
      and len(bot.history_keyboard(888888).inline_keyboard) == 1)

# ۸) validate_config — بسته به وضعیت توکن‌ها رفتار درست باید داشته باشد
has_placeholder = ("اینجا" in bot.TELEGRAM_TOKEN) or ("اینجا" in bot.GROQ_API_KEY)
try:
    bot.validate_config()
    check("validate_config: توکن‌ها پر شده‌اند و ربات اجازه‌ی اجرا دارد", not has_placeholder)
except SystemExit:
    check("validate_config: پلیس‌هولدر است و درست اجرا را متوقف می‌کند", has_placeholder)

# ۹) مسیر ویس — پیام تلگرام frozen است؛ متن ویس باید با override_text به handle_message برسد
import asyncio
import datetime as _dt
import inspect
from types import SimpleNamespace

from telegram import Chat as TgChat, Message as TgMessage, User as TgUser

_vm = TgMessage(message_id=1, date=_dt.datetime.now(), chat=TgChat(1, type=TgChat.PRIVATE),
                from_user=TgUser(id=1, first_name="تست", is_bot=False), text="سلام")
_vm_frozen = False
try:
    _vm.text = "هک"
except Exception:
    _vm_frozen = True
check("آبجکت پیام تلگرام تغییرناپذیر است (علت باگ قبلی ویس) — پس متن ویس باید پاس داده شود",
      _vm_frozen and "override_text" in inspect.signature(bot.handle_message).parameters)


class _FakeMsg:
    def __init__(self):
        self.sent, self.edited = [], []

    async def reply_text(self, txt, **kw):
        self.sent.append(txt)
        return self

    async def edit_text(self, txt, **kw):
        self.edited.append(txt)
        return self


class _FakeBot:
    async def send_chat_action(self, **kw):
        return None


class _FakeCtx:
    def __init__(self, mode):
        self.user_data = {"mode": mode}
        self.bot = _FakeBot()


_vstore_real, _varchive_real, _vstream_real = bot.store, bot.archive, bot.stream_answer
bot.store = bot.SQLStore("test_voice.db", context_max_messages=bot.CONTEXT_MAX_MESSAGES)
bot.archive = bot.store


async def _fake_stream(emp, hist, placeholder, uid, eid):
    _answer = f"جواب تستی از {emp['name']}"
    await placeholder.edit_text(_answer)
    return _answer


bot.stream_answer = _fake_stream
try:
    _vm1, _vc1 = _FakeMsg(), _FakeCtx(("chat", list(bot.EMPLOYEES)[0]))
    _vu1 = SimpleNamespace(message=_vm1, effective_user=SimpleNamespace(id=555001, first_name="ویسی"),
                           effective_chat=SimpleNamespace(id=555001))
    asyncio.run(bot.handle_message(_vu1, _vc1, override_text="سلام این پیام ویس است"))
    check("پیام ویس‌شده مثل پیام تایپی پردازش و جواب زنده گرفت",
          any("در حال فکر کردن" in s for s in _vm1.sent)
          and any("جواب تستی" in s for s in _vm1.edited))
    check("متن ویس در حافظه‌ی کارمند ذخیره شد",
          "سلام این پیام ویس است" in [m["content"] for m in bot.store.get_all(555001, list(bot.EMPLOYEES)[0])])

    _vm2, _vc2 = _FakeMsg(), _FakeCtx(("chat", "scenario_writer"))
    _vu2 = SimpleNamespace(message=_vm2, effective_user=SimpleNamespace(id=555002, first_name="ویسی"),
                           effective_chat=SimpleNamespace(id=555002))
    asyncio.run(bot.handle_message(_vu2, _vc2, override_text="یه کد پایتون هم بنویس"))
    check("ویسِ درخواست کد پیش نگار هم قفل تخصص می‌خورد و جواب AI نمی‌گیرد",
          any("خارجه" in s for s in _vm2.sent) and bot.store.get_all(555002, "scenario_writer") == [])

    _vm3, _vc3 = _FakeMsg(), _FakeCtx(("chat", "hiro"))
    _vu3 = SimpleNamespace(message=_vm3, effective_user=SimpleNamespace(id=555003, first_name="ویسی"),
                           effective_chat=SimpleNamespace(id=555003))
    asyncio.run(bot.handle_message(_vu3, _vc3, override_text="سلام هیرو، خوبی؟"))
    check("چت با هیرو از منوی اصلی، با ویس هم کار می‌کند",
          any("جواب تستی" in s for s in _vm3.edited)
          and "سلام هیرو، خوبی؟" in [m["content"] for m in bot.store.get_all(555003, "hiro")])
finally:
    try:
        bot.store.close()
    except Exception:
        pass
    bot.store = _vstore_real
    bot.archive = _varchive_real
    bot.stream_answer = _vstream_real
if os.path.exists("test_voice.db"):
    os.remove("test_voice.db")

failed = [n for n, ok in results if not ok]
print("\n" + ("🎉 ALL TESTS PASSED" if not failed else f"⚠️ FAILED: {failed}"))
sys.exit(1 if failed else 0)
