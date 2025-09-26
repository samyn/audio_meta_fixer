# 音频文件元数据编码转换工具

将音频文件（MP3、FLAC、M4A等）的元数据从中文编码（GBK、GB2312、Big5等）统一转换为UTF-8编码。

## 功能特点

- 支持多种音频格式：MP3、FLAC、M4A、MP4、OGG、APE、WAV等
- 自动检测中文编码（GBK、GB2312、GB18030、Big5等）
- 递归扫描目录下的所有音频文件
- 支持测试模式（dry-run），可预览转换结果而不修改文件
- 详细的日志记录
- 安全的错误处理

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本用法（交互模式）

程序默认使用交互模式转换指定目录下的所有音频文件：
```bash
python audio_metadata_converter.py /path/to/music/directory
```

### 测试模式

使用 `--dry-run` 参数可以预览将要进行的转换，而不实际修改文件：
```bash
python audio_metadata_converter.py /path/to/music/directory --dry-run
```

### 直接模式（自动转换）

使用 `--direct` 参数可以启用直接模式，程序会自动处理所有转换而不询问用户：
```bash
python audio_metadata_converter.py /path/to/music/directory --direct
```

### 交互模式特点（默认）

交互模式特点：
- 显示处理进度（当前文件数/总文件数）
- 遇到需要转换的内容时，会显示原始文本和转换结果，询问用户是否转换
- 提供3个选项：(y)默认转换、(n)不转换、(q)退出程序
- 程序会记住用户的选择，下次遇到相同内容时会自动应用已确认的转换
- 转换记录保存在 `confirmed_conversions.json` 文件中

### 示例

```bash
# 交互模式转换当前目录下的所有音频文件（默认）
python audio_metadata_converter.py .

# 转换指定目录，测试模式（仍然是交互模式）
python audio_metadata_converter.py ~/Music --dry-run

# 直接模式转换，不询问用户确认
python audio_metadata_converter.py ~/Music --direct

# 直接模式+测试模式
python audio_metadata_converter.py ~/Music --dry-run --direct
```

## 转换的元数据字段

程序会转换以下常见的元数据字段：
- 标题（Title）
- 艺术家（Artist）
- 专辑（Album）
- 专辑艺术家（Album Artist）
- 注释（Comment）
- 流派（Genre）

## 日志

程序会生成 `metadata_conversion.log` 日志文件，记录所有的转换操作和错误信息。

## 注意事项

1. 建议在转换前备份重要的音频文件
2. 首次使用建议使用 `--dry-run` 模式测试  
3. 程序会自动跳过已经是UTF-8编码的文件
4. 智能检测并跳过损坏的元数据，避免错误转换
5. 对于无法识别的文件格式，程序会记录警告信息并跳过