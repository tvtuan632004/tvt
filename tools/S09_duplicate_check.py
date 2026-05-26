import os
import sys
from scipy.io import wavfile
import numpy as np
import hashlib



# https://vinbdi-slp.atlassian.net/wiki/spaces/Speech/pages/820150368/Doc+Ki+m+tra+tr+ng+l+p+d+li+u
wav_scp='list_file'
dup_fpath='dup_file'
check_sums = {}

with open(wav_scp,'r') as f:
     for line in f:
               fpath = line.strip()
               check_sum = hashlib.md5(open(fpath,'rb').read()).hexdigest()
               if check_sum in check_sums.keys():
                    check_sums[check_sum].append(fpath)
               else:
                    check_sums[check_sum] = [fpath,]

for key in check_sums.keys():
     if len(check_sums[key]) > 1:
               for fpath in check_sums[key]:
                    print("{} {}".format(key, fpath))
               print("\n-------------------------------\n")
               
               
               
# https://vinbdi-slp.atlassian.net/wiki/spaces/Speech/pages/767688759/Doc+Ki+m+tra+tr+ng+l+p+speaker