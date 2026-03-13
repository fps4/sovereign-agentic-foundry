from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
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
        "Hello! I'm your sovereign AI platform assistant.\n\n"
        "Commands:\n"
        "/register — create your account\n"
        "/apps — list your applications\n\n"
        "Once registered, tell me what you'd like to build."
    )


@dp.message(Command("register"))
async def cmd_register(message: Message) -> None:
    username = message.from_user.username or message.from_user.first_name
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/register",
                json={
                    "telegram_id": message.from_user.id,
                    "telegram_username": username,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error("Register request failed: %s", e)
        await message.answer("Could not reach the platform. Please try again.")
        return

    if data["message"] == "already_registered":
        await message.answer("You're already registered and verified.")
        return

    await message.answer(
        f"Your verification code is: *{data['code']}*\n\n"
        "Reply with this code to complete registration.",
        parse_mode="Markdown",
    )


@dp.message(lambda msg: msg.text and re.fullmatch(r"\d{6}", msg.text.strip()))
async def handle_verification_code(message: Message) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/verify",
                json={
                    "telegram_id": message.from_user.id,
                    "code": message.text.strip(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error("Verify request failed: %s", e)
        await message.answer("Could not reach the platform. Please try again.")
        return

    if data["success"]:
        await message.answer(
            "You're verified! Your private workspace has been created in Gitea.\n\n"
            "Tell me what you'd like to build."
        )
    elif data["message"] == "wrong_code":
        await message.answer("That code is incorrect. Send /register to get a new one.")
    elif data["message"] == "not_registered":
        await message.answer("Please send /register first.")
    else:
        await message.answer("Already verified. You're good to go!")


@dp.message(Command("apps"))
async def cmd_apps(message: Message) -> None:
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{ORCHESTRATOR_URL}/apps",
                params={"telegram_id": message.from_user.id},
            )
            if resp.status_code == 403:
                await message.answer(
                    "You need to register first. Send /register to get started."
                )
                return
            resp.raise_for_status()
            apps = resp.json()
    except httpx.HTTPError as e:
        log.error("Failed to fetch apps: %s", e)
        await message.answer("Could not reach the platform. Please try again.")
        return

    if not apps:
        await message.answer("No applications yet. Tell me what you'd like to build!")
        return

    lines = ["*Your Applications*\n"]
    for app in apps:
        lines.append(f"• [{app['name']}]({app['url']}) — {app['description']}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


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
