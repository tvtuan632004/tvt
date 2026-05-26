import glob, os

if __name__ == "__main__":
     
     # Dataset_dir = "/data/nhandt23/Dataset/MMSData"  
     Domain=""
     Dataset_dir = "/data/nhandt23/Dataset/MMSData" + Domain
     wav_folders = sorted(glob.glob(Dataset_dir + "/*/raw_audio_22k/*.wav"))
     
     print(len(wav_folders))
     
     for idx, fi in enumerate(wav_folders):
          
          if len(glob.glob(fi.split("/raw_audio_22k/")[0] + "/asr_subtitle/wavs/*")) > 0:
               print(fi)
               os.system("rm " + fi)