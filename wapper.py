#!/bin/python3
import logging
LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)s] %(pathname)s | %(message)s "
DATE_FORMAT = '%Y-%m-%d %H:%M:%S' 
log_level=logging.DEBUG
logging.basicConfig(level=log_level,
                format=LOG_FORMAT,
                datefmt = DATE_FORMAT)
from converter import converter
from ncnn_vulkan import *

if __name__=="__main__":
    realcugan_ncnn_vulkan.set_binpath("D:\\Program Files\\realcugan-ncnn-vulkan\\realcugan-ncnn-vulkan.exe")
    rife_ncnn_vulkan.set_binpath("D:\\Program Files\\rife-ncnn-vulkan\\rife-ncnn-vulkan.exe")
    converter.set_time_interval(3)

    ffmpeg_args={
        "codec":"libx264",
        "pix_fmt":"yuv420p",
        "refs":0,
        "x264opts":"b-pyramid=0",
        "preset":"veryslow"
    }

    converter.set_temp_dir(r"D:\temp")
    out0=r"C:\D\Hatsune Miku Project DIVA Arcade Future Tone M39S\mdata\MZZZ\rom\movie\pv_268_001.mp4"
    converter(r"\\pve.lan\mnt\temp2\movie\pv_268_001.mp4").ffmpeg_v2p(target_fps=1).ffmpeg_p2v(r"d:\temp\test.mp4",overwrite_output=True,**ffmpeg_args).run(sync=True)