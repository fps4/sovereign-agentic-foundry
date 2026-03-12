from __future__ import annotations

import asyncio
import logging
import os

import httpx
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Hello! I'm your sovereign AI platform assistant.\n"
        "Tell me what you'd like to build."
    )


@dp.message()
async def handle_message(message: Message) -> None:
    if not message.text:
        return

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"user_id": str(message.from_user.id), "message": message.text},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error("Orchestrator request failed: %s", e)
        await message.answer(
            "Sorry, I'm having trouble connecting. Please try again."
        )
        return

    await message.answer(data["reply"])


async def main() -> None:
    log.info("Starting Telegram bot (polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
