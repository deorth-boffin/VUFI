#!/bin/python3
from cmath import log
from concurrent.futures import process
import os,sys
import psutil
import time
import asyncio
import logging
from ncnn_vulkan import *
from uuid import uuid1
import math
from re import split,sub
from copy import deepcopy

import importlib.util
MODULE_PATH = os.path.join(os.path.dirname(__file__),"ffmpeg-python","ffmpeg","__init__.py")
MODULE_NAME = "ffmpeg"
spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
ffmpeg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ffmpeg 
spec.loader.exec_module(ffmpeg)


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
    if sys.platform=="win32":
        temp_dir=os.getenv('TEMP')
        logging.debug("current OS is windows")
    else:
        temp_dir="/tmp"
        logging.debug("current OS is None-windows")

    time_interval=5
    frames_interval=200
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
                            if "duration" in stream:
                                time=float(stream["duration"])
                            else:
                                time_str=stream["tags"]['DURATION']
                                time=time_str.split(":")
                                time=int(time[0])*3600+int(time[1])*60+float(time[2])
                        except KeyError:
                            logging.critical("cannot get frames from ffprobe or calculate from duration, exiting, file %s"%file)
                            raise ValueError("Unsupported input video file")
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
    def progress_bar0(results):
        out_str=""
        for proc in results:
            current,total,time_used,eta=results[proc]
            used_time_str=ncnn_vulkan.second2hour(time_used)
            eta_str=ncnn_vulkan.second2hour(eta)
            name=os.path.basename(proc.args[0]).split("-")[0]
            out_str+="[%s %s/%s time used:%s ETA:%s]"%(name,current,total,used_time_str,eta_str)
        print("\r%s  "%out_str,end="")


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
            "cmd":self.ffmpeg_cmd,
            "quiet":True,
            "pipe_stderr":logfile
            }
        self.query.append({
            "obj":run_obj,
            "args":kwargs,
            "current":deepcopy(self.current)
        })
        return self



    def realcugan(self,input=None,output=None,scale=2,noise=-1,model="models-se",j_threads="1:1:1",gpu_id="auto"):
        kwargs=locals()
        if scale in (2,3,4):
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
        elif scale in (6,8):
            self.realcugan(input=input,output=None,scale=int(scale/2),noise=noise,model=model,j_threads=j_threads,gpu_id=gpu_id)
            self.realcugan(input=None,output=output,scale=2,noise=noise,model=model,j_threads=j_threads,gpu_id=gpu_id)
        else:
            logging.error("not supported scale %s, didn't do anything"%scale)
        return self

    def rife(self,input=None,output=None,model="rife-anime",j_threads="1:2:2",f_pattern_format=None,gpu_id="auto"):
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
            logging.error("output file %s a exists, not overwriting. you can use overwrite_output=True to override this"%output)
            raise ValueError("output file %s a exists, not overwriting. you can use overwrite_output=True to override this"%output)
        if input==None:
            input=os.path.join(self.current["file"],self.current["pattern_format"])
        
        logname=os.path.basename(output).replace(".","_")+"_ffmpeg_p2v_stderr.log"
        logfilename=os.path.join(self.temp_dir,logname)
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

    def run(self,sync=True):#no async for now
        try:
            if sync:
                for line in self.query:
                    proc=line["obj"].run_async(**line["args"])
                    line.update({"proc":proc})
                    cmd=get_proc_cmd(proc)
                    logging.debug("ChildProcess Started, cmdline %s, pid %s, log %s"%(cmd,proc.pid,line["args"]["pipe_stderr"].name))
                    while proc.poll()==None:
                        self.progress_bar(1)

                    if proc.returncode!=0:
                        logging.critical("ChildProcess Exiting abnormally, cmdline %s, returncode %s"%(cmd,proc.returncode))
                        logging.critical("You might want to check its stderr %s"%line["args"]["pipe_stderr"].name)
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
            else:
                flag=False
                for line in self.query:
                    proc=line["obj"].run_async(**line["args"])
                    line.update({"proc":proc})
                    cmd=get_proc_cmd(proc)
                    logging.debug("ChildProcess Started, cmdline %s, pid %s, log %s"%(cmd,proc.pid,line["args"]["pipe_stderr"].name))

                    if flag:
                        if sys.platform=="win32":
                            psutil.Process(proc.pid).nice(psutil.IDLE_PRIORITY_CLASS)
                        else:
                            psutil.Process(proc.pid).nice(-20)
                        flag=False
                    else:
                        if sys.platform=="win32":
                            psutil.Process(proc.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                        else:
                            psutil.Process(proc.pid).nice(-10)

                
                    results=self.progress_bar(0)
                    while proc.returncode==None and (results[proc][2]<self.time_interval or results[proc][0]<self.frames_interval):
                        results=self.progress_bar(1)
                        self.progress_contorl(results)

    
                while True:
                    results=self.progress_bar(1)
                    self.progress_contorl(results)
                    polls=[proc.returncode for proc in results.keys()]
                    if not None in polls:
                        break




        except:
            for line in self.query:
                if "proc" in line:
                    line["proc"].terminate()
            raise
                    

    def progress_contorl(self,results):
        procs=list(results.keys())
        procs_num=len(procs)
        for index in range(1,procs_num):
            proc=procs[index]
            proc_former=procs[index-1]
            if proc.returncode==None:
                p=psutil.Process(pid=proc.pid)
                status=p.status()
                if status=="running" and results[proc][0] > results[proc_former][0]+self.frames_interval:
                    p.suspend()
                    status=p.status()
                    logging.debug("paused process pid %s"%proc.pid)
                elif status=="sleeping" and results[proc][0] <= results[proc_former][0]+self.frames_interval:
                    p.resume()
                    status=p.status()
                    logging.debug("resumed process pid %s"%proc.pid)


    def progress_bar(self,time=0):
        loop=asyncio.get_event_loop()
        tasks=[loop.create_task(asyncio.sleep(time))]
        results={}
        for line in self.query:
            if "proc" in line and line["proc"].poll()==None:
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

        converter.progress_bar0(results)

        return results







        



if __name__=="__main__":
    try:
        os.remove("/mnt/temp/test.log")
    except FileNotFoundError:
        pass
    LOG_FORMAT = "%(asctime)s.%(msecs)03d %(name)s: [%(levelname)s] %(pathname)s | %(message)s "
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S' 
    log_level=logging.DEBUG
    logging.basicConfig(level=log_level,
                    format=LOG_FORMAT,
                    datefmt = DATE_FORMAT,
                    force=True,
                    filename="/mnt/temp/test.log")
    converter.set_time_interval(3)
    realcugan_ncnn_vulkan.set_binpath("/root/realcugan-ncnn-vulkan/realcugan-ncnn-vulkan")
    converter.set_temp_dir("/mnt/temp")
    ffmpeg_args={
        "codec":"libx264",
        "pix_fmt":"yuv420p",
        "refs":0,
        "x264opts":"b-pyramid=0",
        "preset":"veryslow"
    }
    input_file="/mnt/ytb/Wall-E explained by an idiot.mkv"
    #input_file=r"/mnt/temp2/movie/pv_277.mp4"
    converter(input_file).ffmpeg_v2p(target_fps=12).ffmpeg_p2v("/mnt/temp/test.mp4",overwrite_output=True).run(sync=False)