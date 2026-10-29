"""Text-message dispatcher.

Single entry point for any non-command text message. The dispatch order is
explicit — read it top-to-bottom. Each step has a clear postcondition.

  Step 1. Inline-result tap (`via_bot` set)
            → reset all conversation state. The user just navigated; their
              previous "What's the idea?" prompt is no longer the right home
              for this message.

  Step 2. Strict regex parse (`gift for X - Y`, `add gift for X - Y`, `X: Y`)
            → if the parsed name matches one or more people in the DB, treat
              the message as a fresh complete-capture sentence. Always wins
              over any in-flight state — typing a complete sentence is an
              unambiguous "do this" intent.
            → if parser matched but the name doesn't exist as a person, fall
              through to step 3; the message might be a reply to an in-flight
              prompt OR genuinely about a missing person (handled in step 5).

  Step 3. In-flight conversation state
            → `awaiting_idea_for` consumes the message as a gift idea.
            → `awaiting_name_search` consumes it as a name search.

  Step 4. Strict-parser matched but no person — surface that now (after
            state has had its chance).

  Step 5. Smart parse (`Gift for Mike cutting board` — no separator, requires
            DB lookup to know where the name ends).

  Step 6. Bare-name search (any 1-60 char string that substring-matches an
            existing person).

  Step 7. Fallback help — show the supported patterns.

Each step that succeeds returns immediately, so later steps see only messages
that earlier ones couldn't handle.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

import state
from config import WEB_APP_URL
from api_client import APIClient
from parser import parse


async def on_text_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    text = (msg.text or "") if msg else ""
    api: APIClient = ctx.bot_data["api"]
    send = msg.reply_text if msg else None

    # Step 1 — inline-result tap is navigation; reset state
    if msg and msg.via_bot is not None:
        state.clear(ctx.user_data)

    # Step 2 — strict parse, treat as fresh capture if person exists
    parsed = parse(text)
    if parsed:
        matches = await api.find_person_by_name(parsed.name)
        if matches:
            state.clear(ctx.user_data)
            from handlers.gift import handle_capture
            await handle_capture(send, api, matches, parsed.idea, parsed.name,
                                 purchased=parsed.purchased)
            return

    # Step 3 — in-flight conversation state
    if state.is_awaiting_idea_for(ctx.user_data):
        from handlers.gift import handle_idea_text
        await handle_idea_text(send, api, ctx.user_data, text)
        return
    if state.is_awaiting_name_search(ctx.user_data):
        from handlers.gift import handle_name_search
        await handle_name_search(send, api, ctx.user_data, text)
        return

    # Step 4 — parser matched but person didn't exist
    if parsed:
        await send(
            f"I don't have a *{parsed.name}* yet. Add them in the web app:\n"
            f"{WEB_APP_URL}",
            parse_mode="Markdown",
        )
        return

    # Step 5 — smart parse with DB lookup ("Gift for Mike cutting board",
    #          "bought ada a cutting board")
    from handlers.gift import smart_parse_capture
    smart = await smart_parse_capture(text, api)
    if smart:
        person, idea, purchased = smart
        from handlers.gift import handle_capture
        await handle_capture(send, api, [person], idea, person.name, purchased=purchased)
        return

    # Step 6 — bare-name search
    bare = text.strip()
    if 1 <= len(bare) <= 60:
        matches = await api.find_person_by_name(bare)
        if matches:
            from handlers.gift import handle_bare_name_match
            await handle_bare_name_match(send, api, matches, bare)
            return

    # Step 7 — fallback help
    await send(
        "I didn't catch that. Examples that work:\n"
        "  • `mike` — search for that person\n"
        "  • `gift for mike - cutting board`\n"
        "  • `add gift for mike - cutting board`\n"
        "  • `gift for mike cutting board` (no dash)\n"
        "  • `mom: vase`\n\n"
        "Or tap /menu for buttons.",
        parse_mode="Markdown",
    )
