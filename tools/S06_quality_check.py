# -*- coding: utf-8 -*-
"""
@author: Gabriel Mittag, TU-Berlin
"""

import argparse, sys, glob
sys.path.append('NISQA')

from nisqa.NISQA_model import nisqaModel

def check_nisqa(wav_folder):
     args["pattern"] = wav_folder + "/*.wav"
     args['pattern'] = "/home/nhandt23/Desktop/bodi/asr_subtitle/test/*.wav"

     nisqa = nisqaModel(args)
     predict_files = nisqa.predict()
     
     predict_files = predict_files[ 
          (predict_files["mos_pred"]<2) &
          (predict_files["noi_pred"]<2) &
          (predict_files["dis_pred"]<2) &
          (predict_files["col_pred"]<2) & 
          (predict_files["loud_pred"]<2) ]
     
     return list(predict_files["file"])

if __name__ == "__main__":

     Domain=""
     Dataset_dir = "/data/nhandt23/Dataset/MMSData" + Domain
     
     wav_folders = sorted(glob.glob(Dataset_dir + "/MMSData/*/asr_subtitle/wavs_enhanced"))
     
     args = {}
     args['tr_bs_val'] = 1
     args['tr_num_workers'] = 16
     args['mode'] = 'predict_pattern'
     args['pretrained_model'] = 'NISQA/weights/nisqa.tar'
     args['ms_channel'] = 1
     args['output_dir'] = None

     for wav_folder in wav_folders:
          poor_audios = check_nisqa(wav_folder)
          
          print(poor_audios)
          break
          
     print("Finish for: ", Domain)































