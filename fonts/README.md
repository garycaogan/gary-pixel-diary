# 字体

引擎需要一个中文可变字体，放在这里，文件名 `NotoSansSC-VF.ttf`。也可以用环境变量 `PIXEL_DIARY_FONT` 指向别的位置。

Noto Sans SC 用的是 SIL Open Font License 1.1，可以从 Google Fonts 的仓库下载：

```bash
curl -L -o fonts/NotoSansSC-VF.ttf "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"
```

构建时只会按这一集用到的字裁出 500、800、900 三个字重，体积很小。
