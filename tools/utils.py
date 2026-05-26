from tqdm import tqdm
from multiprocessing import Pool
from contextlib import closing

def parallel_run(fn, items, desc="", parallel=True):
     results = []
     if parallel:
          with closing(Pool()) as pool:
               for out in tqdm(pool.imap_unordered(
                         fn, items), total=len(items), desc=desc):
                    if out is not None:
                         results.append(out)
     else:
          for item in tqdm(items, total=len(items), desc=desc):
               out = fn(item)
               if out is not None:
                    results.append(out)
     return results

import glob, os, time
from multiprocessing import Pool
import subprocess
from multiprocessing import Pool
import multiprocessing

def resample_rate(audio_path):
     # subprocess.run(['ffmpeg', '-i', audio_path, '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '22050', audio_path + '.tmp.wav'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
     os.system("sox -v 0.99 " + audio_path + " -r 22050 -c 1 -b 16 -t wav " + audio_path + '.tmp.wav')
     subprocess.run(["mkdir", os.path.dirname(audio_path).replace("raw_audio", "raw_audio_22k")])
     subprocess.run(["mv", audio_path + '.tmp.wav', audio_path.replace("raw_audio", "raw_audio_22k")])
     time.sleep(1)
     subprocess.run(["rm", audio_path])
     
def track_resample(Datadir):
     print(len(glob.glob(Datadir + "/MMSData/*/raw_audio_22k/*.wav")))

def time_to_minutes(time_str):
     time_parts = time_str.split(':')
     if len(time_parts) == 2:
          minutes, seconds = map(int, time_parts)
          total_minutes = minutes + seconds / 60
     elif len(time_parts) == 3:
          hours, minutes, seconds = map(int, time_parts)
          total_minutes = hours * 60 + minutes + seconds / 60
     else:
          raise ValueError("Invalid time format")
     return total_minutes

if __name__ == "__main__":
     
     Dataset_dir = "/data/nhandt23/Dataset"
     
     raw_files = glob.glob(Dataset_dir + "/MMSData/*/raw_audio/*.wav")

     with Pool(8) as p:
          p.map(resample_rate, raw_files)