from BiliClient import asyncbili
from queue import Queue
import logging

import asyncio
import random
import time
import datetime
import math


class WatchVideoTask:

    def __init__(self, biliapi, enable, room_id, run_time = 5.5, delete_time = 0, run_no_more_mouth = 2, duplicate = 1):
        self.biliapi = biliapi
        self.enable = enable
        self.run_time = run_time * 60 * 60
        self.delete_time = delete_time if delete_time >= 0 else 0
        self.run_no_more_mouth = run_no_more_mouth
        self.duplicate = duplicate
        self.start_time = time.time()
        self.need_vlist = {}
        if isinstance(room_id, str):
            self.room_id = room_id.split(',')
        elif isinstance(room_id, list):
            self.room_id = room_id
        else:
            self.room_id = [room_id]

    async def get_need_vlist(self, room_id):
        if room_id not in self.need_vlist:
            logging.info(f"获取 up 主{room_id}的视频列表")
            need_vlist = []
            data = await self.biliapi.spaceArcSearch(room_id)
            pages = int(math.ceil(data["data"]["page"]["count"] / 100))
            for i in range(pages):
                data = await self.biliapi.spaceArcSearch(room_id, i + 1)
                need_vlist.extend(data["data"]["list"]["vlist"])
            self.need_vlist[room_id] = need_vlist

    async def work(self):
        if not self.enable:
            return

        logging.info("检查观看视频任务")
        data = await self.biliapi.getWebNav()
        tz = datetime.timezone(datetime.timedelta(hours = 8))
        vip_due_date = datetime.datetime.fromtimestamp(data['data']['vip']['due_date'] / 1000, tz)
        now_date = datetime.datetime.now(tz)
        if (vip_due_date - now_date).days > self.run_no_more_mouth * 30:
            logging.info(f"大会员时长多于 {self.run_no_more_mouth} 月，退出观看视频任务")
            return
        else:
            logging.info(f"大会员时长仅剩 {(vip_due_date - now_date).days} 天，执行观看视频任务")

        # 必须有房间号才能运行
        if not self.room_id:
            logging.warning("观看视频模块up主号未配置,已停止...")
        else:
            tasks = []
            for room_id in self.room_id:
                for i in range(self.duplicate):
                    tasks.append(self.watch(room_id))
            if tasks:
                await asyncio.wait(map(asyncio.ensure_future, tasks))

    async def delete_video_history(self, cid):
        video_history_data = await self.biliapi.getVideoHistory()
        for video_history in video_history_data['data']['list']:
            if video_history['history']['cid'] == cid:
                kid = video_history['kid']
                await self.biliapi.deleteVideoHistory(kid)
                logging.info(f'删除视频 {cid} 的观看历史记录')
                break

    async def watch(self, room_id = None):
        sleep_time = random.randint(0, 15)
        logging.info(f'睡眠{sleep_time}秒，与其他任务错时启动')
        await asyncio.sleep(sleep_time)
        var = 0
        video_history = Queue(self.delete_time)
        while True:
            var += 1
            if room_id is None:
                room_id = random.choice(self.room_id)
            logging.info("本次观看视频为第 %s 次，选择UP %s" % (var, room_id))
            await self.get_need_vlist(room_id)
            video = random.choice(self.need_vlist[room_id])

            logging.info("本次观看选择视频为标题  %s，BV： %s" % (video["title"], video["bvid"]))

            # 获取视频分P
            video_data = await self.biliapi.getVideoPages(video['bvid'])

            for p in range(len(video_data["data"])):
                logging.info("正在观看 %s 第 %d p，共 %d p" % (video["bvid"], p + 1, len(video_data["data"])))
                video_cid = video_data["data"][p]["cid"]
                video_duration = video_data["data"][p]["duration"]
                if self.delete_time > 0:
                    if video_history.full():
                        cid = video_history.get()
                        await self.delete_video_history(cid)
                    video_history.put(video_cid)

                # start_ts = time.time()
                # await self.biliapi.watchVideoReport(video['aid'])
                # rep = await self.biliapi.watchVideoCollector(video['aid'], start_ts * 1000, self.biliapi.uid, random.randint(1000, 1500),
                #                                              start_ts, random.randint(70, 90))
                start_ts = time.time()
                start_time = random.randint(1, 3)
                await asyncio.sleep(start_time)
                cur_time = start_time
                while cur_time <= video_duration:
                    if time.time() - self.start_time > self.run_time:
                        while not video_history.empty():
                            cid = video_history.get()
                            await self.delete_video_history(cid)
                        return
                    rep = await self.biliapi.watchVideoHeartBeat(video['aid'], video_cid, video['bvid'], self.biliapi.uid, cur_time,
                                                                 start_ts = start_ts)
                    if cur_time + 15 <= video_duration:
                        await asyncio.sleep(15)
                    else:
                        await asyncio.sleep(video_duration - cur_time)
                        await self.biliapi.watchVideoHeartBeat(video['aid'], video_cid, video['bvid'], self.biliapi.uid, video_duration,
                                                               start_ts = start_ts)


async def watch_video_task(biliapi: asyncbili, task_config: dict) -> None:
    worker = WatchVideoTask(biliapi, **task_config)
    await worker.work()
