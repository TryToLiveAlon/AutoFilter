import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import CAPTION_LANGUAGES, DATABASE_URI, DATABASE_URI2, DATABASE_URI3, DATABASE_NAME, COLLECTION_NAME, USE_CAPTION_FILTER, MAX_B_TN, MOVIE_UPDATE_CHANNEL, OWNERID
from utils import get_settings, save_group_settings, temp, get_status
from database.users_chats_db import add_name
from .Imdbposter import get_movie_details, fetch_image
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
#---------------------------------------------------------
# Some basic variables needed
tempDict = {'indexDB': DATABASE_URI}

# Primary DB
client = db = instance = Media = None
if DATABASE_URI and DATABASE_URI.startswith('mongodb'):
    try:
        client = AsyncIOMotorClient(DATABASE_URI)
        db = client[DATABASE_NAME]
        instance = Instance.from_db(db)
    except Exception as e:
        logger.error(f"Error initializing Primary DB client: {e}")

# Primary DB Model
def register_primary(cls):
    if instance:
        return instance.register(cls)
    return cls

@register_primary
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

MediaModels = []
if instance:
    MediaModels.append(Media)

#secondary db
client2 = db2 = instance2 = Media2 = None
if DATABASE_URI2 and DATABASE_URI2.startswith('mongodb'):
    try:
        client2 = AsyncIOMotorClient(DATABASE_URI2)
        db2 = client2[DATABASE_NAME]
        instance2 = Instance.from_db(db2)

        @instance2.register
        class Media2(Document):
            file_id = fields.StrField(attribute='_id')
            file_ref = fields.StrField(allow_none=True)
            file_name = fields.StrField(required=True)
            file_size = fields.IntField(required=True)
            file_type = fields.StrField(allow_none=True)
            mime_type = fields.StrField(allow_none=True)
            caption = fields.StrField(allow_none=True)

            class Meta:
                indexes = ('$file_name', )
                collection_name = COLLECTION_NAME
        MediaModels.insert(0, Media2)
    except Exception as e:
        logger.error(f"Error initializing DATABASE_URI2: {e}")

#third db
client3 = db3 = instance3 = Media3 = None
if DATABASE_URI3 and DATABASE_URI3.startswith('mongodb'):
    try:
        client3 = AsyncIOMotorClient(DATABASE_URI3)
        db3 = client3[DATABASE_NAME]
        instance3 = Instance.from_db(db3)

        @instance3.register
        class Media3(Document):
            file_id = fields.StrField(attribute='_id')
            file_ref = fields.StrField(allow_none=True)
            file_name = fields.StrField(required=True)
            file_size = fields.IntField(required=True)
            file_type = fields.StrField(allow_none=True)
            mime_type = fields.StrField(allow_none=True)
            caption = fields.StrField(allow_none=True)

            class Meta:
                indexes = ('$file_name', )
                collection_name = COLLECTION_NAME
        MediaModels.insert(0, Media3)
    except Exception as e:
        logger.error(f"Error initializing DATABASE_URI3: {e}")

async def choose_mediaDB():
    """This Function chooses which database to use based on the value of indexDB key in the dict tempDict."""
    global saveMedia
    if tempDict['indexDB'] == DATABASE_URI:
        logger.info("Using first db (Media)")
        saveMedia = Media
    elif DATABASE_URI2 and tempDict['indexDB'] == DATABASE_URI2 and Media2:
        logger.info("Using second db (Media2)")
        saveMedia = Media2
    elif DATABASE_URI3 and tempDict['indexDB'] == DATABASE_URI3 and Media3:
        logger.info("Using third db (Media3)")
        saveMedia = Media3
    else:
        logger.info("Using fallback first db (Media)")
        saveMedia = Media

async def save_file(bot, media):
  """Save file in database"""
  global saveMedia
  file_id, file_ref = unpack_new_file_id(media.file_id)
  file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
  try:
    for model in MediaModels:
        if model == saveMedia:
            continue
        if await model.count_documents({'file_id': file_id}, limit=1):
            logger.warning(f'{file_name} is already saved in another database!')
            return False, 0

    file = saveMedia(
        file_id=file_id,
        file_ref=file_ref,
        file_name=file_name,
        file_size=media.file_size,
        file_type=media.file_type,
        mime_type=media.mime_type,
        caption=media.caption.html if media.caption else None,
    )
  except ValidationError:
    logger.exception('Error occurred while saving file in database')
    return False, 2
  else:
    try:
      await file.commit()
    except DuplicateKeyError:
      logger.warning(f'{getattr(media, "file_name", "NO_FILE")} is already saved in database')   
      return False, 0
    else:
        logger.info(f'{getattr(media, "file_name", "NO_FILE")} is saved to database')
        if await get_status(bot.me.id):
            await send_msg(bot, file.file_name, file.caption)
        return True, 1

async def get_search_results(chat_id, query, file_type=None, max_results=10, offset=0, filter=False):
    """For given query return (results, next_offset)"""
    if chat_id is not None:
        settings = await get_settings(int(chat_id))
        try:
            if settings['max_btn']:
                max_results = 10
            else:
                max_results = int(MAX_B_TN)
        except KeyError:
            await save_group_settings(int(chat_id), 'max_btn', False)
            settings = await get_settings(int(chat_id))
            if settings['max_btn']:
                max_results = 10
            else:
                max_results = int(MAX_B_TN)
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_()]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []

    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}

    if file_type:
        filter['file_type'] = file_type

    total_results = 0
    for model in MediaModels:
        total_results += await model.count_documents(filter)

    #verifies max_results is an even number or not
    if max_results%2 != 0: 
        logger.info(f"Since max_results is an odd number ({max_results}), bot will use {max_results+1} as max_results to make it even.")
        max_results += 1

    files = []
    accumulated_count = 0
    for model in MediaModels:
        if len(files) >= max_results:
            break

        count = await model.count_documents(filter)
        if offset >= accumulated_count + count:
            accumulated_count += count
            continue

        local_offset = max(0, offset - accumulated_count)
        needed = max_results - len(files)

        cursor = model.find(filter)
        cursor.sort('$natural', -1)
        cursor.skip(local_offset).limit(needed)

        batch = await cursor.to_list(length=needed)
        files.extend(batch)
        accumulated_count += count

    next_offset = offset + len(files)
    if next_offset >= total_results:
        next_offset = ''
    return files, next_offset, total_results


async def get_bad_files(query, file_type=None, filter=False):
    """For given query return (results, next_offset)"""
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_()]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []

    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}

    if file_type:
        filter['file_type'] = file_type

    files = []
    for model in MediaModels:
        cursor = model.find(filter)
        cursor.sort('$natural', -1)
        files.extend(await cursor.to_list(length=await model.count_documents(filter)))

    total_results = len(files)

    return files, total_results

async def get_file_details(query):
    filter = {'file_id': query}
    for model in MediaModels:
        cursor = model.find(filter)
        filedetails = await cursor.to_list(length=1)
        if filedetails:
            return filedetails
    return []


def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0

    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0

            r += bytes([i])

    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    """Return file_id, file_ref"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref


async def send_msg(bot, filename, caption): 
    try:
        filename = re.sub(r'\(\@\S+\)|\[\@\S+\]|\b@\S+|\bwww\.\S+', '', filename).strip()
        caption = re.sub(r'\(\@\S+\)|\[\@\S+\]|\b@\S+|\bwww\.\S+', '', caption).strip()
        
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None

        pattern = r"(?i)(?:s|season)0*(\d{1,2})"
        season = re.search(pattern, caption) or re.search(pattern, filename)
        season = season.group(1) if season else None 

        if year:
            filename = filename[: filename.find(year) + 4]  
        elif season and season in filename:
            filename = filename[: filename.find(season) + 1]

        qualities = ["ORG", "org", "hdcam", "HDCAM", "HQ", "hq", "HDRip", "hdrip", "camrip", "CAMRip", "hdtc", "predvd", "DVDscr", "dvdscr", "dvdrip", "dvdscr", "HDTC", "dvdscreen", "HDTS", "hdts"]
        quality = await get_qualities(caption.lower(), qualities) or "HDRip"

        language = ""
        possible_languages = CAPTION_LANGUAGES
        for lang in possible_languages:
            if lang.lower() in caption.lower():
                language += f"{lang}, "
        language = language[:-2] if language else "Not idea 😄"

        filename = re.sub(r"[\(\)\[\]\{\}:;'\-!]", "", filename)

        text = "#𝑵𝒆𝒘_𝑭𝒊𝒍𝒆_𝑨𝒅𝒅𝒆𝒅 ✅\n\n👷𝑵𝒂𝒎𝒆: `{}`\n\n🌳𝑸𝒖𝒂𝒍𝒊𝒕𝒚: {}\n\n🍁𝑨𝒖𝒅𝒊𝒐: {}"
        text = text.format(filename, quality, language)

        if await add_name(OWNERID, filename):
            imdb = await get_movie_details(filename)  
            resized_poster = None

            if imdb:
                poster_url = imdb.get('poster_url')
                if poster_url:
                    resized_poster = await fetch_image(poster_url)  

            filenames = filename.replace(" ", '-')
            btn = [[InlineKeyboardButton('🌲 Get Files 🌲', url=f"https://telegram.me/{temp.U_NAME}?start=getfile-{filenames}")]]
            
            if resized_poster:
                await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=resized_poster, caption=text, reply_markup=InlineKeyboardMarkup(btn))
            else:              
                await bot.send_message(chat_id=MOVIE_UPDATE_CHANNEL, text=text, reply_markup=InlineKeyboardMarkup(btn))

    except:
        pass

async def get_qualities(text, qualities: list):
    """Get all Quality from text"""
    quality = []
    for q in qualities:
        if q in text:
            quality.append(q)
    quality = ", ".join(quality)
    return quality[:-2] if quality.endswith(", ") else quality






