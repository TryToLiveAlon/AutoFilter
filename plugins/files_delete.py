import re
import logging
from pyrogram import Client, filters
from info import DELETE_CHANNELS
from database.ia_filterdb import Media, Media2, Media3, unpack_new_file_id, MediaModels

logger = logging.getLogger(__name__)

media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(DELETE_CHANNELS) & media_filter)
async def deletemultiplemedia(bot, message):
    """Delete Multiple files from database"""

    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return

    file_id, file_ref = unpack_new_file_id(media.file_id)
    deleted = False
    for model in MediaModels:
        result = await model.collection.delete_one({'_id': file_id})
        if result.deleted_count:
            deleted = True
            break

    if deleted:
        logger.info('File is successfully deleted from database.')
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        for filter_name in [file_name, media.file_name]:
            for model in MediaModels:
                result = await model.collection.delete_many({
                    'file_name': filter_name,
                    'file_size': media.file_size,
                    'mime_type': media.mime_type
                })
                if result.deleted_count:
                    deleted = True
                    break
            if deleted:
                break

        if deleted:
            logger.info('File is successfully deleted from database.')
        else:
            logger.info('File not found in database.')