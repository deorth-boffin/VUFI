#!/bin/python3
import os,sys
import psutil
import time
import asyncio
sys.path.append("./ffmpeg-python")
import ffmpeg
from pprint import pprint
from ncnn_vulkan import *
import platform
from uuid import uuid1
import math
from re import split,sub
from copy import deepcopy


def touch(file_name):
       if os.path.exists(file_name):
           pass
       else:
              fid = open(file_name,'w')
              fid.close()

def multi_touch_png(dir,num,key="%05d.png"):
    try:
        os.mkdir(dir)
    except FileExistsError:
        pass
    for i in range(1,num+1):
        filename=os.path.join(dir,key%i)
        touch(filename)

def get_proc_cmd(proc):
    cmd=""
    for arg in proc.args:
        if " " in arg:
            cmd+="'%s' "%arg
        else:
            cmd+="%s "%arg
    return cmd


class converter():
    if platform.system()=="Windows":
        temp_dir=os.getenv('TEMP')
    else:
        temp_dir="/tmp"

    time_interval=5
    frames_interval=10
    ffmpeg_cmd="ffmpeg"

    @classmethod
    def set_temp_dir(cls,dir):
        cls.temp_dir=dir
    @classmethod
    def set_time_interval(cls,interval):
        cls.time_interval=interval
    @classmethod
    def set_frames_interval(cls,interval):
        cls.frames_interval=interval
    @classmethod
    def set_ffmpeg_cmd(cls,ffmpeg_cmd):
        cls.ffmpeg_cmd=ffmpeg_cmd

    @staticmethod
    def get_png_num(dir):
        num=0
        for file in os.listdir(dir):
            if file.endswith(".png"):
                try:
                    int(file.split(".")[0])
                except ValueError:
                    continue
                num+=1
        return num

    @staticmethod
    def get_videofile_frames(file):
        try:
            info=ffmpeg.probe(file)
            for stream in info['streams']:
                if stream['avg_frame_rate']!="0/0":
                    fr_temp=stream['avg_frame_rate'].split("/")
                    fr_temp[0]=int(fr_temp[0])
                    fr_temp[1]=int(fr_temp[1])
                    framerate=fr_temp[0]/fr_temp[1]
                    try:
                        frames=int(stream['nb_frames'])
                    except KeyError:
                        try:
                            time_str=stream["tags"]['DURATION']
                        except KeyError:
                            raise ValueError("Unsupported input video file")
                        time=time_str.split(":")
                        time=int(time[0])*3600+int(time[1])*60+float(time[2])
                        frames=math.ceil(time*fr_temp[0]/fr_temp[1])
        except ffmpeg.Error:
                raise ValueError("Incorrect video file")
        return frames,framerate

    @staticmethod
    def ffmpeg_get_progress(proc,total=None):
        if total==None:
            cmds=proc.args
            input=cmds[cmds.index("-i")+1]

            if input.endswith("png"):
                input_dir=os.path.dirname(input)
                total=converter.get_png_num(input_dir)
            else:
                total,fps=converter.get_videofile_frames(input)

        start_time=psutil.Process(pid=proc.pid).create_time()
        current=0
        speed=0
        while True:
            try:
                stderr=proc.stderr
                line=stderr.readline(100).decode().split("\r")[-1]
                if line=="":
                    current=total
                    eta=float(0)
                    break
                line=sub(r"= *",r"=",line)
                line=split("[ =]",line)
                current=int(line[1])
                if current>total*2:
                    continue
                speed=float(line[3])
                line[4]
                eta=(total-current)/speed
                break
            except (IndexError,ValueError,ZeroDivisionError):
                continue
        used_time=time.time()-start_time

        return current,total,used_time,eta
    
    @staticmethod
    async def check_proc_progress(proc,total=None):
        cmd=proc.args[0]
        if "ffmpeg" in cmd:
            return converter.ffmpeg_get_progress(proc,total)
        elif "realcugan-ncnn-vulkan" in cmd:
            return ncnn_vulkan.get_progress(proc,total=total)
        elif "rife-ncnn-vulkan" in cmd:
            return ncnn_vulkan.get_progress(proc,times=2,total=total)



    def __init__(self,input_file,framerate=None) -> None:
        self.current={
            "file":input_file,
            "frames":0,
            "framerate":framerate,
            "type":None,
            "pattern_format":None
            }
        if os.path.isdir(input_file) and type(framerate) in (int,float):
            self.current["frames"]=converter.get_png_num(input_file)
            self.current["type"]="dirpngs"
            for file in os.listdir(input_file):
                if file.endswith(".png"):
                    filename=file
            num=len(filename)-4
            self.current["pattern_format"]="%0"+str(num)+"d.png"

        elif os.path.isfile(input_file):
            self.current["type"]="videofile"
            self.current["frames"],self.current["framerate"]=converter.get_videofile_frames(input_file)
        else:
            raise ValueError("Unsupported input type")
        self.query=[]

    def gen_temp_dir(self,key=None):
        dirstr=str(uuid1())
        output=os.path.join(self.temp_dir,dirstr)
        if key==None and self.current["pattern_format"]==None:
            key=self.gen_pattern_format()
        elif key==None:
            key=self.current["pattern_format"]
        multi_touch_png(output,self.current["frames"],key=key)
        return output
    @staticmethod
    def remove_temp_dir(dir,num,key):
        for i in range(1,num+1):
            filename=key%i
            full_filename=os.path.join(dir,filename)
            try:
                os.remove(full_filename)
            except FileNotFoundError:
                pass
        try:
            os.rmdir(dir)
        except OSError:
            pass

    def gen_pattern_format(self):
        file_length=math.ceil(math.log(self.current["frames"],10))
        key="%0"+str(file_length)+"d"
        self.current["pattern_format"]=key+".png"
        return key+".png"

    def ffmpeg_v2p(self,input=None,output=None,target_fps=None,round="up"):
        if input==None:
            input=self.current["file"]
        if target_fps!=None:
            self.current["frames"]=math.ceil(self.current["frames"]*target_fps/self.current["framerate"])
            #self.current["frames"]=round(self.current["frames"]*target_fps/self.current["framerate"])
            self.current["framerate"]=target_fps
        if output==None:
            output=self.gen_temp_dir()

        self.current["file"]=str(output)
        output_arg=os.path.join(output,self.gen_pattern_format())
        if target_fps==None:
            run_obj=ffmpeg.input(input).output(output_arg)
        else:
            run_obj=ffmpeg.input(input).filter("fps",fps=target_fps,round=round).output(output_arg)
            

        kwargs={
            "quiet":True}
        self.query.append({
            "obj":run_obj,
            "args":kwargs,
            "current":deepcopy(self.current)
        })
        return self



    def realcugan(self,input=None,output=None,scale=2,noise=-1,model="models-se",j_threads="1:1:1"):
        kwargs=locals()
        kwargs.pop("self")
        if input==None:
            input=self.current["file"]
            kwargs.update({"input":input})
        if output==None:
            output=self.gen_temp_dir()
            kwargs.update({"output":output})
            self.current["file"]=str(output)
        else:
            multi_touch_png(output,num=self.current["frames"],key=self.current["pattern_format"])

        obj=realcugan_ncnn_vulkan()
        self.query.append({
            "obj":obj,
            "args":kwargs,
            "current":deepcopy(self.current)
        })
        return self

    def rife(self,input=None,output=None,model="rife-anime",j_threads="1:1:1",f_pattern_format=None):
        kwargs=locals()
        kwargs.pop("self")

        self.current["frames"]=self.current["frames"]*2
        self.current["framerate"]=self.current["framerate"]*2-1
        self.gen_pattern_format()

        if input==None:
            input=self.current["file"]
            kwargs.update({"input":input})
        
        if output==None:
            output=self.gen_temp_dir()
            kwargs.update({"output":output})
            self.current["file"]=str(output)
        
        if f_pattern_format==None:
            multi_touch_png(output,self.current["frames"],self.current["pattern_format"])
            kwargs.update({"f_pattern_format":self.current["pattern_format"]})
        else:
            self.current["pattern_format"]=f_pattern_format

        obj=rife_ncnn_vulkan()
        self.query.append({
            "obj":obj,
            "args":kwargs,
            "current":deepcopy(self.current)
        })
        return self

    def ffmpeg_p2v(self,output,input=None,overwrite_output=False,**ffmpeg_args):
        if os.path.exists(output) and not overwrite_output:
            raise ValueError("output file exists, not overwriting. you can use overwrite_output=True to override this")
        if input==None:
            input=os.path.join(self.current["file"],self.current["pattern_format"])
        #ffmpeg_args.update({"r":self.current["framerate"]})
        obj=ffmpeg.input(input,r=self.current["framerate"]).output(output,**ffmpeg_args)
        kwargs={
            "cmd":self.ffmpeg_cmd,
            "quiet":True,
            "overwrite_output":overwrite_output
            }
        self.current["file"]=output
        self.current["pattern_format"]=None
        self.query.append({
            "obj":obj,
            "args":kwargs,
            "current":deepcopy(self.current)
        })
        return self

    def run(self,sync=False):

        try:
            if sync:
                for line in self.query:
                    proc=line["obj"].run_async(**line["args"])
                    line.update({"proc":proc})
                    cmd=get_proc_cmd(proc)
                    while proc.poll()==None:
                        print(self.progress_bar(1))

                    if proc.returncode!=0:
                        print(cmd)
                        raise RuntimeError("subprocess exited none-zero return code %s"%proc.returncode)

                    index=self.query.index(line)
                    if index!=0:
                        current=self.query[index-1]["current"]
                        converter.remove_temp_dir(current["file"],current["frames"],current["pattern_format"])
                    

                return

                
            for line in self.query:
                proc=line["obj"].run_async(**line["args"])
                line.update({"proc":proc})
                if self.query.index(line)!=len(self.query)-1:
                    time.sleep(self.time_interval)
                    print(self.progress_bar())

            while True:
                print(self.progress_bar())

        except:
            for line in self.query:
                if "proc" in line:
                    line["proc"].terminate()
                if line!=self.query[-1]:
                    current=line["current"]
                    converter.remove_temp_dir(current["file"],current["frames"],current["pattern_format"])
            raise



    def progress_bar(self,time=0):
        loop=asyncio.get_event_loop()
        tasks=[loop.create_task(asyncio.sleep(time))]
        for line in self.query:
            if "proc" in line and line["proc"].returncode==None:
                total=line["current"]["frames"]
                tasks.append(
                    loop.create_task(
                        converter.check_proc_progress(line["proc"],total=total)
                        )
                    )
        loop.run_until_complete(asyncio.wait(tasks))
        results=[task.result() for task in tasks]
        results.remove(None)
        return results










        



if __name__=="__main__":
    realcugan_ncnn_vulkan.set_binpath("/root/realcugan-ncnn-vulkan/realcugan-ncnn-vulkan")
    converter.set_time_interval(0)
    converter.set_temp_dir("/mnt/temp")
    ffmpeg_args={
        "codec":"libx264",
        "pix_fmt":"yuv420p",
        "refs":0,
        "x264opts":"b-pyramid=0",
        "preset":"veryslow"
    }
    converter(r"/mnt/temp2/movie/pv_281.mp4").ffmpeg_v2p(target_fps=0.1).realcugan().rife().ffmpeg_p2v("/mnt/temp/test.mp4",overwrite_output=True).run(sync=True)