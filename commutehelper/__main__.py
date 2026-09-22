"""Entry point: python -m commutehelper"""
from __future__ import annotations

import logging

import httpx
from telegram import Update
from telegram.ext import Application

from . import config
from .bart import Bart
from .bot import COMMANDS, CommuteBot
from .maps import FixedDrive
from .planner import Planner
from .state import Store


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    # httpx logs full request URLs at INFO, which include the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cfg = config.load()
    http = httpx.AsyncClient(timeout=20)
    planner = Planner(cfg, Bart(cfg.bart_key, cfg.tz, http), FixedDrive(cfg.drive))
    bot = CommuteBot(cfg, planner, Store(cfg.state_file))

    async def post_init(app: Application) -> None:
        await app.bot.set_my_commands(COMMANDS)

    async def post_shutdown(app: Application) -> None:
        await http.aclose()

    app = (Application.builder().token(cfg.telegram_token).concurrent_updates(True)
           .post_init(post_init).post_shutdown(post_shutdown).build())
    bot.register(app)
    logging.info("commutehelper running; stations=%s office=%s", cfg.home_stations, cfg.office_station)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
