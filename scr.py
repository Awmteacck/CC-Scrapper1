import re
import os
import asyncio
import logging
import aiofiles
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client, filters
from pyrogram.errors import (
    UserAlreadyParticipant,
    InviteHashExpired,
    InviteHashInvalid,
    PeerIdInvalid,
    InviteRequestSent
)
from urllib.parse import urlparse
from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    ADMIN_LIMIT,
    ADMIN_IDS,
    DEFAULT_LIMIT
)

# Setup logging For Capturing Errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Bot Client With Workers
app = Client(
    "app_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=10000
)

# Initialize User Client With Workers
user = Client(
    "user_session",
    session_string=SESSION_STRING,
    workers=10000
)


START_MESSAGE = """
<b>Welcome to the Credit Card Scraper Bot 🕵️‍♂️💳</b>

I'm here to help you scrape credit card information from Telegram channels.
Use the commands below to get started:

/scr [channel_username] [limit] - Scrape from a single channel. 📺
/mc [channel_username1] [channel_username2] ... [limit] - Scrape from multiple channels. 📡

<strong>Examples:</strong>
/scr @username 100 515462
/scr @username 100 BankName
/scr username 100 
/scr username 100 515462
/scr username 100 BankName
/scr t.me/username 100
/scr t.me/username 100 515462
/scr t.me/username 100 Bank Name
/scr https://t.me/username 100 
/scr https://t.me/username 100 515462
/scr https://t.me/username Bank Name
/scr https://t.me/+ZBqGFP5evRpmY2Y1 100
/scr https://t.me/+ZBqGFP5evRpmY2Y1 100 515462
/scr https://t.me/+ZBqGFP5evRpmY2Y1 100 BankName

Happy scraping! 🚀
"""


async def scrape_messages(client, channel_username, limit, start_number=None, bank_name=None):
    messages = []
    count = 0
    pattern = r'\d{16}\D*\d{2}\D*\d{2,4}\D*\d{3,4}'
    bin_pattern = re.compile(r'^\d{6}') if start_number else None

    logger.info(f"Starting to scrape messages from {channel_username} with limit {limit}")

    # Fetch messages in batches
    async for message in user.search_messages(channel_username):
        if count >= limit:
            break
        text = message.text or message.caption
        if text:
            # Check if the bank name is mentioned in the message (case-insensitive)
            if bank_name and bank_name.lower() not in text.lower():
                continue
            matched_messages = re.findall(pattern, text)
            if matched_messages:
                formatted_messages = []
                for matched_message in matched_messages:
                    extracted_values = re.findall(r'\d+', matched_message)
                    if len(extracted_values) == 4:
                        card_number, mo, year, cvv = extracted_values
                        year = year[-2:]
                        # Apply BIN filter if start_number is provided
                        if start_number:
                            if card_number.startswith(start_number[:6]):
                                formatted_messages.append(f"{card_number}|{mo}|{year}|{cvv}")
                        else:
                            formatted_messages.append(f"{card_number}|{mo}|{year}|{cvv}")
                messages.extend(formatted_messages)
                count += len(formatted_messages)
    logger.info(f"Scraped {len(messages)} messages from {channel_username}")
    return messages[:limit]

def remove_duplicates(messages):
    unique_messages = list(set(messages))
    duplicates_removed = len(messages) - len(unique_messages)
    logger.info(f"Removed {duplicates_removed} duplicates")
    return unique_messages, duplicates_removed

async def send_results(client, message, unique_messages, duplicates_removed, source_name, bin_filter=None, bank_filter=None):
    if unique_messages:
        file_name = f"x{len(unique_messages)}_{source_name.replace(' ', '_')}.txt"
        # Use aiofiles for asynchronous file writing
        async with aiofiles.open(file_name, mode='w') as f:
            await f.write("\n".join(unique_messages))
        
        # Use aiofiles for asynchronous file reading
        async with aiofiles.open(file_name, mode='rb') as f:
            user_link = await get_user_link(message)
            caption = (
                f"<b>CC Scrapped Successful ✅</b>\n"
                f"<b>━━━━━━━━━━━━━━━━</b>\n"
                f"<b>Source:</b> <code>{source_name} 🌐</code>\n"
                f"<b>Amount:</b> <code>{len(unique_messages)} 📝</code>\n"
                f"<b>Duplicates Removed:</b> <code>{duplicates_removed} 🗑️</code>\n"
            )
            # Add BIN filter to caption if provided
            if bin_filter:
                caption += f"<b>📝 BIN Filter:</b> <code>{bin_filter}</code>\n"
            # Add Bank filter to caption if provided
            if bank_filter:
                caption += f"<b>📝 Bank Filter:</b> <code>{bank_filter}</code>\n"
            caption += (
                f"<b>━━━━━━━━━━━━━━━━</b>\n"
                f"<b>✅ Card-Scrapped By: {user_link}</b>\n"
            )
            await message.delete()
            await client.send_document(message.chat.id, file_name, caption=caption)
        os.remove(file_name)
        logger.info(f"Results sent successfully for {source_name}")
    else:
        await message.edit_text("<b>Sorry Bro ❌ No Credit Card Found</b>")
        logger.info("No credit cards found")

async def get_user_link(message):
    if message.from_user is None:
        return '<a href="https://t.me/Awmtee">Awmtea Polythene</a>'
    else:
        user_first_name = message.from_user.first_name
        user_last_name = message.from_user.last_name or ""
        user_full_name = f"{user_first_name} {user_last_name}".strip()
        return f'<a href="tg://user?id={message.from_user.id}">{user_full_name}</a>'

async def join_private_chat(client, invite_link):
    try:
        await client.join_chat(invite_link)
        logger.info(f"Joined chat via invite link: {invite_link}")
        return True
    except UserAlreadyParticipant:
        logger.info(f"Already a participant in the chat: {invite_link}")
        return True
    except InviteRequestSent:
        logger.info(f"Join request sent to the chat: {invite_link}")
        return False
    except (InviteHashExpired, InviteHashInvalid) as e:
        logger.error(f"Failed to join chat {invite_link}: {e}")
        return False

async def send_join_request(client, invite_link, message):
    try:
        await client.join_chat(invite_link)
        logger.info(f"Sent join request to chat: {invite_link}")
        return True
    except PeerIdInvalid as e:
        logger.error(f"Failed to send join request to chat {invite_link}: {e}")
        return False
    except InviteRequestSent:
        logger.info(f"Join request sent to the chat: {invite_link}")
        await message.edit_text("<b>Hey Bro I Have Sent Join Request✅</b>")
        return False

def setup_scr_handler(app):
    @app.on_message(filters.command(["scr", "ccscr", "scrcc"], prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
    async def scr_cmd(client, message):
        args = message.text.split()[1:]
        user_id = message.from_user.id if message.from_user else None

        if len(args) < 2:
            await client.send_message(message.chat.id, "<b>⚠️ Provide channel username and amount to scrape ❌</b>")
            logger.warning("Invalid command: Missing arguments")
            return

        # Extract channel identifier (username, invite link, or chat ID)
        channel_identifier = args[0]
        chat = None
        channel_name = ""
        channel_username = ""

        # Handle private channel chat ID (numeric)
        if channel_identifier.lstrip("-").isdigit():
            # Treat it as a chat ID
            chat_id = int(channel_identifier)
            try:
                # Fetch the chat details
                chat = await user.get_chat(chat_id)
                channel_name = chat.title
                logger.info(f"Scraping from private channel: {channel_name} (ID: {chat_id})")
            except Exception as e:
                await client.send_message(message.chat.id, "<b>Hey Bro! 🥲 Invalid chat ID ❌</b>")
                logger.error(f"Failed to fetch private channel: {e}")
                return
        else:
            # Handle public channels or private invite links
            if channel_identifier.startswith("https://t.me/+"):
                # Private invite link
                invite_link = channel_identifier
                temporary_msg = await client.send_message(message.chat.id, "<b>Checking Username...</b>")
                joined = await join_private_chat(user, invite_link)
                if not joined:
                    request_sent = await send_join_request(user, invite_link, temporary_msg)
                    if not request_sent:
                        return
                else:
                    await temporary_msg.delete()
                    chat = await user.get_chat(invite_link)
                    channel_name = chat.title
                    logger.info(f"Joined private channel via link: {channel_name}")
            elif channel_identifier.startswith("https://t.me/"):
                # Remove "https://t.me/" for regular links
                channel_username = channel_identifier[13:]
            elif channel_identifier.startswith("t.me/"):
                # Remove "t.me/" for short links
                channel_username = channel_identifier[5:]
            else:
                # Assume it's already a username
                channel_username = channel_identifier

            if not chat:
                try:
                    # Fetch the chat details
                    chat = await user.get_chat(channel_username)
                    channel_name = chat.title
                    logger.info(f"Scraping from public channel: {channel_name} (Username: {channel_username})")
                except Exception as e:
                    await client.send_message(message.chat.id, "<b>Hey Bro! 🥲 Incorrect username or chat ID ❌</b>")
                    logger.error(f"Failed to fetch public channel: {e}")
                    return

        # Extract limit (second argument)
        try:
            limit = int(args[1])
            logger.info(f"Scraping limit set to: {limit}")
        except ValueError:
            await client.send_message(message.chat.id, "<b>⚠️ Invalid limit value. Please provide a valid number ❌</b>")
            logger.warning("Invalid limit value provided")
            return

        # Extract optional arguments (starting number or bank name)
        start_number = None
        bank_name = None
        bin_filter = None
        if len(args) > 2:
            # Check if the third argument is a starting number (digits only)
            if args[2].isdigit():
                start_number = args[2]
                bin_filter = args[2][:6]  # Extract first 6 digits as BIN filter
                logger.info(f"BIN filter applied: {bin_filter}")
            else:
                # Otherwise, treat it as a bank name
                bank_name = " ".join(args[2:])
                logger.info(f"Bank filter applied: {bank_name}")

        # Enforce maximum limit based on user role
        max_lim = ADMIN_LIMIT if user_id in ADMIN_IDS else DEFAULT_LIMIT
        if limit > max_lim:
            await client.send_message(message.chat.id, f"<b>Sorry Bro! Amount over Max limit is {max_lim} ❌</b>")
            logger.warning(f"Limit exceeded: {limit} > {max_lim}")
            return

        # Send a temporary message to check the username
        temporary_msg = await client.send_message(message.chat.id, "<b>Checking The Username...</b>")
        await asyncio.sleep(1.5)

        # Start scraping
        await temporary_msg.edit_text("<b>Scraping In Progress</b>")
        scrapped_results = await scrape_messages(user, chat.id, limit, start_number=start_number, bank_name=bank_name)
        unique_messages, duplicates_removed = remove_duplicates(scrapped_results)

        if not unique_messages:
            await temporary_msg.edit_text("<b>Sorry Bro ❌ No Credit Card Found</b>")
        else:
            await send_results(client, temporary_msg, unique_messages, duplicates_removed, channel_name, bin_filter=bin_filter, bank_filter=bank_name)

    @app.on_message(filters.command(["mc", "multiscr", "mscr"], prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
    async def mc_cmd(client, message):
        args = message.text.split()[1:]
        if len(args) < 2:
            await client.send_message(message.chat.id, "<b>⚠️ Provide at least one channel username</b>")
            logger.warning("Invalid command: Missing arguments")
            return

        channel_identifiers = args[:-1]
        limit = int(args[-1])
        user_id = message.from_user.id if message.from_user else None

        max_lim = ADMIN_LIMIT if user_id in ADMIN_IDS else DEFAULT_LIMIT
        if limit > max_lim:
            await client.send_message(message.chat.id, f"<b>Sorry Bro! Amount over Max limit is {max_lim} ❌</b>")
            logger.warning(f"Limit exceeded: {limit} > {max_lim}")
            return

        temporary_msg = await client.send_message(message.chat.id, "<b>Scraping In Progress</b>")
        all_messages = []
        tasks = []

        for channel_identifier in channel_identifiers:
            parsed_url = urlparse(channel_identifier)
            channel_username = parsed_url.path.lstrip('/') if not parsed_url.scheme else channel_identifier

            tasks.append(scrape_messages_task(user, channel_username, limit, client, message))

        results = await asyncio.gather(*tasks)
        for result in results:
            all_messages.extend(result)

        unique_messages, duplicates_removed = remove_duplicates(all_messages)
        unique_messages = unique_messages[:limit]

        if not unique_messages:
            await temporary_msg.edit_text("<b>Sorry Bro ❌ No Credit Card Found</b>")
        else:
            await send_results(client, temporary_msg, unique_messages, duplicates_removed, "Multiple Chats")

async def scrape_messages_task(client, channel_username, limit, bot_client, message):
    try:
        chat = None
        if channel_username.startswith("https://t.me/+"):
            invite_link = channel_username
            temporary_msg = await bot_client.send_message(message.chat.id, "<b>Checking Username...</b>")
            joined = await join_private_chat(client, invite_link)
            if not joined:
                request_sent = await send_join_request(client, invite_link, temporary_msg)
                if not request_sent:
                    return []
            else:
                await temporary_msg.delete()
                chat = await client.get_chat(invite_link)
        else:
            chat = await client.get_chat(channel_username)

        return await scrape_messages(client, chat.id, limit)
    except Exception as e:
        await bot_client.send_message(message.chat.id, f"<b>Hey Bro! 🥲 Incorrect username for {channel_username} ❌</b>")
        logger.error(f"Failed to scrape from {channel_username}: {e}")
        return []

@app.on_message(filters.command("start", prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
async def start(client, message):
    buttons = [
        [InlineKeyboardButton("Update Channel", url="https://t.me/awmteee"), InlineKeyboardButton("Awmtea Polythene", user_id=7237320756)]
    ]
    await client.send_message(message.chat.id, START_MESSAGE, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(buttons))

if __name__ == "__main__":
    setup_scr_handler(app)
    user.start()
    app.run()
