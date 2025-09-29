#!/usr/bin/env python3
"""
Audio Meta Fixer - 音频元数据编码修复工具
将音频文件（MP3、FLAC、M4A等）的元数据从中文编码转换为UTF-8，解决音频播放器中文乱码问题

Author: Claude (Anthropic)
Version: 1.0.0
License: MIT
"""

import os
import sys
import logging
import argparse
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set
import chardet
from mutagen import File
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, COMM, USLT
from mutagen.id3 import ID3NoHeaderError
import struct

# 程序信息
__version__ = "1.0.0"
__author__ = "Claude (Anthropic)"
__license__ = "MIT"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # 只显示消息内容，去掉时间戳和级别
    handlers=[
        logging.FileHandler('metadata_conversion.log', encoding='utf-8', 
                          mode='w'),  # 每次运行覆盖日志文件
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 支持的音频格式
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.mp4', '.ogg', '.oga', '.opus', '.wma', '.ape', '.wav'}

# 常见的中文编码
CHINESE_ENCODINGS = ['gbk', 'gb2312', 'gb18030', 'big5', 'big5hkscs', 'cp936', 'cp950']


class AudioMetadataConverter:
    """音频文件元数据编码转换器"""
    
    def __init__(self, target_dir: str, dry_run: bool = False, interactive: bool = False, list_only: bool = False):
        """
        初始化转换器

        Args:
            target_dir: 目标目录路径
            dry_run: 是否为测试模式（不实际修改文件）
            interactive: 是否为交互模式（半自动转换）
            list_only: 是否只列出元数据（不进行转换）
        """
        self.target_dir = Path(target_dir)
        self.dry_run = dry_run
        self.interactive = interactive
        self.list_only = list_only
        self.processed_count = 0
        self.converted_count = 0
        self.error_count = 0
        self.total_files = 0
        self.current_progress = ""
        self.confirmed_conversions: Dict[str, str] = {}  # 已确认的转换映射
        self.conversion_log_file = Path("confirmed_conversions.json")

        # 加载已确认的转换记录
        self.load_confirmed_conversions()
    
    def load_confirmed_conversions(self):
        """加载已确认的转换记录"""
        try:
            if self.conversion_log_file.exists():
                with open(self.conversion_log_file, 'r', encoding='utf-8') as f:
                    self.confirmed_conversions = json.load(f)
        except Exception as e:
            logger.warning(f"无法加载转换记录: {e}")
            self.confirmed_conversions = {}
    
    def save_confirmed_conversions(self):
        """保存已确认的转换记录"""
        try:
            with open(self.conversion_log_file, 'w', encoding='utf-8') as f:
                json.dump(self.confirmed_conversions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"无法保存转换记录: {e}")
    
    def get_suggested_text(self, field: str, file_path: Optional[Path]) -> str:
        """
        根据字段类型和文件路径获取建议的文本
        
        Args:
            field: 字段名称
            file_path: 文件路径
            
        Returns:
            建议的文本
        """
        suggested_text = ""
        if not file_path:
            return suggested_text
            
        filename = file_path.stem  # 获取不带扩展名的文件名
        
        # 根据字段类型选择合适的建议
        if field in ['标题', '曲目', 'title', 'TIT2']:
            # 对于标题字段，使用文件名或去掉编号后的部分
            if '-' in filename:
                parts = filename.split('-')
                # 如果第一部分是数字，使用第二部分
                if len(parts) > 1 and parts[0].strip().isdigit():
                    suggested_text = '-'.join(parts[1:]).strip()
                else:
                    suggested_text = filename
            else:
                # 去掉开头的数字
                import re
                suggested_text = re.sub(r'^\d+\s*', '', filename).strip()
                if not suggested_text:
                    suggested_text = filename
                    
        elif field in ['专辑', 'album', 'TALB']:
            # 对于专辑字段，使用目录名
            parent_dir = file_path.parent
            suggested_text = parent_dir.name
            
        elif field in ['艺术家', '专辑艺术家', 'artist', 'TPE1', 'TPE2']:
            # 对于艺术家字段，优先使用父目录的父目录（如果是艺术家/专辑结构）
            # 否则尝试从文件名提取第一部分
            parent_dir = file_path.parent
            grandparent_dir = parent_dir.parent
            
            # 检查是否是 艺术家/专辑/歌曲 的目录结构
            if grandparent_dir.name and not grandparent_dir.name.startswith('/'):
                # 可能是艺术家名称
                suggested_text = grandparent_dir.name
            elif '-' in filename:
                # 从文件名提取
                suggested_text = filename.split('-')[0].strip()
            else:
                suggested_text = parent_dir.name
                
        elif field in ['流派', 'genre', 'TCON']:
            # 对于流派字段，可以尝试从目录结构推测
            # 但通常流派比较难从文件名推测，使用文件名作为后备
            suggested_text = filename.replace('_', ' ').strip()
            
        else:
            # 其他字段使用文件名
            suggested_text = filename.replace('_', ' ').strip()
            
        return suggested_text
    
    def ask_user_confirmation(self, original: str, converted: str, field: str, file_path: Path, progress: str = "") -> str:
        """
        询问用户是否进行转换
        
        Args:
            original: 原始文本
            converted: 转换后的文本
            field: 字段名称
            file_path: 文件路径
            
        Returns:
            用户选择: 'y' (转换), 'n' (不转换), 'q' (退出)
        """
        if progress:
            print(f"\n{progress}")
        print(f"文件: {file_path}")
        print(f"字段: {field}")
        print(f"原始: {original}")
        print(f"转换: {converted}")
        
        while True:
            choice = input("\n请选择: (y)默认转换 / (n)不转换 / (q)退出 [y]: ").lower().strip()
            if choice in ['y', 'yes', ''] or choice == '':
                return 'y'
            elif choice in ['n', 'no']:
                return 'n'
            elif choice in ['q', 'quit', 'exit']:
                return 'q'
            else:
                print("无效选择，请输入 y、n 或 q")
    
    
    def confirm_conversion(self, original: str, converted: str, field: str = "", file_path: Optional[Path] = None, progress: str = "") -> Tuple[str, bool]:
        """
        确认是否进行转换（交互模式下使用）
        
        Args:
            original: 原始文本
            converted: 转换后的文本
            field: 字段名称
            file_path: 文件路径
            
        Returns:
            (最终文本, 是否转换)
        """
        
        if not self.interactive:
            return converted, True
        
        # 检查是否已经确认过这个转换
        if original in self.confirmed_conversions:
            confirmed_conversion = self.confirmed_conversions[original]
            if confirmed_conversion == "SKIP":
                return original, False
            else:
                return confirmed_conversion, True
        
        # 询问用户
        choice = self.ask_user_confirmation(original, converted, field, file_path or Path("未知文件"), progress)
        
        if choice == 'q':
            print("\n用户选择退出程序")
            self.save_confirmed_conversions()
            sys.exit(0)
        elif choice == 'y':
            # 记录用户确认的转换
            self.confirmed_conversions[original] = converted
            self.save_confirmed_conversions()
            return converted, True
        else:  # choice == 'n'
            # 记录用户选择不转换
            self.confirmed_conversions[original] = "SKIP"
            self.save_confirmed_conversions()
            return original, False
        
    def scan_audio_files(self) -> List[Path]:
        """
        扫描目标目录下的所有音频文件
        
        Returns:
            音频文件路径列表
        """
        audio_files = []
        logger.info(f"扫描目录: {self.target_dir}")
        
        # 扫描所有文件，然后根据扩展名过滤（大小写不敏感）
        for file_path in self.target_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
                audio_files.append(file_path)
        
        # 统计各扩展名的文件数量
        ext_count = {}
        for file_path in audio_files:
            ext = file_path.suffix.lower()
            ext_count[ext] = ext_count.get(ext, 0) + 1
        
        for ext, count in sorted(ext_count.items()):
            logger.info(f"找到 {count} 个 {ext} 文件")
        
        logger.info(f"共找到 {len(audio_files)} 个音频文件")
        return audio_files
    
    def parse_wav_info_tags(self, file_path: Path) -> dict:
        """
        手动解析WAV文件中的INFO标签
        
        Args:
            file_path: WAV文件路径
            
        Returns:
            标签字典
        """
        tags = {}
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # 查找LIST INFO块
            list_pos = data.find(b'LIST')
            if list_pos == -1:
                return tags
            
            # 跳到LIST大小
            info_pos = data.find(b'INFO', list_pos)
            if info_pos == -1:
                return tags
            
            # 解析INFO标签
            pos = info_pos + 4  # 跳过"INFO"
            
            # 常见的INFO标签映射
            info_tags = {
                b'IART': '艺术家',
                b'INAM': '标题', 
                b'IPRD': '专辑',
                b'IGNR': '流派',
                b'ICRD': '日期',
                b'ITRK': '音轨',
                b'ICMT': '注释'
            }
            
            while pos < len(data) - 8:
                try:
                    # 读取标签ID（4字节）
                    tag_id = data[pos:pos+4]
                    
                    if tag_id not in info_tags:
                        # 不是我们关心的标签，继续寻找
                        if tag_id == b'data':  # 到达音频数据部分
                            break
                        pos += 1
                        continue
                    
                    # 读取标签数据长度（4字节，小端序）
                    length = struct.unpack('<I', data[pos+4:pos+8])[0]
                    
                    # 读取标签数据
                    tag_data = data[pos+8:pos+8+length]
                    
                    # 解码字符串（去除null终止符）
                    try:
                        value = tag_data.rstrip(b'\x00').decode('utf-8', errors='ignore')
                        if value:
                            tags[info_tags[tag_id]] = value
                    except:
                        # 如果UTF-8解码失败，尝试其他编码
                        try:
                            value = tag_data.rstrip(b'\x00').decode('latin-1', errors='ignore')
                            if value:
                                tags[info_tags[tag_id]] = value
                        except:
                            pass
                    
                    # 移动到下一个标签（考虑对齐）
                    pos += 8 + length
                    if length % 2 == 1:  # WAV需要2字节对齐
                        pos += 1
                        
                except (struct.error, IndexError):
                    break
            
        except Exception as e:
            logger.warning(f"解析WAV INFO标签失败 {file_path}: {e}")
        
        return tags
    
    def detect_encoding(self, text: bytes) -> Optional[str]:
        """
        检测文本的编码
        
        Args:
            text: 待检测的字节数据
            
        Returns:
            检测到的编码名称，如果检测失败返回None
        """
        if not text:
            return None
            
        # 使用chardet检测编码
        result = chardet.detect(text)
        if result and result['confidence'] > 0.7:
            encoding = result['encoding']
            if encoding and encoding.lower() in [enc.lower() for enc in CHINESE_ENCODINGS]:
                return encoding
        
        # 尝试常见的中文编码
        for encoding in CHINESE_ENCODINGS:
            try:
                text.decode(encoding)
                return encoding
            except (UnicodeDecodeError, AttributeError):
                continue
        
        return None
    
    def _check_mp3_needs_conversion(self, file_path: Path) -> bool:
        """检查MP3文件是否需要转换"""
        try:
            from mutagen.id3 import ID3, ID3NoHeaderError
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                return False
            
            tag_frames = ['TIT2', 'TPE1', 'TALB', 'TPE2', 'TCON', 'TYER', 'TRCK']
            for frame_id in tag_frames:
                if frame_id in audio:
                    frame = audio[frame_id]
                    if frame.text:
                        _, did_convert = self.convert_text_to_utf8(str(frame.text[0]), field=frame_name, file_path=file_path)
                        if did_convert:
                            return True
            
            for frame in audio.getall('COMM'):
                if frame.text:
                    for text in frame.text:
                        _, did_convert = self.convert_text_to_utf8(str(text), field="注释", file_path=file_path)
                        if did_convert:
                            return True
        except:
            pass
        return False
    
    def _check_flac_needs_conversion(self, file_path: Path) -> bool:
        """检查FLAC文件是否需要转换"""
        try:
            from mutagen.flac import FLAC
            audio = FLAC(file_path)
            tags = ['title', 'artist', 'album', 'albumartist', 'comment', 'genre', 'date', 'tracknumber']
            for tag in tags:
                if tag in audio:
                    for value in audio[tag]:
                        _, did_convert = self.convert_text_to_utf8(value, field=tag, file_path=file_path)
                        if did_convert:
                            return True
        except:
            pass
        return False
    
    def _check_mp4_needs_conversion(self, file_path: Path) -> bool:
        """检查MP4/M4A文件是否需要转换"""
        try:
            from mutagen.mp4 import MP4
            audio = MP4(file_path)
            tags = ['\xa9nam', '\xa9ART', '\xa9alb', '\xa9cmt', '\xa9gen', '\xa9day', '\xa9wrt', 'aART']
            for tag in tags:
                if tag in audio:
                    for value in audio[tag]:
                        if tag == 'trkn' and isinstance(value, tuple):
                            continue
                        _, did_convert = self.convert_text_to_utf8(str(value), field=tag, file_path=file_path)
                        if did_convert:
                            return True
        except:
            pass
        return False
    
    def _check_generic_needs_conversion(self, file_path: Path) -> bool:
        """检查通用音频文件是否需要转换"""
        try:
            from mutagen import File
            audio = File(file_path)
            if audio and hasattr(audio, 'tags') and audio.tags:
                for key, value in audio.tags.items():
                    if isinstance(value, str):
                        _, did_convert = self.convert_text_to_utf8(value, field=str(key), file_path=file_path)
                        if did_convert:
                            return True
        except:
            pass
        return False
    
    def convert_text_to_utf8(self, text: str, original_encoding: Optional[str] = None, field: str = "", file_path: Optional[Path] = None) -> Tuple[str, bool]:
        """
        将文本转换为UTF-8编码
        
        Args:
            text: 原始文本
            original_encoding: 原始编码（可选）
            
        Returns:
            (转换后的文本, 是否进行了转换)
        """
        if not text:
            return text, False
        
        # 处理字节类型
        if isinstance(text, bytes):
            encoding = original_encoding or self.detect_encoding(text)
            if encoding:
                try:
                    converted = text.decode(encoding, errors='ignore')
                    # 对于字节类型，使用原始字节的表示作为确认的key
                    original_repr = text.hex() if hasattr(text, 'hex') else str(text)
                    final_text, should_convert = self.confirm_conversion(original_repr, converted, field, file_path, self.current_progress)
                    return final_text, should_convert
                except Exception:
                    pass
        
        # 处理字符串类型
        elif isinstance(text, str):
            # 检查是否是损坏的文本
            # 1. 包含问号开头且跟着奇怪字符的模式
            if text.startswith('?') and len(text) > 1:
                # 检查是否是明显的损坏模式
                suspicious_chars = set([
                    '\u02c6',  # ˆ (Modifier Letter Circumflex Accent)
                    '\u0152',  # Œ (Latin Capital Ligature OE)  
                    '\u2026',  # … (Horizontal Ellipsis)
                    '\u2018',  # ' (Left Single Quotation Mark)
                    '\u2019',  # ' (Right Single Quotation Mark)
                    '\u201c',  # " (Left Double Quotation Mark)
                    '\u201d',  # " (Right Double Quotation Mark)
                    '\u2013',  # – (En Dash)
                    '\u2014',  # — (Em Dash)
                ])
                has_suspicious = any(c in text for c in suspicious_chars)
                if has_suspicious:
                    if self.interactive:
                        print(f"\n发现严重编码问题:")
                        print(f"  字段: {field}")
                        print(f"  原始数据: '{text}'")
                        print(f"  问题: 包含损坏的字符，数据已不可恢复")
                        print("说明: 文本包含多次编码转换导致的损坏字符")
                        print("建议: 手动修正或从原始来源重新获取正确的元数据")
                        return text, False
                    else:
                        logger.warning(f"跳过损坏的文本数据: {text} (包含不可恢复的字符)")
                        return text, False
            
            # 2. 检查是否包含过多的问号（另一种损坏模式）
            if text.count('?') >= len(text) * 0.3 and len(text) > 2:
                if self.interactive:
                    print(f"\n发现编码问题:")
                    print(f"  字段: {field}")
                    print(f"  原始数据: '{text}'")
                    print(f"  问题: 包含过多问号({text.count('?')}/{len(text)}个字符)，数据严重损坏")
                    print("说明: 大量问号表示字符编码彻底损坏")
                    print("建议: 手动修正或查看原始音频文件的正确信息")
                    if file_path:
                        print(f"文件参考: {file_path.name}")
                    
                    print("\n选项:")
                    print("1. 手动输入正确的文本 (默认)")
                    print("2. 跳过这个转换")
                    print("3. 退出程序")
                    
                    while True:
                        choice = input("请选择 (1/2/3，默认1): ").strip() or '1'  # 默认选择1
                        if choice == '1':
                            # 使用辅助函数获取建议文本
                            suggested_text = self.get_suggested_text(field, file_path)
                            
                            prompt = f"请输入正确的文本"
                            if suggested_text:
                                prompt += f" (默认: {suggested_text})"
                            prompt += ": "
                            
                            manual_text = input(prompt).strip()
                            
                            # 如果用户直接回车，使用建议值
                            if not manual_text and suggested_text:
                                manual_text = suggested_text
                            
                            if manual_text:
                                self.confirmed_conversions[text] = manual_text
                                self.save_confirmed_conversions()
                                return manual_text, True
                            else:
                                print("输入为空，跳过转换")
                                self.confirmed_conversions[text] = "SKIP"
                                self.save_confirmed_conversions()
                                return text, False
                        elif choice == '2':
                            self.confirmed_conversions[text] = "SKIP"
                            self.save_confirmed_conversions()
                            return text, False
                        elif choice == '3':
                            print("\n用户选择退出程序")
                            self.save_confirmed_conversions()
                            sys.exit(0)
                        else:
                            print("无效选择，请输入 1、2 或 3")
                else:
                    logger.warning(f"跳过可能损坏的文本数据: {text} (包含过多问号)")
                    return text, False
            
            # 3. 检查部分损坏模式（包含单个或少量问号的情况）
            if '?' in text and len(text) > 3:
                question_count = text.count('?')
                # 检查是否是正常的问句（问号在末尾且前面是字母或空格）
                is_normal_question = (
                    text.endswith('?') and 
                    question_count == 1 and
                    len(text) > 1 and
                    (text[-2].isalpha() or text[-2].isspace())
                )
                
                if 1 <= question_count <= 2 and not is_normal_question:  # 排除正常问句
                    if self.interactive:
                        print(f"\n发现编码问题:")
                        print(f"  字段: {field}")
                        print(f"  原始数据: '{text}'")
                        print(f"  问题: 包含{question_count}个问号，部分字符可能丢失")
                        if file_path:
                            # 从文件路径提取可能的正确名称作为建议
                            filename = file_path.stem  # 获取不带扩展名的文件名
                            print(f"文件名参考: {filename}")
                            # 尝试从文件名中提取有用信息
                            if '-' in filename:
                                parts = filename.split('-')
                                for part in parts:
                                    clean_part = part.strip()
                                    if len(clean_part) > 1 and not clean_part.isdigit():
                                        print(f"可能的正确文本: {clean_part}")
                                        break
                        
                        print("说明: 文本中的问号(?)表示某些字符在编码过程中丢失")
                        print("建议: 请根据文件名手动输入正确的文本，或选择跳过")
                        
                        print("\n选项:")
                        print("1. 手动输入正确的文本")
                        print("2. 跳过这个转换")
                        print("3. 退出程序")
                        
                        while True:
                            choice = input("请选择 (1/2/3，默认1): ").strip() or '1'  # 默认选择1
                            if choice == '1':
                                # 使用辅助函数获取建议文本
                                suggested_text = self.get_suggested_text(field, file_path)
                                
                                prompt = f"请输入正确的文本"
                                if suggested_text:
                                    prompt += f" (默认: {suggested_text})"
                                prompt += ": "
                                
                                manual_text = input(prompt).strip()
                                
                                # 如果用户直接回车，使用建议值
                                if not manual_text and suggested_text:
                                    manual_text = suggested_text
                                
                                if manual_text:
                                    self.confirmed_conversions[text] = manual_text
                                    self.save_confirmed_conversions()
                                    return manual_text, True
                                else:
                                    print("输入为空，跳过转换")
                                    self.confirmed_conversions[text] = "SKIP"
                                    self.save_confirmed_conversions()
                                    return text, False
                            elif choice == '2':
                                self.confirmed_conversions[text] = "SKIP"
                                self.save_confirmed_conversions()
                                return text, False
                            elif choice == '3':
                                print("\n用户选择退出程序")
                                self.save_confirmed_conversions()
                                sys.exit(0)
                            else:
                                print("无效选择，请输入 1、2 或 3")
                    else:
                        # 非交互模式下，记录警告并跳过
                        logger.warning(f"跳过部分损坏的文本数据: {text} (包含{question_count}个问号，建议手动处理)")
                        return text, False
            
            # 首先检查是否已经是正确的UTF-8
            try:
                # 检查是否包含中文、日文字符且正确显示
                has_cjk_chars = any(
                    '\u4e00' <= char <= '\u9fff' or  # 中日韩统一汉字
                    '\u3040' <= char <= '\u309f' or  # 平假名
                    '\u30a0' <= char <= '\u30ff' or  # 片假名
                    '\u31f0' <= char <= '\u31ff' or  # 片假名拼音扩展
                    '\u3000' <= char <= '\u303f' or  # 中日韩符号和标点（包含全角空格）
                    '\u3200' <= char <= '\u32ff' or  # 中日韩符号和标点
                    '\uff00' <= char <= '\uffef'     # 全角ASCII、全角标点
                    for char in text
                )

                if has_cjk_chars:
                    # 即使包含CJK字符，也要检查是否同时包含可疑的西欧字符（可能是部分乱码）
                    suspicious_western = set('ÕÅÓÉúÌØ')  # 常见的中文乱码字符
                    has_suspicious = any(c in suspicious_western for c in text)

                    if has_suspicious:
                        # 可能是部分乱码的情况，如 "ÕÅÓêÉú / 张雨生"
                        # 尝试转换可疑部分
                        parts = text.split(' / ')
                        if len(parts) > 1:
                            # 对每部分单独检查
                            converted_parts = []
                            did_convert = False
                            for part in parts:
                                # 检查这部分是否可能是乱码
                                part_non_ascii = {c for c in part if ord(c) > 127}
                                part_has_cjk = any('\u4e00' <= c <= '\u9fff' for c in part)

                                if not part_has_cjk and part_non_ascii:
                                    # 这部分没有中文但有非ASCII字符，可能是乱码
                                    try:
                                        bytes_text = part.encode('latin-1', errors='ignore')
                                        test_converted = bytes_text.decode('gbk', errors='ignore')
                                        if any('\u4e00' <= c <= '\u9fff' for c in test_converted):
                                            # 转换后有中文，使用转换结果
                                            converted_parts.append(test_converted)
                                            did_convert = True
                                        else:
                                            converted_parts.append(part)
                                    except:
                                        converted_parts.append(part)
                                else:
                                    converted_parts.append(part)

                            if did_convert:
                                converted_text = ' / '.join(converted_parts)
                                if self.interactive:
                                    final_text, should_convert = self.confirm_conversion(text, converted_text, field, file_path, self.current_progress)
                                    return final_text, should_convert
                                else:
                                    return converted_text, True

                    # 没有可疑字符，认为已经是正确的UTF-8
                    text.encode('utf-8')
                    return text, False
            except UnicodeEncodeError:
                pass
            
            # 检查是否包含可能的编码问题字符
            # 修饰字符(U+02B0-U+02FF)通常不会单独出现，可能是编码问题
            has_modifier_chars = any('\u02b0' <= char <= '\u02ff' for char in text)
            if has_modifier_chars and len(text.strip()) <= 3:  # 短文本且包含修饰字符，很可能是编码问题
                # 尝试通过编码转换来修复
                for source_encoding in ['latin-1', 'cp1252']:
                    for target_encoding in ['gbk', 'gb2312', 'big5']:
                        try:
                            bytes_text = text.encode(source_encoding, errors='ignore')
                            converted = bytes_text.decode(target_encoding, errors='ignore')
                            # 检查转换结果是否更合理（包含中文字符）
                            if converted != text and any('\u4e00' <= char <= '\u9fff' for char in converted):
                                if self.interactive:
                                    final_text, should_convert = self.confirm_conversion(text, converted, field, file_path, self.current_progress)
                                    return final_text, should_convert
                                else:
                                    return converted, True
                        except Exception:
                            continue
                            
                # 如果没找到合适的转换，在交互模式下询问用户
                if self.interactive:
                    print(f"\n发现编码问题:")
                    print(f"  字段: {field}")
                    print(f"  原始数据: '{text}'")
                    print(f"  问题: 包含不常见的修饰字符 ('{text}' = U+{ord(text):04X})")
                    print("说明: 此字符通常不会单独出现在音乐元数据中，很可能是编码错误")
                    if file_path:
                        print(f"文件参考: {file_path.name}")
                    print("建议: 请根据文件名和字段类型手动输入正确内容")
                    
                    print("\n选项:")
                    print("1. 手动输入正确的文本")
                    print("2. 跳过这个转换")  
                    print("3. 退出程序")
                    
                    while True:
                        choice = input("请选择 (1/2/3，默认1): ").strip() or '1'  # 默认选择1
                        if choice == '1':
                            # 使用辅助函数获取建议文本
                            suggested_text = self.get_suggested_text(field, file_path)
                            
                            prompt = f"请输入正确的文本"
                            if suggested_text:
                                prompt += f" (默认: {suggested_text})"
                            prompt += ": "
                            
                            manual_text = input(prompt).strip()
                            
                            # 如果用户直接回车，使用建议值
                            if not manual_text and suggested_text:
                                manual_text = suggested_text
                            
                            if manual_text:
                                self.confirmed_conversions[text] = manual_text
                                self.save_confirmed_conversions()
                                return manual_text, True
                            else:
                                print("输入为空，跳过转换")
                                self.confirmed_conversions[text] = "SKIP"
                                self.save_confirmed_conversions()
                                return text, False
                        elif choice == '2':
                            self.confirmed_conversions[text] = "SKIP"
                            self.save_confirmed_conversions()
                            return text, False
                        elif choice == '3':
                            print("\n用户选择退出程序")
                            self.save_confirmed_conversions()
                            sys.exit(0)
                        else:
                            print("无效选择，请输入 1、2 或 3")
                else:
                    # 非交互模式下，记录警告但不转换
                    logger.warning(f"检测到可疑的修饰字符但未转换: {text} (包含修饰字符，建议手动检查)")
                    return text, False
            
            # 检查是否包含正常的西欧语言字符（不应转换）
            # Latin-1 Supplement (U+0080-U+00FF) 中的常见西欧字符
            common_western_chars = set()
            # 法语字符
            common_western_chars.update([
                'À', 'Á', 'Â', 'Ã', 'Ä', 'Å', 'Æ', 'Ç', 'È', 'É', 'Ê', 'Ë', 'Ì', 'Í', 'Î', 'Ï',
                'Ð', 'Ñ', 'Ò', 'Ó', 'Ô', 'Õ', 'Ö', 'Ø', 'Ù', 'Ú', 'Û', 'Ü', 'Ý', 'Þ', 'ß',
                'à', 'á', 'â', 'ã', 'ä', 'å', 'æ', 'ç', 'è', 'é', 'ê', 'ë', 'ì', 'í', 'î', 'ï',
                'ð', 'ñ', 'ò', 'ó', 'ô', 'õ', 'ö', 'ø', 'ù', 'ú', 'û', 'ü', 'ý', 'þ', 'ÿ'
            ])
            
            # 检查文本是否主要由ASCII和常见西欧字符组成
            text_chars = set(text)
            non_ascii_chars = {c for c in text_chars if ord(c) > 127}
            
            # 先尝试检测是否是日语或中文乱码
            if non_ascii_chars:
                # 检查是否是日语编码的乱码
                japanese_euc_jp_result = None
                japanese_gbk_result = None
                
                try:
                    # 检测EUC-JP模式：包含¤字符（0xa4）通常是EUC-JP的标记
                    if '¤' in text:
                        bytes_text = text.encode('latin-1', errors='ignore')
                        
                        # 尝试EUC-JP解码
                        japanese_converted = bytes_text.decode('euc-jp', errors='ignore')
                        has_hiragana = any(0x3040 <= ord(c) <= 0x309F for c in japanese_converted)
                        has_katakana = any(0x30A0 <= ord(c) <= 0x30FF for c in japanese_converted)
                        has_kanji = any(0x4E00 <= ord(c) <= 0x9FFF for c in japanese_converted)
                        
                        if (has_hiragana or has_katakana or has_kanji) and len(japanese_converted) <= len(text):
                            japanese_euc_jp_result = japanese_converted
                        
                        # 同时尝试GBK解码
                        gbk_converted = bytes_text.decode('gbk', errors='ignore')
                        gbk_has_hiragana = any(0x3040 <= ord(c) <= 0x309F for c in gbk_converted)
                        gbk_has_katakana = any(0x30A0 <= ord(c) <= 0x30FF for c in gbk_converted)
                        gbk_has_kanji = any(0x4E00 <= ord(c) <= 0x9FFF for c in gbk_converted)
                        
                        if (gbk_has_hiragana or gbk_has_katakana or gbk_has_kanji) and len(gbk_converted) <= len(text):
                            japanese_gbk_result = gbk_converted
                        
                        # 如果两种解码都有日语字符，选择更优的结果
                        if japanese_euc_jp_result and japanese_gbk_result:
                            # 优先选择GBK解码结果，因为它通常产生更合理的日语文本
                            # 检查是否包含常见的日语词汇模式
                            common_japanese_words = ['小道', '通', 'を', 'って', 'の', 'に', 'で', 'と', 'が', 'は']
                            gbk_score = sum(1 for word in common_japanese_words if word in japanese_gbk_result)
                            euc_score = sum(1 for word in common_japanese_words if word in japanese_euc_jp_result)
                            
                            # 如果GBK包含更多常见日语词汇，或者包含"小道を通"这样的模式，优先选择GBK
                            if gbk_score >= euc_score or '小道' in japanese_gbk_result or 'を通' in japanese_gbk_result:
                                if self.interactive:
                                    final_text, should_convert = self.confirm_conversion(text, japanese_gbk_result, field, file_path, self.current_progress)
                                    return final_text, should_convert
                                else:
                                    return japanese_gbk_result, True
                            else:
                                if self.interactive:
                                    final_text, should_convert = self.confirm_conversion(text, japanese_euc_jp_result, field, file_path, self.current_progress)
                                    return final_text, should_convert
                                else:
                                    return japanese_euc_jp_result, True
                        elif japanese_gbk_result:
                            if self.interactive:
                                final_text, should_convert = self.confirm_conversion(text, japanese_gbk_result, field, file_path, self.current_progress)
                                return final_text, should_convert
                            else:
                                return japanese_gbk_result, True
                        elif japanese_euc_jp_result:
                            if self.interactive:
                                final_text, should_convert = self.confirm_conversion(text, japanese_euc_jp_result, field, file_path, self.current_progress)
                                return final_text, should_convert
                            else:
                                return japanese_euc_jp_result, True
                            
                except Exception:
                    pass
                
                # 尝试转换看是否能得到有意义的中文
                best_result = None
                best_chinese_count = 0
                
                for source_encoding in ['cp1252', 'latin-1', 'iso-8859-1']:
                    for target_encoding in CHINESE_ENCODINGS:
                        try:
                            bytes_text = text.encode(source_encoding, errors='ignore')
                            converted = bytes_text.decode(target_encoding, errors='ignore')
                            
                            # 计算CJK字符数量，包括中文、日文、全角字符
                            cjk_count = sum(1 for char in converted if (
                                '\u4e00' <= char <= '\u9fff' or  # 中日韩统一汉字
                                '\u3040' <= char <= '\u309f' or  # 平假名
                                '\u30a0' <= char <= '\u30ff' or  # 片假名
                                '\u31f0' <= char <= '\u31ff' or  # 片假名拼音扩展
                                '\u3000' <= char <= '\u303f' or  # 中日韩符号和标点（包含全角空格）
                                '\u3200' <= char <= '\u32ff' or  # 中日韩符号和标点
                                '\uff00' <= char <= '\uffef'     # 全角ASCII、全角标点
                            ))
                            
                            # 计算CJK字符比例
                            cjk_ratio = cjk_count / len(converted) if len(converted) > 0 else 0
                            
                            # 计算全角字符数量（这些通常是正确的转换）
                            fullwidth_count = sum(1 for char in converted if '\uff00' <= char <= '\uffef')
                            
                            # 判断转换质量，优选：
                            # 1. CJK字符数量更多的结果
                            # 2. 在CJK字符数量相近时，优选包含更多全角字符的结果（通常更准确）
                            is_better = False
                            
                            if cjk_ratio >= 0.3:  # 必须有足够的CJK字符
                                if cjk_count > best_chinese_count:
                                    # 更多CJK字符，直接更好
                                    is_better = True
                                elif cjk_count == best_chinese_count and fullwidth_count > 0:
                                    # CJK字符数量相同，但包含全角字符（通常更准确）
                                    current_best_fullwidth = sum(1 for char in (best_result or '') if '\uff00' <= char <= '\uffef')
                                    if fullwidth_count > current_best_fullwidth:
                                        is_better = True
                            
                            if is_better:
                                best_chinese_count = cjk_count
                                best_result = converted
                        except Exception:
                            continue
                
                # 如果找到了包含较多中文字符的转换结果，则进行转换
                if best_result and best_chinese_count > 0:
                    if self.interactive:
                        final_text, should_convert = self.confirm_conversion(text, best_result, field, file_path, self.current_progress)
                        return final_text, should_convert
                    else:
                        return best_result, True
                
                # 如果没有找到中文转换，检查是否都是合理的西欧字符
                # 对于纯西欧语言文本，检查字符组合是否合理
                text_lower = text.lower()
                
                # 检查是否包含明显的乱码字符（但排除合理的重音字符组合）
                obvious_garbled_chars = {'¿', '½', '¡', '¤', '¦', '§', '©', 'ª', '«', '¬', '®', '¯', 
                                       '°', '±', '²', '³', '´', 'µ', '¶', '·', '¸', '¹', 'º', '»', '¼', '¾'}
                
                # 检查是否是合理的重音字符组合
                # ¨¤ = à, ¨¨ = è, ¨ª = ê, ¨º = ô, ¨¢ = á, ¨ª = í, ¨² = í, ¨´ = ú, ¨¹ = ù 等
                valid_accent_patterns = ['¨¤', '¨¨', '¨ª', '¨º', '¨¬', '¨®', '¨¯', '¨²', '¨´', '¨¹', '¨»', '¨¿', '¨¢']
                has_valid_accents = any(pattern in text for pattern in valid_accent_patterns)
                
                # 如果包含有效的重音模式，检查是否是西欧语言
                if has_valid_accents:
                    # 检查是否包含西欧语言词汇
                    western_language_patterns = [
                        # 意大利语
                        'roma', 'nun', 'la', 'il', 'di', 'del', 'della', 'stupida', 'stasera', 'per', 'nel', 'mio',
                        'sole', 'blu', 'chiamano', 'estate', 'cuore', 'anni', 'miei', 'piove', 'fino',
                        # 法语
                        'dans', 'mon', 'le', 'de', 'une', 'valse', 'musique', 'française', 'rencontre', 
                        'dernière', 'café', 'français', 'île', 'rever', 'rêver', 'r', 'ver',
                        # 西班牙语
                        'quiz', 'quizas', 'frenes', 'bien', 'comp', 's',
                        # 通用罗曼语词汇
                        'cosa', 'hai', 'messo', 'caffe'
                    ]
                    
                    if any(pattern in text_lower for pattern in western_language_patterns):
                        return text, False  # 看起来是正常的西欧语言，不转换
                
                # 如果包含明显的乱码字符但不是有效重音，尝试转换
                if any(c in obvious_garbled_chars for c in text) and not has_valid_accents:
                    pass  # 继续转换逻辑
                else:
                    # 常见的法语/其他西欧语言词汇模式（已移到上面）
                    if any(pattern in text_lower for pattern in [
                        'dans', 'mon', 'la', 'le', 'de', 'une', 'valse', 'musique', 
                        'française', 'rencontre', 'bossa', 'nova', 'dernière',
                        'café', 'français', 'île'
                    ]):
                        return text, False  # 看起来是正常的法语，不转换
                
                # 如果非ASCII字符都是常见的西欧字符，需要检查是否实际上是中文乱码
                if non_ascii_chars.issubset(common_western_chars):
                    # 尝试转换看是否能得到有意义的中文
                    possible_chinese = False
                    test_result = None

                    # 尝试Latin-1 -> GBK转换（最常见的情况）
                    try:
                        bytes_text = text.encode('latin-1', errors='ignore')
                        test_converted = bytes_text.decode('gbk', errors='ignore')
                        # 检查转换后是否包含中文字符
                        if any('\u4e00' <= c <= '\u9fff' for c in test_converted):
                            possible_chinese = True
                            test_result = test_converted
                    except:
                        pass

                    # 如果没找到，尝试其他编码组合
                    if not possible_chinese:
                        for source_enc in ['latin-1', 'cp1252']:
                            for target_enc in ['gb2312', 'big5']:
                                try:
                                    bytes_text = text.encode(source_enc, errors='ignore')
                                    test_converted = bytes_text.decode(target_enc, errors='ignore')
                                    if any('\u4e00' <= c <= '\u9fff' for c in test_converted):
                                        possible_chinese = True
                                        test_result = test_converted
                                        break
                                except:
                                    continue
                            if possible_chinese:
                                break

                    # 如果转换后得到有意义的中文，继续处理
                    if possible_chinese:
                        pass  # 继续下面的转换逻辑，让正常的转换流程处理
                    # 额外检查：如果是短文本且字符组合看起来不像正常单词，可能是乱码
                    elif len(text) <= 6 and not any(c.isspace() for c in text):
                        # 短文本且无空格，可能是乱码，尝试转换
                        pass  # 继续下面的转换逻辑
                    else:
                        # 真的是西欧语言文本，不需要转换
                        return text, False
            
            # 对于其他情况，尝试转换
            if any(ord(c) > 127 for c in text):
                # 首先尝试直接构建正确的字节序列
                try:
                    # 处理特殊的Unicode字符映射
                    bytes_list = []
                    for char in text:
                        code = ord(char)
                        if code < 256:
                            # 普通Latin-1字符
                            bytes_list.append(code)
                        elif code == 0x2021:  # ‡ (double dagger) 应该是 0x87
                            bytes_list.append(0x87)
                        elif code == 0x2030:  # ‰ (per mille) 应该是 0x89
                            bytes_list.append(0x89)
                        elif code == 0x2039:  # ‹ 应该是 0x8B
                            bytes_list.append(0x8B)
                        elif code == 0x2018:  # ' 应该是 0x91
                            bytes_list.append(0x91)
                        elif code == 0x2019:  # ' 应该是 0x92
                            bytes_list.append(0x92)
                        elif code == 0x201C:  # " 应该是 0x93
                            bytes_list.append(0x93)
                        elif code == 0x201D:  # " 应该是 0x94
                            bytes_list.append(0x94)
                        elif code == 0x2022:  # • 应该是 0x95
                            bytes_list.append(0x95)
                        elif code == 0x2013:  # – 应该是 0x96
                            bytes_list.append(0x96)
                        elif code == 0x2014:  # — 应该是 0x97
                            bytes_list.append(0x97)
                        else:
                            # 其他字符保持原样
                            bytes_list.append(code if code < 256 else ord('?'))
                    
                    bytes_text = bytes(bytes_list)
                    
                    # 尝试用中文编码解码
                    for target_encoding in CHINESE_ENCODINGS:
                        try:
                            converted = bytes_text.decode(target_encoding, errors='ignore')
                            # 验证转换结果是否包含有效的中文字符
                            if converted and any('\u4e00' <= char <= '\u9fff' for char in converted):
                                # 验证是否是有效的转换（避免产生太多?）
                                if '?' not in converted or converted.count('?') < len(converted) / 4:
                                    if self.interactive:
                                        final_text, should_convert = self.confirm_conversion(text, converted, field, file_path, self.current_progress)
                                        return final_text, should_convert
                                    else:
                                        return converted, True
                        except Exception:
                            pass
                except Exception:
                    pass
                
                # 如果特殊处理失败，回退到原来的方法
                for source_encoding in ['cp1252', 'latin-1', 'iso-8859-1']:
                    for target_encoding in CHINESE_ENCODINGS:
                        try:
                            # 先用source_encoding编码回字节
                            bytes_text = text.encode(source_encoding, errors='ignore')
                            # 再用目标中文编码解码
                            converted = bytes_text.decode(target_encoding, errors='ignore')
                            
                            # 验证转换结果是否包含有效的中文字符，或者明显改善了乱码
                            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in converted)
                            has_improvement = (
                                # 移除了明显的乱码字符
                                sum(1 for c in text if c in obvious_garbled_chars) > 
                                sum(1 for c in converted if c in obvious_garbled_chars)
                            )
                            
                            if has_chinese or has_improvement:
                                # 进一步验证转换质量
                                if len(converted) > 0 and not all(c in '?' for c in converted):
                                    if self.interactive:
                                        final_text, should_convert = self.confirm_conversion(text, converted, field, file_path, self.current_progress)
                                        return final_text, should_convert
                                    else:
                                        return converted, True
                        except Exception:
                            continue
            
            # 如果不包含特殊字符，可能是ASCII或已经是UTF-8
            try:
                text.encode('ascii')
                # 纯ASCII文本，不需要转换
                return text, False
            except UnicodeEncodeError:
                # 包含非ASCII字符但不是乱码，可能已经是UTF-8
                pass
        
        return text, False
    
    def process_mp3_file(self, file_path: Path) -> bool:
        """
        处理MP3文件的元数据
        
        Args:
            file_path: MP3文件路径
            
        Returns:
            是否成功转换
        """
        converted = False
        conversion_details = []
        
        try:
            # 尝试读取ID3标签
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                audio = ID3()
                audio.save(file_path)
                audio = ID3(file_path)
            
            # 需要转换的ID3标签
            tag_frames = {
                'TIT2': '标题',
                'TPE1': '艺术家',
                'TALB': '专辑',
                'TPE2': '专辑艺术家',
                'TCON': '流派',
                'TYER': '年份',
                'TRCK': '音轨',
            }
            
            for frame_id, frame_name in tag_frames.items():
                if frame_id in audio:
                    frame = audio[frame_id]
                    original_text = str(frame.text[0]) if frame.text else ""
                    
                    if original_text:
                        converted_text, did_convert = self.convert_text_to_utf8(original_text, field=frame_name, file_path=file_path)
                        
                        if did_convert:
                            if self.dry_run:
                                # 测试模式下，首次发现需要转换时才显示文件信息
                                if not conversion_details:
                                    logger.info(f"\n{'='*60}")
                                    logger.info(f"文件: {file_path}")
                                    logger.info(f"{'='*60}")
                                # 显示完整信息
                                logger.info(f"  [{frame_name}]:")
                                logger.info(f"    原始: {original_text}")
                                logger.info(f"    转换: {converted_text}")
                                conversion_details.append({
                                    'field': frame_name,
                                    'original': original_text,
                                    'converted': converted_text
                                })
                            else:
                                logger.info(f"  转换 {frame_name}: {original_text} -> {converted_text}")
                                # 创建新的ID3标签框，明确指定UTF-8编码
                                from mutagen.id3 import TIT2, TPE1, TALB, TPE2, TCON, TYER, TRCK
                                tag_classes = {
                                    'TIT2': TIT2, 'TPE1': TPE1, 'TALB': TALB, 'TPE2': TPE2,
                                    'TCON': TCON, 'TYER': TYER, 'TRCK': TRCK
                                }
                                if frame_id in tag_classes:
                                    # encoding=3 表示UTF-8编码
                                    audio[frame_id] = tag_classes[frame_id](encoding=3, text=converted_text)
                                else:
                                    # 回退到原来的方法
                                    frame.text[0] = converted_text
                            converted = True
            
            # 处理注释
            for frame in audio.getall('COMM'):
                if frame.text:
                    for i, text in enumerate(frame.text):
                        converted_text, did_convert = self.convert_text_to_utf8(str(text), field="注释", file_path=file_path)
                        if did_convert:
                            if self.dry_run:
                                # 测试模式下，首次发现需要转换时才显示文件信息
                                if not conversion_details:
                                    logger.info(f"\n{'='*60}")
                                    logger.info(f"文件: {file_path}")
                                    logger.info(f"{'='*60}")
                                logger.info(f"  [注释]:")
                                logger.info(f"    原始: {text}")
                                logger.info(f"    转换: {converted_text}")
                                conversion_details.append({
                                    'field': '注释',
                                    'original': text,
                                    'converted': converted_text
                                })
                            else:
                                logger.info(f"  转换注释: {text} -> {converted_text}")
                                # 对于注释，直接更新文本，mutagen会自动处理编码
                                frame.text[i] = converted_text
                                # 确保注释使用UTF-8编码
                                frame.encoding = 3
                            converted = True
            
            # 在测试模式下显示转换总结
            if self.dry_run and conversion_details:
                logger.info(f"  ---- 共 {len(conversion_details)} 个字段需要转换 ----")
            
            # 保存修改
            if converted and not self.dry_run:
                audio.save(file_path, v2_version=3)
                
        except Exception as e:
            import traceback
            logger.error(f"处理MP3文件失败 {file_path}: {e}")
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return False
        
        return converted
    
    def process_flac_file(self, file_path: Path) -> bool:
        """
        处理FLAC文件的元数据
        
        Args:
            file_path: FLAC文件路径
            
        Returns:
            是否成功转换
        """
        converted = False
        conversion_details = []
        
        try:
            audio = FLAC(file_path)
            
            # 需要转换的Vorbis注释标签
            tags_to_convert = {
                'title': '标题',
                'artist': '艺术家',
                'album': '专辑',
                'albumartist': '专辑艺术家',
                'comment': '注释',
                'genre': '流派',
                'date': '日期',
                'tracknumber': '音轨号'
            }
            
            for tag, tag_name in tags_to_convert.items():
                if tag in audio:
                    values = audio[tag]
                    new_values = []
                    
                    for value in values:
                        converted_text, did_convert = self.convert_text_to_utf8(value, field=tag_name, file_path=file_path)
                        
                        if did_convert:
                            if self.dry_run:
                                # 测试模式下，首次发现需要转换时才显示文件信息
                                if not conversion_details:
                                    logger.info(f"\n{'='*60}")
                                    logger.info(f"文件: {file_path}")
                                    logger.info(f"{'='*60}")
                                logger.info(f"  [{tag_name}]:")
                                logger.info(f"    原始: {value}")
                                logger.info(f"    转换: {converted_text}")
                                conversion_details.append({
                                    'field': tag_name,
                                    'original': value,
                                    'converted': converted_text
                                })
                            else:
                                logger.info(f"  转换 {tag_name}: {value} -> {converted_text}")
                            new_values.append(converted_text)
                            converted = True
                        else:
                            new_values.append(value)
                    
                    if converted and not self.dry_run:
                        audio[tag] = new_values
            
            # 在测试模式下显示转换总结
            if self.dry_run and conversion_details:
                logger.info(f"  ---- 共 {len(conversion_details)} 个字段需要转换 ----")
            
            # 保存修改
            if converted and not self.dry_run:
                audio.save()
                
        except Exception as e:
            logger.error(f"处理FLAC文件失败 {file_path}: {e}")
            return False
        
        return converted
    
    def process_mp4_file(self, file_path: Path) -> bool:
        """
        处理MP4/M4A文件的元数据
        
        Args:
            file_path: MP4文件路径
            
        Returns:
            是否成功转换
        """
        converted = False
        conversion_details = []
        
        try:
            audio = MP4(file_path)
            
            # MP4标签映射
            tags_to_convert = {
                '\xa9nam': '标题',
                '\xa9ART': '艺术家',
                '\xa9alb': '专辑',
                '\xa9cmt': '注释',
                '\xa9gen': '流派',
                '\xa9day': '年份',
                '\xa9wrt': '作曲家',
                'aART': '专辑艺术家',
                'trkn': '音轨号'
            }
            
            for tag, name in tags_to_convert.items():
                if tag in audio:
                    values = audio[tag]
                    new_values = []
                    
                    for value in values:
                        # 处理特殊的音轨号格式
                        if tag == 'trkn' and isinstance(value, tuple):
                            continue  # 跳过元组格式的音轨号
                        
                        converted_text, did_convert = self.convert_text_to_utf8(str(value), field=name, file_path=file_path)
                        
                        if did_convert:
                            if self.dry_run:
                                # 测试模式下，首次发现需要转换时才显示文件信息
                                if not conversion_details:
                                    logger.info(f"\n{'='*60}")
                                    logger.info(f"文件: {file_path}")
                                    logger.info(f"{'='*60}")
                                logger.info(f"  [{name}]:")
                                logger.info(f"    原始: {value}")
                                logger.info(f"    转换: {converted_text}")
                                conversion_details.append({
                                    'field': name,
                                    'original': str(value),
                                    'converted': converted_text
                                })
                            else:
                                logger.info(f"  转换 {name}: {value} -> {converted_text}")
                            new_values.append(converted_text)
                            converted = True
                        else:
                            new_values.append(value)
                    
                    if converted and not self.dry_run:
                        audio[tag] = new_values
            
            # 在测试模式下显示转换总结
            if self.dry_run and conversion_details:
                logger.info(f"  ---- 共 {len(conversion_details)} 个字段需要转换 ----")
            
            # 保存修改
            if converted and not self.dry_run:
                audio.save()
                
        except Exception as e:
            logger.error(f"处理MP4文件失败 {file_path}: {e}")
            return False
        
        return converted
    
    def process_wav_file(self, file_path: Path) -> bool:
        """
        处理WAV文件
        
        Args:
            file_path: WAV文件路径
            
        Returns:
            是否成功转换
        """
        try:
            # 首先尝试用mutagen处理（支持ID3标签的WAV文件）
            from mutagen import File
            audio = File(file_path)
            
            if audio and hasattr(audio, 'tags') and audio.tags:
                # 如果mutagen能读取到标签，使用通用方法处理
                return self.process_generic_file(file_path)
            
            # 如果mutagen无法读取标签，尝试手动解析WAV INFO标签
            info_tags = self.parse_wav_info_tags(file_path)
            
            if not info_tags:
                # 如果也没有INFO标签，返回False
                return False
            
            converted = False
            conversion_details = []
            
            for tag_name, original_text in info_tags.items():
                if original_text:
                    converted_text, did_convert = self.convert_text_to_utf8(original_text, field=tag_name, file_path=file_path)
                    
                    if did_convert:
                        if self.dry_run:
                            # 测试模式下，首次发现需要转换时才显示文件信息
                            if not conversion_details:
                                logger.info(f"\n{'='*60}")
                                logger.info(f"文件: {file_path}")
                                logger.info(f"{'='*60}")
                            logger.info(f"  [{tag_name}]:")
                            logger.info(f"    原始: {original_text}")
                            logger.info(f"    转换: {converted_text}")
                            conversion_details.append({
                                'field': tag_name,
                                'original': original_text,
                                'converted': converted_text
                            })
                        else:
                            logger.info(f"  转换{tag_name}: {original_text} -> {converted_text}")
                            # TODO: 实际写入WAV INFO标签（需要重写整个INFO块）
                            logger.warning(f"  注意: WAV文件的标签修改需要重写整个INFO块，当前版本暂不支持实际修改")
                        
                        converted = True
            
            if self.dry_run and conversion_details:
                logger.info(f"  ---- 共 {len(conversion_details)} 个字段需要转换 ----")
            
            return converted
            
        except Exception as e:
            logger.error(f"处理WAV文件时出错 {file_path}: {e}")
            return False
    
    def process_generic_file(self, file_path: Path) -> bool:
        """
        使用通用方法处理音频文件
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            是否成功转换
        """
        # 尝试使用通用的mutagen处理
        audio = File(file_path)
        if audio is None:
            logger.warning(f"  无法识别文件格式: {file_path}")
            return False
        
        converted = False
        conversion_details = []
        if hasattr(audio, 'tags') and audio.tags:
            for key, value in audio.tags.items():
                if isinstance(value, str):
                    converted_text, did_convert = self.convert_text_to_utf8(value, field=str(key), file_path=file_path)
                    if did_convert:
                        if self.dry_run:
                            # 测试模式下，首次发现需要转换时才显示文件信息
                            if not conversion_details:
                                logger.info(f"\n{'='*60}")
                                logger.info(f"文件: {file_path}")
                                logger.info(f"{'='*60}")
                            logger.info(f"  [标签 {key}]:")
                            logger.info(f"    原始: {value}")
                            logger.info(f"    转换: {converted_text}")
                            conversion_details.append({
                                'field': key,
                                'original': value,
                                'converted': converted_text
                            })
                        else:
                            logger.info(f"  转换标签 {key}: {value} -> {converted_text}")
                            audio.tags[key] = converted_text
                        converted = True
                elif hasattr(value, 'text') and value.text:
                    # 处理ID3标签对象（如TPE1, TIT2等）
                    new_texts = []
                    frame_converted = False
                    for text_item in value.text:
                        if isinstance(text_item, str):
                            converted_text, did_convert = self.convert_text_to_utf8(text_item, field=str(key), file_path=file_path)
                            if did_convert:
                                if self.dry_run:
                                    # 测试模式下，首次发现需要转换时才显示文件信息
                                    if not conversion_details:
                                        logger.info(f"\n{'='*60}")
                                        logger.info(f"文件: {file_path}")
                                        logger.info(f"{'='*60}")
                                    logger.info(f"  [标签 {key}]:")
                                    logger.info(f"    原始: {text_item}")
                                    logger.info(f"    转换: {converted_text}")
                                    conversion_details.append({
                                        'field': key,
                                        'original': text_item,
                                        'converted': converted_text
                                    })
                                else:
                                    logger.info(f"  转换标签 {key}: {text_item} -> {converted_text}")
                                new_texts.append(converted_text)
                                frame_converted = True
                            else:
                                new_texts.append(text_item)
                        else:
                            new_texts.append(text_item)
                    
                    if frame_converted:
                        if not self.dry_run:
                            # 更新ID3标签的文本内容
                            value.text = new_texts
                            value.encoding = 3  # UTF-8编码
                        converted = True
                elif isinstance(value, list):
                    new_values = []
                    list_converted = False
                    for item in value:
                        if isinstance(item, str):
                            converted_text, did_convert = self.convert_text_to_utf8(item, field=str(key), file_path=file_path)
                            if did_convert:
                                if self.dry_run:
                                    # 测试模式下，首次发现需要转换时才显示文件信息
                                    if not conversion_details:
                                        logger.info(f"\n{'='*60}")
                                        logger.info(f"文件: {file_path}")
                                        logger.info(f"{'='*60}")
                                    logger.info(f"  [标签 {key}]:")
                                    logger.info(f"    原始: {item}")
                                    logger.info(f"    转换: {converted_text}")
                                    conversion_details.append({
                                        'field': key,
                                        'original': item,
                                        'converted': converted_text
                                    })
                                else:
                                    logger.info(f"  转换标签 {key}: {item} -> {converted_text}")
                                new_values.append(converted_text)
                                list_converted = True
                            else:
                                new_values.append(item)
                        else:
                            new_values.append(item)
                    
                    if list_converted:
                        if not self.dry_run:
                            audio.tags[key] = new_values
                        converted = True
        
        if self.dry_run and conversion_details:
            logger.info(f"  ---- 共 {len(conversion_details)} 个字段需要转换 ----")
        
        if converted and not self.dry_run:
            try:
                audio.save()
                logger.info(f"  已保存: {file_path}")
            except Exception as e:
                logger.error(f"  保存文件失败: {e}")
                return False
        
        return converted
    
    def process_audio_file(self, file_path: Path) -> bool:
        """
        处理单个音频文件
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            是否成功转换
        """
        # 测试模式下先不显示文件信息，等确认有转换内容再显示
        if not self.dry_run:
            logger.info(f"处理文件: {file_path}")
        
        ext = file_path.suffix.lower()
        
        try:
            if ext == '.mp3':
                return self.process_mp3_file(file_path)
            elif ext == '.flac':
                return self.process_flac_file(file_path)
            elif ext in ['.m4a', '.mp4']:
                return self.process_mp4_file(file_path)
            elif ext == '.wav':
                return self.process_wav_file(file_path)
            else:
                # 使用通用方法处理其他格式
                return self.process_generic_file(file_path)
                
        except Exception as e:
            logger.error(f"处理文件失败 {file_path}: {e}")
            return False
    
    def list_metadata(self, file_path: Path) -> dict:
        """列出音频文件的元数据

        Args:
            file_path: 音频文件路径

        Returns:
            元数据字典
        """
        metadata = {}
        ext = file_path.suffix.lower()

        try:
            if ext == '.mp3':
                try:
                    audio = ID3(file_path)
                    # 提取常见的ID3标签
                    tag_mapping = {
                        'TIT2': '标题',
                        'TPE1': '艺术家',
                        'TALB': '专辑',
                        'TPE2': '专辑艺术家',
                        'TCON': '流派',
                        'TYER': '年份',
                        'TRCK': '音轨',
                    }
                    for frame_id, name in tag_mapping.items():
                        if frame_id in audio:
                            frame = audio[frame_id]
                            if frame.text:
                                metadata[name] = str(frame.text[0])
                    # 处理注释
                    comments = []
                    for frame in audio.getall('COMM'):
                        if frame.text:
                            for text in frame.text:
                                comments.append(str(text))
                    if comments:
                        metadata['注释'] = '; '.join(comments)
                except ID3NoHeaderError:
                    pass

            elif ext == '.flac':
                audio = FLAC(file_path)
                tag_mapping = {
                    'title': '标题',
                    'artist': '艺术家',
                    'album': '专辑',
                    'albumartist': '专辑艺术家',
                    'genre': '流派',
                    'date': '日期',
                    'tracknumber': '音轨号',
                    'comment': '注释'
                }
                for tag, name in tag_mapping.items():
                    if tag in audio:
                        values = audio[tag]
                        if values:
                            metadata[name] = '; '.join(values)

            elif ext in ['.m4a', '.mp4']:
                audio = MP4(file_path)
                tag_mapping = {
                    '\xa9nam': '标题',
                    '\xa9ART': '艺术家',
                    '\xa9alb': '专辑',
                    '\xa9cmt': '注释',
                    '\xa9gen': '流派',
                    '\xa9day': '年份',
                    '\xa9wrt': '作曲家',
                    'aART': '专辑艺术家',
                }
                for tag, name in tag_mapping.items():
                    if tag in audio:
                        values = audio[tag]
                        if values:
                            metadata[name] = '; '.join(str(v) for v in values if not isinstance(v, tuple))
                # 处理音轨号
                if 'trkn' in audio:
                    trkn = audio['trkn'][0]
                    if isinstance(trkn, tuple):
                        metadata['音轨号'] = f"{trkn[0]}/{trkn[1]}" if len(trkn) > 1 else str(trkn[0])

            elif ext == '.wav':
                # 尝试读取WAV INFO标签
                info_tags = self.parse_wav_info_tags(file_path)
                if info_tags:
                    metadata.update(info_tags)
                # 也尝试用mutagen读取ID3标签（某些WAV文件可能有）
                audio = File(file_path)
                if audio and hasattr(audio, 'tags') and audio.tags:
                    for key, value in audio.tags.items():
                        if isinstance(value, str):
                            metadata[str(key)] = value
                        elif hasattr(value, 'text'):
                            metadata[str(key)] = '; '.join(str(t) for t in value.text)

            else:
                # 使用通用方法
                audio = File(file_path)
                if audio and hasattr(audio, 'tags') and audio.tags:
                    for key, value in audio.tags.items():
                        if isinstance(value, str):
                            metadata[str(key)] = value
                        elif hasattr(value, 'text'):
                            metadata[str(key)] = '; '.join(str(t) for t in value.text)
                        elif isinstance(value, list):
                            metadata[str(key)] = '; '.join(str(v) for v in value)

            # 添加文件信息 - 需要重新读取文件以获取info
            try:
                audio_with_info = File(file_path)
                if audio_with_info and hasattr(audio_with_info, 'info'):
                    info = audio_with_info.info
                    if hasattr(info, 'length'):
                        length = info.length
                        minutes = int(length // 60)
                        seconds = int(length % 60)
                        metadata['时长'] = f"{minutes}:{seconds:02d}"
                    if hasattr(info, 'bitrate'):
                        metadata['比特率'] = f"{info.bitrate} bps"
                    if hasattr(info, 'sample_rate'):
                        metadata['采样率'] = f"{info.sample_rate} Hz"
                    if hasattr(info, 'channels'):
                        metadata['声道数'] = str(info.channels)
            except:
                pass  # 忽略获取音频信息的错误

        except Exception as e:
            metadata['错误'] = str(e)

        return metadata

    def run(self):
        """运行转换过程"""
        logger.info("=" * 60)
        logger.info(f"Audio Meta Fixer v{__version__}")
        logger.info(f"作者: {__author__} | 许可证: {__license__}")
        logger.info("-" * 60)

        if self.list_only:
            logger.info(f"列出音频文件元数据")
            logger.info(f"目标目录: {self.target_dir}")
        else:
            logger.info(f"开始转换音频文件元数据编码")
            logger.info(f"目标目录: {self.target_dir}")
            mode_info = []
            if self.dry_run:
                mode_info.append("测试模式（不修改文件）")
            if self.interactive:
                mode_info.append("交互模式")
            if not mode_info:
                mode_info.append("正常模式")
            logger.info(f"模式: {' + '.join(mode_info)}")
        logger.info("=" * 60)
        
        # 扫描音频文件
        audio_files = self.scan_audio_files()

        if not audio_files:
            logger.info("未找到音频文件")
            return

        self.total_files = len(audio_files)
        logger.info(f"找到 {self.total_files} 个音频文件")

        if self.list_only:
            # 列出元数据模式
            logger.info("\n" + "=" * 60)
            for file_path in audio_files:
                self.processed_count += 1
                logger.info(f"\n[{self.processed_count}/{self.total_files}] {file_path.relative_to(self.target_dir)}")
                logger.info("-" * 60)

                metadata = self.list_metadata(file_path)

                if metadata:
                    # 计算最长的键名长度用于对齐
                    max_key_length = max(len(key) for key in metadata.keys()) if metadata else 0

                    for key, value in metadata.items():
                        # 格式化输出，键名右对齐
                        logger.info(f"  {key:>{max_key_length}}: {value}")
                else:
                    logger.info("  (无元数据)")

            logger.info("\n" + "=" * 60)
            logger.info(f"列出完成！共 {self.processed_count} 个文件")
            logger.info("=" * 60)
        else:
            # 转换模式
            for file_path in audio_files:
                try:
                    self.processed_count += 1

                    # 设置当前进度信息
                    self.current_progress = f"[{self.processed_count}/{self.total_files}] 处理文件: {file_path}"

                    # 在交互模式下显示进度
                    if self.interactive:
                        print(f"\n{self.current_progress}")

                    if self.process_audio_file(file_path):
                        self.converted_count += 1
                except Exception as e:
                    logger.error(f"处理文件时出错 {file_path}: {e}")
                    self.error_count += 1

            # 输出统计信息
            logger.info("=" * 60)
            logger.info("转换完成！")
            logger.info(f"处理文件数: {self.processed_count}")
            logger.info(f"转换文件数: {self.converted_count}")
            logger.info(f"错误文件数: {self.error_count}")
            logger.info("=" * 60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Audio Meta Fixer - 音频元数据编码修复工具，将中文编码转换为UTF-8',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  audio_meta_fixer.py /path/to/music                    # 交互模式转换指定目录下的所有音频文件（默认）
  audio_meta_fixer.py /path/to/music --list             # 列出指定目录下所有音频文件的元数据
  audio_meta_fixer.py /path/to/music --dry-run          # 测试模式，只显示将要转换的内容
  audio_meta_fixer.py /path/to/music --direct           # 直接模式，自动处理所有转换不询问用户
  audio_meta_fixer.py .                                 # 交互模式转换当前目录下的所有音频文件

Author: Claude (Anthropic) | Version: 1.0.0 | License: MIT
        """
    )
    
    parser.add_argument(
        'directory',
        help='要处理的目录路径'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='列出目录下所有音频文件的元数据信息'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='测试模式，不实际修改文件，只显示将要进行的转换'
    )

    parser.add_argument(
        '--direct',
        action='store_true',
        help='直接模式，自动处理所有转换不询问用户（默认为交互模式）'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'Audio Meta Fixer v{__version__} by {__author__}'
    )
    
    args = parser.parse_args()
    
    # 验证目录
    target_dir = Path(args.directory)
    if not target_dir.exists():
        logger.error(f"目录不存在: {target_dir}")
        sys.exit(1)
    
    if not target_dir.is_dir():
        logger.error(f"不是有效的目录: {target_dir}")
        sys.exit(1)
    
    # 创建转换器并运行
    # 默认交互模式，除非使用--direct参数
    interactive = not args.direct and not args.list  # 列出模式时不需要交互
    converter = AudioMetadataConverter(args.directory, args.dry_run, interactive, args.list)
    
    try:
        converter.run()
    except KeyboardInterrupt:
        logger.info("\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()