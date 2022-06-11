#!/bin/python3
import os
import subprocess
import psutil
import time
import asyncio
import logging
import platform
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class ncnn_vulkan():
    if platform.system() == "Windows":
        correct_return_code = 4294967295
    else:
        correct_return_code = 255

    def __init__(self) -> None:
        status, result = subprocess.getstatusoutput(self.binpath)
        if status != self.correct_return_code:
            logging.error("running %s error, %s" % (self.binpath, result))
            raise FileNotFoundError("running %s error")

    @classmethod
    def set_binpath(cls, binpath):
        cls.binpath = binpath

    @staticmethod
    def second2hour(input_second):
        input_second = int(input_second)
        second = input_second % 60
        minute = input_second//60 % 60
        hour = input_second//3600
        return "%d:%02d:%02d" % (hour, minute, second)

    def progress_bar(self, interval=1):
        while self.proc.poll() == None:
            co = asyncio.sleep(interval)
            current, total, used_time, eta = self.get_progress()
            used_time_str = ncnn_vulkan.second2hour(used_time)
            eta_str = ncnn_vulkan.second2hour(eta)
            print("[%s/%s time used:%s ETA:%s]" %
                  (current, total, used_time_str, eta_str), end="\r")

            loop = asyncio.get_event_loop()
            loop.run_until_complete(co)

        if self.proc.poll() != 0:
            cmds = self.proc.args
            print(cmds)

    def get_progress(self):
        used_time = time.time()-self.start_time
        self.current = len(self.o_files)
        speed = self.current/used_time
        if speed != 0:
            eta = (self.total-self.current)/speed
        else:
            eta = 0
        return self.current, self.total, used_time, eta

    @staticmethod
    def get_if_file_changes(file, start_time):
        filetime = os.path.getmtime(file)
        return filetime >= start_time

    def run(self, **kwargs):
        self.run_async(**kwargs)
        self.progress_bar()

    def run_async(self, pipe_stderr=subprocess.DEVNULL, **kwargs):
        cmd = [self.binpath]
        self.input = kwargs.get("input", kwargs.get("i"))
        self.output = kwargs.get("output", kwargs.get("o"))
        for arg in kwargs:
            cmd.append("-%s" % arg[0])
            cmd.append(str(kwargs[arg]))
        self.proc = subprocess.Popen(
            cmd, stderr=pipe_stderr, stdout=subprocess.DEVNULL)
        self.start_time = psutil.Process(pid=self.proc.pid).create_time()
        self.total = len(os.listdir(self.input))*self.times
        self.o_files = set()
        self.observer = Observer()

        class UpdateCurrent(FileSystemEventHandler):
            def on_modified(_, event):
                self.o_files.add(event.src_path)
        self.observer.schedule(UpdateCurrent(), self.output, recursive=False)
        self.observer.start()

        return self.proc

    def __str__(self) -> str:
        return "ncnn-vulkan"

    def __del__(self) -> None:
        self.observer.stop()
        self.proc.terminate()


class realcugan_ncnn_vulkan(ncnn_vulkan):
    binpath = "realcugan-ncnn-vulkan"
    times = 1


class rife_ncnn_vulkan(ncnn_vulkan):
    binpath = "rife-ncnn-vulkan"
    times = 2


if __name__ == "__main__":
    pass
