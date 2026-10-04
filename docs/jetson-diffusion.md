# 在这台 Jetson 上部署文生图

当前机器是 **NVIDIA Jetson Orin Nano Super**（JetPack R36.4.4，约 7.4GB 统一内存，GPU 为 Orin）。MyGearCard 不会把扩散模型载进网页进程，只调用一个已经在跑的 HTTP 服务。

2019 年的 Jetson Nano（4GB、Maxwell、JetPack 4）是另一块板子。下面的容器镜像面向 Orin / JetPack 6，不要装到那块旧板上。旧板请改用外部 API。

## 内存

扩散模型和网页可以同时开，但不要再同时跑大的视觉模型。出图前先看 `free -h`。可用内存低于大约 3GB 时，先停掉别的模型。

给这台板子的出图参数：

- 模型用 **Stable Diffusion 1.5**，不要用 SDXL
- 分辨率 **512×512**
- 步数 **20** 左右

对应环境变量：

```bash
MYGEAR_LOCAL_IMAGE_BACKEND=a1111
MYGEAR_LOCAL_IMAGE_BASE_URL=http://127.0.0.1:7860
MYGEAR_LOCAL_IMAGE_STEPS=20
MYGEAR_LOCAL_IMAGE_WIDTH=512
MYGEAR_LOCAL_IMAGE_HEIGHT=512
```

改完 `.env` 后重启网页服务。页面上选出图方式「本地文生图」。

## 用容器跑 Automatic1111

网页认的是 `POST /sdapi/v1/txt2img`，所以 WebUI 必须带 `--api`。不要加 `--listen`，这样接口只留在本机 `127.0.0.1:7860`，和网页服务一样不要暴露到公网。

镜像体积和模型权重大，大约几 GB，磁盘上需要预留 20GB。第一次启动会下载 SD 1.5 权重。

```bash
docker pull dustynv/stable-diffusion-webui:r36.4.0
```

若这台 R36.4.4 拉起后依赖装不上，改用论坛里针对 R36.4.3 的预构建镜像 `daivdl487/stable-diffusion-webui:r36.4.3`，启动参数相同。

```bash
docker run --runtime nvidia --gpus all --net host --ipc host -it --name sd \
  -e PIP_INDEX_URL=https://pypi.jetson-ai-lab.io/jp6/cu126 \
  -e TAR_INDEX_URL=https://apt.jetson-ai-lab.io/jp6/cu126 \
  -v "$HOME/sd-models:/data/models/stable-diffusion" \
  dustynv/stable-diffusion-webui:r36.4.0 \
  bash -lc 'cd /opt/stable-diffusion-webui && python3 launch.py \
    --api --port 7860 --medvram --opt-sdp-attention \
    --data=/data/models/stable-diffusion'
```

`--medvram` 把一部分权重留在内存和磁盘之间倒腾，8GB 板上比默认模式稳。`--opt-sdp-attention` 用 PyTorch 自带的注意力实现，避免在 aarch64 上编译 xformers。

看到 `Running on local URL: http://127.0.0.1:7860` 之后，在另一个终端检查，这条命令只列模型、不出图：

```bash
python3 scripts/probe_image_api.py local
```

然后启动 MyGearCard（`./run.sh`），用一张示例图走「本地文生图」。第一次出图会慢，因为还在把模型送进 GPU。

容器已经创建过时，下次用：

```bash
docker start -ai sd
```

## 外部 API

不在本机跑扩散模型时，把密钥写进 `.env`：

```bash
MYGEAR_EXTERNAL_IMAGE_BASE_URL=https://api.openai.com/v1
MYGEAR_EXTERNAL_IMAGE_MODEL=dall-e-3
MYGEAR_EXTERNAL_IMAGE_API_KEY=sk-...

MYGEAR_EXTERNAL_VISION_BASE_URL=https://api.openai.com/v1
MYGEAR_EXTERNAL_VISION_MODEL=gpt-4o-mini
MYGEAR_EXTERNAL_VISION_API_KEY=sk-...
```

SiliconFlow、智谱等只要提供 `/images/generations` 和 `/chat/completions`，换掉地址和模型名即可。页面上选「外部 API」。

调用形状由单元测试固定，不访问真实接口、不消耗额度：

```bash
python3 -m pytest tests/test_providers.py -q
```

确认真的密钥可用时，再显式打开一次真实请求。这会出一张图，可能计费：

```bash
MYGEAR_LIVE_EXTERNAL=1 python3 -m pytest tests/test_providers.py -q -k live
```
