"""
服务器讯息打印

"""
from datetime import datetime, timezone, timedelta
from pyrogram import filters
from sqlalchemy import Nullable

from bot import bot, emby_line, special_emby_line
from bot.func_helper.emby import emby
from bot.func_helper.filters import user_in_group_on_filter
from bot.sql_helper.sql_emby import sql_get_emby
from bot.func_helper.fix_bottons import cr_page_server
from bot.func_helper.msg_utils import callAnswer, editMessage


@bot.on_callback_query(filters.regex('server') & user_in_group_on_filter)
async def server(_, call):
    data = sql_get_emby(tg=call.from_user.id)
    if not data:
        return await editMessage(call, '⚠️ 数据库没有你，请重新 /start录入')
    await callAnswer(call, '🌐查询中...')
    try:
        # 支持数字ID (Nezha) 和 UUID (Komari)
        server_id = call.data.split(':')[1]
        try:
            server_id = int(server_id)  # 尝试转为整数 (Nezha)
        except ValueError:
            pass  # 保持为字符串 UUID (Komari)
    except IndexError:
        # 第一次查看
        send = await editMessage(call, "**▎🌐查询中...\n\nο(=•ω＜=)ρ⌒☆ 发送bibo电波~bibo~ \n⚡ 点击按钮查看相应服务器状态**")
        if send is False:
            return

        keyboard, sever = await cr_page_server()
        server_info = sever[0]['server'] if sever == '' else ''
    else:
        keyboard, sever = await cr_page_server()
        server_info = ''.join([item['server'] for item in sever if item['id'] == server_id])

    pwd = '空' if not data.pwd else data.pwd
    if data.lv == "b":
        line = f'{emby_line}'
    elif data.lv == 'a':
        line = f'{emby_line}'
        if special_emby_line:
            line += f'\n{special_emby_line}'
    else:
        line = ' - **无权查看**'
    try:
        online = await emby.get_current_playing_count()
        if online == -1:
            online = 'Emby服务器断连 ·0'
    except Exception:
        online = 'Emby服务器断连 ·0'
    text = f'**▎↓目前线路 & 用户密码：**`{pwd}`\n' \
           f'{line}\n\n' \
           f'{server_info}' \
           f'· 🎬 在线 | **{online}** 人\n\n' \
           f'**· 🌏 [{(datetime.now(timezone(timedelta(hours=0)))).strftime("%Y-%m-%d %H:%M:%S")}]**'
    await editMessage(call, text, buttons=keyboard)
