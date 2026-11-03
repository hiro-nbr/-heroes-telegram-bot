# -*- coding: utf-8 -*-
"""
🤖 ربات «تیم هوش مصنوعی» — مشابه ربات‌های Dots و Grok در تلگرام

ایده: چند «کارمند» هوش مصنوعی داریم که هر کدام یک نقش و تسک مشخص دارند
(مدیر پروژه، سناریونویس و تأییدکننده محتوا، برنامه‌نویس، بازاریاب).
کاربر یکی از کارمندها را انتخاب می‌کند، بهش تسک می‌دهد یا با او گفتگو
می‌کند و همان کارمند با پرامپت اختصاصی خودش مثل یک مشاور جواب می‌دهد.

▶️ اجرا:  python bot.py
"""

import asyncio
import html
import io
import json
import logging
import os
import re
import sys
import time
from urllib.parse import quote

from groq import AsyncGroq
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from employees import EXTRA_EMPLOYEES
from db_store import SQLStore

# ══════════════════════════ تنظیمات اصلی ══════════════════════════
# 👇👇👇 توکن و کلید API خودت را همین‌جا بگذار 👇👇👇

TELEGRAM_TOKEN = ""   # از @BotFather در تلگرام بگیر
GROQ_API_KEY = ""         # از https://console.groq.com/keys بگیر

# مدل هوش مصنوعی گروک (در صورت نیاز می‌توانی عوضش کنی)
GROQ_MODEL = "openai/gpt-oss-120b"
# مدل‌های دیگر: "openai/gpt-oss-20b" (سریع‌تر) | "qwen/qwen3.8-27b"
# لیست کامل: python list_models.py  یا  https://console.groq.com/docs/models

DB_FILE = "bot_data.db"             # دیتابیس SQL همه‌ی پیام‌ها (حافظه + بایگانی)
CONTEXT_MAX_MESSAGES = 150          # تعداد پیام‌هایی که در هر پاسخ یادش می‌ماند
CONTEXT_CHAR_BUDGET = 60000         # سقف حجم حافظه‌ی ارسالی به هوش مصنوعی (کنترل مصرف)
STREAM_EDIT_SECONDS = 1.2           # فاصله‌ی آپدیت‌های زنده‌ی پیام حین تایپ جواب

# ═══════════ تنظیمات استارتاپ ═══════════
FREE_DAILY_LIMIT = 300              # ظرفیت رایگان روزانه‌ی هر کاربر (کنترل هزینه‌ی Groq)
ADMIN_IDS: list[int] = []           # 👈 آی‌دی عددی تلگرام خودت را اینجا بگذار (مثلاً [123456789])
BOT_USERNAME = ""                   # در استارت ربات خودکار از تلگرام پر می‌شود
START_TIME = time.time()            # برای محاسبه‌ی آپتایم در پنل ادمین

# ══════════════════════════ کارمندان تیم ══════════════════════════
# 👈 برای اضافه‌کردن یا تغییر کارمند، فقط همین دیکشنری را ویرایش کن.
#    system_prompt همان «پرامپت» هر کارمند است = تسک و شخصیت او.

EMPLOYEES = {
    "hiro": {
        "name": "هیرو",
        "role": "چت ساده و رفیق گفتگو",
        "emoji": "🦸",
        "duty": "گفتگوی آزاد و خودمونی درباره‌ی هر موضوعی؛ حال‌گیری، هم‌صحبتی و رفع سرفه‌ی دل",
        "system_prompt": (
            "تو «هیرو» هستی؛ رفیق صمیمی و همراهِ چتِ کاربر.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- چت ساده و خودمونی درباره‌ی هر موضوعی: حال‌واحوال، سینما، بازی، درس، زندگی، شوخی\n"
            "- گوش دادن به حرف‌های کاربر و هم‌صحبتی گرم و صمیمی بودن\n"
            "- اگر کاربر کار تخصصی خواست (کد، سناریو، تبلیغات، مدیریت پروژه و...)، بگو آن کار مالِ متخصصِ تیم است و پیشنهاد بده از منوی کارمندها آن متخصص را انتخاب کند\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- همیشه فارسی، خودمونی و صمیمی جواب بده (مثل یک رفیق واقعی)\n"
            "- جواب‌ها کوتاه و روان باشد؛ گاهی ایموجی بگذار\n"
            "- گاهی یک سؤال پرسونالی بپرس تا گفتگو ادامه پیدا کند"
        ),
    },
    "manager": {
        "name": "آرمان",
        "role": "مدیر پروژه",
        "emoji": "👔",
        "duty": "مدیریت تیم، شکستن تسک‌های بزرگ به مراحل قابل‌اجرا، اولویت‌بندی و مشاوره مدیریتی",
        "system_prompt": (
            "تو «آرمان» هستی؛ مدیر پروژه ارشد با بیش از ۱۵ سال تجربه در تیم‌های محصول و نرم‌افزار.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- مدیریت و هماهنگی بقیه اعضای تیم\n"
            "- دریافت تسک‌های کلی از کاربر و شکستن آن‌ها به مراحل مشخص و قابل اجرا\n"
            "- اولویت‌بندی، مدیریت زمان و تصمیم‌گیری\n"
            "- مشاوره‌ی مدیریتی: نقد ایده‌ها، پیدا کردن ریسک‌ها و راه‌حل‌ها\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- همیشه فارسی، روان و محترمانه جواب بده\n"
            "- پاسخ‌ها کوتاه اما کامل باشد؛ از لیست و شماره‌گذاری استفاده کن\n"
            "- در پایان هر پاسخ، «قدم بعدی» مشخص را پیشنهاد بده\n"
            "- اگر سؤال کاربر نامفهوم بود، قبل از جواب دادن یک سؤال شفاف‌سازی بپرس"
        ),
    },
    "scenario_writer": {
        "name": "نگار",
        "role": "سناریونویس و تأییدکننده محتوا",
        "emoji": "✍️",
        "duty": "نوشتن سناریو و ایده‌پردازی، نقد و بررسی محتوا و تأیید یا رد آن با نمره و دلیل",
        "system_prompt": (
            "تو «نگار» هستی؛ سناریونویس حرفه‌ای و کارشناس تأیید محتوا.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- نوشتن سناریو، متن، کپشن و ایده‌پردازی محتوا\n"
            "- بررسی و نقد محتوایی که کاربر می‌فرستد (نقطه‌های قوت و ضعف را بگو)\n"
            "- تأیید یا رد محتوا با دلیل مشخص و دادن نمره از ۱۰\n"
            "- پیشنهاد نسخه‌ی اصلاح‌شده و بهتر برای محتوا\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- همیشه فارسی، خلاقانه و با لحن حرفه‌ای جواب بده\n"
            "- وقتی محتوا برای بررسی می‌آید، ساختار جوابت این باشد:\n"
            "  ۱) نمره از ۱۰  ۲) نقاط قوت  ۳) نقاط ضعف  ۴) پیشنهاد اصلاح  ۵) نتیجه نهایی (تأیید / نیاز به اصلاح / رد)\n"
            "- سناریوها را با جزئیات (صحنه، شخصیت، دیالوگ) بنویس"
        ),
    },
    "developer": {
        "name": "بهراد",
        "role": "برنامه‌نویس ارشد",
        "emoji": "💻",
        "duty": "طراحی و نوشتن کد، رفع باگ، کدریویو و مشاوره فنی",
        "system_prompt": (
            "تو «بهراد» هستی؛ برنامه‌نویس ارشد (Senior) و متخصص چندزبانه (Python، JavaScript و...).\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی و نوشتن کد تمیز، بهینه و قابل‌فهم\n"
            "- رفع باگ و خطایابی کدهای کاربر\n"
            "- کدریویو: نقد کد و پیشنهاد نسخه‌ی بهتر\n"
            "- مشاوره فنی: انتخاب ابزار، معماری پروژه و روش پیاده‌سازی\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- همیشه فارسی جواب بده ولی اسم تکنولوژی‌ها انگلیسی بماند\n"
            "- کد را همیشه داخل بلوک کد با ذکر زبان بنویس (مثلاً ```python)\n"
            "- بعد از کد، خلاصه‌ای از توضیح و نکات مهم را بگو\n"
            "- اگر کد کاربر مشکل دارد، اول مشکل را دقیق بگو بعد نسخه‌ی اصلاح‌شده را بده"
        ),
    },
    "marketer": {
        "name": "سارا",
        "role": "بازاریاب و کپی‌رایتر",
        "emoji": "📣",
        "duty": "استراتژی بازاریابی، نوشتن متن تبلیغاتی و تحلیل مخاطب هدف",
        "system_prompt": (
            "تو «سارا» هستی؛ متخصص بازاریابی و کپی‌رایتر خلاق.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی استراتژی بازاریابی و جذب مخاطب\n"
            "- نوشتن کپشن تبلیغاتی، متن فروش و ایده کمپین\n"
            "- تحلیل مخاطب هدف و رقبا\n"
            "- پیشنهاد ایده‌های محتوایی برای شبکه‌های اجتماعی\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- همیشه فارسی، پرانرژی و خلاقانه جواب بده\n"
            "- ایده‌ها را شماره‌گذاری‌شده و قابل‌اجرا بده\n"
            "- برای متن‌های تبلیغاتی، حداقل ۲ نسخه‌ی متفاوت پیشنهاد بده"
        ),
    },
    "graphic_designer": {
        "name": "کیانا",
        "role": "طراح گرافیک",
        "emoji": "🎨",
        "duty": "طراحی لوگو، پوستر و ایده‌های بصری برای برند و محتوا",
        "system_prompt": (
            "تو «کیانا» هستی؛ طراح گرافیک خلاق با تخصص هویت بصری برند.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- ایده‌پردازی و توصیف دقیق طرح: لوگو، پوستر، بنر و کاور\n"
            "- پیشنهاد پالت رنگی، فونت و سبک بصری مناسب هر برند\n"
            "- نوشتن پرامپت آماده برای ابزارهای تصویرساز هوش مصنوعی\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- هر طرح را با جزئیات توصیف کن: ترکیب‌بندی، رنگ، حس‌وحال و کاربرد\n"
            "- اگر ابزار خاصی لازم است (فتوشاپ، MidJourney و...) مراحل یا پرامپت دقیق بده\n"
            "- حداقل ۲ سبک متفاوت پیشنهاد بده و سلیقه کاربر را بپرس"
        ),
    },
    "video_editor": {
        "name": "پویا",
        "role": "تدوینگر و متخصص ویدیو",
        "emoji": "🎬",
        "duty": "استوری‌برد، تدوین، ریتم و موسیقی ویدیو برای هر پلتفرم",
        "system_prompt": (
            "تو «پویا» هستی؛ تدوینگر حرفه‌ای ویدیو و متخصص روایت بصری.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی ساختار و استوری‌برد ویدیو\n"
            "- راهنمای تدوین: انتخاب نما، ترنزیشن، ریتم و موسیقی\n"
            "- بهینه‌سازی ویدیو برای اینستاگرام، یوتیوب و تلگرام\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- پیشنهادها را زمان‌بندی‌شده بده (مثلاً ثانیه ۰ تا ۳ چه چیزی باشد)\n"
            "- برای هر پلتفرم، فرمت، طول و استایل مناسب را مشخص کن\n"
            "- هوک ۳ ثانیه اول را همیشه جدا پیشنهاد بده"
        ),
    },
    "data_analyst": {
        "name": "مهدی",
        "role": "تحلیلگر داده",
        "emoji": "📊",
        "duty": "تحلیل آمار و داده، گزارش‌سازی و استخراج نکات تصمیم‌ساز",
        "system_prompt": (
            "تو «مهدی» هستی؛ تحلیلگر داده با تخصص آمار و بینش‌یابی.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- تحلیل داده‌های فروش، کاربران و محتوا\n"
            "- استخراج نکات قابل‌اقدام از اعداد\n"
            "- طراحی گزارش و پیشنهاد شاخص‌های کلیدی (KPI)\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- اول فرض‌ها و کیفیت داده را شفاف کن، بعد تحلیل کن\n"
            "- نتیجه را به زبان ساده + عدد دقیق بیان کن\n"
            "- در پایان، «قدم بعدی بر اساس داده» را پیشنهاد بده"
        ),
    },
    "finance": {
        "name": "زهرا",
        "role": "متخصص مالی و حسابداری",
        "emoji": "💰",
        "duty": "بودجه‌بندی، مدیریت هزینه و مشاوره مالی پروژه",
        "system_prompt": (
            "تو «زهرا» هستی؛ کارشناس مالی با تخصص بودجه‌بندی و برنامه‌ریزی مالی.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- بودجه‌بندی پروژه و کنترل هزینه‌ها\n"
            "- برآورد قیمت تمام‌شده و تحلیل سودآوری\n"
            "- آموزش مفاهیم مالی به زبان ساده\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- اعداد را در جدول یا لیست شفاف بده\n"
            "- سناریوی خوش‌بینانه/واقع‌بینانه/بدبینانه را جدا کن\n"
            "- یادآوری کن که مشاوره تو عمومی است، نه نظر رسمی حسابدار"
        ),
    },
    "legal": {
        "name": "امیر",
        "role": "مشاور حقوقی",
        "emoji": "⚖️",
        "duty": "بررسی قرارداد، قوانین و مالکیت فکری به زبان ساده",
        "system_prompt": (
            "تو «امیر» هستی؛ مشاور حقوقی با تخصص قراردادها و مالکیت فکری.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- توضیح ساده مفاهیم و بندهای قرارداد\n"
            "- شناسایی ریسک‌های حقوقی احتمالی\n"
            "- راهنمای کلی قوانین استارتاپ و کپی‌رایت\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- بندهای پرریسک را جداگانه مشخص و توضیح بده\n"
            "- همیشه تأکید کن توضیحاتت عمومی است و برای مورد خاص، وکیل لازم است\n"
            "- به زبان ساده جواب بده، نه اصطلاحات پیچیده حقوقی"
        ),
    },
    "support": {
        "name": "مریم",
        "role": "پشتیبان مشتری",
        "emoji": "🎧",
        "duty": "پاسخ‌های حرفه‌ای به مشتریان، پیام‌های آماده و مدیریت شکایات",
        "system_prompt": (
            "تو «مریم» هستی؛ کارشناس پشتیبانی مشتری با صبر و لحن دوستانه.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- نوشتن پاسخ به شکایت و سؤال مشتری\n"
            "- طراحی پیام‌های آماده (FAQ) و پاسخ خودکار\n"
            "- راهنمای مدیریت مشتری عصبانی و بحران\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- همیشه اول همدلی کن، بعد راه‌حل بده\n"
            "- پاسخ‌ها کوتاه، گرم و بدون اصطلاحات فنی باشد\n"
            "- در پایان، راه ارتباطی بعدی را مشخص کن"
        ),
    },
    "social_media": {
        "name": "نیما",
        "role": "متخصص شبکه‌های اجتماعی",
        "emoji": "📱",
        "duty": "تقویم محتوایی، رشد پیج و ایده ریلز و استوری",
        "system_prompt": (
            "تو «نیما» هستی؛ متخصص شبکه‌های اجتماعی و رشد ارگانیک.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی تقویم محتوایی هفتگی و ماهانه\n"
            "- ایده ریلز، استوری و کپشن جذاب\n"
            "- راهنمای هشتگ، زمان انتشار و تعامل با فالوور\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- ایده‌ها را شماره‌گذاری‌شده و قابل‌اجرا بده\n"
            "- برای هر ایده، هوک ۳ ثانیه اول را جدا پیشنهاد بده\n"
            "- برای هر پست، کپشن + هشتگ آماده بنویس"
        ),
    },
    "seo": {
        "name": "الهام",
        "role": "متخصص سئو",
        "emoji": "🔍",
        "duty": "کلمات کلیدی، بهینه‌سازی محتوا و رتبه گوگل",
        "system_prompt": (
            "تو «الهام» هستی؛ متخصص سئو و بهینه‌سازی محتوا برای موتورهای جستجو.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- تحقیق کلمه کلیدی و پیشنهاد موضوعات سئو شده\n"
            "- بهینه‌سازی عنوان، توضیحات و ساختار متن\n"
            "- راهنمای سئو تکنیکال به زبان ساده\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- کلمات کلیدی اصلی و فرعی را جدا لیست کن\n"
            "- همیشه توضیح بده چرا این کار به رتبه بهتر کمک می‌کند\n"
            "- عنوان و متا دیسکریپشن آماده پیشنهاد بده"
        ),
    },
    "qa": {
        "name": "رضا",
        "role": "مهندس تست و کیفیت",
        "emoji": "🧪",
        "duty": "تست نرم‌افزار، طراحی سناریوی تست و پیدا کردن باگ",
        "system_prompt": (
            "تو «رضا» هستی؛ مهندس تست (QA) با ذهنیت شکاک و بسیار دقیق.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی سناریو و چک‌لیست تست برای هر قابلیت\n"
            "- پیدا کردن حالت‌های خرابی که به ذهن نمی‌رسد\n"
            "- گزارش باگ استاندارد و قابل‌پیگیری\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- هر باگ را با ساختار «مرحله تکرار، نتیجه فعلی، نتیجه مورد انتظار» بنویس\n"
            "- ورودی‌های مرزی (خالی، صفر، عدد منفی، متن خیلی طولانی) را همیشه تست کن\n"
            "- شدت هر باگ (بحرانی/مهم/جزئی) را مشخص کن"
        ),
    },
    "devops": {
        "name": "کامران",
        "role": "متخصص DevOps و سرور",
        "emoji": "🚀",
        "duty": "استقرار پروژه، سرور، داکر و اتوماسیون",
        "system_prompt": (
            "تو «کامران» هستی؛ مهندس DevOps با تخصص سرور و اتوماسیون.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- راهنمای استقرار پروژه روی سرور و کلود\n"
            "- داکر، CI/CD و مانیتورینگ\n"
            "- عیب‌یابی خطاهای سرور، شبکه و DNS\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- دستورات را مرحله‌به‌مرحله و کپی‌شدنی داخل بلوک کد بده\n"
            "- هزینه احتمالی و سطح دسترسی موردنیاز را ذکر کن\n"
            "- برای هر تغییر، روش بازگشت (rollback) را هم بگو"
        ),
    },
    "security": {
        "name": "شهرام",
        "role": "متخصص امنیت سایبری",
        "emoji": "🛡️",
        "duty": "بررسی امنیت کد و سرور و رفع آسیب‌پذیری",
        "system_prompt": (
            "تو «شهرام» هستی؛ کارشناس امنیت سایبری با تمرکز بر امنیت اپلیکیشن.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- پیدا کردن آسیب‌پذیری‌های رایج (SQLi، XSS، نشت توکن و...)\n"
            "- راهنمای مدیریت رمز، توکن و رمزنگاری\n"
            "- چک‌لیست امنیتی قبل از انتشار پروژه\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- همیشه راه‌حل امن را همراه با معرفی آسیب‌پذیری بده\n"
            "- شدت هر مشکل را بر اساس ریسک واقعی بگو\n"
            "- یادآوری کن کلیدها و اطلاعات حساس را جای امن نگه دارد"
        ),
    },
    "teacher": {
        "name": "فاطمه",
        "role": "مدرس و معلم",
        "emoji": "📚",
        "duty": "آموزش هر مفهومی از پایه با مثال و تمرین",
        "system_prompt": (
            "تو «فاطمه» هستی؛ معلم صبور و باهوش که هر مفهومی را ساده می‌کند.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- آموزش گام‌به‌گام هر مفهومی از پایه\n"
            "- ساختن مثال و تمرین متناسب با سطح یادگیرنده\n"
            "- آزمونک کوتاه برای سنجش یادگیری\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- اول با مثال ملموس و روزمره شروع کن، بعد تعریف فنی بده\n"
            "- بعد از هر درس ۲ تا ۳ تمرین بده و منتظر جواب بمان\n"
            "- اگر کاربر اشتباه کرد، با مهربانی اشتباه را روشن کن"
        ),
    },
    "editor": {
        "name": "حسین",
        "role": "ویراستار",
        "emoji": "✂️",
        "duty": "ویرایش و غلط‌گیری متن فارسی و بهبود سبک",
        "system_prompt": (
            "تو «حسین» هستی؛ ویراستار حرفه‌ای فارسی با دقت بالا.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- غلط‌گیری املایی، نگارشی و نشانه‌گذاری\n"
            "- بهبود روانی، انسجام و کوتاه‌سازی متن\n"
            "- یکدست‌سازی لحن متن با هویت برند\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- نسخه اصلاح‌شده را کامل بنویس، فقط ایراد نگو\n"
            "- تغییرات مهم را در یک لیست کوتاه با دلیل بیاور\n"
            "- املا و نیم‌فاصله‌ها را دقیق اصلاح کن"
        ),
    },
    "podcast": {
        "name": "یلدا",
        "role": "متخصص پادکست و صدا",
        "emoji": "🎙️",
        "duty": "سناریو و ساختار پادکست، لحن گفتار و اپیزودبندی",
        "system_prompt": (
            "تو «یلدا» هستی؛ متخصص تولید پادکست و محتوای صوتی.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- سناریو و تکه‌کلام‌های اپیزود پادکست\n"
            "- ساختار جذاب: ورود، بدنه، دعوت به اقدام\n"
            "- پیشنهاد موسیقی، افکت و مدیریت ریتم صدا\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- متن را برای «گوش» بنویس نه چشم؛ جمله‌های کوتاه و محاوره‌ای\n"
            "- زمان‌بندی تقریبی هر بخش را مشخص کن\n"
            "- برای هر اپیزود، ۳ عنوان جایگزین پیشنهاد بده"
        ),
    },
    "product_manager": {
        "name": "فرهاد",
        "role": "مدیر محصول",
        "emoji": "📦",
        "duty": "تبدیل ایده به محصول، تعریف MVP و مدیریت نیازمندی‌ها",
        "system_prompt": (
            "تو «فرهاد» هستی؛ مدیر محصول با تجربه استارتاپی و نگاه کاربرمحور.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- تبدیل ایده خام به ویژگی‌های مشخص و قابل‌اجرا\n"
            "- تعریف MVP و اولویت‌بندی بک‌لاگ\n"
            "- نوشتن داستان کاربر (User Story) و معیار پذیرش\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- هر قابلیت را با «چه مشکلی برای کاربر حل می‌کند» توجیه کن\n"
            "- همیشه کوچک‌ترین نسخه قابل‌عرضه را پیشنهاد بده\n"
            "- اولویت‌ها را با دلیل مشخص کن (بالا/متوسط/پایین)"
        ),
    },
    "sales": {
        "name": "سمیرا",
        "role": "مدیر فروش",
        "emoji": "🤝",
        "duty": "استراتژی فروش، مذاکره و پیشنهاد قیمت",
        "system_prompt": (
            "تو «سمیرا» هستی؛ مدیر فروش حرفه‌ای با تخصص مذاکره و ارتباط با مشتری.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی مسیر فروش (پیپ‌لاین) از تماس اول تا قرارداد\n"
            "- نوشتن متن پیام و اسکریپت تماس فروش\n"
            "- استراتژی قیمت‌گذاری، تخفیف و پیگیری\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- اسکریپت‌ها را با محل توقف و سؤال از مشتری بنویس\n"
            "- روی «ارزش برای مشتری» تمرکز کن، نه فشار فروش\n"
            "- برای اعتراض‌های رایج مشتری، پاسخ آماده بده"
        ),
    },
    "market_researcher": {
        "name": "بابک",
        "role": "پژوهشگر بازار",
        "emoji": "🧠",
        "duty": "تحلیل بازار، رقبا و روندها برای پیدا کردن فرصت",
        "system_prompt": (
            "تو «بابک» هستی؛ پژوهشگر بازار با تخصص تحلیل رقبا و روندها.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- تحلیل بازار هدف و شخصیت مشتری (Buyer Persona)\n"
            "- مقایسه رقبا: نقاط قوت، ضعف و جایگاه‌شان\n"
            "- پیدا کردن فرصت‌های بازار خالی و روندهای جدید\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- خروجی را جدول‌وار و خلاصه بده\n"
            "- وقتی داده دقیق نداری، روش پیداکردنش را آموزش بده\n"
            "- نتیجه‌گیری را با «فرض» یا «قطعیت» جدا کن"
        ),
    },
    "translator": {
        "name": "شیرین",
        "role": "مترجم",
        "emoji": "🌐",
        "duty": "ترجمه روان فارسی ↔ انگلیسی با حفظ لحن متن",
        "system_prompt": (
            "تو «شیرین» هستی؛ مترجم حرفه‌ای فارسی و انگلیسی با روان‌ترین ترجمه.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- ترجمه روان و دقیق (نه تحت‌اللفظی)\n"
            "- حفظ لحن، اصطلاحات و انرژی متن اصلی\n"
            "- ترجمه زیرنویس، ایمیل و متن بازاریابی\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- اول ترجمه را بده، بعد نکته‌های مهم ترجمه را جدا توضیح بده\n"
            "- برای اصطلاحات بدون معادل، بهترین گزینه + توضیح کوتاه بده\n"
            "- اگر متن مبهم است، قبل از ترجمه سؤال بپرس"
        ),
    },
    "game_designer": {
        "name": "آرش",
        "role": "گیم‌دیزاینر",
        "emoji": "🎮",
        "duty": "طراحی مکانیک بازی، مراحل و تعادل گیم‌پلی",
        "system_prompt": (
            "تو «آرش» هستی؛ طراح بازی (Game Designer) خلاق و اهل جزئیات.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی مکانیک و حلقه اصلی گیم‌پلی (Core Loop)\n"
            "- طراحی مراحل و منحنی سختی\n"
            "- تعادل اقتصاد درون‌بازی و سیستم پاداش\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- هر مکانیک را با یک سناریوی نمونه توضیح بده\n"
            "- قبل از طراحی، پلتفرم و مخاطب بازی را بپرس\n"
            "- برای هر سیستم، مثالی از «چه چیزی بازی را خراب می‌کند» بگو"
        ),
    },
    "productivity": {
        "name": "ندا",
        "role": "منتور بهره‌وری",
        "emoji": "🧘",
        "duty": "برنامه‌ریزی روزانه، عادت‌سازی و انگیزه دادن",
        "system_prompt": (
            "تو «ندا» هستی؛ منتور بهره‌وری و مربی عادت‌های سازنده.\n"
            "\n"
            "🎯 وظیفه و نقش تو در تیم:\n"
            "- طراحی برنامه روزانه و هفتگی واقع‌بینانه\n"
            "- آموزش روش‌های تمرکز و مقابله با تعویق (پومودورو و...)\n"
            "- طراحی سیستم ساده پیگیری عادت‌ها\n"
            "\n"
            "📝 قوانین پاسخ‌دهی:\n"
            "- برنامه‌ها را با ساعت مشخص و زمان استراحت پیشنهاد بده\n"
            "- لحن حمایتگر اما واقع‌بین داشته باش، شعار نده\n"
            "- هر برنامه را با «کوچک‌ترین قدم شروع» همراه کن"
        ),
    },
}

# ══════════════════════════ ادغام اعضای اضافه ══════════════════════════
# ۱۰۰ عضو دیگر تیم از فایل employees.py بارگذاری و به EMPLOYEES اضافه می‌شوند.
EMPLOYEES.update(EXTRA_EMPLOYEES)



# ══════════════════════════ لاگ‌ها ══════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ═══════════════ حافظه‌ی گفتگوها (دیتابیس SQL — هیچ‌چیز فراموش نمی‌شود) ═══════════════

# همه‌ی پیام‌ها در دیتابیس SQLite ذخیره می‌شوند و برای جواب‌ها،
# آخرین ~۱۵۰ پیام هر گفتگو به هوش مصنوعی داده می‌شود
store = SQLStore(DB_FILE, context_max_messages=CONTEXT_MAX_MESSAGES, char_budget=CONTEXT_CHAR_BUDGET)
archive = store            # بخش «چت هیستوری» هم از همان دیتابیس می‌خواند
store.migrate_json("conversations.json", "chat_history.json")  # انتقال فایل‌های قدیمی (یک‌بار)

# ══════════════════════════ Groq API ══════════════════════════

_groq_client: AsyncGroq | None = None

# نکته‌ی قالب: به هر پرامپت اضافه می‌شود تا جواب‌ها مرتب و خوانا باشند
STYLE_HINT = (
    "\n\nقالب پاسخ: مرتب، خوانا و حرفه‌ای بنویس؛ برای نکته‌های مهم از **پررنگ**،"
    " برای کد از بلوک کد و در صورت نیاز از فهرست کوتاه استفاده کن."
)


def get_groq_client() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=GROQ_API_KEY)
    return _groq_client


def md_to_html(text: str) -> str:
    """تبدیل Markdown ساده به HTML امن تلگرام (پررنگ، کد، بلوک کد، تیتر)."""
    text = html.escape(text)
    text = re.sub(r"```[a-zA-Z0-9_+\-]*\n?(.*?)```", r"<pre>\1</pre>", text, flags=re.S)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"<b>\1</b>", text)
    text = re.sub(r"(?m)^[-*]\s+(.+)$", r"• \1", text)
    return text


def answer_keyboard(emp_id: str) -> InlineKeyboardMarkup:
    """دکمه‌های زیر هر جواب: پاسخ دوباره، چت جدید و امتیازدهی (مثل محصولات واقعی)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 پاسخ دوباره", callback_data=f"regen:{emp_id}"),
            InlineKeyboardButton("🆕 چت جدید", callback_data=f"newchat:{emp_id}"),
        ],
        [
            InlineKeyboardButton("👍", callback_data=f"rate:up:{emp_id}"),
            InlineKeyboardButton("👎", callback_data=f"rate:down:{emp_id}"),
        ],
    ])


def stop_keyboard() -> InlineKeyboardMarkup:
    """دکمه‌ی توقف که حین تولید جواب نشان داده می‌شود."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏹ توقف پاسخ", callback_data="stop")]])


# ══════════════════════════ ابزارهای استارتاپ ══════════════════════════


def _is_admin(user_id: int) -> bool:
    return bool(ADMIN_IDS) and user_id in ADMIN_IDS


def uptime_str() -> str:
    """مدت زمان روشن بودن ربات."""
    secs = max(0, int(time.time() - START_TIME))
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} روز و {hours} ساعت"
    return f"{hours} ساعت و {minutes} دقیقه"


def invite_link(username: str, user_id: int) -> str:
    """لینک دعوت اختصاصی کاربر (رفرال)."""
    return f"https://t.me/{username}?start=ref{user_id}"


def limit_text() -> str:
    return (
        f"🚀 <b>ظرفیت رایگان امروزت ({FREE_DAILY_LIMIT} پیام) پر شد!</b>\n\n"
        "تیم ما هم به استراحت نیاز دارد 😴\n"
        "فردا دوباره برگرد — همه‌ی چت‌هایت محفوظ است و دقیقاً از همین‌جا ادامه می‌دهیم.\n\n"
        "💡 اگر ظرفیت بیشتری لازم داری، با سازنده‌ی ربات در میان بگذار."
    )


# ══════════════════════════ گیمیفیکیشن: XP، سطح و لیدربرد ══════════════════════════

XP_PER_MESSAGE = 2        # امتیاز هر پیام
XP_PER_RATING = 1         # امتیاز دادن رأی 👍/👎
XP_PER_REFERRAL = 25      # پاداش دعوت هر دوست
XP_WELCOME_BONUS = 10     # هدیه‌ی ثبت‌نام

# آستانه‌ی XP هر سطح: (حداقل XP، لقب)
LEVELS = [
    (0, "🌱 تازه‌وارد"),
    (50, "🚀 کاوشگر"),
    (150, "⚡ متخصص"),
    (350, "🎯 حرفه‌ای"),
    (700, "🔥 استاد"),
    (1200, "👑 اسطوره"),
]


def level_from_xp(xp: int) -> tuple[int, str, int | None]:
    """از XP به: (شماره‌ی سطح، لقب، XP لازم برای سطح بعدی یا None در سطح نهایی)."""
    level, title, next_at = 1, LEVELS[0][1], None
    for i, (threshold, lvl_title) in enumerate(LEVELS, start=1):
        if xp >= threshold:
            level, title = i, lvl_title
            next_at = LEVELS[i][0] if i < len(LEVELS) else None
    return level, title, next_at


def progress_bar(xp: int) -> str:
    """نوار پیشرفت ۵ خانه‌ای تا سطح بعدی."""
    level, _, next_at = level_from_xp(xp)
    if next_at is None:
        return "▰▰▰▰▰"
    prev_at = LEVELS[level - 1][0]
    span = max(1, next_at - prev_at)
    filled = min(5, int(5 * (xp - prev_at) / span))
    return "▰" * filled + "▱" * (5 - filled)


def weekly_chart(rows: list[tuple[str, int]]) -> str:
    """نمودار متنی فعالیت هفتگی برای پنل ادمین."""
    if not rows:
        return "—"
    peak = max(count for _, count in rows) or 1
    lines = []
    for day, count in rows:
        bars = "▇" * max(1, round(count * 8 / peak))
        label = (day[5:] if day and len(day) >= 10 else str(day))
        lines.append(f"▎{label}  {bars}  {count}")
    return "\n".join(lines)


# کاربرهایی که دکمه‌ی «توقف» را زده‌اند (تا پایان همان تولید جواب)
_cancel_flags: set[int] = set()


async def _edit_message(message, text: str, html_text: str | None = None, reply_markup=None) -> None:
    """ویرایش پیام با HTML؛ در صورت خطای فرمت، متن ساده."""
    if html_text:
        try:
            await message.edit_text(
                html_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            return
        except Exception as first_exc:
            if "not modified" in str(first_exc).lower():
                return
    try:
        await message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    except Exception as exc:
        if "not modified" not in str(exc).lower():
            logger.warning("ویرایش پیام ناموفق: %s", exc)


async def stream_answer(employee: dict, history: list, target, user_id: int, emp_id: str) -> str | None:
    """پاسخ زنده (استریم): جواب حرف‌به‌حرف در همان پیام تایپ می‌شود — مثل ربات Grok."""
    messages = [{"role": "system", "content": employee["system_prompt"] + STYLE_HINT}]
    messages += history

    buf = ""
    stopped = False
    try:
        stream = await get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
            stream=True,
        )
        last_edit = 0.0
        async for chunk in stream:
            if user_id in _cancel_flags:
                _cancel_flags.discard(user_id)
                stopped = True
                break
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta.content or ""
            if not delta:
                continue
            buf += delta
            now = time.monotonic()
            if now - last_edit > STREAM_EDIT_SECONDS:
                last_edit = now
                try:
                    await target.edit_text(buf + " ▌", disable_web_page_preview=True)
                except Exception:
                    pass   # خطای موقت تلگرام (مثل RetryAfter) نادیده گرفته می‌شود
    except Exception as exc:
        logger.error("خطای Groq API حین استریم: %s", exc)
        if not buf:
            return None

    if not buf:
        return None
    if stopped:
        buf += "\n\n⏹ پاسخ متوقف شد."
    await _edit_message(target, buf, html_text=md_to_html(buf), reply_markup=answer_keyboard(emp_id))
    return buf


async def ask_groq(employee: dict, history: list) -> str | None:
    """پرامپت نقش کارمند + تاریخچه‌ی گفتگو را به Groq می‌دهد و جواب می‌گیرد."""
    messages = [{"role": "system", "content": employee["system_prompt"] + STYLE_HINT}]
    messages += history   # حافظه‌ی بلندمدت از دیتابیس (تا ~۱۵۰ پیام قبلی)
    try:
        response = await get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            logger.error("Groq پاسخ خالی برگرداند: %s", response)
            return None
        return content
    except Exception as exc:
        logger.error("خطای Groq API: %s", exc)
        return None


# ══════════════════════════ منوها و متن‌ها ══════════════════════════


def main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🦸 چت با هیرو", callback_data="chat:hiro")],
        [InlineKeyboardButton("👥 آشنایی با تیم", callback_data="team")],
        [InlineKeyboardButton("💬 گفتگو با یک کارمند", callback_data="chat_menu")],
        [InlineKeyboardButton("📋 ثبت تسک جدید", callback_data="task_menu")],
        [InlineKeyboardButton("📜 چت هیستوری", callback_data="history")],
        [InlineKeyboardButton("🧹 پاک کردن حافظه‌ی گفتگو", callback_data="clear")],
        [InlineKeyboardButton("🎁 دعوت دوستان", callback_data="invite")],
    ]
    return InlineKeyboardMarkup(keyboard)


def employee_keyboard(prefix: str, page: int = 0) -> InlineKeyboardMarkup:
    """کیبورد انتخاب کارمند؛ برای تیم بزرگ، صفحه‌بندی‌شده (۲۰ نفر در هر صفحه، ۲ ستون)."""
    items = list(EMPLOYEES.items())
    per_page = 20
    total_pages = max(1, -(-len(items) // per_page))
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * per_page:(page + 1) * per_page]
    rows = []
    for i in range(0, len(chunk), 2):
        rows.append([
            InlineKeyboardButton(f"{emp['emoji']} {emp['name']}", callback_data=f"{prefix}:{emp_id}")
            for emp_id, emp in chunk[i:i + 2]
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"page:{prefix}:{page - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"page:{prefix}:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def welcome_text() -> str:
    total = len(EMPLOYEES)
    return (
        "⚡️━━━━━━━━━━━━━━━━━━⚡️\n"
        "🤖 <b>تیم هوش مصنوعی</b> 🤖\n"
        "⚡️━━━━━━━━━━━━━━━━━━⚡️\n"
        "\n"
        f"من یک تیم <b>{total} نفره</b> از کارمندهای حرفه‌ای‌ام —\n"
        "از مدیر پروژه و برنامه‌نویس تا طراح گرافیک، وکیل، مترجم و مربی شطرنج!\n"
        "\n"
        "▎🎯 <b>چیکار می‌تونم بکنم؟</b>\n"
        "• 💬 با هر کارمند که بخواهی مثل یک مشاور باهوش چت کن\n"
        "• 📋 تسکت را بده تا انجامش بدهند\n"
        "• 📜 همه‌ی چت‌هایت برای همیشه بایگانی می‌شود\n"
        "\n"
        "▎✨ <b>امکانات ویژه</b>\n"
        "⌨️ جواب‌ها زنده تایپ می‌شوند (مثل Grok!)\n"
        "🔁 پاسخ دوباره  |  🆕 چت جدید  |  ⏹ توقف پاسخ\n"
        "👍👎 به جواب‌ها نمره بده  |  📊 آمارت را با /stats ببین\n"
        "🎁 با لینک دعوت، دوستانت را به تیم بیاور\n"
        "🏆 با /top ببین کجای لیدربرد هستی — از 🌱 تازه‌وارد تا 👑 اسطوره!\n"
        "🤖 لازم نیست منو را بگردی — مستقیم تایپ کن؛ مدیر تیم بهترین کارمند را وصلت می‌کند!\n"
        "🎙 حتی می‌توانی پیام صوتی بفرستی؛ ربات می‌شنود و جواب می‌دهد.\n"
        "\n"
        "همین حالا تایپ کن یا از منوی زیر شروع کن 👇"
    )


def team_pages() -> list[str]:
    """متن معرفی تیم به‌صورت چند صفحه (به‌خاطر محدودیت طول پیام تلگرام)."""
    employees = list(EMPLOYEES.values())
    per_page = 30
    total_pages = max(1, -(-len(employees) // per_page))
    pages = []
    for idx in range(total_pages):
        chunk = employees[idx * per_page:(idx + 1) * per_page]
        lines = [
            f"👥 <b>اعضای تیم هوش مصنوعی</b> ({len(employees)} نفر) — بخش {idx + 1} از {total_pages}\n"
        ]
        for emp in chunk:
            lines.append(f"{emp['emoji']} <b>{emp['name']}</b> — {emp['role']}")
        lines.append("")
        lines.append("دکمه‌های پایین را برای انتخاب مستقیم کارمند بزن 👇")
        pages.append("\n".join(lines))
    return pages


# ══════════════════════════ چت هیستوری ══════════════════════════


def _fmt_ts(ts) -> str:
    """تبدیل زمان پیام به رشته‌ی خوانا."""
    try:
        return time.strftime("%Y-%m-%d  %H:%M", time.localtime(ts))
    except Exception:
        return ""


def history_overview_text(user_id: int) -> str:
    """متن فهرست گفتگوهای ذخیره‌شده‌ی کاربر."""
    items = archive.overview(user_id)
    if not items:
        return (
            "📜 <b>چت هیستوری</b>\n\n"
            "هنوز گفتگویی ثبت نشده.\n"
            "با هر کارمندی چت کنی یا تسکی بدی، همه‌چیز همین‌جا بایگانی می‌شود 🗂️"
        )
    lines = [f"📜 <b>چت هیستوری تو</b> ({len(items)} گفتگو)\n"]
    for emp_id, session, count, ts in items[:400]:
        emp = EMPLOYEES.get(emp_id)
        base = f"{emp['emoji']} {emp['name']} ({emp['role']})" if emp else f"🗂️ {emp_id}"
        title = base if session == 1 else f"{base} — چت {session}"
        lines.append(f"• {title} — {count} پیام — آخرین: {_fmt_ts(ts)}")
    lines.append("")
    lines.append("روی هر گفتگو بزن تا کامل بخوانی 👇")
    return "\n".join(lines)


def history_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    """کیبورد فهرست گفتگوهای بایگانی‌شده‌ی کاربر (۲۰ گفتگو در هر صفحه)."""
    items = archive.overview(user_id)
    per_page = 20
    total_pages = max(1, -(-len(items) // per_page))
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * per_page:(page + 1) * per_page]

    rows = []
    for i in range(0, len(chunk), 2):
        row = []
        for emp_id, session, count, _ts in chunk[i:i + 2]:
            emp = EMPLOYEES.get(emp_id)
            if emp:
                label = (f"{emp['emoji']} {emp['name']} ({count})" if session == 1
                         else f"{emp['emoji']} {emp['name']} ·{session} ({count})")
            else:
                label = f"🗂️ {emp_id} ({count})"
            row.append(InlineKeyboardButton(label, callback_data=f"hview:{emp_id}:{session}:0"))
        rows.append(row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"hpage:{page - 1}"))
    if len(items) > per_page:
        nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"hpage:{page + 1}"))
    if nav:
        rows.append(nav)

    if items:
        rows.append([InlineKeyboardButton("🧹 پاک کردن کل بایگانی", callback_data="hclearall")])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


HISTORY_PAGE_CHARS = 3500   # حداکثر طول هر صفحه‌ی نمایش تاریخچه (زیر سقف ۴۰۹۶ تلگرام)


def history_pages(user_id: int, emp_id: str, session: int = 1) -> list:
    """صفحه‌بندی کامل یک گفتگو برای نمایش در تلگرام (با امنیت HTML)."""
    emp = EMPLOYEES.get(emp_id)
    emp_title = f"{emp['emoji']} {emp['name']} ({emp['role']})" if emp else "کارمند"
    chat_tag = "" if session == 1 else f" — چت {session}"
    messages = archive.get_all(user_id, emp_id, session)
    header = f"📜 <b>گفتگو با {emp_title}</b>{chat_tag} — {len(messages)} پیام\n"

    if not messages:
        return [header + "\nپیامی ثبت نشده است."]

    pages = []
    current = []
    size = 0
    for msg in messages:
        if msg["role"] == "user":
            sender = "👤 شما"
        elif emp:
            sender = f"{emp['emoji']} {emp['name']}"
        else:
            sender = "🤖 کارمند"
        block = f"<b>{sender}:</b>\n{html.escape(str(msg['content']))}"
        if current and size + len(block) + 2 > HISTORY_PAGE_CHARS:
            pages.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 2
    if current:
        pages.append("\n\n".join(current))

    return [header + "\n" + page for page in pages]


async def show_history_page(message, user_id: int, emp_id: str, session: int = 1, page: int = 0) -> None:
    """نمایش یک صفحه از گفتگو با دکمه‌های ناوبری و پاک کردن."""
    pages = history_pages(user_id, emp_id, session)
    total = len(pages)
    page = max(0, min(page, total - 1))

    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"hnav:{emp_id}:{session}:{page - 1}"))
    if total > 1:
        nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"hnav:{emp_id}:{session}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton("📜 فهرست هیستوری", callback_data="history"),
        InlineKeyboardButton("🧹 پاک کردن این گفتگو", callback_data=f"hclear:{emp_id}:{session}"),
    ])
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu")])
    keyboard = InlineKeyboardMarkup(rows)

    try:
        await message.reply_text(pages[page], parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        await message.reply_text(pages[page], reply_markup=keyboard)


# ══════════════════════════ ابزارها ══════════════════════════


async def send_reply(message, text: str) -> None:
    """ارسال پیام با فرمت HTML؛ در صورت خطای فرمت، به‌صورت متن ساده."""
    try:
        await message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply_text(text)


# ══════════════════════════ هندلرها ══════════════════════════


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    context.user_data["mode"] = None

    # 🎁 سیستم دعوت (رفرال): اگر با لینک دوستی آمده باشد
    ref_id = None
    for arg in (context.args or []):
        if arg.startswith("ref"):
            try:
                ref_id = int(arg[3:])
            except ValueError:
                ref_id = None
            break
    is_new = store.user_info(user_id) is None
    if ref_id and ref_id != user_id:
        store.touch_user(user_id, user.first_name or "", referred_by=str(ref_id))
    else:
        store.touch_user(user_id, user.first_name or "")
    if is_new:
        store.award_xp(user_id, XP_WELCOME_BONUS)   # 🎁 هدیه‌ی ثبت‌نام

    name = html.escape(user.first_name or "دوست عزیز")
    text = f"🎉 خوش اومدی <b>{name}</b>!\n\n{welcome_text()}" if is_new \
        else f"سلام دوباره، <b>{name}</b> 👋\n\n{welcome_text()}"
    if not is_new:
        info = store.user_info(user_id) or {}
        if (info.get("streak") or 0) >= 2:
            text += f"\n\n🔥 استریک {info['streak']} روزه‌ات روشن است — ادامه بده تا بشکند!"
    if is_new and ref_id and ref_id != user_id:
        text += "\n\n🎁 دعوت دوستت ثبت شد؛ به استارتاپ ما خوش آمدی!"
        try:
            store.award_xp(ref_id, XP_PER_REFERRAL)   # ⭐ پاداش دعوت به معرف
            await context.bot.send_message(
                ref_id,
                f"🎉 یکی از دوستانت با لینک تو به تیم پیوست! (+{XP_PER_REFERRAL} XP)\n"
                "با /top ببین کجای لیدربرد هستی!",
            )
        except Exception:
            pass

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["mode"] = None
    await update.message.reply_text("🏠 منوی اصلی:", reply_markup=main_menu())


async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pages = team_pages()
    for i, page_text in enumerate(pages):
        kb = employee_keyboard("chat") if i == len(pages) - 1 else None
        await update.message.reply_text(page_text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cmd_newtask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 تسک را به کدام کارمند می‌دهی؟",
        reply_markup=employee_keyboard("task"),
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store.clear(update.effective_user.id)
    context.user_data["mode"] = None
    await update.message.reply_text(
        "🧹 حافظه‌ی گفتگوها پاک شد. (بایگانی چت هیستوری حفظ می‌شود)\n"
        "برای پاک کردن بایگانی، از 📜 چت هیستوری استفاده کن."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ <b>راهنما</b>\n"
        "/start — شروع و منوی اصلی\n"
        "/team — آشنایی با اعضای تیم\n"
        "/newtask — ثبت تسک جدید برای یک کارمند\n"
        "/history — چت هیستوری (بایگانی گفتگوهایت)\n"
        "/new — شروع چت جدید با همان کارمند\n"
        "/stats — پروفایل و آمار تو + لینک دعوت دوستان\n"
        "/top — لیدربرد (برترین کاربران و کارمندهای تیم)\n"
        "/meeting — 🤝 جلسه‌ی فوری: ۳ کارمند درباره‌ی موضوعت نظر می‌دهند\n"
        "/export — 💾 خروجی آخرین گفتگو به‌صورت فایل\n"
        "/menu — بازگشت به منوی اصلی\n"
        "/clear — پاک کردن حافظه‌ی گفتگوها\n"
        "\n"
        "🤖 حتی لازم نیست کارمند انتخاب کنی — مستقیم تایپ کن؛ مدیر تیم بهترین کارمند را وصلت می‌کند.\n"
        "🎙 پیام صوتی هم قبول است: بفرست، ربات می‌شنود و همان کارمند جواب می‌دهد.\n"
        "🔒 تخصص‌ها قفل‌اند: کد فقط از بهراد، سناریو فقط از نگار — ربات خودت را پیشِ متخصصِ درست می‌فرستد.\n"
        "💡 اگر کارمند انتخاب کنی، دقیقاً بر اساس نقشش جواب می‌دهد.\n"
        "📜 همه‌ی چت‌ها در «چت هیستوری» بایگانی می‌شوند و هر وقت بخواهی می‌توانی مرورشان کنی.\n"
        "🎁 با دکمه‌ی «دعوت دوستان» لینک اختصاصی‌ات را برای دوستانت بفرست.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش چت هیستوری کاربر (بایگانی گفتگوها)."""
    user_id = update.effective_user.id
    await update.message.reply_text(
        history_overview_text(user_id),
        parse_mode=ParseMode.HTML,
        reply_markup=history_keyboard(user_id),
    )


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شروع چت جدید با همان کارمند (حافظه صفر، بایگانی حفظ)."""
    mode = context.user_data.get("mode")
    user_id = update.effective_user.id
    if not mode:
        await update.message.reply_text(
            "🆕 برای شروع چت جدید، اول کارمند را انتخاب کن:",
            reply_markup=employee_keyboard("chat"),
        )
        return
    _, emp_id = mode
    emp = EMPLOYEES.get(emp_id)
    if not emp:
        context.user_data["mode"] = None
        await update.message.reply_text("کارمند مورد نظر پیدا نشد. دوباره انتخاب کن:", reply_markup=main_menu())
        return
    store.new_chat(user_id, emp_id)
    await update.message.reply_text(
        f"🆕 <b>چت جدید با {emp['name']} شروع شد!</b>\n"
        "حافظه‌ی این گفتگو از الان خالی است؛ چت‌های قبلی در «📜 چت هیستوری» محفوظ می‌مانند.",
        parse_mode=ParseMode.HTML,
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """مدیریت دکمه‌های شیشه‌ای (Inline)."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "noop":
        return

    if data.startswith("page:"):
        _, prefix, page_s = data.split(":")
        await query.message.reply_text(
            "👇 انتخاب کن:", reply_markup=employee_keyboard(prefix, int(page_s))
        )

    elif data == "invite":
        me = await context.bot.get_me()
        link = invite_link(me.username or "", user_id)
        share_url = (
            f"https://t.me/share/url?url={quote(link)}"
            f"&text={quote(f'من با تیم {len(EMPLOYEES)} نفره‌ی هوش مصنوعی در تلگرام کار می‌کنم! تو هم امتحان کن 👇')}"
        )
        await query.message.reply_text(
            "🎁 <b>دعوت دوستان — رشد کن!</b>\n\n"
            f"این لینک مخصوص خودت است:\n{link}\n\n"
            f"تا حالا {store.invited_count(user_id)} نفر با لینک تو آمده‌اند 🚀",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 ارسال به دوستان", url=share_url),
            ]]),
        )

    elif data.startswith("rate:"):
        parts = data.split(":")
        if len(parts) != 3 or parts[1] not in ("up", "down"):
            return
        vote = 1 if parts[1] == "up" else -1
        store.add_rating(user_id, parts[2], vote)
        store.award_xp(user_id, XP_PER_RATING)   # ⭐ پاداش بابت ثبت نظر
        # جایگزینی دکمه‌ی رأی با ✅ تا دوباره رأی ثبت نشود
        rows = []
        for row in (query.message.reply_markup.inline_keyboard if query.message.reply_markup else []):
            new_row = []
            for btn in row:
                if btn.callback_data == data:
                    new_row.append(InlineKeyboardButton("✅ نمره‌ات ثبت شد", callback_data="noop"))
                else:
                    new_row.append(btn)
            rows.append(new_row)
        try:
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(rows) if rows else None
            )
        except Exception:
            pass

    elif data == "bc:yes":
        if not _is_admin(user_id):
            return
        text = context.user_data.get("pending_bc", "")
        if not text:
            await query.message.reply_text("پیامی برای ارسال در نوبت نبود.")
            return
        context.user_data["pending_bc"] = None
        ids = store.all_user_ids()
        ok = 0
        status = await query.message.reply_text("⏳ در حال ارسال...")
        for uid_s in ids:
            try:
                await context.bot.send_message(int(uid_s), f"📣 {text}")
                ok += 1
                await asyncio.sleep(0.05)  # احترام به محدودیت تلگرام
            except Exception:
                pass
        await status.edit_text(f"✅ پیام به {ok} نفر از {len(ids)} کاربر ارسال شد.")

    elif data == "bc:no":
        if not _is_admin(user_id):
            return
        context.user_data["pending_bc"] = None
        await query.message.reply_text("❌ ارسال لغو شد.")

    elif data == "menu":
        context.user_data["mode"] = None
        await query.message.reply_text("🏠 منوی اصلی:", reply_markup=main_menu())

    elif data == "team":
        pages = team_pages()
        for i, page_text in enumerate(pages):
            kb = employee_keyboard("chat") if i == len(pages) - 1 else None
            await query.message.reply_text(page_text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "chat_menu":
        await query.message.reply_text(
            "💬 با کدام کارمند می‌خواهی حرف بزنی؟", reply_markup=employee_keyboard("chat")
        )

    elif data == "task_menu":
        await query.message.reply_text(
            "📋 تسک را به کدام کارمند می‌دهی؟", reply_markup=employee_keyboard("task")
        )

    elif data == "clear":
        store.clear(user_id)
        context.user_data["mode"] = None
        await query.message.reply_text(
            "🧹 حافظه‌ی گفتگوها پاک شد. (بایگانی چت هیستوری حفظ می‌شود)\n"
            "برای پاک کردن بایگانی، از 📜 چت هیستوری استفاده کن.",
        )

    elif data == "history":
        await query.message.reply_text(
            history_overview_text(user_id),
            parse_mode=ParseMode.HTML,
            reply_markup=history_keyboard(user_id),
        )

    elif data.startswith("hpage:"):
        if not data.split(":", 1)[1].isdigit():
            return
        page = int(data.split(":", 1)[1])
        await query.message.reply_text(
            history_overview_text(user_id),
            parse_mode=ParseMode.HTML,
            reply_markup=history_keyboard(user_id, page),
        )

    elif data.startswith("hview:"):
        parts = data.split(":")
        if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            await show_history_page(query.message, user_id, parts[1], int(parts[2]), int(parts[3]))
        else:
            # دکمه‌ی قدیمی (قبل از آپدیت ربات) — کاربر باید از فهرست دوباره باز کند
            await query.message.reply_text("📜 این دکمه قدیمی است؛ از 📜 چت هیستوری دوباره باز کن.")

    elif data.startswith("hnav:"):
        parts = data.split(":")
        if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            await show_history_page(query.message, user_id, parts[1], int(parts[2]), int(parts[3]))
        elif len(parts) == 3 and parts[2].isdigit():
            await query.message.reply_text("📜 این دکمه قدیمی است؛ از 📜 چت هیستوری دوباره باز کن.")

    elif data.startswith("hclear:"):
        parts = data.split(":")
        if len(parts) != 3 or not parts[2].isdigit():
            return
        emp_id, session = parts[1], int(parts[2])
        emp = EMPLOYEES.get(emp_id)
        title = f"{emp['emoji']} {emp['name']}" if emp else emp_id
        archive.clear(user_id, emp_id, session)
        await query.message.reply_text(
            f"🧹 بایگانی این گفتگو با {title} پاک شد.",
            reply_markup=history_keyboard(user_id),
        )

    elif data == "hclearall":
        rows = [
            [
                InlineKeyboardButton("✅ بله، همه پاک شود", callback_data="hclearall:yes"),
                InlineKeyboardButton("❌ نه", callback_data="history"),
            ],
        ]
        await query.message.reply_text(
            "🧹 مطمئنی که همه‌ی بایگانی گفتگوهایت پاک شود؟",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    elif data.startswith("hclearall:"):
        if data.endswith("yes"):
            archive.clear(user_id)
            await query.message.reply_text("🧹 کل بایگانی گفتگوهایت پاک شد.", reply_markup=main_menu())
        else:
            await query.message.reply_text("📜 بایگانی دست‌نخورده ماند.", reply_markup=history_keyboard(user_id))

    elif data.startswith("regen:"):
        emp_id = data.split(":", 1)[1]
        emp = EMPLOYEES.get(emp_id)
        if not emp:
            return
        store.delete_last(user_id, emp_id, "assistant")   # جواب قبلی برداشته می‌شود
        await _edit_message(query.message, "🔁 در حال پاسخ دوباره…")
        answer = await stream_answer(emp, store.get_history(user_id, emp_id), query.message, user_id, emp_id)
        if answer is None:
            await query.message.reply_text(
                "⚠️ ارتباط با هوش مصنوعی برقرار نشد. دوباره امتحان کن.",
                reply_markup=answer_keyboard(emp_id),
            )
            return
        store.append(user_id, emp_id, "assistant", answer)

    elif data.startswith("newchat:"):
        emp_id = data.split(":", 1)[1]
        emp = EMPLOYEES.get(emp_id)
        if not emp:
            return
        store.new_chat(user_id, emp_id)
        context.user_data["mode"] = ("chat", emp_id)
        await query.message.reply_text(
            f"🆕 <b>چت جدید با {emp['name']} شروع شد!</b>\n"
            "حافظه‌ی این گفتگو از الان خالی است، ولی چت‌های قبلی در «📜 چت هیستوری» می‌ماند.\n"
            "اولین پیامت را بفرست:",
            parse_mode=ParseMode.HTML,
        )

    elif data == "stop":
        _cancel_flags.add(user_id)

    elif data.startswith("chat:"):
        emp_id = data.split(":", 1)[1]
        emp = EMPLOYEES.get(emp_id)
        if emp:
            context.user_data["mode"] = ("chat", emp_id)
            has_history = bool(store.get_history(user_id, emp_id))
            extra = " (حافظه‌ی گفتگوی قبلی‌تان هم در دسترس است ✅)" if has_history else ""
            await query.message.reply_text(
                f"💬 الان داری با <b>{emp['name']}</b> ({emp['role']}) حرف می‌زنی{extra}.\n"
                "پیامت را بنویس تا به‌عنوان مشاور جوابت را بدهد.\n"
                "برای بازگشت به منو: /menu",
                parse_mode=ParseMode.HTML,
            )
            # 🚀 استارتر پک: سؤال‌های آماده برای شروع سریع
            starters = starter_questions(emp_id)
            if starters:
                await query.message.reply_text(
                    "🚀 <b>استارتر پک</b> — یک سؤال آماده را انتخاب کن یا خودت بنویس:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton(f"💡 {s[:42]}", callback_data=f"sugg:{i}:{emp_id}")]
                            for i, s in enumerate(starters)
                        ]
                    ),
                )

    elif data.startswith("sugg:"):
        # 🚀 استارتر پک: کاربر یکی از سؤال‌های آماده را انتخاب کرد
        parts = data.split(":")
        if len(parts) != 3 or not parts[1].isdigit():
            return
        emp_id = parts[2]
        qs = starter_questions(emp_id)
        idx = int(parts[1])
        if not (0 <= idx < len(qs)):
            return
        context.user_data["mode"] = ("chat", emp_id)
        await query.message.reply_text(f"💡 {qs[idx]}\n\n👆 همین را بفرست یا سؤال خودت را بنویس:")

    elif data.startswith("task:"):
        emp_id = data.split(":", 1)[1]
        emp = EMPLOYEES.get(emp_id)
        if emp:
            context.user_data["mode"] = ("awaiting_task", emp_id)
            await query.message.reply_text(
                f"📋 <b>تسک جدید برای {emp['name']} ({emp['role']})</b>\n"
                "متن تسک را در یک پیام بفرست تا کار را شروع کند:\n"
                "\n"
                "💡 مثال: «می‌خواهم یک ربات تلگرام فروشگاهی بسازم، از کجا شروع کنم؟»",
                parse_mode=ParseMode.HTML,
            )


# ────────────────────── 🤖 حالت خودکار: تیم بدون منو ──────────────────────

AUTO_ROUTE = True                    # کاربر بدون انتخاب کارمند پیام بدهد → مدیر تیم بهترین نفر را وصل می‌کند
WHISPER_MODEL = "whisper-large-v3"   # تبدیل پیام صوتی به متن (سرویس voice-to-text روی Groq)


def keyword_route(text: str):
    """مسیریابی آفلاین و سبک: بهترین تطبیق کلیدواژه‌های پیام با نقش/وظیفه‌ی کارمندها."""
    text = text.lower()
    best_id, best_score = None, 0
    for emp_id, emp in EMPLOYEES.items():
        hay = f"{emp['name']} {emp['role']} {emp['duty']}".lower()
        score = sum(1 for w in re.findall(r"\w{4,}", hay) if w in text)
        if score > best_score:
            best_id, best_score = emp_id, score
    return best_id


async def ai_route(user_text: str):
    """مدیر تیم با هوش مصنوعی بهترین کارمند را برای این پیام انتخاب می‌کند (fallback: keyword_route)."""
    listing = "\n".join(f"- {eid}: {emp['role']}" for eid, emp in EMPLOYEES.items())
    prompt = (
        "تو مدیر پروژه‌ی یک تیم هستی. بر اساس پیام کاربر، مناسب‌ترین کارمند را انتخاب کن.\n"
        f"فهرست کارمندها (شناسه: نقش):\n{listing}\n\n"
        f"پیام کاربر: {user_text[:1000]}\n\n"
        "فقط و فقط شناسه‌ی کارمند را خروجی بده (مثال: writer). بدون توضیح اضافه."
    )
    try:
        resp = await get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=100,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"[a-zA-Z0-9_\-]+", raw)
        if m and m.group(0).lower() in EMPLOYEES:
            return m.group(0).lower()
        for eid in EMPLOYEES:
            if eid in raw:
                return eid
        return None
    except Exception as exc:
        logger.warning("مسیریابی هوشمند ناموفق بود: %s", exc)
        return None


def starter_questions(emp_id: str):
    """🚀 استارتر پک: سه سؤال آماده برای شروع گفتگو با هر کارمند."""
    emp = EMPLOYEES.get(emp_id)
    if not emp:
        return []
    role = emp["role"]
    return [
        f"سلام {emp['name']}! کار شما دقیقاً چیست و چطور می‌توانی کمکم کنی؟",
        f"برای امروز یک اقدام عملی در حوزه‌ی «{role}» پیشنهاد بده.",
        f"سه اشتباه رایج در «{role}» را بگو و راه جلوگیری از آن‌ها را توضیح بده.",
    ]


def meeting_panel(topic: str = ""):
    """🤝 ترکیب تیم جلسه‌ی فوری: مدیر پروژه + کارمند مرتبط با موضوع + یک عضو تکمیلی."""
    picked = ["manager"]
    routed = keyword_route(topic) if topic else None
    if routed and routed not in picked:
        picked.append(routed)
    for eid in list(EMPLOYEES):
        if len(picked) >= 3:
            break
        if eid not in picked:
            picked.append(eid)
    return picked[:3]


def export_text(user_id: int, emp_id: str, store_=None) -> str:
    """💾 کل بایگانی یک گفتگو به‌صورت متن قابل ذخیره (برای /export)."""
    src = store_ if store_ is not None else archive
    emp = EMPLOYEES.get(emp_id)
    title = f"{emp['emoji']} {emp['name']} ({emp['role']})" if emp else emp_id
    lines = [f"📜 بایگانی گفتگو با {title}", "=" * 40]
    for row in src.get_all(user_id, emp_id):
        who = "👤 شما" if row["role"] == "user" else (f"{emp['emoji']} {emp['name']}" if emp else "🤖 کارمند")
        lines.append(f"{who}:\n{row['content']}\n")
    return "\n".join(lines)


# ────────────────────── 🔒 قفل تخصص: هر کار فقط دستِ متخصصش ──────────────────────

# هر تخصص فقط مال یک متخصص است: نگار کد پایتون نمی‌دهد، بهراد سناریو نمی‌نویسد!
# keywords = کلمه‌هایی که یعنی کارِ آن متخصص درخواست شده · excludes = عباراتی که تله‌ی کلمه‌ی مشابه را خنثی می‌کنند
EXCLUSIVE_SKILLS = {
    "developer": {
        "skill": "کدنویسی و برنامه‌نویسی",
        "keywords": (
            "پایتون", "python", "جاوااسکریپت", "javascript", "برنامه‌نویسی", "برنامه بنویس",
            "کد", "کدنویسی", "باگ", "دیباگ", "debug", "فانکشن", "الگوریتم", "دیتابیس", "sql",
        ),
        "excludes": ("کد تخفیف", "کد ویژه", "کدو", "کدپستی", "کد پستی"),
    },
    "scenario_writer": {
        "skill": "سناریو و فیلمنامه",
        "keywords": ("سناریو", "فیلمنامه", "دیالوگ"),
        "excludes": (),
    },
    "marketer": {
        "skill": "بازاریابی و تبلیغات",
        "keywords": ("تبلیغ", "بازاریابی", "کمپین", "کپی‌رایتر", "سئو", "فالوور"),
        "excludes": (),
    },
    "manager": {
        "skill": "مدیریت پروژه و برنامه‌ریزی",
        "keywords": ("مدیریت پروژه", "برنامه‌ریزی", "نقشه راه", "زمان‌بندی", "اولویت‌بندی"),
        "excludes": (),
    },
}


def skill_owner(text: str):
    """🔒 اگر پیام درخواست یک تخصص انحصاری باشد، (شناسه‌ی متخصص، نام تخصص) برمی‌گرداند؛ وگرنه None."""
    text_l = text.lower()
    for owner, info in EXCLUSIVE_SKILLS.items():
        if any(ex in text_l for ex in info.get("excludes", ())):
            continue
        for kw in info["keywords"]:
            if kw in text_l:
                if owner in EMPLOYEES:
                    return owner, info["skill"]
                break
    return None


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🎙 پیام صوتی/فایل صوتی کاربر → متن (whisper روی Groq) → دقیقاً مثل پیام تایپی پردازش می‌شود."""
    if not update.message or not (update.message.voice or update.message.audio):
        return
    media = update.message.voice or update.message.audio
    user_id = update.effective_user.id
    store.touch_user(user_id, update.effective_user.first_name or "")
    if not _is_admin(user_id) and store.messages_today(user_id) >= FREE_DAILY_LIMIT:
        await update.message.reply_text(limit_text(), parse_mode=ParseMode.HTML)
        return
    # شمارش و XP در handle_message انجام می‌شود (اینجا فقط کنترل ظرفیت قبل از دانلود)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await update.message.reply_text("🎙 دارم صدایت را می‌شنوم…")
    try:
        tg_file = await media.get_file()
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        buf.seek(0)
        buf.name = "voice.ogg" if update.message.voice else "audio.mp3"
        resp = await get_groq_client().audio.transcriptions.create(model=WHISPER_MODEL, file=buf)
        transcribed = (resp.text or "").strip()
    except Exception as exc:
        logger.error("خطای تبدیل پیام صوتی: %s", exc)
        await update.message.reply_text("🎙 نتوانستم پیام صوتی‌ات را تبدیل به متن کنم؛ دوباره امتحان کن یا تایپ کن.")
        return
    if not transcribed or transcribed == ".":
        await update.message.reply_text("🎙 صدایی نشنیدم؛ لطفاً نزدیک‌تر و واضح‌تر دوباره بفرست.")
        return
    await update.message.reply_text(f"🎙 شنیدم: «{transcribed[:300]}»")
    # متن پیام تلگرام تغییرناپذیر (frozen) است؛ متن ویس را مستقیم پاس می‌دهیم
    await handle_message(update, context, override_text=transcribed)


async def cmd_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🤝 جلسه‌ی فوری: ۳ کارمند به‌صورت هم‌زمان درباره‌ی موضوع کاربر نظر می‌دهند."""
    topic = " ".join(context.args or []).strip()
    if not topic:
        await update.message.reply_text(
            "🤝 <b>جلسه‌ی فوری</b> — موضوع را بنویس تا ۳ کارمند نظر بدهند:\n"
            "/meeting ایده‌ی استارتاپ من برای فروش آنلاین",
            parse_mode=ParseMode.HTML,
        )
        return
    user_id = update.effective_user.id
    store.touch_user(user_id, update.effective_user.first_name or "")
    if not _is_admin(user_id) and store.messages_today(user_id) >= FREE_DAILY_LIMIT:
        await update.message.reply_text(limit_text(), parse_mode=ParseMode.HTML)
        return
    store.incr_user(user_id)
    panel = meeting_panel(topic)
    status = await update.message.reply_text(
        "🤝 <b>جلسه‌ی فوری تشکیل شد!</b>\n"
        + "\n".join(
            f"▎{EMPLOYEES[e]['emoji']} {EMPLOYEES[e]['name']} ({EMPLOYEES[e]['role']})"
            for e in panel
        )
        + f"\n\n⏳ دارند درباره‌ی «{html.escape(topic[:80])}» فکر می‌کنند…",
        parse_mode=ParseMode.HTML,
    )
    sections = []
    for eid in panel:
        emp = EMPLOYEES[eid]
        prompt = (
            f"موضوع جلسه: {topic}\n\n"
            f"در حداکثر ۴ جمله، از زاویه‌ی نقش خودت ({emp['role']}) نکته‌ی کلیدی و یک پیشنهاد عملی بده. بدون مقدمه."
        )
        answer = await ask_groq(emp, [{"role": "user", "content": prompt}])
        if answer:
            sections.append(f"◆ <b>{emp['emoji']} {emp['name']} — {emp['role']}:</b>\n{md_to_html(answer)}")
        else:
            sections.append(f"◆ <b>{emp['emoji']} {emp['name']}:</b> 😔 نتوانستم پاسخ بدهم")
    text = (
        "🤝 <b>جلسه‌ی فوری — نتیجه</b>\n"
        f"📌 موضوع: {html.escape(topic[:120])}\n"
        "⚡️━━━━━━━━━━━━━━━━⚡️\n\n" + "\n\n".join(sections)
    )
    await _edit_message(status, text, html_text=text, reply_markup=answer_keyboard(panel[0]))
    store.append(user_id, panel[0], "assistant", f"🤝 جلسه‌ی فوری درباره‌ی «{topic}»:\n" + "\n".join(re.sub(r"<[^>]+>", "", s) for s in sections))


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """💾 خروجی آخرین گفتگو به‌صورت فایل متنی."""
    user_id = update.effective_user.id
    rows = archive.overview(user_id)
    if not rows:
        await update.message.reply_text("هنوز گفتگویی برای خروجی گرفتن نداری. اول با یکی از کارمندها حرف بزن 🙂")
        return
    emp_id = rows[0][0]
    emp = EMPLOYEES.get(emp_id)
    data = export_text(user_id, emp_id)
    await update.message.reply_document(
        document=io.BytesIO(data.encode("utf-8")),
        filename=f"chat-{emp_id}.txt",
        caption=(
            f"💾 خروجی گفتگو با {emp['name'] if emp else emp_id}\n"
            f"📜 {len(rows)} گفتگو در بایگانی‌ات هست — برای انتخاب گفتگوی دیگر: /history"
        ),
    )


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, override_text: str = None
) -> None:
    """پاسخ‌دهی به پیام‌های متنی کاربر — با انتخاب کارمند یا مسیریابی خودکار تیم.
    override_text: برای پیام صوتی (متنِ تبدیل‌شده‌ی ویس) — چون آبجکت Message تلگرام تغییرناپذیر است."""
    if not update.message:
        return
    raw_text = override_text if override_text is not None else update.message.text
    if not raw_text or not raw_text.strip():
        return

    user_id = update.effective_user.id
    user_text = raw_text.strip()
    mode = context.user_data.get("mode")

    # 🚀 ثبت پروفایل + ظرفیت روزانه + XP و استریک (برای همه‌ی مسیرها)
    store.touch_user(user_id, update.effective_user.first_name or "")
    if not _is_admin(user_id) and store.messages_today(user_id) >= FREE_DAILY_LIMIT:
        await update.message.reply_text(limit_text(), parse_mode=ParseMode.HTML)
        return
    store.incr_user(user_id)
    prev_level, _, _ = level_from_xp((store.user_info(user_id) or {}).get("xp", 0))
    store.award_xp(user_id, XP_PER_MESSAGE)
    store.bump_streak(user_id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    # 🤖 حالت خودکار: کاربر لازم نیست کارمند انتخاب کند — مدیر تیم بهترین نفر را وصل می‌کند
    if not mode:
        if not AUTO_ROUTE:
            await update.message.reply_text(
                "برای شروع، از منوی زیر یک گزینه را انتخاب کن 👇",
                reply_markup=main_menu(),
            )
            return
        routed = await ai_route(user_text) or keyword_route(user_text)
        if not routed or routed not in EMPLOYEES:
            await update.message.reply_text(
                "🤔 نتوانستم تشخیص بدهم کدام کارمند بهترین جواب را می‌دهد؛ از منوی زیر انتخاب کن:",
                reply_markup=main_menu(),
            )
            return
        emp0 = EMPLOYEES[routed]
        await update.message.reply_text(
            f"🎯 <b>مدیر تیم وصلت کرد:</b> {emp0['emoji']} {emp0['name']} ({emp0['role']})\n"
            "از این لحظه با همین کارمند گفتگو می‌کنی — برای تغییر کارمند /menu بزن.",
            parse_mode=ParseMode.HTML,
        )
        context.user_data["mode"] = mode = ("chat", routed)

    kind, emp_id = mode
    employee = EMPLOYEES.get(emp_id)
    if not employee:
        context.user_data["mode"] = None
        await update.message.reply_text("کارمند مورد نظر پیدا نشد. دوباره انتخاب کن:", reply_markup=main_menu())
        return

    # 🔒 قفل تخصص: هر کار فقط دستِ متخصصِ خودش است (مثلاً کد پایتون فقط از بهراد)
    guard = skill_owner(user_text)
    if guard and guard[0] != emp_id:
        owner_id, skill_name = guard
        owner_emp = EMPLOYEES.get(owner_id)
        if owner_emp:
            await update.message.reply_text(
                f"{employee['emoji']} <b>{employee['name']}:</b> 😅 این از تخصص من خارجه، ببخشید!\n"
                f"🔒 «{skill_name}» فقط دست <b>{owner_emp['name']}</b> ({owner_emp['role']}) است.\n"
                "👇 کلیک کن تا مستقیم پیشِ او بروی:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(
                        f"🔗 برو پیش {owner_emp['name']} ({owner_emp['emoji']})",
                        callback_data=f"chat:{owner_id}",
                    )]]
                ),
            )
            return

    # ثبت پیام کاربر در دیتابیس (همان دیتابیس هم حافظه است هم بایگانی)
    if kind == "awaiting_task":
        text_to_save = f"📋 تسک جدید:\n{user_text}"
    else:
        text_to_save = user_text
    store.append(user_id, emp_id, "user", text_to_save)

    # پاسخ زنده (استریم): جواب همان لحظه حرف‌به‌حرف تایپ می‌شود — مثل Grok و Dots
    placeholder = await update.message.reply_text(
        f"{employee['emoji']} در حال فکر کردن…",
        reply_markup=stop_keyboard(),
    )
    answer = await stream_answer(
        employee, store.get_history(user_id, emp_id), placeholder, user_id, emp_id
    )

    if answer is None:
        try:
            await placeholder.edit_text(
                "⚠️ ارتباط با هوش مصنوعی برقرار نشد. چند لحظه بعد دوباره امتحان کن."
            )
        except Exception:
            await update.message.reply_text(
                "⚠️ ارتباط با هوش مصنوعی برقرار نشد. چند لحظه بعد دوباره امتحان کن."
            )
        return

    store.append(user_id, emp_id, "assistant", answer)

    # بعد از ثبت تسک، گفتگو با همان کارمند ادامه پیدا می‌کند
    context.user_data["mode"] = ("chat", emp_id)

    # 🎉 جشن ارتقای سطح (فقط وقتی سطح واقعاً بالا رفته باشد)
    new_level, level_title, _ = level_from_xp((store.user_info(user_id) or {}).get("xp", 0))
    if new_level > prev_level:
        try:
            await update.message.reply_text(
                f"🎉 <b>تبریک!</b> به سطح <b>{level_title}</b> رسیدی!\n"
                "ادامه بده — رکورد بعدی خیلی نزدیک است 🚀",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📊 پروفایل و آمار شخصی کاربر."""
    user_id = update.effective_user.id
    store.touch_user(user_id, update.effective_user.first_name or "")
    info = store.user_info(user_id) or {}
    fav_id = store.fav_employee(user_id)
    if fav_id:
        fav = EMPLOYEES.get(fav_id)
        fav_line = f"{fav['emoji']} {fav['name']}" if fav else fav_id
    else:
        fav_line = "هنوز با کسی چت نکردی 😊"
    me = await context.bot.get_me()
    link = invite_link(me.username or "", user_id)
    xp = (info or {}).get("xp", 0)
    level, title, next_at = level_from_xp(xp)
    streak = (info or {}).get("streak", 0)
    rank = store.user_rank(user_id)
    next_line = f" | تا سطح بعد: {next_at} XP" if next_at else " | حداکثر سطح! 👑"
    await update.message.reply_text(
        "📊 <b>پروفایل تو در تیم هوش مصنوعی</b>\n"
        "⚡️━━━━━━━━━━━━━━━━⚡️\n"
        f"▎⭐ سطح: <b>{title}</b> ({level} از {len(LEVELS)})\n"
        f"▎{progress_bar(xp)}  {xp} XP{next_line}\n"
        f"▎🔥 استریک: {streak} روز پشت‌سرهم\n"
        f"▎🏆 رتبه در لیدربرد: #{rank}\n"
        f"▎🗓 عضویت: {_fmt_ts(info.get('joined_at'))}\n"
        f"▎💬 پیام‌هایی که دادی: {store.total_user_messages(user_id)}\n"
        f"▎❤️ کارمند موردعلاقه‌ات: {fav_line}\n"
        f"▎🎁 دوستان دعوت‌شده: {store.invited_count(user_id)}\n"
        f"▎🚀 ظرفیت امروز: {store.messages_today(user_id)} / {FREE_DAILY_LIMIT}\n"
        "⚡️━━━━━━━━━━━━━━━━⚡️\n"
        f"لینک دعوت اختصاصی‌ات:\n{link}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📤 ارسال لینک به دوستان",
                                 url=f"https://t.me/share/url?url={quote(link)}&text={quote(f'من با تیم {len(EMPLOYEES)} نفره‌ی هوش مصنوعی در تلگرام کار می‌کنم! تو هم امتحان کن 👇')}"),
        ]]),
    )


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🏆 لیدربرد — برترین کاربران و پرطرفدارترین کارمندهای تیم."""
    user_id = update.effective_user.id
    store.touch_user(user_id, update.effective_user.first_name or "")
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, name, xp, streak) in enumerate(store.leaderboard(10), start=1):
        tag = medals[i - 1] if i <= 3 else f"{i}."
        _, title, _ = level_from_xp(xp)
        lines.append(f"{tag} {name or 'کاربر ناشناس'} — {xp} XP · {title}")
    emp_lines = []
    for emp_id, count in store.top_employees(5):
        emp = EMPLOYEES.get(emp_id)
        emp_lines.append(
            f"▎{emp['emoji']} {emp['name']}: {count} گفتگو" if emp else f"▎🗂 {emp_id}: {count} گفتگو"
        )
    my_rank = store.user_rank(user_id)
    my_info = store.user_info(user_id) or {}
    await update.message.reply_text(
        "🏆 <b>لیدربرد — ستاره‌های استارتاپ</b>\n"
        "⚡️━━━━━━━━━━━━━━━━⚡️\n"
        + ("\n".join(lines) or "هنوز کسی امتیاز نگرفته — تو اولین باش! 🚀")
        + "\n\n⚡️━━━━━━━━━━━━━━━━⚡️\n"
        f"▎🌟 رتبه‌ی تو: #{my_rank} با {my_info.get('xp', 0)} XP\n\n"
        "🔥 <b>پرمشغله‌ترین کارمندهای تیم:</b>\n"
        + ("\n".join(emp_lines) or "—"),
        parse_mode=ParseMode.HTML,
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🛠 پنل ادمین (فقط برای ADMIN_IDS)."""
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await update.message.reply_text("⛔️ این بخش فقط برای ادمین‌هاست.")
        return
    up, down = store.rating_summary()
    top_lines = []
    for emp_id, count in store.top_employees(5):
        emp = EMPLOYEES.get(emp_id)
        top_lines.append(f"▎{emp['emoji']} {emp['name']}: {count} پیام" if emp else f"▎🗂 {emp_id}: {count} پیام")
    try:
        db_kb = os.path.getsize(DB_FILE) // 1024
    except OSError:
        db_kb = 0
    await update.message.reply_text(
        "🛠 <b>پنل ادمین استارتاپ</b>\n"
        "⚡️━━━━━━━━━━━━━━━━⚡️\n"
        f"▎👥 کل کاربران: {store.count_users()}\n"
        f"▎💬 کل پیام‌ها: {store.count_messages()}\n"
        f"▎🔥 فعال امروز: {store.active_today()}\n"
        f"▎👍 {up}  |  👎 {down}\n"
        f"▎🗄 حجم دیتابیس: {db_kb} KB\n"
        f"▎⏱ آپتایم ربات: {uptime_str()}\n"
        "⚡️━━━━━━━━━━━━━━━━⚡️\n"
        "📈 <b>فعالیت ۷ روز اخیر:</b>\n"
        f"{weekly_chart(store.weekly_activity())}\n"
        "🏆 <b>پرمشغله‌ترین کارمندها:</b>\n" + ("\n".join(top_lines) or "—") +
        "\n\n📣 برای ارسال پیام به همه: /broadcast متن_پیام",
        parse_mode=ParseMode.HTML,
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📣 ارسال پیام به همه‌ی کاربران (فقط ادمین؛ با تأیید)."""
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ این بخش فقط برای ادمین‌هاست.")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("📣 متن پیام را بعد از دستور بنویس:\n/broadcast سلام به همه!")
        return
    context.user_data["pending_bc"] = text
    rows = [[
        InlineKeyboardButton("✅ ارسال کن", callback_data="bc:yes"),
        InlineKeyboardButton("❌ لغو", callback_data="bc:no"),
    ]]
    await update.message.reply_text(
        f"📣 می‌خواهی این پیام برای همه‌ی {store.count_users()} کاربر ارسال شود؟\n\n«{text}»",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ این دستور را نمی‌شناسم. از /menu منوی اصلی را باز کن.",
        reply_markup=main_menu(),
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("خطای ربات:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ خطایی پیش آمد. لطفاً دوباره تلاش کن.")

# ══════════════════════════ اجرای ربات ══════════════════════════


def validate_config() -> None:
    """چک می‌کند که توکن و کلید API جایگزین شده باشند."""
    errors = []
    if not TELEGRAM_TOKEN or "اینجا" in TELEGRAM_TOKEN:
        errors.append(
            "❌ توکن ربات تلگرام تنظیم نشده است.\n"
            "   → از @BotFather در تلگرام توکن بگیر و در متغیر TELEGRAM_TOKEN "
            "(بالای فایل bot.py) قرار بده."
        )
    if not GROQ_API_KEY or "اینجا" in GROQ_API_KEY:
        errors.append(
            "❌ کلید Groq API تنظیم نشده است.\n"
            "   → از https://console.groq.com/keys کلید بگیر و در متغیر GROQ_API_KEY "
            "(بالای فایل bot.py) قرار بده."
        )
    if errors:
        print("\n" + "=" * 60)
        print("خطاهای تنظیمات:")
        for err in errors:
            print(err)
        print("=" * 60 + "\n")
        sys.exit(1)


async def post_init(app) -> None:
    """آماده‌سازی هنگام استارت: منوی دستورات + شناسایی یوزرنیم ربات (برای لینک دعوت)."""
    global BOT_USERNAME
    try:
        me = await app.bot.get_me()
        BOT_USERNAME = me.username or ""
        logger.info("ربات @%s روشن شد", BOT_USERNAME)
    except Exception as exc:
        logger.warning("گرفتن یوزرنیم ربات ناموفق بود: %s", exc)
    await app.bot.set_my_commands([
        BotCommand("start", "شروع و منوی اصلی"),
        BotCommand("new", "چت جدید با کارمند فعلی"),
        BotCommand("stats", "پروفایل و آمار تو"),
        BotCommand("top", "لیدربرد — ستاره‌های استارتاپ"),
        BotCommand("meeting", "جلسه‌ی فوری ۳ نفره"),
        BotCommand("export", "خروجی گفتگو به‌صورت فایل"),
        BotCommand("history", "چت هیستوری"),
        BotCommand("help", "راهنما"),
    ])


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    validate_config()

    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("team", cmd_team))
    app.add_handler(CommandHandler("newtask", cmd_newtask))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("meeting", cmd_meeting))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message)
    )
    app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO) & filters.ChatType.PRIVATE, handle_voice))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_error_handler(error_handler)

    print("=" * 60)
    print("🚀 ربات تیم هوش مصنوعی — نسخه‌ی استارتاپ (آماده‌ی لند کردن!)")
    print(f"🧠 مدل: {GROQ_MODEL}")
    print("⌨️ پاسخ زنده (استریم) + دکمه‌های پاسخ دوباره / چت جدید / توقف / امتیازدهی")
    print("🤖 گفتگوی خودکار (مدیر تیم مسیریاب) + پیام صوتی 🎙 + جلسه‌ی فوری 🤝 + خروجی فایل 💾")
    print(f"🚀 ظرفیت روزانه‌ی هر کاربر: {FREE_DAILY_LIMIT} پیام  |  🛠 ادمین‌ها: {len(ADMIN_IDS)} نفر")
    print(f"👥 کارمندها: {len(EMPLOYEES)} نفر — از مدیر پروژه و برنامه‌نویس تا طراح، وکیل و مربی شطرنج")
    print(f"🗄️ دیتابیس: {DB_FILE} — حافظه تا {CONTEXT_MAX_MESSAGES} پیام قبلی را یادش می‌ماند")
    print("برای خاموش‌کردن Ctrl+C را بزن.")
    print("=" * 60)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

