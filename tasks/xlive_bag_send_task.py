from BiliClient import asyncbili
from .push_message_task import webhook
import logging, time
import math


async def send_gift(biliapi, roomid, uid, bag, gift_num = None):
    if gift_num is None or gift_num > bag['gift_num']:
        gift_num = bag['gift_num']
    ret = await biliapi.xliveBagSend(roomid, uid, bag["bag_id"], bag["gift_id"], gift_num)
    if ret["code"] == 0:
        bag['gift_num'] -= gift_num
        logging.info(f'{biliapi.name}: 向 {uid} {ret["data"]["send_tips"]} {ret["data"]["gift_name"]} 数量{ret["data"]["gift_num"]}')
    return bag['gift_num'] <= 0


async def xlive_bag_send_task(biliapi: asyncbili,
                              task_config: dict
                              ) -> None:
    expire = task_config.get("expire", 172800)
    try:
        medal = await biliapi.xliveGetAllFansMedal()
        medal = [m for m in medal if m['status']] + sorted([m for m in medal if m['status'] == 0], key = lambda x: x['level'])
        bagList = sorted((await biliapi.xliveGiftBagList())["data"]["list"], key = lambda x: x['expire_at'])

        # lighting medals
        medals_to_send = [m for m in medal if m['is_lighted'] == 0]
        small_hearts = [bag for bag in bagList if
                        bag['gift_id'] == 30607 and bag['gift_num'] > 0 and bag["expire_at"] - int(time.time()) >= 0]
        i = 0
        for m in medals_to_send:
            while i < len(small_hearts) and small_hearts[i]['gift_num'] <= 0:
                i += 1
            if i >= len(small_hearts):
                break
            i += await send_gift(biliapi, m['roomid'], m['target_id'], small_hearts[i], 1)

        # send expire bags
        bag_to_send = [bag for bag in bagList if bag['gift_num'] > 0 and expire > bag["expire_at"] - int(time.time()) > 0]
        small_hearts = [bag for bag in bagList if
                        bag['gift_id'] == 30607 and bag['gift_num'] > 0 and bag["expire_at"] - int(time.time()) >= expire]
        heart_num_to_left = len(medal)
        for i in range(len(small_hearts) - 1, -1, -1):
            if small_hearts[i]['gift_num'] <= heart_num_to_left:
                heart_num_to_left -= small_hearts[i]['gift_num']
                del small_hearts[i]
            else:
                small_hearts[i]['gift_num'] -= heart_num_to_left
                break
        bag_to_send += small_hearts
        if not bag_to_send:
            logging.info(f'{biliapi.name}: 没有需要赠送的直播礼物，跳过赠送')
            return
        i = 0
        price = {1: {'name': '辣条', 'price': 1},
                 6: {'name': '亿元', 'price': 10},
                 30607: {'name': '小心心', 'price': 50},
                 30610: {'name': '激爽刨冰', 'price': 1}, }
        for bag in bag_to_send:
            while bag['gift_num'] > 0:
                while i < len(medal) and medal[i]['today_intimacy'] >= medal[i]['day_limit']:
                    i += 1
                if i == len(medal):
                    return
                num = min(max(math.ceil((medal[i]['day_limit'] - medal[i]['today_intimacy']) / price[bag['gift_id']]['price']), 1),
                          bag['gift_num'])
                await send_gift(biliapi, medal[i]['roomid'], medal[i]['target_id'], bag, num)
                bag['gift_num'] -= num
                medal[i]['today_intimacy'] += num * price[bag['gift_id']]['price']
    except Exception as e:
        logging.warning(f'{biliapi.name}: 直播送出即将过期礼物异常，原因为{str(e)}')
        webhook.addMsg('msg_simple', f'{biliapi.name}:直播送出礼物失败\n')
