import requests

url = "http://10.124.68.83:8010/check_quality"

files = {'file_key': open('/data/nhandt23/Dataset/MMSData/_-cMExcUphc/asr_subtitle/wavs/_-cMExcUphc_02745.wav', 'rb')}

response = requests.post(url, files=files)

print(response.status_code)
print(response.text)