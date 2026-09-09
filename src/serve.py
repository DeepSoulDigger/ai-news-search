#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务器部署入口(无图形界面):
- 监听地址与端口读取 config.json 的 server 节(默认 0.0.0.0:8765)
- 固定端口模式:被占用直接报错退出,便于容器编排发现问题
- 响应 SIGTERM/SIGINT 优雅退出(docker stop / systemd stop 友好)
用法: python serve.py   (Docker 内为默认命令)
"""
import os
import signal
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server


def main():
    host, port = server.get_bind()
    try:
        actual = server.run_server(host, port, strict=True)
    except Exception as e:
        sys.stderr.write("服务启动失败：%s\n" % e)
        sys.exit(1)

    shown = "127.0.0.1" if host == "0.0.0.0" else host
    print("人工智能报道检索平台已启动: http://%s:%d/ (监听 %s)" % (shown, actual, host), flush=True)
    print("文章数: %d | 数据目录: %s" % (len(server._articles), server.DATA_DIR), flush=True)

    stop_evt = threading.Event()

    def _graceful(signum, frame):
        print("收到退出信号(%d),正在停止…" % signum, flush=True)
        stop_evt.set()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    stop_evt.wait()
    server.stop_server()
    print("服务已停止", flush=True)


if __name__ == "__main__":
    main()
