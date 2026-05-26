import speech_recognition as sr
import glob, tqdm, os, sys, wave, json, random
import tritonclient.grpc as grpcclient
import numpy as np
import time

sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')

from Wav2vec.inference import extract_audio, Wav2Vec

sys.path.append("vosk-api-asronly/python/example")
from vosk import Model, KaldiRecognizer, SetLogLevel

from multiprocessing import Pool
import multiprocessing




def google_tts(wav_file):
     recognizer = sr.Recognizer()
     with sr.AudioFile(wav_file) as source:
          audio = recognizer.record(source)
     try:
          text_vi = recognizer.recognize_google(audio, language="vi")
     except sr.UnknownValueError:
          text_vi = ""
     except sr.RequestError as e:
          text_vi = ""

     return text_vi

def w2v_tts(wav_file):
     w2v = Wav2Vec()
     audio_filename, audio_rate = extract_audio(wav_file)
     tts_w2v = w2v.inference(audio_filename)
     return tts_w2v

def kaldi_tts(wav_file):
     
     model_kaldi = Model("vosk-api-asronly/python/example/model")
     
     SetLogLevel(1)
     wf = wave.open(wav_file)
     if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
          print ("Audio file must be WAV format mono PCM.")
          exit (1)
     
     rec = KaldiRecognizer(model_kaldi, wf.getframerate())
     rec.SetWords(True)

     while True:
          data = wf.readframes(1600)
          if len(data) == 0:
               break
          rec.AcceptWaveform(data)

     return json.loads(rec.FinalResult())["text"]