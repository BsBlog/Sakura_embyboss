import asyncio
import json
import base64
import os
from datetime import datetime, timedelta
from pyrogram import filters
from bot.func_helper.utils import pwd_create, judge_admins
from bot.func_helper.filters import user_in_group_on_filter
from bot.func_helper.msg_utils import deleteMessage, sendMessage
from bot.sql_helper.sql_emby import Emby
from bot.sql_helper import Session
from bot import bot, prefixes, group, config, url_scheme_secret_key, LOGGER

token_timestamps = {}

async def cleanup_expired_tokens():
    while True:
        try:
            current_time = datetime.now()
            expired_tokens = []
            
            for tg_id, timestamp in token_timestamps.items():
                if current_time - timestamp > timedelta(minutes=10):
                    expired_tokens.append(tg_id)
            
            for tg_id in expired_tokens:
                with Session() as session:
                    try:
                        emby = session.query(Emby).filter(Emby.tg == tg_id).first()
                        if emby:
                            emby.url_scheme_token = None
                            session.commit()
                        del token_timestamps[tg_id]
                    except Exception as e:
                        session.rollback()
                        print(f"清理token {tg_id} 时发生错误: {e}")
            
            await asyncio.sleep(30)
        except Exception as e:
            print(f"清理过期token时发生错误: {e}")
            await asyncio.sleep(30)

_cleanup_task = None

def start_cleanup_task():
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        try:
            loop = asyncio.get_running_loop()
            _cleanup_task = loop.create_task(cleanup_expired_tokens())
        except RuntimeError:
            pass


@bot.on_message(filters.command('url_scheme', prefixes) & user_in_group_on_filter & filters.private)
async def url_scheme_command(_, msg):
    await deleteMessage(msg)
    
    start_cleanup_task()
    
    tg_id = msg.from_user.id
    
    with Session() as session:
        try:
            emby = session.query(Emby).filter(Emby.tg == tg_id).first()
            
            if not emby:
                await sendMessage(msg, "❌ **错误：** 您还没有注册，请先使用 `/start` 进行注册。", timer=60)
                return
            
            token = await pwd_create(32)
            url_scheme_url = config.url_scheme_url
            
            emby.url_scheme_token = token
            session.commit()
            
            token_timestamps[tg_id] = datetime.now()
            
            url_scheme_text = (
                f"✅ **URL Scheme 生成成功！**\n\n"
                f"**您的链接：** `https://{url_scheme_url}?token={token}`\n\n"
                f"**注意：**请不要在公开场合分享此链接。链接将于10分钟后失效\n"
                f"打开链接后，单击按钮即可导入至对应的播放器"
            )

            await sendMessage(msg, url_scheme_text, timer=600)
        except Exception as e:
            session.rollback()
            await sendMessage(msg, "❌ **错误：** 数据库更新失败，请稍后重试或联系管理员。", timer=60)


@bot.on_message(filters.command('url_scheme', prefixes) & filters.chat(group))
async def url_scheme_group_command(_, msg):
    await asyncio.gather(deleteMessage(msg),
                         sendMessage(msg,
                                     f"🤖 亲爱的 [{msg.from_user.first_name}](tg://user?id={msg.from_user.id}) 这是一条私聊命令",
                                     timer=60))
