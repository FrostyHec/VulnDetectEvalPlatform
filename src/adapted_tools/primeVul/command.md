python src/adapted_tools/primeVul/train.py

python src/adapted_tools/primeVul/train.py --model_config codebert --exp_name exp1

python src/adapted_tools/primeVul/train.py --model_config codebert --load_pretrained /path/to/model.pt

python src/adapted_tools/primeVul/train.py --model_config codebert --exp_name exp1 --continue_train

python src/adapted_tools/primeVul/train.py --model_config codebert --exp_name exp1-codebert --gpu 0


python src/adapted_tools/primeVul/train.py --model_config unixcoder --exp_name exp1-unixcoder --gpu 1

python src/adapted_tools/primeVul/train.py --model_config codet5 --exp_name exp1-codet5 --gpu 2

```text
# 1) SSH 进入远端（无论用 VSCode、mobaxterm 还是普通 ssh）
tmux new -s codebert

# 2) 在 tmux 会话里运行你的脚本
python train.py

# 3) detach（保持脚本继续运行）
Ctrl-b d

# 4) 需要查看时：
tmux attach -t train
```

```shell
export ALL_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=$ALL_PROXY
export HTTPS_PROXY=$ALL_PROXY

NAME=codebert
LOG=${NAME}.log

nohup python -u src/adapted_tools/primeVul/train.py --model_config codebert --exp_name exp1-codebert --gpu 0 >> "${LOG}" 2>&1 &
PID=$!                                  
echo "${PID}" > "${NAME}.pid"
disown "${PID}"                         

kill $(cat $NAME.pid) 
```

```shell
export ALL_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=$ALL_PROXY
export HTTPS_PROXY=$ALL_PROXY

NAME=unixcoder
LOG=${NAME}.log

nohup python -u src/adapted_tools/primeVul/train.py --model_config unixcoder --exp_name exp1-unixcoder --gpu 1 >> "${LOG}" 2>&1 &
PID=$!                                  
echo "${PID}" > "${NAME}.pid"
disown "${PID}"                         

kill $(cat $NAME.pid) 
```

```shell
export ALL_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=$ALL_PROXY
export HTTPS_PROXY=$ALL_PROXY

NAME=codet5
LOG=${NAME}.log

nohup python -u src/adapted_tools/primeVul/train.py --model_config codet5 --exp_name exp1-codet5 --gpu 2 >> "${LOG}" 2>&1 &
PID=$!                                  
echo "${PID}" > "${NAME}.pid"
disown "${PID}"                         

kill $(cat $NAME.pid) 
```