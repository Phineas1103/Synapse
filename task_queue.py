# -*- coding: utf-8 -*-
"""Synapse — 异步任务队列"""

import os
import time
import threading
import queue
import traceback


class TaskQueue:
    """
    通用异步任务队列，支持并发控制、进度回调、暂停/恢复。
    用于图片生成和视频生成的批量任务管理。
    """

    def __init__(self, max_concurrent=3, poll_interval=5):
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.tasks = {}  # task_id -> TaskInfo
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 默认不暂停
        self._workers = []
        self._running = False
        self._submit_queue = queue.Queue()
        self._progress_callback = None
        self._complete_callback = None

    def set_progress_callback(self, callback):
        """设置进度回调：callback(completed, total, task_id, status)"""
        self._progress_callback = callback

    def set_complete_callback(self, callback):
        """设置全部完成回调：callback(results)"""
        self._complete_callback = callback

    def add_task(self, task_id, task_type, func, *args, **kwargs):
        """添加任务到队列"""
        with self._lock:
            self.tasks[task_id] = {
                "id": task_id,
                "type": task_type,  # "image" / "video"
                "func": func,
                "args": args,
                "kwargs": kwargs,
                "status": "pending",  # pending/running/completed/failed/paused
                "result": None,
                "error": None,
                "created_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "retry_count": 0,
                "max_retries": 3,
            }
        self._submit_queue.put(task_id)

    def start(self):
        """启动任务队列"""
        if self._running:
            return
        self._running = True
        self._pause_event.set()

        # 启动工作线程
        for i in range(self.max_concurrent):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"TaskWorker-{i}")
            t.start()
            self._workers.append(t)

    def stop(self):
        """停止任务队列"""
        self._running = False
        self._pause_event.set()  # 唤醒所有等待的线程

    def pause(self):
        """暂停任务执行"""
        self._pause_event.clear()

    def resume(self):
        """恢复任务执行"""
        self._pause_event.set()

    def is_paused(self):
        return not self._pause_event.is_set()

    def get_status(self):
        """获取整体状态"""
        with self._lock:
            total = len(self.tasks)
            completed = sum(1 for t in self.tasks.values() if t["status"] == "completed")
            failed = sum(1 for t in self.tasks.values() if t["status"] == "failed")
            running = sum(1 for t in self.tasks.values() if t["status"] == "running")
            pending = sum(1 for t in self.tasks.values() if t["status"] == "pending")

            tasks_detail = []
            for tid, t in self.tasks.items():
                tasks_detail.append({
                    "id": tid,
                    "type": t["type"],
                    "status": t["status"],
                    "error": t["error"],
                    "created_at": t["created_at"],
                    "started_at": t["started_at"],
                    "completed_at": t["completed_at"],
                })

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "is_paused": self.is_paused(),
            "is_running": self._running,
            "tasks": tasks_detail,
        }

    def retry_task(self, task_id):
        """重试失败的任务"""
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task["status"] == "failed":
                task["status"] = "pending"
                task["error"] = None
                task["retry_count"] += 1
                self._submit_queue.put(task_id)

    def get_task_result(self, task_id):
        """获取任务结果"""
        with self._lock:
            task = self.tasks.get(task_id)
            if task:
                return {
                    "id": task_id,
                    "status": task["status"],
                    "result": task["result"],
                    "error": task["error"],
                }
        return None

    def _worker_loop(self):
        """工作线程主循环"""
        while self._running:
            try:
                task_id = self._submit_queue.get(timeout=1)
            except queue.Empty:
                continue

            # 等待暂停恢复
            self._pause_event.wait()
            if not self._running:
                break

            with self._lock:
                task = self.tasks.get(task_id)
                if not task or task["status"] != "pending":
                    continue
                task["status"] = "running"
                task["started_at"] = time.time()

            try:
                result = task["func"](*task["args"], **task["kwargs"])
                with self._lock:
                    task["status"] = "completed"
                    task["result"] = result
                    task["completed_at"] = time.time()
                if self._progress_callback:
                    self._progress_callback(task_id, "completed", None)
            except Exception as e:
                with self._lock:
                    if task["retry_count"] < task["max_retries"]:
                        task["status"] = "pending"
                        task["retry_count"] += 1
                        task["error"] = f"重试中 ({task['retry_count']}): {str(e)}"
                        self._submit_queue.put(task_id)
                    else:
                        task["status"] = "failed"
                        task["error"] = str(e)
                        task["completed_at"] = time.time()
                if self._progress_callback:
                    self._progress_callback(task_id, task["status"], str(e))

        # 检查是否全部完成
        if self._complete_callback:
            with self._lock:
                all_done = all(
                    t["status"] in ("completed", "failed")
                    for t in self.tasks.values()
                )
            if all_done:
                self._complete_callback(self.get_status())
