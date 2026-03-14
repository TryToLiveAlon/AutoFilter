import os
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command(["img", "tgm", "telegraph"], prefixes="/") & filters.reply)
async def c_upload(client, message: Message):
    reply = message.reply_to_message
    if not reply.media:
        return await message.reply_text("Reply to a media to upload it to Cloud.")
    if reply.document and reply.document.file_size > 5 * 1024 * 1024:  # 5 MB
        return await message.reply_text("File size limit is 5 MB.")
    msg = await message.reply_text("Processing...")
    try:
        downloaded_media = await reply.download()
        if not downloaded_media:
            return await msg.edit_text("Something went wrong during download.")
        async with aiohttp.ClientSession() as session:
            with open(downloaded_media, "rb") as f:
                form_data = aiohttp.FormData()
                form_data.add_field('file', f)
                async with session.post("https://envs.sh", data=form_data) as resp:
                    if resp.status == 200:
                        res_text = await resp.text()
                        await msg.edit_text(f"{res_text}")
                    else:
                        await msg.edit_text("Something went wrong. Please try again later.")
        os.remove(downloaded_media)
    except Exception as e:
        await msg.edit_text(f"Error: {str(e)}")


