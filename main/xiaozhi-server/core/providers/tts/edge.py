import os
import uuid
import edge_tts
from datetime import datetime
from core.providers.tts.base import TTSProviderBase

# =============================================================================
# [兼容补丁 2026-10-13] 微软 Edge Read Aloud 由 v1 迁移到 v2，旧端点 403
# -----------------------------------------------------------------------------
# 现象：
#   Edge TTS请求失败: 403, message='Invalid response status',
#   url=wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?...
#   设备端表现为「能听懂、会思考、但不出声」。
#
# 根因（已实测确认，不是网络被墙、也不是系统时钟不准）：
#   · 音色列表接口仍返回 200，说明 TrustedClientToken 有效；
#   · 直连与走代理（FlClash 7890，可正常访问 Google/HuggingFace）均返回 403；
#   · 微软自 2026-10 起分区域灰度，把 Edge 朗读服务从
#       wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1
#     迁移到
#       wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1
#     已升级到 v2 的后端节点会用 403 直接拒绝旧的 v1 握手。
#
# 上游进展：rany2/edge-tts issue #490 / PR #491。补丁尚未随 PyPI 版本发布，
#           故此处就地打补丁。上游发版修好后，本段可整段删除（下方有自动判断，
#           一旦端点不再指向旧域名就不动手）。
# =============================================================================
_LEGACY_WSS_HOST = "speech.platform.bing.com"
_V2_WSS_URL = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    "?Ocp-Apim-Subscription-Key=" + edge_tts.constants.TRUSTED_CLIENT_TOKEN
)


def _apply_edge_tts_v2_patch():
    """把 edge_tts 的合成端点切到 v2。仅在它仍指向旧 v1 端点时才替换。"""
    try:
        import edge_tts.communicate as _communicate
    except Exception:
        return
    if _LEGACY_WSS_HOST in getattr(_communicate, "WSS_URL", ""):
        _communicate.WSS_URL = _V2_WSS_URL


_apply_edge_tts_v2_patch()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        if config.get("private_voice"):
            self.voice = config.get("private_voice")
        else:
            self.voice = config.get("voice")
        self.audio_file_type = config.get("format", "mp3")

    def generate_filename(self, extension=".mp3"):
        return os.path.join(
            self.output_file,
            f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}",
        )

    async def text_to_speak(self, text, output_file):
        try:
            communicate = edge_tts.Communicate(text, voice=self.voice)
            if output_file:
                # 确保目录存在并创建空文件
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "wb") as f:
                    pass

                # 流式写入音频数据
                with open(output_file, "ab") as f:  # 改为追加模式避免覆盖
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":  # 只处理音频数据块
                            f.write(chunk["data"])
            else:
                # 返回音频二进制数据
                audio_bytes = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]
                return audio_bytes
        except Exception as e:
            error_msg = f"Edge TTS请求失败: {e}"
            raise Exception(error_msg)  # 抛出异常，让调用方捕获