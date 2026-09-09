#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动器：启动本地离线检索服务，自动打开浏览器，并提供一个极简的
"运行中"小窗口（含访问地址与"退出"按钮），适配中老年用户操作。
打包为 --windowed 后无控制台闪烁。

说明：HTTP 服务在后台线程运行，主线程保持存活；"运行中"窗口在独立
线程中创建（若当前环境无图形界面则该窗口自动跳过，服务不受影响）。
"""
import os
import sys
import time
import webbrowser
import threading

from server import run_server, stop_server, BASE


def show_window(port):
    """在独立线程中显示极简运行窗口。失败则静默跳过。"""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        return
    try:
        root = tk.Tk()
        root.title("人工智能报道检索平台")
        root.resizable(False, False)
        try:
            root.iconbitmap(os.path.join(BASE, "app.ico"))
        except Exception:
            pass
        w, h = 380, 170
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2, (sh - h) // 2))

        url = "http://127.0.0.1:%d/" % port
        tk.Label(root, text="人工智能报道检索平台", font=("Microsoft YaHei", 15, "bold"),
                 fg="#16335b").pack(pady=(14, 4))
        tk.Label(root, text="程序正在运行中", font=("Microsoft YaHei", 11), fg="#555").pack()
        tk.Label(root, text="请在浏览器中使用本系统", font=("Microsoft YaHei", 11), fg="#555").pack(pady=(2, 2))
        tk.Label(root, text="访问地址：%s" % url, font=("Microsoft YaHei", 10), fg="#9e1b1b").pack(pady=(4, 8))

        def quit_app():
            if messagebox.askokcancel("退出", "确定要退出检索平台吗？"):
                try:
                    stop_server()
                except Exception:
                    pass
                root.destroy()
                os._exit(0)

        btn = tk.Button(root, text="退 出", font=("Microsoft YaHei", 12),
                        bg="#9e1b1b", fg="white", width=12, height=1, command=quit_app)
        btn.pack()
        root.protocol("WM_DELETE_WINDOW", quit_app)
        root.mainloop()
    except Exception:
        # 无图形界面环境下静默跳过，服务继续运行
        pass


def main():
    try:
        # 桌面单机形态:固定回环地址,端口被占用时自动向后寻找
        port = run_server(host="127.0.0.1")
    except Exception as e:
        sys.stderr.write("服务启动出错：%s\n" % e)
        return

    url = "http://127.0.0.1:%d/" % port
    try:
        webbrowser.open(url)
    except Exception:
        pass

    # 运行窗口放入独立线程；主线程持续保活
    threading.Thread(target=show_window, args=(port,), daemon=True).start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop_server()


if __name__ == "__main__":
    main()
