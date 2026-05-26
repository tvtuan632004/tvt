#!/bin/bash

# Domain=Sitcom
# keywords="sitcom Gia đình là số 1"

Domain=$1
keywords=$2
video_limit=$3
channel_limit=$4
mms_data_dir=$5

lang="vi" 
region="VN"

pwd=$PWD

asset_folder=$mms_data_dir"/MMSData"$Domain/asset

if [ -f "$keywords" ]; then
    cp "$keywords" "$asset_folder/keywords.txt"
else
    echo "$keywords" > $asset_folder/keywords.txt 
fi

cd tools
python crawl_async.py --keyword $asset_folder/keywords.txt --search video --output $asset_folder/json --lang $lang --region $region --mark $asset_folder/mark --limit $video_limit

# if [ $? -ne 0 ]; then
#      exit 1
# fi

python crawl_async.py --keyword $asset_folder/keywords.txt --search channel --output $asset_folder/json --lang $lang --region $region --mark $asset_folder/mark --limit $channel_limit
cd ..

# if [ $? -ne 0 ]; then
#      exit 1
# fi

# exit 0
# python get_video.py
