# -*- coding: utf-8 -*-
"""لیست مدل‌های موجود Groq با کلید کاربر."""
import asyncio
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

from groq import AsyncGroq

src = open("bot.py", encoding="utf-8").read()
key = re.search(r'GROQ_API_KEY\s*=\s*"([^"]*)"', src).group(1)

out = open("models_list.txt", "w", encoding="utf-8")


async def main():
    try:
        client = AsyncGroq(api_key=key, timeout=30)
        models = await client.models.list()
        out.write("مدل‌های در دسترس:\n")
        for m in sorted(models.data, key=lambda x: x.id):
            out.write(f"  - {m.id}\n")
    except Exception as e:
        out.write(f"FAILED: {type(e).__name__}: {e}\n")
    finally:
        out.close()
        print("done")


asyncio.run(main())
