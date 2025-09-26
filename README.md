# Audio Meta Fixer

**Audio metadata encoding repair tool** - Convert audio file metadata from Chinese encodings (GBK, GB2312, Big5, etc.) to UTF-8 encoding, solving Chinese character display issues in audio players.

音频元数据编码修复工具 - 将音频文件（MP3、FLAC、M4A等）的元数据从中文编码（GBK、GB2312、Big5等）统一转换为UTF-8编码，解决音频播放器中文乱码问题。

## 功能特点

- 🎵 **多格式支持**：MP3、FLAC、M4A、MP4、OGG、APE、WAV等
- 🌏 **智能编码检测**：自动识别GBK、GB2312、GB18030、Big5、EUC-JP等编码
- 🤖 **交互式修复**：默认交互模式，智能建议修复内容
- 📁 **目录递归扫描**：自动处理所有子目录中的音频文件
- 🔍 **测试模式**：支持dry-run模式，安全预览转换结果
- 🎯 **损坏检测**：智能识别并处理部分损坏的元数据
- 💾 **记忆功能**：记住用户选择，避免重复询问
- 📊 **进度显示**：实时显示处理进度和统计信息
- 🛡️ **安全可靠**：完整的错误处理和日志记录

## 快速开始

1. **克隆项目**
```bash
git clone https://github.com/your-username/audio-meta-fixer.git
cd audio-meta-fixer
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **开始使用**
```bash
# 交互模式修复音频元数据（推荐）
python audio_meta_fixer.py /path/to/your/music

# 测试模式预览（安全）
python audio_meta_fixer.py /path/to/your/music --dry-run
```

## 使用方法

### 基本用法（交互模式）

程序默认使用交互模式转换指定目录下的所有音频文件：
```bash
python audio_meta_fixer.py /path/to/music/directory
```

### 测试模式

使用 `--dry-run` 参数可以预览将要进行的转换，而不实际修改文件：
```bash
python audio_meta_fixer.py /path/to/music/directory --dry-run
```

### 直接模式（自动转换）

使用 `--direct` 参数可以启用直接模式，程序会自动处理所有转换而不询问用户：
```bash
python audio_meta_fixer.py /path/to/music/directory --direct
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
python audio_meta_fixer.py .

# 转换指定目录，测试模式（仍然是交互模式）
python audio_meta_fixer.py ~/Music --dry-run

# 直接模式转换，不询问用户确认
python audio_meta_fixer.py ~/Music --direct

# 直接模式+测试模式
python audio_meta_fixer.py ~/Music --dry-run --direct
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

## 版本信息

**当前版本**: 1.0.0

查看版本信息：
```bash
python audio_meta_fixer.py --version
```

## 作者

**Claude (Anthropic)**

这个项目由 Claude AI 助手开发，旨在解决中文音频元数据编码问题，提升音乐爱好者的聆听体验。

## 贡献

欢迎提交 Issues 和 Pull Requests 来改进这个项目！

## 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。