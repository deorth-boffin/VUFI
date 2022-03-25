#!/bin/python3
import os
import subprocess
import psutil
import time
import asyncio



class ncnn_vulkan():

    def __init__(self) -> None:
        pass

    @classmethod
    def set_binpath(cls,binpath):
        cls.binpath=binpath

    @staticmethod
    def second2hour(input_second):
        input_second=int(input_second)
        second=input_second%60
        minute=input_second//60%60
        hour=input_second//3600
        return "%d:%02d:%02d"%(hour,minute,second)

    @staticmethod
    def progress_bar(proc,times=1,interval=1):
        while proc.poll()==None:
            co=asyncio.sleep(interval)
            current,total,used_time,eta=ncnn_vulkan.get_progress(proc,times)
            used_time_str=ncnn_vulkan.second2hour(used_time)
            eta_str=ncnn_vulkan.second2hour(eta)
            print("%s/%s time used:%s eta:%s"%(current,total,used_time_str,eta_str),end="\r")

            loop = asyncio.get_event_loop()
            loop.run_until_complete(co)
            
        
        if proc.poll()!=0:
            cmds=proc.args
            print(cmds)

    @staticmethod
    def get_progress(proc,times=1,total=None):
        psProcess=psutil.Process(pid=proc.pid)
        cmds=proc.args
        indir=cmds[cmds.index("-i")+1]
        if total==None:
            total=len(os.listdir(indir))*times

        outdir=cmds[cmds.index("-o")+1]
        start_time=psProcess.create_time()


        #loop=asyncio.get_event_loop()
        tasks=[]
        for file in os.listdir(outdir):
            ffile=os.path.join(outdir,file)
            tasks.append((ncnn_vulkan.get_if_file_changes(ffile,start_time)))

        current=tasks.count(True)

        used_time=time.time()-start_time
        speed=current/used_time
        if speed!=0:
            eta=(total-current)/speed
        else:
            eta=0
        return current,total,used_time,eta
    
    @staticmethod
    def get_if_file_changes(file,start_time):
        filetime=os.path.getmtime(file)
        return filetime>=start_time


    def run(self,**kwargs):
        pp=self.run_async(**kwargs)
        try:
            ncnn_vulkan.progress_bar(pp)
        except:
            pp.terminate()
            raise


    def run_async(self,**kwargs):
        cmd=[self.binpath]
        for arg in kwargs:
            cmd.append("-%s"%arg[0])
            cmd.append(str(kwargs[arg]))
        return subprocess.Popen(cmd,stderr=subprocess.DEVNULL,stdout=subprocess.DEVNULL)


class realcugan_ncnn_vulkan(ncnn_vulkan):
    binpath="realcugan-ncnn-vulkan"
    
class rife_ncnn_vulkan(ncnn_vulkan):
    binpath="rife-ncnn-vulkan"
    def run(self,**kwargs):
        pp=self.run_async(**kwargs)
        try:
            super().progress_bar(pp,times=2)
        except:
            pp.terminate()
            raise



if __name__=="__main__":
    #realcugan_ncnn_vulkan.set_binpath("D:\\Program Files\\realcugan-ncnn-vulkan\\realcugan-ncnn-vulkan.exe")
    #realcugan_ncnn_vulkan().run(input="Z:\\279_2",output="Z:\\temp")
    #rife_ncnn_vulkan.set_binpath("D:\\Program Files\\rife-ncnn-vulkan\\rife-ncnn-vulkan.exe")
    #rife_ncnn_vulkan().run(input="Z:\\279_2",output="Z:\\279_3")
    realcugan_ncnn_vulkan.set_binpath("/root/realcugan-ncnn-vulkan/realcugan-ncnn-vulkan")
    realcugan_ncnn_vulkan().run(input="/mnt/ytb/111",output="/mnt/temp",scale=3)