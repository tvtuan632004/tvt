import sys, os
import pandas as pd
import json
DEFAULT_QUALITY_THRESHOLD = {
    'min_snr': 5,
    'min_ovrl': 2.5,
    'min_p808_mos': 3.0,
    'min_bak': float('-inf'),
    'min_sig': float('-inf'),
    'max_speaker': 1
}

def load_csv_data(csv_file):
    quality_data = {}
    csv_data = pd.read_csv(csv_file)
    row_index = csv_data.index
    for r_idx in row_index:
        file_id = csv_data.loc[r_idx, "id"]
        snr = csv_data.loc[r_idx, "snr"]
        ovrl = csv_data.loc[r_idx, "ovrl"]
        bak = csv_data.loc[r_idx, "bak"]
        sig = csv_data.loc[r_idx, "sig"]
        p808_mos = csv_data.loc[r_idx, "p808_mos"]
        speaker_numbers = csv_data.loc[r_idx, "speaker_numbers"]
        quality_data[file_id] = {
            'snr' : csv_data.loc[r_idx, "snr"],
            'ovrl' : csv_data.loc[r_idx, "ovrl"],
            'bak' : csv_data.loc[r_idx, "bak"],
            'sig' : csv_data.loc[r_idx, "sig"],
            'p808_mos' : csv_data.loc[r_idx, "p808_mos"],
            'speaker_num' : csv_data.loc[r_idx, "speaker_numbers"],
        }
    return quality_data

if __name__=='__main__':
    scp_file = sys.argv[1]
    csv_file = sys.argv[2]
    quality_threshold_file = sys.argv[3] if len(sys.argv) > 3 else None

    if quality_threshold_file is None:
        qualtiy_threshold = DEFAULT_QUALITY_THRESHOLD
        filter_name = 'default_threshold'
    else:
        with open(quality_threshold_file) as f:
            qualtiy_threshold = json.load(f)
        filter_name = os.path.splitext(os.path.basename(quality_threshold_file))[0]
    with open(scp_file) as f:
        scp_list = [scp.strip() for scp in f.readlines()]
    quality_data = load_csv_data(csv_file)
    remove_scp_list = []
    for file_id, sample_quality_data in quality_data.items():
        snr = sample_quality_data['snr']
        ovrl = sample_quality_data['ovrl']
        bak = sample_quality_data['bak']
        sig = sample_quality_data['sig']
        p808_mos = sample_quality_data['p808_mos']
        speaker_num = sample_quality_data['speaker_num']
    
        # Audio Quality Check:
        if snr < qualtiy_threshold['min_snr'] or sig < qualtiy_threshold['min_sig'] or bak < qualtiy_threshold['min_bak']:
            remove_scp_list.append(file_id)
            continue
        if ovrl < qualtiy_threshold['min_ovrl'] and p808_mos < qualtiy_threshold['min_p808_mos']:
            remove_scp_list.append(file_id)
            continue
        if speaker_num > qualtiy_threshold['max_speaker']:
            remove_scp_list.append(file_id)
            continue
    
    filtered_scp_file = os.path.join(os.path.dirname(scp_file), os.path.splitext(os.path.basename(scp_file))[0] + '.quality_' + filter_name + '_filtered.scp')
    with open(filtered_scp_file, 'w') as f:
        for scp in scp_list:
            if scp not in remove_scp_list:
                f.write(scp + '\n') 