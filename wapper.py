#!/bin/python3

from converter import *
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


    #converter.set_temp_dir("C:\\temp\\test")
    converter.set_temp_dir(r"D:\temp")
    #converter("\\\\pve.lan\\mnt\\ytb\\【kradness＆れをる】 おこちゃま戦争 【歌ってみた】.mkv").ffmpeg_v2p().realcugan(scale=3).rife(output="C:\\temp\\test\\gg").run(sync=True)
    #file=r"C:\D\Hatsune Miku Project DIVA Arcade Future Tone M39S\mdata\MYSN\rom\movie\pv_869.mp4"
    out0=r"C:\D\Hatsune Miku Project DIVA Arcade Future Tone M39S\mdata\MZZZ\rom\movie\pv_268_001.mp4"
    #converter(file).ffmpeg_v2p().realcugan(j_threads="2:2:2").ffmpeg_p2v(out0,overwrite_output=True,**ffmpeg_args).run(sync=True)
    #converter("\\\\pve.lan\\mnt\\ytb\\【kradness＆れをる】 おこちゃま戦争 【歌ってみた】.mkv").ffmpeg_v2p().ffmpeg_p2v("Z:\\temp\test.mp4",**ffmpeg_args).run(sync=True)
    #converter(r"D:\temp\d76fbc18-a922-11ec-adc8-5c879c887e02",framerate=60).ffmpeg_p2v(out0,overwrite_output=True,**ffmpeg_args).run(sync=True)
    #converter(r"D:\temp\gg",framerate=59.94).ffmpeg_p2v("D:\temp\gg\pv_869_1s.mp4",overwrite_output=False,**ffmpeg_args).run(sync=True)
    converter(r"\\pve.lan\mnt\temp2\movie\pv_268_001.mp4").ffmpeg_v2p().realcugan(scale=2,j_threads="2:2:2",noise=0).ffmpeg_p2v(out0,overwrite_output=False,**ffmpeg_args).run(sync=True)