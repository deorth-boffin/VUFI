#!/bin/python3
import logging
import os
import click
from pprint import pprint
from converter import converter,ffmpeg
from ncnn_vulkan import *
import math


def list_video_file(dir,exts=("mkv","mp4","wmv")):
    for file in os.listdir(dir):
        if file.split(".")[-1] in exts:
            yield os.path.join(dir,file)

def get_res_fps(video_file):
    try:
        info=ffmpeg.probe(video_file)
        for stream in info['streams']:
            if stream['avg_frame_rate']!="0/0":
                fps_temp=stream['avg_frame_rate'].split("/")
                fps_temp[0]=int(fps_temp[0])
                fps_temp[1]=int(fps_temp[1])
                fps=fps_temp[0]/fps_temp[1]
                res=(stream["width"],stream["height"])

    except ffmpeg.Error:
            logging.critical("Incorrect video file %s"%video_file)
            raise ffmpeg.Error("Incorrect video file")
    try:
        return res,fps
    except UnboundLocalError:
        logging.critical("no video stream in file %s"%video_file)
        raise


@click.command(no_args_is_help=True,context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True))
@click.option("--input",'--in', type=click.Path(exists=True), help='input video file or forder',prompt=True)
@click.option("--refps", type=float, help='rearrange input video fps via ffmpeg',default=None,show_default=True)
@click.option("--output",'--out', type=click.Path(), help='output video file or forder',prompt=True)
@click.option("--temp-dir",'--temp', type=click.Path(exists=True),default=None, help='set temp dir for converter')
@click.option("--ffmpeg-bin", type=click.Path(exists=True),default=None, help='set ffmpeg binary path')
@click.option("--realcugan", type=click.Path(exists=True),default=None, help='set realcuga-ncnn-vulkan binary path')
@click.option("--realcugan-models", type=str,default="models-se", help='set realcuga-ncnn-vulkan models path',show_default=True)
@click.option("--noise-level", type=int,default=-1, help='set realcuga-ncnn-vulkan denoise level',show_default=True)
@click.option("--rife", type=click.Path(exists=True),default=None, help='set rife-ncnn-vulkan binary path')
@click.option("--rife-models", type=str,default="rife-anime", help='set rife-ncnn-vulkan models path',show_default=True)
@click.option("--gpu-id", type=str,default="auto", help='gpu device to use (-1=cpu) can be 0,1,2 for multi-gpu',show_default=True)
@click.option("--j-threads", type=str,default="1:2:2", help='thread count for load/proc/save, can be 1:2,2,2:2 for multi-gpu',show_default=True)
@click.option("--resolution",'--res', type=str, help='resolution for output video',default="3840x2160",show_default=True)
@click.option("--fps", type=float, help='fps (frames per second) for output video',default=60,show_default=True)
@click.option("--log-level", type=str, help='set log level',default="WARNING",show_default=True)
@click.option("--log-file", type=str, help='set log file instead of log to stderr',default=None)
@click.option('--yes', default=False,type=click.BOOL, is_flag=True,help='overwrite distination file',show_default=True)
@click.pass_context
def main(ctx,input,refps,output,temp_dir,ffmpeg_bin,realcugan,realcugan_models,noise_level,rife,rife_models,gpu_id,j_threads,resolution,fps,log_level,log_file,yes):
    """Combine realcugan rife and ffmpeg to upscale and frame interpolation for anime video in one command \n
    Any option not listed below will be passed to ffmpeg, if it's not a ffmpeg option, convertion will failed! 
    """
    LOG_FORMAT = "%(asctime)s.%(msecs)03d %(name)s: [%(levelname)s] %(pathname)s | %(message)s "
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S' 
    log_level=eval("logging.%s"%log_level.upper())
    logging.basicConfig(level=log_level,
                    format=LOG_FORMAT,
                    datefmt = DATE_FORMAT,
                    filename = log_file,
                    force = True)
    
    env_ffmpeg_args=os.getenv("FFMPEG_ARGS")
    if env_ffmpeg_args:
        env_ffmpeg_args=env_ffmpeg_args.split(" ")
    else:
        env_ffmpeg_args=[]
    ffmpeg_args={}
    args_list=env_ffmpeg_args+ctx.args
    for arg in env_ffmpeg_args+args_list:
        index=args_list.index(arg)
        if arg.startswith("-"):
            arg=arg.lstrip("-")
            if index==len(args_list)-1 or args_list[index+1].startswith("-"):
                ffmpeg_args.update({arg:""})
            else:
                ffmpeg_args.update({arg:args_list[index+1]})
    ffmpeg_args.update({"s":resolution})
    logging.debug("Get ffmpeg_args %s"%ffmpeg_args)

    target_res=resolution.split("x")
    target_res=int(target_res[0]),int(target_res[1])

    if os.path.isfile(input):
        input_files=[input]
    else:
        input_files=list_video_file(input)

    if temp_dir:
        converter.set_temp_dir(temp_dir)
    if realcugan:
        realcugan_ncnn_vulkan.set_binpath(realcugan)
    if rife:
        rife_ncnn_vulkan.set_binpath(rife)
    if ffmpeg_bin:
        converter.set_ffmpeg_cmd(ffmpeg_bin)
    


    for input_file in input_files:
        if os.path.isdir(output):
            basefile=os.path.basename(input_file)
            output_file=os.path.join(output,basefile)
        elif len(input_files)==1 and (os.path.isfile(output) or not os.path.exists(output)):
            output_file=output
        else:
            logging.critical("input: %s"%input)
            logging.critical("output: %s"%output)
            raise ValueError("input and output must be same type, both file or both dir!")

        input_res,input_fps=get_res_fps(input_file)
        if refps:
            input_fps=refps
        w_scale=target_res[0]/input_res[0]
        h_scale=target_res[1]/input_res[1]
        if w_scale!=h_scale:
            logging.WARNING("input %sx%s and output %s is not the same ratio, it might be a problem"%(input_res[0],input_res[1],resolution))
        res_scale=math.ceil((w_scale+h_scale)/2)
        time_scale=round(fps/input_fps)
        
        conv_obj=converter(input_file).ffmpeg_v2p(target_fps=refps)
        if res_scale in (2,3,4):
            conv_obj.realcugan(scale=res_scale,noise=noise_level,model=realcugan_models,gpu_id=gpu_id,j_threads=j_threads)
        elif res_scale in (5,6):
            conv_obj.realcugan(scale=6,noise=noise_level,model=realcugan_models,gpu_id=gpu_id,j_threads=j_threads)
        elif res_scale in (7,8):
            conv_obj.realcugan(scale=8,noise=noise_level,model=realcugan_models,gpu_id=gpu_id,j_threads=j_threads)
        elif res_scale==1:
            pass
        else:
            logging.WARNING("not support scale larger than 8, current scale %s, doing scale=8 anyway"%res_scale)
            conv_obj.realcugan(scale=8)
        
        #I need to know if rife support any other scale other than 2
        if time_scale>=2:
            conv_obj.rife(model=rife_models,gpu_id=gpu_id,j_threads=j_threads)

        conv_obj.ffmpeg_p2v(output=output_file,overwrite_output=yes,**ffmpeg_args).run()








if __name__=="__main__":
    main()