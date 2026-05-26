import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

def enhance_analysis():
     df_enhance = pd.read_csv('/home/nhandt23/Desktop/VCtube/NISQA/NISQA_results_enhance.csv')
     df = pd.read_csv('/home/nhandt23/Desktop/VCtube/NISQA/NISQA_results_all.csv')

     colors = "red"

     # Create a histogram
     plt.subplot(2, 2, 1)
     plt.hist(df['noi_pred'], bins=25, range=(0, 5), edgecolor='black', label ='Raw Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Noisiness', fontsize=12)
     plt.grid(True)

     plt.hist(df_enhance['noi_pred'], bins=25, range=(0, 5), edgecolor='black', color=colors, alpha=0.6, label ='Enhanced Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Noisiness', fontsize=12)
     plt.grid(True)

     plt.legend()

     # Create a histogram
     plt.subplot(2, 2, 2)
     plt.hist(df['dis_pred'], bins=25, range=(0, 5), edgecolor='black', label ='Raw Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Coloration', fontsize=12)
     plt.grid(True)

     plt.subplot(2, 2, 2)
     plt.hist(df_enhance['dis_pred'], bins=25, range=(0, 5), edgecolor='black', color=colors, alpha=0.6, label ='Enhanced Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Coloration', fontsize=12)
     plt.grid(True)

     plt.legend()

     # Create a histogram
     plt.subplot(2, 2, 3)
     plt.hist(df['col_pred'], bins=25, range=(0, 5), edgecolor='black', label ='Raw Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Discontinuity', fontsize=12)
     plt.grid(True)

     plt.subplot(2, 2, 3)
     plt.hist(df_enhance['col_pred'], bins=25, range=(0, 5), edgecolor='black', color=colors, alpha=0.6, label ='Enhanced Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Discontinuity', fontsize=12)
     plt.grid(True)

     plt.legend()

     # Create a histogram
     plt.subplot(2, 2, 4)
     plt.hist(df['loud_pred'], bins=25, range=(0, 5), edgecolor='black', label ='Raw Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Loudness', fontsize=12)
     plt.grid(True)

     plt.subplot(2, 2, 4)
     plt.hist(df_enhance['loud_pred'], bins=25, range=(0, 5), edgecolor='black', color=colors, alpha=0.6, label ='Enhanced Audio')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     plt.title('Loudness', fontsize=12)
     plt.grid(True)

     plt.legend()

     plt.show()
     
def model_analysis():
     df_tts = pd.read_csv('/home/nhandt23/Desktop/VCtube/NISQA/NISQA_results.csv')
     df = pd.read_csv('/home/nhandt23/Desktop/VCtube/NISQA/NISQA_results_all.csv')
     
     colors = "red"

     # Create a histogram
     plt.hist(df['mos_pred'], bins=50, range=(0, 5), edgecolor='black', label ='MOS General')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     
     plt.hist(df_tts['mos_pred'], bins=50, range=(0, 5), edgecolor='black', color=colors, alpha=0.6, label ='MOS Speech Synthesis')
     plt.xlabel('Value')
     plt.ylabel('Frequency')
     
     
     plt.title('MOS of NISQA Overall & Speech Synthesis', fontsize=12)
     plt.grid(True)
     
     plt.legend()
     plt.show()

if __name__ == "__main__":
     # model_analysis()
     enhance_analysis()