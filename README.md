conda activate adaptourds

export ALL_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=$ALL_PROXY
export HTTPS_PROXY=$ALL_PROXY

python3 -u src/scripts/dataset_preprocessing/dataset_patch/generate_index.py --continue | tee logs/generate_index_3.log

遇到网络环境问题记得使用

conda env update -n adaptourds -f env.yml

bash scripts/init_env.sh --install-torch

conda env update -n adaptourds -f environment.yml


