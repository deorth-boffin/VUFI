#!/bin/python3
from curses import KEY_B2
import os,sys
import click
from ffmpeg import probe
from pprint import pprint


def list_video_file(dir,exts=("mkv","mp4","wmv")):
    for file in os.listdir(dir):
        if file.split(".")[-1] in exts:
            yield os.path.join(dir,file)

@click.command(no_args_is_help=True,context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True))
@click.option("--input",'--in', type=str, help='input video file or forder',prompt=True,)
@click.option("--output",'--out', type=str, help='output video file or forder',prompt=True)
@click.option("--resolution",'--res', type=str, help='resolution for output video',default="3840x2160",show_default=True)
@click.option("--fps", type=float, help='fps (frames per second) for output video',default=60,show_default=True)
@click.option('--yes', default=False,type=click.BOOL, is_flag=True,help='overwrite distination file',show_default=True)
@click.pass_context
#@click.echo("any other option will be passed to ffmpeg, if it's not a ffmpeg option, convertion will failed! ")
def main(ctx,input,output,resolution,fps,yes):
    """Combine realcugan rife and ffmpeg to upscale and frame interpolation for anime video in one command \n
    any option not listed below will be passed to ffmpeg, if it's not a ffmpeg option, convertion will failed! 
    """
    ffmpeg_args={}
    for arg in ctx.args:
        index=ctx.args.index(arg)
        if arg.startswith("-"):
            if index==len(ctx.args)-1 or ctx.args[index+1].startswith("-"):
                ffmpeg_args.update({arg:""})
            else:
                ffmpeg_args.update({arg:ctx.args[index+1]})
    
    pprint(ffmpeg_args)
    if os.path.isfile:
        input_files=[input]
    else:
        input_files=list_video_file(input)
    for file in input_files:
        pass





if __name__=="__main__":
    main()