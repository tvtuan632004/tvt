import glob 
import wave
import subprocess, os, tqdm
from multiprocessing import Pool
import multiprocessing
from S10_data_analysis import validate_video

def upload_video(arg):
     
     Dataset_dir, video_folder, server_ip, server_address = arg
     print("=============================== Upload for: ", video_folder)
     os.system("rsync -avz --no-o --no-g " + Dataset_dir + "/" + video_folder + " " + server_ip + ":" + server_address)
          
def get_uploaded_id(server_ip, server_address):
     find_command = f"find {server_address} -type f -name '*.wav'"
     ssh_command = f"ssh {server_ip} {find_command} "

     output = subprocess.check_output(ssh_command, shell=True, text=True)

     # Split the output into lines to get individual folder names
     folder_list = output.strip().split('\n')
     video_id = [i.split("/")[-3] for i in folder_list if i != ""]
     return video_id

def remove_interupt_upload(server_ip, server_address, videos_uploaded):
     output = subprocess.check_output(f"ssh {server_ip} ls {server_address}", shell=True, text=True)
     folder_list = output.strip().split('\n')
     all_video = [i.split("/")[-1] for i in folder_list if i != ""]
     
     videos_for_remove = [i for i in all_video if i not in videos_uploaded]
     
     print("Remove Interupt: ", len(videos_for_remove))
     
     for fi in videos_for_remove:
          os.system("ssh " + server_ip + " rm -r " + server_address + "/" +fi)

def remove_video(Dataset_dir, video_folders):
     for video_folder in video_folders:
          os.system("rm -r " + Dataset_dir + "/" + video_folder)
          
if __name__ == "__main__":
     
     Dataset_dir = "/data/nhandt23/Dataset/MMSData"
     server_ip = "HPC3"
     server_address = "/data1/3P/speechData/rawData/TTSMMS/MMSData"
     
     ################# Server
     videos_uploaded = get_uploaded_id(server_ip, server_address)
     print("Number uploaded / server: ", len(videos_uploaded))
     ################# Remove interupt upload
     remove_interupt_upload(server_ip, server_address, videos_uploaded)
     
     ################# Local
     valid_folders, invalid_folders = validate_video(Dataset_dir)
     valid_folders = sorted(valid_folders)
     
     ################# Sync
     
     videos_for_upload = [i for i in valid_folders if i not in videos_uploaded]
     print("Number video for upload: ", len(videos_for_upload))
     
     input = [(Dataset_dir, video, server_ip, server_address) for video in videos_for_upload]
     with Pool(4) as p:
          p.map(upload_video, input)
     
     