import glob 
import wave, time
import tqdm, os

def get_wav_duration(file_path):
     with wave.open(file_path, 'rb') as wav_file:
          frames = wav_file.getnframes()
          frame_rate = wav_file.getframerate()
          duration = frames / float(frame_rate)
          return duration
     
if __name__ == "__main__":
     
     total_duration = 0
     MMSData = "/data/nhandt23/Dataset/MMSData_Television"
     for folder_video in tqdm.tqdm(glob.glob(MMSData + "/*")):
          
          meta_file_update = folder_video + "/asr_subtitle/metadata_update.csv"
          if os.path.isfile(meta_file_update):
             continue 
          
          meta_file = folder_video + "/asr_subtitle/metadata.csv"
          # remove_file = Dataset_dir + "/" + id + "/asr_subtitle/remove.csv"
          if os.path.isfile(meta_file):
               f = open(meta_file, "r", encoding="utf-8")
               scripts = f.read().splitlines()
               f.close()
               
               fw = open(folder_video + "/asr_subtitle/metadata_update.csv", "w+", encoding="utf-8")
               for script in scripts:
                    ids = script.split("|")[0]
                    wav_file = folder_video + "/asr_subtitle/wavs_enhanced/" + ids
                    duration = get_wav_duration(wav_file)
                    total_duration += duration
                    fw.write(script + "|" + str(duration) + "\n")
               fw.close()
               
     print(total_duration/3600)
                    
               