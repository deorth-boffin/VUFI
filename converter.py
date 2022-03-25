#!/bin/python3
import os,sys
import psutil
import time
import asyncio
import logging
sys.path.append("./ffmpeg-python")
import ffmpeg
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
        logging.debug("Existed png dir %s"%dir)
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
        logging.debug("current OS is windows")
    else:
        temp_dir="/tmp"
        logging.debug("current OS is None-windows")

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
                        logging.debug("cannot get frames from ffprobe, try calculate from duration, file %s"%file)
                        try:
                            time_str=stream["tags"]['DURATION']
                        except KeyError:
                            logging.critical("cannot get frames from ffprobe or calculate from duration, exiting, file %s"%file)
                            raise ValueError("Unsupported input video file")
                        time=time_str.split(":")
                        time=int(time[0])*3600+int(time[1])*60+float(time[2])
                        frames=math.ceil(time*fr_temp[0]/fr_temp[1])
        except ffmpeg.Error:
            logging.critical("Incorrect video file %s"%file)
            raise ffmpeg.Error("Incorrect video file")
        try:
            return frames,framerate
        except UnboundLocalError:
            logging.critical("no video stream in file %s"%file)
            raise

    @staticmethod
    def ffmpeg_get_progress(proc,logfile,total=None):
        start_time=psutil.Process(pid=proc.pid).create_time()
        if total==None:
            cmds=proc.args
            input=cmds[cmds.index("-i")+1]

            if input.endswith("png"):
                input_dir=os.path.dirname(input)
                total=converter.get_png_num(input_dir)
            else:
                total,fps=converter.get_videofile_frames(input)

        current=0
        speed=0
        logfile.seek(0)
        while True:
            line=logfile.readline()
            if line=="":
                break
            line=sub(r"= *",r"=",line)
            line=split("[ =]",line)
            if line[0]!='frame':
                continue
            try:
                current=int(line[1])
            except ValueError:
                current=0
            if current>total+1:
                logging.debug("impossable value current/total %s/%s, gonna retry"%(current,total))
                continue
            used_time=time.time()-start_time
            speed=current/used_time
            if speed==float(0):
                eta=0
            else:
                eta=(total-current)/speed

                
        
        try:
            return current,total,used_time,eta
        except UnboundLocalError:
            logging.debug("cannot get current framecount from stderr, returning defaults")
            return 0,total,time.time()-start_time,0 
    
    @staticmethod
    async def check_proc_progress(proc,total=None,logfile=None):
        cmd=proc.args[0]
        if "ffmpeg" in cmd:
            return converter.ffmpeg_get_progress(proc,logfile,total)
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
        logging.info("generated temp dir %s"%output)
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
            logging.debug("removed temp dir %s"%dir)
        except OSError:
            logging.warning("cannot remove temp dir %s because there are other files in it"%dir)

    @staticmethod
    def progress_bar0(current,total,time_used,eta):
        used_time_str=ncnn_vulkan.second2hour(time_used)
        eta_str=ncnn_vulkan.second2hour(eta)
        print("[%s/%s time used:%s ETA:%s]"%(current,total,used_time_str,eta_str),end="\r")


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
            self.current["framerate"]=target_fps
        if output==None:
            output=self.gen_temp_dir()

        logfilename=os.path.join(output,"stderr.log")
        logfile=open(logfilename,"w+",encoding="utf8")
        self.current["file"]=str(output)
        output_arg=os.path.join(output,self.gen_pattern_format())
        if target_fps==None:
            run_obj=ffmpeg.input(input).output(output_arg)
        else:
            run_obj=ffmpeg.input(input).filter("fps",fps=target_fps,round=round).output(output_arg)
            

        kwargs={
            "quiet":True,
            "pipe_stderr":logfile
            }
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
        logfilename=os.path.join(output,"stderr.log")
        logfile=open(logfilename,"w+",encoding="utf8")
        kwargs.update({"pipe_stderr":logfile})
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
        self.current["framerate"]=self.current["framerate"]*2
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
        logfilename=os.path.join(output,"stderr.log")
        logfile=open(logfilename,"w+",encoding="utf8")
        kwargs.update({"pipe_stderr":logfile})
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
        
        logfilename=os.path.join(self.temp_dir,"ffmpeg_p2v_stderr.log")
        logfile=open(logfilename,"w+",encoding="utf8")
        obj=ffmpeg.input(input,r=self.current["framerate"]).output(output,**ffmpeg_args)


        kwargs={
            "cmd":self.ffmpeg_cmd,
            "quiet":True,
            "overwrite_output":overwrite_output,
            "pipe_stderr":logfile
            }
        self.current["file"]=output
        self.current["pattern_format"]=None
        self.query.append({
            "obj":obj,
            "args":kwargs,
            "current":deepcopy(self.current)
        })
        return self

    def run(self,sync=False):#no async for now
        try:
                for line in self.query:
                    proc=line["obj"].run_async(**line["args"])
                    line.update({"proc":proc})
                    cmd=get_proc_cmd(proc)
                    while proc.poll()==None:
                        self.progress_bar(1)

                    if proc.returncode!=0:
                        logging.critical("ChildProcess Exiting abnormally, cmdline %s, returncode %s"%(cmd,proc.returncode))
                        logging.critical("You might want to check its stderr %s"%line["args"]["pipe_stderr"])
                        raise RuntimeError("subprocess exited none-zero return code %s"%proc.returncode)
                    else:
                        logging.info("ChildProcess Exiting Normally, cmdline %s"%cmd)
                        f=line["args"]["pipe_stderr"]
                        fname=f.name
                        f.close()
                        os.remove(fname)
                        logging.debug("removed ChildProcess stderr log %s"%f.name)
                    
                        index=self.query.index(line)
                        if index!=0:
                            current=self.query[index-1]["current"]
                            converter.remove_temp_dir(current["file"],current["frames"],current["pattern_format"])
        except:
            for line in self.query:
                if "proc" in line:
                    line["proc"].terminate()
            raise
                    




    def progress_bar(self,time=0):
        loop=asyncio.get_event_loop()
        tasks=[loop.create_task(asyncio.sleep(time))]
        results={}
        for line in self.query:
            if "proc" in line and line["proc"].returncode==None:
                kwargs={
                    "total":line["current"]["frames"],
                    "logfile":line["args"]["pipe_stderr"]
                }
                task=loop.create_task(
                        converter.check_proc_progress(line["proc"],**kwargs)
                        )
                tasks.append(task)
                results.update({line["proc"]:task})
        loop.run_until_complete(asyncio.wait(tasks))

        for proc in results:
            result=results[proc].result()
            results.update({proc:result})
            last_result=result
        converter.progress_bar0(*last_result)

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
    converter(r"/mnt/temp2/movie/pv_281.mp4").ffmpeg_v2p(target_fps=12).ffmpeg_p2v("/mnt/temp/test.mp4",overwrite_output=True).run(sync=True)