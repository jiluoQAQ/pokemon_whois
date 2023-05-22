import os
import re
import io
import json
import requests
from io import BytesIO
import base64
from collections import OrderedDict
import aiohttp
from os import path
import math
import random
from hoshino import Service
from hoshino.typing import CQEvent, MessageSegment
from hoshino.util import pic2b64
from hoshino import aiorequests
import asyncio, sqlite3
from numpy import zeros, uint8, ones
from random import choice
from . import chara
from  PIL  import   Image,ImageFont,ImageDraw
from . import poke_data

PIC_SIDE_LENGTH = 25 
LH_SIDE_LENGTH = 75
ONE_TURN_TIME = 20
DB_PATH = os.path.expanduser('~/.hoshino/poke_whois_winning_counter.db')
BLACKLIST_ID = [1072, 1908, 4031, 9000]

FILE_PATH = os.path.dirname(__file__)
FONTS_PATH = os.path.join(FILE_PATH,'font')
FONTS_PATH = os.path.join(FONTS_PATH,'sakura.ttf')

class WinnerJudger:
    def __init__(self):
        self.on = {}
        self.winner = {}
        self.correct_chara_id = {}
    
    def record_winner(self, gid, uid):
        self.winner[gid] = str(uid)
        
    def get_winner(self, gid):
        return self.winner[gid] if self.winner.get(gid) is not None else ''
        
    def get_on_off_status(self, gid):
        return self.on[gid] if self.on.get(gid) is not None else False
    
    def set_correct_chara_id(self, gid, cid):
        self.correct_chara_id[gid] = cid
    
    def get_correct_chara_id(self, gid):
        return self.correct_chara_id[gid] if self.correct_chara_id.get(gid) is not None else chara.UNKNOWN
    
    def turn_on(self, gid):
        self.on[gid] = True
        
    def turn_off(self, gid):
        self.on[gid] = False
        self.winner[gid] = ''
        self.correct_chara_id[gid] = chara.UNKNOWN


winner_judger = WinnerJudger()

class WinningCounter:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._create_table()


    def _connect(self):
        return sqlite3.connect(DB_PATH)


    def _create_table(self):
        try:
            self._connect().execute('''CREATE TABLE IF NOT EXISTS WINNINGCOUNTER
                          (GID             INT    NOT NULL,
                           UID             INT    NOT NULL,
                           COUNT           INT    NOT NULL,
                           PRIMARY KEY(GID, UID));''')
        except:
            raise Exception('创建表发生错误')
    
    
    def _record_winning(self, gid, uid):
        try:
            winning_number = self._get_winning_number(gid, uid)
            conn = self._connect()
            conn.execute("INSERT OR REPLACE INTO WINNINGCOUNTER (GID,UID,COUNT) \
                                VALUES (?,?,?)", (gid, uid, winning_number+1))
            conn.commit()       
        except:
            raise Exception('更新表发生错误')


    def _get_winning_number(self, gid, uid):
        try:
            r = self._connect().execute("SELECT COUNT FROM WINNINGCOUNTER WHERE GID=? AND UID=?",(gid,uid)).fetchone()        
            return 0 if r is None else r[0]
        except:
            raise Exception('查找表发生错误')

def get_pic(address):
    return requests.get(address,timeout=20).content

def get_win_pic(name,enname):
    picfile = path.join(path.dirname(__file__), 'icon', f'{name}.png')
    im = Image.new("RGB", (640, 464), (255, 255, 255))
    base_img = os.path.join(FILE_PATH, "whois_bg.jpg")
    dtimg = Image.open(base_img)
    dtbox = (0, 0)
    im.paste(dtimg, dtbox)
    
    image=Image.open(picfile).convert('RGBA')
    image = image.resize((230, 230))
    dtbox = (50, 60)
    im.paste(image, dtbox, mask=image.split()[3])
    
    draw = ImageDraw.Draw(im)
    line = enname
    font = ImageFont.truetype(FONTS_PATH, 40)
    w, h = draw.textsize(line, font=font)
    draw.text(((926 - w) / 2, 40), line, font=font, fill = (255, 255, 0))
    
    line = name
    font = ImageFont.truetype(FONTS_PATH, 42)
    w, h = draw.textsize(line, font=font)
    draw.text(((926 - w) / 2, 100), line, font=font, fill = (255, 255, 0))
    output = BytesIO()
    im.save(output, format="PNG")
    base64_str = 'base64://' + base64.b64encode(output.getvalue()).decode()
    mes = f"[CQ:image,file={base64_str}]"
    return mes
    
async def get_user_card_dict(bot, group_id):
    mlist = await bot.get_group_member_list(group_id=group_id)
    d = {}
    for m in mlist:
        d[m['user_id']] = m['card'] if m['card']!='' else m['nickname']
    return d


def uid2card(uid, user_card_dict):
    return str(uid) if uid not in user_card_dict.keys() else user_card_dict[uid]

sv = Service('whois', enable_on_default=True, help_='''我是谁
猜猜我是谁
''')
#w:230,hL230, x:50,y:60
#en x:926-w y:60
#ch x:926-w y:100
@sv.on_prefix(['我是谁'])
async def whois_poke(bot, ev: CQEvent):
    try:
        if winner_judger.get_on_off_status(ev.group_id):
            await bot.send(ev, "此轮游戏还没结束，请勿重复使用指令")
            return
        winner_judger.turn_on(ev.group_id)
        chara_id_list = list(poke_data.CHARA_NAME.keys())
        poke_list = poke_data.CHARA_NAME
        while True:
            random.shuffle(chara_id_list)
            if chara_id_list[0] not in BLACKLIST_ID: break
        winner_judger.set_correct_chara_id(ev.group_id, chara_id_list[0])
        #print(chara_id_list[0])
        
        c = chara.fromid(chara_id_list[0])
        enname = poke_list[chara_id_list[0]][1]
        win_mes = get_win_pic(c.name,enname)
        
        picfile = path.join(path.dirname(__file__), 'icon', f'{c.name}.png')
        #print(c.name)
        im = Image.new("RGB", (640, 464), (255, 255, 255))
        base_img = os.path.join(FILE_PATH, "whois_bg.jpg")
        dtimg = Image.open(base_img)
        dtbox = (0, 0)
        im.paste(dtimg, dtbox)
        
        image=Image.open(picfile).convert('RGBA')
        image = image.resize((230, 230))
        width=image.size[0]   #获取图片宽度
        height=image.size[1]  #获取图片高度
        for x in range(width):
            for y in range(height):
                
                R,G,B,A=image.getpixel((x,y)) #获取单个像素点的RGB
                
                """转化为灰度：整数方法"""
                if A == 0:
                    Gray = 255
                else:
                    Gray = 0
                    A = 255
                # if x == 0 and y == 0:
                    # print(str(rgba))
                    # print("R:"+str(R))
                    # print("G:"+str(G))
                    # print("B:"+str(B))
                    # print("A:"+str(A))
                    # print("Gray:"+str(Gray))
                """转化为灰度图：GRB(Gray,Gray,Gray)替换GRB(R,G,B)"""
                image.putpixel((x,y),(Gray,Gray,Gray,A))
        """保存灰度图"""
        image=image.convert('RGBA')
        dtbox = (50, 60)
        im.paste(image, dtbox, mask=image.split()[3])
        
        draw = ImageDraw.Draw(im)
        line = "？？？"
        font = ImageFont.truetype(FONTS_PATH, 40)
        w, h = draw.textsize(line, font=font)
        draw.text(((926 - w) / 2, 40), line, font=font, fill = (255, 255, 0))
        
        line = "我是谁"
        font = ImageFont.truetype(FONTS_PATH, 42)
        w, h = draw.textsize(line, font=font)
        draw.text(((926 - w) / 2, 100), line, font=font, fill = (255, 255, 0))
        
        output = BytesIO()
        im.save(output, format="PNG")
        base64_str = 'base64://' + base64.b64encode(output.getvalue()).decode()
        mes = f"猜猜我是谁，({ONE_TURN_TIME}s后公布答案)[CQ:image,file={base64_str}]"
        #print(img_send)
        await bot.send(ev, mes)
        await asyncio.sleep(ONE_TURN_TIME)
        if winner_judger.get_winner(ev.group_id) != '':
            winner_judger.turn_off(ev.group_id)
            return
        msg =  f'正确答案是:{win_mes}\n很遗憾，没有人答对~'
        winner_judger.turn_off(ev.group_id)
        await bot.send(ev, msg)
        #os.remove(picfile) 
    except Exception as e:
        winner_judger.turn_off(ev.group_id)
        await bot.send(ev, '错误:\n' + str(e))

@sv.on_message()
async def on_input_chara_name(bot, ev: CQEvent):
    try:
        if winner_judger.get_on_off_status(ev.group_id):
            gid = ev.group_id
            uid = ev.user_id
            s = ev.message.extract_plain_text()
            cid = chara.name2id(s)
            if cid != chara.UNKNOWN and cid == winner_judger.get_correct_chara_id(ev.group_id) and winner_judger.get_winner(ev.group_id) == '':
                winner_judger.record_winner(ev.group_id, ev.user_id)
                winning_counter = WinningCounter()
                winning_counter._record_winning(ev.group_id, ev.user_id)
                winning_count = winning_counter._get_winning_number(ev.group_id, ev.user_id)
                user_card_dict = await get_user_card_dict(bot, ev.group_id)
                user_card = uid2card(ev.user_id, user_card_dict)
                msg_part = f'{user_card}猜对了，真厉害！TA已经猜对{winning_count}次了~\n'
                
                
                cid_win = winner_judger.get_correct_chara_id(ev.group_id)
                c = chara.fromid(cid_win)
                poke_list = poke_data.CHARA_NAME
                enname = poke_list[cid_win][1]
                win_mes = get_win_pic(c.name,enname)
                
                msg =  f'正确答案是:{win_mes}\n{msg_part}'
                await bot.send(ev, msg)
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))
