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

_HELP_REGISTERED = (
    "Here's what I can do for you:\n\n"
    "*Build an app*\n"
    "Just tell me what you need in plain language, for example:\n"
    "_I need a form to collect patient intake information_\n"
    "_Build me a sales overview screen_\n\n"
    "I can build:\n"
    "• *Forms* — capture and manage information\n"
    "• *Dashboards* — display data at a glance\n"
    "• *Workflows* — guide tasks through steps or approvals\n"
    "• *Integrations* — connect two services behind the scenes\n"
    "• *Assistants* — answer questions from your documents\n\n"
    "*Commands*\n"
    "/apps — see your apps\n"
    "/help — show this message"
)

_HELP_UNREGISTERED = (
    "Hi! I turn your ideas into working apps — no coding needed.\n\n"
    "Just describe what you want and I'll take care of the rest: "
    "your app will be ready and running in minutes.\n\n"
    "*To get started:*\n"
    "1. Send /register to create your account\n"
    "2. Enter the 6-digit code you'll receive here\n"
    "3. Describe the app you have in mind\n\n"
    "/register — create your account\n"
    "/help — show this message"
)


async def _is_registered(telegram_id: int) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{ORCHESTRATOR_URL}/me", params={"telegram_id": telegram_id}
            )
            resp.raise_for_status()
            return resp.json().get("registered", False)
    except httpx.HTTPError:
        return False


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    registered = await _is_registered(message.from_user.id)
    if registered:
        await message.answer(
            f"Welcome back, {message.from_user.first_name}!\n\n{_HELP_REGISTERED}",
            parse_mode="Markdown",
        )
    else:
        await message.answer(_HELP_UNREGISTERED, parse_mode="Markdown")


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    registered = await _is_registered(message.from_user.id)
    text = _HELP_REGISTERED if registered else _HELP_UNREGISTERED
    await message.answer(text, parse_mode="Markdown")


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
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return

    if data["message"] == "already_registered":
        await message.answer(
            "You're already set up! Send /help to see what I can build for you."
        )
        return

    await message.answer(
        f"Your confirmation code is: *{data['code']}*\n\n"
        "Reply with this code to finish setting up your account.",
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
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return

    if data["success"]:
        await message.answer(
            f"You're all set, {message.from_user.first_name}! Your personal space is ready.\n\n"
            + _HELP_REGISTERED,
            parse_mode="Markdown",
        )
    elif data["message"] == "wrong_code":
        await message.answer(
            "That code doesn't match. Send /register to receive a new one."
        )
    elif data["message"] == "not_registered":
        await message.answer("Please send /register first to create your account.")
    else:
        await message.answer(
            "You're already set up! Send /help to see what I can build for you."
        )


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
                    "You'll need an account first. Send /register to get started."
                )
                return
            resp.raise_for_status()
            apps = resp.json()
    except httpx.HTTPError as e:
        log.error("Failed to fetch apps: %s", e)
        await message.answer("Something went wrong on our end. Please try again in a moment.")
        return

    if not apps:
        await message.answer(
            "You haven't built anything yet. Tell me what you'd like to create!"
        )
        return

    lines = ["*Your Apps*\n"]
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
            "Something went wrong on our end. Please try again in a moment."
        )
        return

    await message.answer(data["reply"])


async def main() -> None:
    log.info("Starting Telegram bot (polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
