#!/bin/python3
import os
import sys
import psutil
import time
import asyncio
import logging
from ncnn_vulkan import *
from uuid import uuid1
import math
from copy import deepcopy
import threading
from traceback import format_exc
import ffmpeg
import tempfile


def touch(file_name):
    if os.path.exists(file_name):
        pass
    else:
        fid = open(file_name, 'w')
        fid.close()


def multi_touch_png(dir, num, key="%05d.png"):
    try:
        os.mkdir(dir)
    except FileExistsError:
        logging.debug("Existed png dir %s" % dir)
    for i in range(1, num+1):
        filename = os.path.join(dir, key % i)
        touch(filename)


def get_proc_cmd(proc):
    cmd = ""
    for arg in proc.args:
        if " " in arg or "\\" in arg:
            cmd += "'%s' " % arg
        else:
            cmd += "%s " % arg
    return cmd


class converter():
    if sys.platform == "win32":
        temp_dir = os.getenv('TEMP')
        logging.debug("current OS is windows")
    else:
        temp_dir = "/tmp"
        logging.debug("current OS is %s" % sys.platform)

    time_interval = 5
    frames_interval = 200
    ffmpeg_cmd = "ffmpeg"
    ffprobe_cmd = "ffprobe"

    ffmpeg_progess_args = ('-progress', 'pipe:', '-nostats')

    @classmethod
    def set_temp_dir(cls, dir):
        logging.debug("set temp_dir to %s" % dir)
        cls.temp_dir = dir

    @classmethod
    def set_time_interval(cls, interval):
        logging.debug("set time_interval to %s" % interval)
        cls.time_interval = interval

    @classmethod
    def set_frames_interval(cls, interval):
        logging.debug("set frames_interval to %s" % interval)
        cls.frames_interval = interval

    @classmethod
    def set_ffmpeg_cmd(cls, ffmpeg_cmd):
        logging.debug("set ffmpeg_cmd to %s" % ffmpeg_cmd)
        cls.ffmpeg_cmd = ffmpeg_cmd

    @classmethod
    def set_ffprobe_cmd(cls, ffprobe_cmd):
        logging.debug("set ffprobe_cmd to %s" % ffprobe_cmd)
        cls.ffprobe_cmd = ffprobe_cmd

    @staticmethod
    def get_png_num(dir):
        num = 0
        for file in os.listdir(dir):
            if file.endswith(".png"):
                try:
                    int(file.split(".")[0])
                except ValueError:
                    continue
                num += 1
        return num

    @staticmethod
    def proc_wait_log(proc, total=None, obj=None):
        if "ffmpeg" in proc.cmd:
            converter.ffmpeg_progress_thread(proc, total)

        proc.wait()
        if hasattr(obj, "observer"):
            obj.observer.stop()
        converter.proc_end_log_clean(proc)

    @staticmethod
    def proc_end_log_clean(proc):
        if proc.terminated:
            logging.debug(
                "ChildProcess has been terminated, pid %s, cmd: %s" % (proc.pid, proc.cmd))
            return
        if proc.returncode != 0:
            logging.critical("ChildProcess Exiting abnormally, cmdline %s, returncode %s" % (
                proc.cmd, proc.returncode))

            proc.stderr.seek(0)
            stderr_text = proc.stderr.read().decode()
            if sys.platform == "win32":
                stderr_text = stderr_text.replace("\r\n", "\n")
            logging.critical(
                "You might want to check its stderr, see below \n%s" % stderr_text)
            raise RuntimeError(
                "subprocess exited none-zero return code %s" % proc.returncode)
        else:
            logging.info(
                "ChildProcess Exiting Normally, cmdline %s" % proc.cmd)
            input_file = proc.args[proc.args.index("-i")+1]
            if not os.path.exists(input_file):
                dirname = os.path.dirname(input_file)
                pattern = os.path.basename(input_file)
                converter.remove_temp_dir(dirname, pattern)
            elif os.path.isdir(input_file):
                num = len(os.listdir(input_file))
                file_length = math.ceil(math.log(num, 10))
                key = "%0"+str(file_length)+"d.png"
                converter.remove_temp_dir(input_file, key)

    @staticmethod
    def check_file_has_audio(file):
        info = ffmpeg.probe(
            file, cmd=converter.ffprobe_cmd, select_streams="a")
        if len(info["streams"]) == 0:
            return False
        else:
            return True

    @staticmethod
    def get_videofile_frames(file):
        try:
            info = ffmpeg.probe(
                file, cmd=converter.ffprobe_cmd, select_streams="v:0")
            stream = info["streams"][0]
            fr_temp = stream['avg_frame_rate'].split("/")
            fr_temp[0] = int(fr_temp[0])
            fr_temp[1] = int(fr_temp[1])
            framerate = fr_temp[0]/fr_temp[1]
            try:
                frames = int(stream['nb_frames'])
            except KeyError:
                cmd = (converter.ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
                       "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", file)
                logging.debug(
                    "cannot get frames from ffmpeg.ffprobe, try get it from command line, cmd %s" % " ".join(cmd))
                p = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE)
                p.wait()
                frames = int(p.stdout.read())
        except ffmpeg.Error:
            logging.critical("Incorrect video file %s" % file)
            raise ffmpeg.Error("Incorrect video file")
        except IndexError:
            logging.critical("no video stream in file %s" % file)
            raise
        return frames, framerate

    @staticmethod
    def ffmpeg_progress_thread(proc: subprocess.Popen, total: int = None):
        start_time = psutil.Process(pid=proc.pid).create_time()
        proc.current = 0
        proc.used_time = 0
        proc.eta = 0
        if total == None:
            cmds = proc.args
            input = cmds[cmds.index("-i")+1]

            if input.endswith("png"):
                input_dir = os.path.dirname(input)
                proc.total = converter.get_png_num(input_dir)
            else:
                proc.total, _ = converter.get_videofile_frames(input)
        else:
            proc.total = total

        logfile = proc.stdout
        while proc.poll() == None:
            line = logfile.readline().decode().strip("\n")
            if line == "":
                break
            key, value = line.split("=")
            if key == "progress" and value == "end":
                proc.stderr.read()
                break
            elif key == "frame":
                proc.current = int(value)
            else:
                continue
            proc.used_time = time.time()-start_time
            speed = proc.current/proc.used_time
            if speed == float(0):
                proc.eta = 0
            else:
                proc.eta = (proc.total-proc.current)/speed

    @staticmethod
    def ffmpeg_get_progress(proc):
        while not hasattr(proc, "total"):
            time.sleep(0.1)
        return proc.current, proc.total, proc.used_time, proc.eta

    @staticmethod
    async def check_proc_progress(proc, obj):
        cmd = proc.args[0]
        try:
            if "ffmpeg" in cmd:
                return converter.ffmpeg_get_progress(proc)
            else:
                return obj.get_progress()
        except psutil.NoSuchProcess:
            return (0, 0, 0, 0)

    def __init__(self, input_file, framerate=None) -> None:
        logging.info("starting process input file %s" % input_file)
        self.current = {
            "file": input_file,
            "frames": 0,
            "framerate": framerate,
            "type": None,
            "pattern_format": None
        }
        if os.path.isdir(input_file) and type(framerate) in (int, float):
            logging.debug("input %s is directory" % input_file)
            self.current["frames"] = converter.get_png_num(input_file)
            self.current["type"] = "dirpngs"
            for file in os.listdir(input_file):
                if file.endswith(".png"):
                    filename = file
            num = len(filename)-4
            self.current["pattern_format"] = "%0"+str(num)+"d.png"

        elif os.path.isfile(input_file):
            logging.debug("input %s is file" % input_file)
            self.current["type"] = "videofile"
            self.current["frames"], self.current["framerate"] = converter.get_videofile_frames(
                input_file)
        else:
            raise ValueError("Unsupported input type")
        self.query = []

    def gen_temp_dir(self, key=None):
        dirstr = str(uuid1())
        output = os.path.join(self.temp_dir, dirstr)
        if key == None and self.current["pattern_format"] == None:
            key = self.gen_pattern_format()
        elif key == None:
            key = self.current["pattern_format"]
        multi_touch_png(output, self.current["frames"], key=key)
        logging.info("generated temp dir %s" % output)
        return output

    @staticmethod
    def remove_temp_dir(dir, key, num=float("Inf")):
        i = 1
        while i <= num:
            filename = key % i
            full_filename = os.path.join(dir, filename)
            try:
                os.remove(full_filename)
                i += 1
            except FileNotFoundError:
                break
        try:
            os.rmdir(dir)
            logging.debug("removed temp dir %s" % dir)
        except FileNotFoundError:
            logging.debug(
                "cannot remove temp dir %s because it doesn't exist" % dir)
        except OSError:
            logging.warning(
                "cannot remove temp dir %s because there are other files in it" % dir)

    @staticmethod
    def progress_bar0(results):
        out_str = ""
        for proc in results:
            current, total, time_used, eta = results[proc]
            used_time_str = ncnn_vulkan.second2hour(time_used)
            eta_str = ncnn_vulkan.second2hour(eta)
            name = os.path.basename(proc.args[0]).split("-")[0]
            out_str += "[%s %s/%s time used:%s ETA:%s]" % (
                name, current, total, used_time_str, eta_str)
        width = os.get_terminal_size().columns
        space_num = width-len(out_str)-1
        print("\r"+out_str+" "*space_num, end="")

    def gen_pattern_format(self):
        file_length = math.ceil(math.log(self.current["frames"], 10))
        key = "%0"+str(file_length)+"d"
        self.current["pattern_format"] = key+".png"
        return key+".png"

    def ffmpeg_v2p(self, input=None, output=None, target_fps=None, round="up", **ffmpeg_args):
        if input == None:
            input = self.current["file"]
        if target_fps != None:
            self.current["frames"] = math.ceil(
                self.current["frames"]*target_fps/self.current["framerate"])
            self.current["framerate"] = target_fps
        if output == None:
            output = self.gen_temp_dir()

        self.current["file"] = str(output)
        output_arg = os.path.join(output, self.gen_pattern_format())
        input_obj = ffmpeg.input(input)
        if target_fps == None:
            run_obj = input_obj.output(output_arg, **ffmpeg_args)
        else:
            run_obj = input_obj.filter("fps", fps=target_fps, round=round).output(
                output_arg, **ffmpeg_args)

        run_obj = run_obj.global_args(*self.ffmpeg_progess_args)

        if converter.check_file_has_audio(input):
            self.audio = input_obj.audio

        kwargs = {
            "cmd": self.ffmpeg_cmd,
            "pipe_stdout": True,
            "pipe_stderr": True
        }
        self.query.append({
            "obj": run_obj,
            "args": kwargs,
            "current": deepcopy(self.current)
        })
        return self

    def realcugan(self, input=None, output=None, scale=2, noise=-1, model="models-se", j_threads="1:1:1", gpu_id="auto"):
        kwargs = locals()
        if scale in (2, 3, 4):
            kwargs.pop("self")
            if input == None:
                input = self.current["file"]
                kwargs.update({"input": input})
            if output == None:
                output = self.gen_temp_dir()
                kwargs.update({"output": output})
                self.current["file"] = str(output)
            else:
                multi_touch_png(
                    output, num=self.current["frames"], key=self.current["pattern_format"])

            obj = realcugan_ncnn_vulkan()

            kwargs.update({"pipe_stderr": tempfile.SpooledTemporaryFile()})
            self.query.append({
                "obj": obj,
                "args": kwargs,
                "current": deepcopy(self.current)
            })
        elif scale in (6, 8):
            self.realcugan(input=input, output=None, scale=int(
                scale/2), noise=noise, model=model, j_threads=j_threads, gpu_id=gpu_id)
            self.realcugan(input=None, output=output, scale=2, noise=noise,
                           model=model, j_threads=j_threads, gpu_id=gpu_id)
        else:
            logging.error("not supported scale %s, didn't do anything" % scale)
        return self

    def rife(self, input=None, output=None, model="rife-anime", j_threads="1:2:2", f_pattern_format=None, gpu_id="auto"):
        kwargs = locals()
        kwargs.pop("self")

        self.current["frames"] = self.current["frames"]*2
        self.current["framerate"] = self.current["framerate"]*2
        self.gen_pattern_format()

        if input == None:
            input = self.current["file"]
            kwargs.update({"input": input})

        if output == None:
            output = self.gen_temp_dir()
            kwargs.update({"output": output})
            self.current["file"] = str(output)

        if f_pattern_format == None:
            multi_touch_png(
                output, self.current["frames"], self.current["pattern_format"])
            kwargs.update({"f_pattern_format": self.current["pattern_format"]})
        else:
            self.current["pattern_format"] = f_pattern_format

        obj = rife_ncnn_vulkan()
        kwargs.update({"pipe_stderr": tempfile.SpooledTemporaryFile()})
        self.query.append({
            "obj": obj,
            "args": kwargs,
            "current": deepcopy(self.current)
        })
        return self

    def ffmpeg_p2v(self, output, input=None, overwrite_output=False, filters=None, **ffmpeg_args):
        if os.path.exists(output) and not overwrite_output:
            logging.error(
                "output file %s a exists, not overwriting. you can use overwrite_output=True to override this" % output)
            raise ValueError(
                "output file %s a exists, not overwriting. you can use overwrite_output=True to override this" % output)
        if input == None:
            input = os.path.join(
                self.current["file"], self.current["pattern_format"])

        stream = ffmpeg.input(input, r=self.current["framerate"])
        if filters:
            for line in filters:
                stream = stream.filter(**line)
        streams = [stream]
        if hasattr(self, "audio"):
            streams.append(self.audio)
            ffmpeg_args.update({"acodec": "copy"})
        if "metadata:s:v" not in ffmpeg_args:
            ffmpeg_args.update(
                {'metadata:s:v': 'encoder=github.com/deorth-kku/aufit'})
        run_obj = ffmpeg.output(*streams, output, **ffmpeg_args)

        run_obj = run_obj.global_args(*self.ffmpeg_progess_args)

        kwargs = {
            "cmd": self.ffmpeg_cmd,
            "pipe_stdout": True,
            "overwrite_output": overwrite_output,
            "pipe_stderr": True
        }
        self.current["file"] = output
        self.current["pattern_format"] = None
        self.query.append({
            "obj": run_obj,
            "args": kwargs,
            "current": deepcopy(self.current)
        })
        return self

    def ffmpeg_p2p_resize(self, width: int, height: int, input: str = None, output: str = None):
        if input == None:
            input = os.path.join(
                self.current["file"], self.current["pattern_format"])
        if output == None:
            output = self.gen_temp_dir()

        self.current["file"] = str(output)
        output_arg = os.path.join(output, self.gen_pattern_format())
        input_obj = ffmpeg.input(input)

        run_obj = input_obj.filter("scale", width, height).output(output_arg)

        run_obj = run_obj.global_args(*self.ffmpeg_progess_args)

        kwargs = {
            "cmd": self.ffmpeg_cmd,
            "pipe_stdout": True,
            "pipe_stderr": True
        }
        self.query.append({
            "obj": run_obj,
            "args": kwargs,
            "current": deepcopy(self.current)
        })
        return self

    def run(self, parallel=False):
        try:
            if not parallel:
                logging.debug("running serial mode")
                for line in self.query:
                    proc = line["obj"].run_async(**line["args"])
                    proc.sleeping = False
                    proc.cmd = get_proc_cmd(proc)
                    proc.terminated = False

                    line.update({"proc": proc})
                    logging.debug(
                        "ChildProcess Started, cmdline %s, pid %s" % (proc.cmd, proc.pid))
                    while proc.poll() == None:
                        self.progress_bar(1)

                    converter.proc_end_log_clean(proc)

            else:
                logging.debug("running parallel mode")
                for i in range(len(self.query)):
                    line = self.query[i]
                    proc = line["obj"].run_async(**line["args"])

                    proc.sleeping = False
                    proc.cmd = get_proc_cmd(proc)
                    proc.terminated = False

                    line.update({"proc": proc})
                    logging.debug(
                        "ChildProcess Started, cmdline %s, pid %s" % (proc.cmd, proc.pid))
                    th = threading.Thread(target=converter.proc_wait_log, args=(
                        proc, line["current"]["frames"], line["obj"]))
                    th.start()
                    line.update({"thread": th})
                    if os.path.basename(proc.args[0]) == "ffmpeg":
                        if sys.platform == "win32":
                            psutil.Process(proc.pid).nice(
                                psutil.IDLE_PRIORITY_CLASS)
                        else:
                            psutil.Process(proc.pid).nice(-20)
                    else:
                        if sys.platform == "win32":
                            psutil.Process(proc.pid).nice(
                                psutil.BELOW_NORMAL_PRIORITY_CLASS)
                        else:
                            psutil.Process(proc.pid).nice(-10)

                    results = self.progress_bar(0)
                    flag = False
                    while flag or proc.returncode == None and (results[proc][2] < self.time_interval or results[proc][0] < self.frames_interval):
                        results = self.progress_bar(1)
                        try:
                            next_name = str(self.query[i+1]["obj"])
                        except IndexError:
                            break
                        if next_name != "ncnn-vulkan":
                            next_name = "ffmpeg"
                        else:
                            next_name = "vulkan"
                        current_names = [os.path.basename(
                            proc.args[0]).split("-")[-1] for proc in results]
                        flag = next_name in current_names
                        self.progress_contorl(results)

                while True:
                    results = self.progress_bar(1)
                    self.progress_contorl(results)
                    polls = [proc.poll() for proc in results.keys()]
                    if not None in polls:
                        break
                for line in self.query:
                    if "thread" in line:
                        line["thread"].join()

            logging.info("All process finish, process output file %s successful" %
                         self.query[-1]["current"]["file"])
        except KeyboardInterrupt:
            message = "Ctrl+C pressed, now exiting..."
            print("\n"+message)
            logging.warning(message)
            self.close()
            self.clean()
            print("exited!")
            sys.exit(1)
        except Exception as e:
            logging.error("Enconter error %s, terminating ChildProcesses" % e)
            logging.error(format_exc())
            self.close()
            raise e

    def progress_contorl(self, results):
        procs = list(results.keys())
        procs_num = len(procs)
        for index in range(1, procs_num):
            proc = procs[index]
            proc_former = procs[index-1]
            if proc.returncode == None:
                p = psutil.Process(pid=proc.pid)
                if (not proc.sleeping) and (results[proc][0] > results[proc_former][0]-self.frames_interval):
                    p.suspend()
                    proc.sleeping = True
                    logging.debug("paused process pid %s" % proc.pid)
                elif proc.sleeping and (results[proc][0] <= results[proc_former][0]-self.frames_interval):
                    p.resume()
                    proc.sleeping = False
                    logging.debug("resumed process pid %s" % proc.pid)
        if procs_num == 1:
            proc = procs[0]
            if proc.sleeping and proc.poll() == None and os.path.basename(proc.args[0]) == "ffmpeg":
                p = psutil.Process(pid=proc.pid)
                p.resume()
                proc.sleeping = False
                logging.debug("resumed process pid %s" % proc.pid)

    def progress_bar(self, time=0):
        loop = asyncio.get_event_loop()
        tasks = [loop.create_task(asyncio.sleep(time))]
        results = {}
        for line in self.query:
            if "proc" in line and line["proc"].poll() == None:
                kwargs = {
                    "obj": line["obj"]
                }
                task = loop.create_task(
                    converter.check_proc_progress(line["proc"], **kwargs)
                )
                tasks.append(task)
                results.update({line["proc"]: task})
        loop.run_until_complete(asyncio.wait(tasks))

        for proc in results:
            try:
                result = results[proc].result()
                results.update({proc: result})
            except (psutil.NoSuchProcess, FileNotFoundError):
                continue

        converter.progress_bar0(results)

        return results

    def close(self):
        for line in self.query:
            if "proc" in line:
                proc = line["proc"]
                proc.terminate()
                proc.terminated = True

    def clean(self):
        for line in self.query:
            index = self.query.index(line)
            if index != 0:
                current = self.query[index-1]["current"]
                converter.remove_temp_dir(
                    current["file"], current["pattern_format"], current["frames"])


if __name__ == "__main__":
    pass
