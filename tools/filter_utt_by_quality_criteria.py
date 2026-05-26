import sys, os
sys.path.append('../')
import concurrent.futures
import multiprocessing
import tqdm
import traceback
from quality_measurement.DNSMOS.dnsmos_local import ComputeScore
from S06_quality_measurement import compute_score, SAMPLING_RATE
from inaSpeechSegmenter import Segmenter

QUALITY_THRESHOLD = {
    'min_snr': 5,
    'min_ovrl': 3.0,
    'min_p808_mos': 3.5,
    'min_bak': float('-inf'),
    'min_sig': float('-inf'),
    'max_speaker': 1
}

VALID_SPEECH_LABELS = ["speech", "male", "female"]
def is_contain_speech(classes):
    for speech_class in classes:
        if speech_class in VALID_SPEECH_LABELS:
            return True
    return False

def cal_speaker_num(pipeline, audio_path):
    diarization = pipeline(audio_path)
    speakers = set()
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        # print(f"start={turn.start:.1f}s stop={turn.end:.1f}s speaker_{speaker}")
        speakers.add(speaker)
    filename = os.path.splitext(
                        os.path.basename(audio_path))[0]
    return filename, len(speakers)
def get_speech_class(segmentation, audio_path):
    worker_id = multiprocessing.current_process().pid
    time_stamps = segmentation(audio_path)
    filename = os.path.splitext(os.path.basename(audio_path))[0]
    classes = []
    for segment_class, start_time, end_time in time_stamps:
        classes.append(segment_class)
    return filename, classes

if __name__=='__main__':
    scp_file = sys.argv[1]
    wav_dir = sys.argv[2]
    n_cpus = os.cpu_count()
    num_worker =  int(sys.argv[3]) if len(sys.argv) > 3 else int(n_cpus/2)
    with open(scp_file) as f:
        scp_list = [scp.strip() for scp in f.readlines()]
    audio_files = [os.path.join(wav_dir, scp + '.wav') for scp in scp_list if os.path.isfile(os.path.join(wav_dir, scp + '.wav'))]
    quality_data = {}
    segmentation = Segmenter(vad_engine="smn",  detect_gender=False, batch_size=16, energy_ratio=0.03)
    print('Estimate Speech Classes: Speech, Noises, Music with number worker: {}'.format(num_worker))
    for audio_path in tqdm.tqdm(audio_files):
        speech_classes = get_speech_class(segmentation, audio_path)
        sample_id = speech_classes[0]
        if sample_id not in quality_data:
            quality_data[sample_id] = {}
        quality_data[sample_id]['classes'] = speech_classes[1]
    del segmentation
    PYANNOTE_MODEL_PATH='/data/work/models/pretrain_models/pyannote'
    model_path = '../quality_measurement/DNSMOS/DNSMOS/sig_bak_ovr.onnx'
    p808_model_path = '../quality_measurement/DNSMOS/DNSMOS/model_v8.onnx'
    dnsmos_model = ComputeScore(model_path, p808_model_path)
    print('Estimate Speech Audio Quality')
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_worker) as executor:
            future_to_url = {executor.submit(compute_score, dnsmos_model, audio_path,
                                             SAMPLING_RATE, False): audio_path for audio_path in audio_files}
            for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_url)):
                clip = future_to_url[future]
                try:
                    quality_dict = future.result()
                except Exception as exc:
                    active_childs = multiprocessing.active_children()
                    for child in active_childs:
                        child.terminate()
                    raise Exception(
                        '%r generated an exception: %s' % (clip, exc))
                except KeyboardInterrupt:
                    active_childs = multiprocessing.active_children()
                    for child in active_childs:
                        child.terminate()
                    raise Exception('keyboard interrupt')
                else:
                    # rows.append(data)
                    segment_id = os.path.splitext(
                        os.path.basename(quality_dict['filename']))[0]
                    quality_index = {
                        'snr': quality_dict['snr'],
                        'ovrl': quality_dict['OVRL'],
                        'bak': quality_dict['BAK'],
                        'sig': quality_dict['SIG'],
                        'p808_mos': quality_dict['P808_MOS']
                    }
                    quality_data[segment_id] = quality_index
    os.environ['PYANNOTE_CACHE'] = PYANNOTE_MODEL_PATH
    from pyannote.audio import Pipeline
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
    print('Estimate Speaker Number per Audio')
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_worker) as executor:
            future_to_url = {executor.submit(cal_speaker_num, pipeline, audio_path): audio_path for audio_path in audio_files}
            for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_url)):
                clip = future_to_url[future]
                try:
                    speaker_num_data = future.result()
                except Exception as exc:
                    active_childs = multiprocessing.active_children()
                    for child in active_childs:
                        child.terminate()
                    raise Exception(
                        '%r generated an exception: %s' % (clip, exc))
                except KeyboardInterrupt:
                    active_childs = multiprocessing.active_children()
                    for child in active_childs:
                        child.terminate()
                    raise Exception('keyboard interrupt')
                else:
                    # rows.append(data)
                    quality_data[speaker_num_data[0]]['speaker_num'] = speaker_num_data[1]
    
    print('Clear model to free memory')
    del dnsmos_model
    del pipeline
    
        # future_to_url = {executor.submit(get_speech_class, audio_path): audio_path for audio_path in audio_files}
        # for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_url)):
        #     clip = future_to_url[future]
        #     try:
        #         speech_classes = future.result()
        #     except Exception as exc:
        #         active_childs = multiprocessing.active_children()
        #         for child in active_childs:
        #             child.terminate()
        #         raise Exception(
        #             '%r generated an exception: %s' % (clip, exc))
        #     except KeyboardInterrupt:
        #         active_childs = multiprocessing.active_children()
        #         for child in active_childs:
        #             child.terminate()
        #         raise Exception('keyboard interrupt')
        #     else:
        #         # rows.append(data)
        #         quality_data[speech_classes[0]]['classes'] = speech_classes[1]

    quality_data_file = os.path.join(os.path.dirname(scp_file), os.path.splitext(os.path.basename(scp_file))[0] + '.quality_data.csv')
    filtered_scp_file = os.path.join(os.path.dirname(scp_file), os.path.splitext(os.path.basename(scp_file))[0] + '.quality_filtered.scp')
    csv_delimiter = ','
    print('SELECT DATA')
    remove_scp_list = []
    with open(quality_data_file, 'w') as fqa:
        fqa.write(csv_delimiter.join(['id', 'snr', 'ovrl', 'bak', 'sig', 'p808_mos', 'speaker_numbers', 'speech class']) + '\n')
        for file_id, sample_quality_data in quality_data.items():
            snr = sample_quality_data['snr']
            ovrl = sample_quality_data['ovrl']
            bak = sample_quality_data['bak']
            sig = sample_quality_data['sig']
            p808_mos = sample_quality_data['p808_mos']
            speaker_num = sample_quality_data['speaker_num']
            sample_speech_classes = sample_quality_data['classes']
            fqa.write(csv_delimiter.join([file_id, str(snr), str(ovrl), str(bak), str(sig), str(p808_mos), str(speaker_num), ' '.join(sample_speech_classes)]) + '\n')

            # Audio Quality Check:
            if snr < QUALITY_THRESHOLD['min_snr'] or sig < QUALITY_THRESHOLD['min_sig'] or bak < QUALITY_THRESHOLD['min_bak']:
                remove_scp_list.append(file_id)
                continue
            if ovrl < QUALITY_THRESHOLD['min_ovrl'] and p808_mos < QUALITY_THRESHOLD['min_p808_mos']:
                remove_scp_list.append(file_id)
                continue
            if speaker_num > 1:
                remove_scp_list.append(file_id)
                continue
            if not is_contain_speech(sample_speech_classes):
                remove_scp_list.append(file_id)
                continue
            elif "music" in sample_speech_classes or "noise" in sample_speech_classes:
                remove_scp_list.append(file_id)
                continue
    with open(filtered_scp_file, 'w') as f:
        for scp in scp_list:
            if scp not in remove_scp_list:
                f.write(scp + '\n') 
    print('quality_data_file: {}'.format(quality_data_file))
    print('filtered_scp_file: {}'.format(filtered_scp_file))
    print('DONE!')
