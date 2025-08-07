import asyncio
import json
import base64
import os
from datetime import datetime, timedelta
from pyrogram import filters
from aiohttp import web
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad

from bot.func_helper.utils import pwd_create, judge_admins
from bot.func_helper.filters import user_in_group_on_filter
from bot.func_helper.msg_utils import deleteMessage, sendMessage
from bot.sql_helper.sql_emby import Emby
from bot.sql_helper import Session
from bot import bot, prefixes, group, config, url_scheme_secret_key, LOGGER

token_timestamps = {}

def decrypt_data(encrypted_str):
    """
    解密数据
    :param encrypted_str: 加密的字符串
    :return: 解密后的JSON对象
    """
    try:
        iv_str, ciphertext_b64 = encrypted_str.split('::', 1)
        iv = iv_str.encode('utf-8')
        ciphertext = base64.b64decode(ciphertext_b64)
        
        cipher = AES.new(url_scheme_secret_key, AES.MODE_CBC, iv=iv)
        
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")

def encrypt_data(data):
    """
    加密数据
    :param data: 要加密的数据（字典）
    :return: 加密后的字符串
    """
    try:
        iv = os.urandom(16)
        
        json_data = json.dumps(data, ensure_ascii=False)
        
        cipher = AES.new(url_scheme_secret_key, AES.MODE_CBC, iv=iv)
        
        padded_data = pad(json_data.encode('utf-8'), AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)
        
        iv_str = iv.decode('utf-8', errors='ignore')
        ciphertext_b64 = base64.b64encode(encrypted_data).decode('utf-8')
        
        return f"{iv_str}::{ciphertext_b64}"
    except Exception as e:
        raise ValueError(f"Encryption failed: {str(e)}")

async def handle_url_scheme_post(request):
    """
    处理URL Scheme的POST请求
    """
    try:
        body = await request.json()
        
        if 'url_scheme_token' not in body or 'time' not in body:
            return web.json_response({
                "code": 400,
                "message": "Missing required parameters: url_scheme_token and time"
            }, status=400)
        
        encrypted_token = body['url_scheme_token']
        timestamp = body['time']
        
        try:
            request_time = datetime.fromtimestamp(int(timestamp))
            current_time = datetime.now()
            
            time_diff = abs((current_time - request_time).total_seconds())
            if time_diff > 300:  # 5分钟
                return web.json_response({
                    "code": 400,
                    "message": "Timestamp is too old or in the future"
                }, status=400)
                
        except (ValueError, TypeError):
            return web.json_response({
                "code": 400,
                "message": "Invalid timestamp format"
            }, status=400)
        
        try:
            decrypted_data = decrypt_data(encrypted_token)
            LOGGER.info(f"Successfully decrypted data: {decrypted_data}")
        except ValueError as e:
            LOGGER.error(f"Decryption failed: {str(e)}")
            return web.json_response({
                "code": 400,
                "message": "Invalid encrypted data"
            }, status=400)
        
        if not isinstance(decrypted_data, dict):
            return web.json_response({
                "code": 400,
                "message": "Decrypted data is not a valid JSON object"
            }, status=400)
        
        with Session() as session:
            try:
                emby = session.query(Emby).filter(Emby.url_scheme_token == encrypted_token).first()
                
                if not emby:
                    return web.json_response({
                        "code": 403,
                        "message": "Token not found or expired"
                    }, status=403)
                
                LOGGER.info(f"URL scheme token used successfully for user {emby.tg}")
                
                # 准备要加密的数据
                response_data = {
                    "name": emby.name,
                    "password": emby.pwd2
                }
                
                # 加密响应数据
                try:
                    encrypted_response = encrypt_data(response_data)
                    LOGGER.info("Response data encrypted successfully")
                except ValueError as e:
                    LOGGER.error(f"Failed to encrypt response data: {e}")
                    return web.json_response({
                        "code": 500,
                        "message": "Failed to encrypt response data"
                    }, status=500)
                
                return web.json_response({
                    "code": 200,
                    "message": "URL scheme processed successfully",
                    "encrypted_data": encrypted_response
                })
                
            except Exception as e:
                session.rollback()
                LOGGER.error(f"Database error: {str(e)}")
                return web.json_response({
                    "code": 500,
                    "message": "Database error"
                }, status=500)
                
    except json.JSONDecodeError:
        return web.json_response({
            "code": 400,
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        LOGGER.error(f"Unexpected error in URL scheme handler: {str(e)}")
        return web.json_response({
            "code": 500,
            "message": "Internal server error"
        }, status=500)

async def start_http_server():
    """
    启动HTTP服务器
    """
    app = web.Application()
    app.router.add_post('/url_scheme', handle_url_scheme_post)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 5000)
    await site.start()
    
    LOGGER.info("URL Scheme HTTP server started on port 5000")
    return runner

http_server_runner = None

async def init_http_server():
    global http_server_runner
    if http_server_runner is None:
        http_server_runner = await start_http_server()

async def start_url_scheme_server():
    """在bot启动时启动URL Scheme HTTP服务器"""
    try:
        await init_http_server()
        LOGGER.info("URL Scheme HTTP server initialized successfully")
    except Exception as e:
        LOGGER.error(f"Failed to start URL Scheme HTTP server: {e}")

@bot.on_start()
async def on_bot_start():
    """Bot启动时启动HTTP服务器"""
    await start_url_scheme_server()

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
