# -*- coding: utf-8 -*-
"""
🗄️ دیتابیس SQL (SQLite) — حافظه‌ی کامل و همیشگی ربات

- همه‌ی پیام‌ها (کاربر و کارمند) در دیتابیس SQL ذخیره می‌شوند
- برای هر کاربر و هر کارمند، گفتگوها جداگانه نگه داشته می‌شوند
- هوش مصنوعی آخرین ~۱۵۰ پیام را در جوابش در نظر می‌گیرد،
  پس دیگر با آمدن پیام‌های جدید، پیام‌های قبلی فراموش نمی‌شوند
- بخش «چت هیستوری» هم از همین دیتابیس می‌خواند
- SQLite داخل خود پایتون هست؛ نیاز به نصب چیز اضافه‌ای نیست
"""

import json
import logging
import os
import sqlite3
import time

logger = logging.getLogger(__name__)


class SQLStore:
    """ذخیره‌ی همه‌ی پیام‌ها در SQLite با جداسازی کامل کاربر/کارمند."""

    def __init__(self, path: str, context_max_messages: int = 150, char_budget: int = 60000) -> None:
        self.path = path
        self.context_max_messages = context_max_messages
        self.char_budget = char_budget
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._create_tables()
        self._migrate_schema()
        self._dedupe()

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT    NOT NULL,
                emp_id  TEXT    NOT NULL,
                role    TEXT    NOT NULL,
                content TEXT    NOT NULL,
                ts      INTEGER NOT NULL,
                session INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_state (
                user_id TEXT NOT NULL,
                emp_id  TEXT NOT NULL,
                session INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, emp_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     TEXT PRIMARY KEY,
                name        TEXT,
                joined_at   INTEGER NOT NULL,
                last_seen   INTEGER NOT NULL,
                msg_count   INTEGER NOT NULL DEFAULT 0,
                referred_by TEXT,
                xp          INTEGER NOT NULL DEFAULT 0,
                streak      INTEGER NOT NULL DEFAULT 0,
                last_day    TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT    NOT NULL,
                emp_id  TEXT    NOT NULL,
                vote    INTEGER NOT NULL,
                ts      INTEGER NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_emp ON messages(user_id, emp_id, id)"
        )
        self._conn.commit()

    def _migrate_schema(self) -> None:
        """اگر دیتابیس قدیمی باشد، ستون‌های جدید خودکار اضافه می‌شوند (هیچ‌چیز از دست نمی‌رود)."""
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "session" not in cols:
            self._conn.execute("ALTER TABLE messages ADD COLUMN session INTEGER NOT NULL DEFAULT 1")
        ucols = {row[1] for row in self._conn.execute("PRAGMA table_info(users)").fetchall()}
        for col in ("xp", "streak", "last_day"):
            if ucols and col not in ucols:
                suffix = " TEXT" if col == "last_day" else " INTEGER NOT NULL DEFAULT 0"
                self._conn.execute(f"ALTER TABLE users ADD COLUMN {col}{suffix}")
        self._conn.commit()

    def _dedupe(self) -> None:
        """حذف پیام‌های تکراری (اگر جایی یک پیام دوبار ثبت شده باشد)."""
        try:
            self._conn.execute(
                """
                DELETE FROM messages WHERE id IN (
                    SELECT m1.id FROM messages m1, messages m2
                    WHERE m1.user_id = m2.user_id AND m1.emp_id = m2.emp_id
                      AND m1.role = m2.role AND m1.content = m2.content
                      AND m1.ts = m2.ts AND m1.id > m2.id
                )
                """
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("خطا در حذف پیام‌های تکراری: %s", exc)

    # ─────────────── ثبت پیام ───────────────

    def append(self, user_id: int, emp_id: str, role: str, content: str) -> None:
        """ثبت یک پیام جدید (هرگز چیزی حذف نمی‌شود)."""
        self.add(user_id, emp_id, role, content)

    def _current_session(self, user_id: int, emp_id: str) -> int:
        """شماره‌ی نشست (چت) فعلی این کاربر با این کارمند."""
        row = self._conn.execute(
            "SELECT session FROM chat_state WHERE user_id = ? AND emp_id = ?",
            (str(user_id), emp_id),
        ).fetchone()
        return row[0] if row else 1

    def new_chat(self, user_id: int, emp_id: str) -> int:
        """شروع چت جدید: حافظه‌ی گفتگو از این لحظه خالی است، ولی بایگانی چت‌های قبلی می‌ماند."""
        next_session = self._current_session(user_id, emp_id) + 1
        self._conn.execute(
            """
            INSERT INTO chat_state (user_id, emp_id, session) VALUES (?, ?, ?)
            ON CONFLICT(user_id, emp_id) DO UPDATE SET session = excluded.session
            """,
            (str(user_id), emp_id, next_session),
        )
        self._conn.commit()
        return next_session

    def add(self, user_id: int, emp_id: str, role: str, content: str, session: int | None = None) -> None:
        """ثبت یک پیام در دیتابیس (در نشست فعلی گفتگو)."""
        try:
            if session is None:
                session = self._current_session(user_id, emp_id)
            self._conn.execute(
                "INSERT INTO messages (user_id, emp_id, role, content, ts, session) VALUES (?, ?, ?, ?, ?, ?)",
                (str(user_id), emp_id, role, str(content), int(time.time()), session),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("خطا در ذخیره‌ی پیام در دیتابیس: %s", exc)

    # ─────────────── خواندن ───────────────

    def get_history(self, user_id: int, emp_id: str) -> list:
        """حافظه‌ای که به هوش مصنوعی داده می‌شود: آخرین ~۱۵۰ پیام (تا وقتی جا باشد).
        یعنی پیام‌های قبلی یادش نمی‌رود؛ فقط برای کنترل مصرف، سقف حجم دارد."""
        rows = self._conn.execute(
            """
            SELECT role, content FROM
                (SELECT id, role, content FROM messages
                 WHERE user_id = ? AND emp_id = ? AND session = ?
                 ORDER BY id DESC LIMIT ?)
            ORDER BY id ASC
            """,
            (str(user_id), emp_id, self._current_session(user_id, emp_id), self.context_max_messages),
        ).fetchall()

        # از جدید به قدیم برمی‌گردیم تا مجموع حجم از سقف نگذرد
        picked = []
        total = 0
        for role, content in reversed(rows):
            if picked and total + len(content) > self.char_budget:
                break
            picked.append({"role": role, "content": content})
            total += len(content) + 4
        picked.reverse()
        return picked

    def get_all(self, user_id: int, emp_id: str, session: int | None = None) -> list:
        """پیام‌های یک گفتگو (با زمان) — پیش‌فرض همه‌ی نشست‌ها؛ برای بخش چت هیستوری."""
        if session is None:
            rows = self._conn.execute(
                "SELECT role, content, ts FROM messages WHERE user_id = ? AND emp_id = ? ORDER BY id ASC",
                (str(user_id), emp_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT role, content, ts FROM messages WHERE user_id = ? AND emp_id = ? AND session = ? ORDER BY id ASC",
                (str(user_id), emp_id, session),
            ).fetchall()
        return [{"role": r, "content": c, "ts": t} for r, c, t in rows]

    def overview(self, user_id: int) -> list:
        """فهرست گفتگوهای کاربر به تفکیک نشست:
        [(emp_id, session, تعداد پیام, زمان آخرین پیام)] — جدیدترین اول."""
        rows = self._conn.execute(
            """
            SELECT emp_id, session, COUNT(*), MAX(ts) FROM messages
            WHERE user_id = ? GROUP BY emp_id, session ORDER BY MAX(ts) DESC
            """,
            (str(user_id),),
        ).fetchall()
        return [(emp_id, session, count, last_ts) for emp_id, session, count, last_ts in rows if count]

    # ─────────────── پاک کردن ───────────────

    def clear(self, user_id: int, emp_id: str | None = None, session: int | None = None) -> None:
        """پاک کردن: کل کاربر، یک کارمند، یا فقط یک نشست از یک کارمند."""
        try:
            if emp_id and session is not None:
                self._conn.execute(
                    "DELETE FROM messages WHERE user_id = ? AND emp_id = ? AND session = ?",
                    (str(user_id), emp_id, session),
                )
            elif emp_id:
                self._conn.execute(
                    "DELETE FROM messages WHERE user_id = ? AND emp_id = ?",
                    (str(user_id), emp_id),
                )
            else:
                self._conn.execute("DELETE FROM messages WHERE user_id = ?", (str(user_id),))
            self._conn.commit()
        except Exception as exc:
            logger.error("خطا در پاک کردن دیتابیس: %s", exc)

    # ══════════ کاربران، امتیازها و آمار (مود استارتاپ) ══════════

    def touch_user(self, user_id: int, name: str = "", referred_by: str | None = None) -> bool:
        """ثبت/به‌روزرسانی کاربر. اگر کاربر تازه‌وارد باشد True برمی‌گرداند."""
        try:
            row = self._conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (str(user_id),)
            ).fetchone()
            now = int(time.time())
            if row is None:
                self._conn.execute(
                    "INSERT INTO users (user_id, name, joined_at, last_seen, msg_count, referred_by)"
                    " VALUES (?, ?, ?, ?, 0, ?)",
                    (str(user_id), name, now, now, referred_by),
                )
                self._conn.commit()
                return True
            self._conn.execute(
                "UPDATE users SET name = COALESCE(NULLIF(?, ''), name), last_seen = ? WHERE user_id = ?",
                (name, now, str(user_id)),
            )
            self._conn.commit()
            return False
        except Exception as exc:
            logger.error("خطا در ثبت کاربر: %s", exc)
            return False

    def incr_user(self, user_id: int) -> None:
        """یک پیام به شمارنده‌ی کاربر اضافه می‌کند (کاربر غایب را هم می‌سازد)."""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO users (user_id, name, joined_at, last_seen) VALUES (?, '', ?, ?)",
                (str(user_id), int(time.time()), int(time.time())),
            )
            self._conn.execute(
                "UPDATE users SET msg_count = msg_count + 1, last_seen = ? WHERE user_id = ?",
                (int(time.time()), str(user_id)),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("خطا در شمارش کاربر: %s", exc)

    def user_info(self, user_id: int) -> dict | None:
        """اطلاعات پروفایل کاربر (شامل XP و استریک)."""
        row = self._conn.execute(
            "SELECT user_id, name, joined_at, last_seen, msg_count, referred_by, xp, streak, last_day"
            " FROM users WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row[0], "name": row[1], "joined_at": row[2],
            "last_seen": row[3], "msg_count": row[4], "referred_by": row[5],
            "xp": row[6], "streak": row[7], "last_day": row[8],
        }

    def messages_today(self, user_id: int) -> int:
        """تعداد پیام‌های کاربر از نیمه‌شب امروز (به وقت محلی)."""
        lt = time.localtime()
        midnight = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))
        row = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user' AND ts >= ?",
            (str(user_id), midnight),
        ).fetchone()
        return row[0] if row else 0

    def total_user_messages(self, user_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user'", (str(user_id),)
        ).fetchone()
        return row[0] if row else 0

    def active_days(self, user_id: int) -> int:
        """تعداد روزهای متمایزی که کاربر پیام داده."""
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT date(ts, 'unixepoch', 'localtime')) FROM messages WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        return row[0] if row else 0

    def fav_employee(self, user_id: int) -> str | None:
        """کارمند موردعلاقه‌ی کاربر (بیشترین گفتگو)."""
        row = self._conn.execute(
            "SELECT emp_id FROM messages WHERE user_id = ? GROUP BY emp_id ORDER BY COUNT(*) DESC LIMIT 1",
            (str(user_id),),
        ).fetchone()
        return row[0] if row else None

    def invited_count(self, user_id: int) -> int:
        """تعداد دوستانی که با لینک این کاربر آمده‌اند."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (str(user_id),)
        ).fetchone()
        return row[0] if row else 0

    def count_users(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def count_messages(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def active_today(self) -> int:
        """تعداد کاربران فعال از نیمه‌شب امروز."""
        lt = time.localtime()
        midnight = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))
        return self._conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM messages WHERE ts >= ?", (midnight,)
        ).fetchone()[0]

    def all_user_ids(self) -> list[str]:
        return [row[0] for row in self._conn.execute("SELECT user_id FROM users").fetchall()]

    def add_rating(self, user_id: int, emp_id: str, vote: int) -> None:
        """ثبت رأی 👍 (+1) یا 👎 (-1) کاربر به جواب یک کارمند."""
        try:
            self._conn.execute(
                "INSERT INTO ratings (user_id, emp_id, vote, ts) VALUES (?, ?, ?, ?)",
                (str(user_id), emp_id, 1 if vote >= 0 else -1, int(time.time())),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("خطا در ثبت رأی: %s", exc)

    def rating_summary(self) -> tuple[int, int]:
        """مجموع 👍 و 👎 کل ربات."""
        up = self._conn.execute("SELECT COUNT(*) FROM ratings WHERE vote = 1").fetchone()[0]
        down = self._conn.execute("SELECT COUNT(*) FROM ratings WHERE vote = -1").fetchone()[0]
        return up, down

    def top_employees(self, n: int = 5) -> list[tuple[str, int]]:
        rows = self._conn.execute(
            "SELECT emp_id, COUNT(*) FROM messages WHERE role = 'user'"
            " GROUP BY emp_id ORDER BY COUNT(*) DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [(emp_id, count) for emp_id, count in rows]

    # ─────────────── گیمیفیکیشن: XP، سطح و استریک ───────────────

    def award_xp(self, user_id: int, amount: int) -> int:
        """امتیاز تجربه (XP) می‌دهد و XP جدید را برمی‌گرداند."""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO users (user_id, name, joined_at, last_seen) VALUES (?, '', ?, ?)",
                (str(user_id), int(time.time()), int(time.time())),
            )
            self._conn.execute(
                "UPDATE users SET xp = MAX(0, xp + ?) WHERE user_id = ?",
                (amount, str(user_id)),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT xp FROM users WHERE user_id = ?", (str(user_id),)
            ).fetchone()
            return row[0] if row else 0
        except Exception as exc:
            logger.error("خطا در ثبت XP: %s", exc)
            return 0

    def bump_streak(self, user_id: int) -> tuple[int, bool]:
        """استریک روزانه (روزهای پشت‌سرهم فعالیت).
        خروجی: (استریک فعلی، آیا امروز اولین فعالیت بود؟)"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO users (user_id, name, joined_at, last_seen) VALUES (?, '', ?, ?)",
                (str(user_id), int(time.time()), int(time.time())),
            )
            today = time.strftime("%Y-%m-%d")
            yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
            row = self._conn.execute(
                "SELECT last_day, streak FROM users WHERE user_id = ?", (str(user_id),)
            ).fetchone()
            last_day, streak = row[0], row[1] or 0
            if last_day == today:
                return streak, False
            new_streak = streak + 1 if last_day == yesterday else 1
            self._conn.execute(
                "UPDATE users SET last_day = ?, streak = ? WHERE user_id = ?",
                (today, new_streak, str(user_id)),
            )
            self._conn.commit()
            return new_streak, True
        except Exception as exc:
            logger.error("خطا در ثبت استریک: %s", exc)
            return 0, False

    def user_rank(self, user_id: int) -> int | None:
        """رتبه‌ی کاربر در لیدربرد (بر اساس XP)."""
        info = self.user_info(user_id)
        if not info:
            return None
        row = self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE xp > ?", (info["xp"],)
        ).fetchone()
        return row[0] + 1

    def leaderboard(self, n: int = 10) -> list[tuple[str, str | None, int, int]]:
        """برترین کاربران بر اساس XP: (user_id, name, xp, streak)."""
        return [
            (r[0], r[1], r[2], r[3])
            for r in self._conn.execute(
                "SELECT user_id, name, xp, streak FROM users WHERE xp > 0 ORDER BY xp DESC LIMIT ?",
                (n,),
            ).fetchall()
        ]

    def weekly_activity(self) -> list[tuple[str, int]]:
        """تعداد پیام‌های ۷ روز اخیر (به تفکیک روز) — برای نمودار ادمین."""
        week_ago = int(time.time()) - 7 * 86400
        return [
            (r[0], r[1])
            for r in self._conn.execute(
                "SELECT date(ts, 'unixepoch', 'localtime') AS d, COUNT(*) FROM messages"
                " WHERE ts >= ? GROUP BY d ORDER BY d",
                (week_ago,),
            ).fetchall()
        ]

    def delete_last(self, user_id: int, emp_id: str, role: str = "assistant") -> None:
        """حذف آخرین پیامِ یک نقش از نشست فعلی (برای «پاسخ دوباره»)."""
        try:
            self._conn.execute(
                """
                DELETE FROM messages WHERE id = (
                    SELECT id FROM messages
                    WHERE user_id = ? AND emp_id = ? AND role = ? AND session = ?
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (str(user_id), emp_id, role, self._current_session(user_id, emp_id)),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("خطا در حذف آخرین پیام: %s", exc)

    # ─────────────── انتقال داده‌های قدیمی ───────────────

    def migrate_json(self, conversations_path: str | None = None, history_path: str | None = None) -> int:
        """اگر فایل‌های JSON قدیمی (حافظه یا بایگانی) موجود باشند، محتوایشان
        یک‌بار به دیتابیس منتقل و فایل به .bak تغییر نام می‌یابد."""
        moved = 0
        for path in (conversations_path, history_path):
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for user_id, employees in data.items():
                    for emp_id, messages in employees.items():
                        for msg in messages:
                            self.add(user_id, emp_id, msg.get("role", "user"), msg.get("content", ""))
                            moved += 1
                os.replace(path, path + ".bak")
                logger.info("%s پیام از %s به دیتابیس منتقل شد", moved, path)
            except Exception as exc:
                logger.error("خطا در انتقال %s به دیتابیس: %s", path, exc)
        return moved

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass