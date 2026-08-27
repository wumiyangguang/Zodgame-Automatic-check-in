"""推送通知模块。

渠道设计：
- 每个渠道是一个签名为 (title, content, config) -> bool 的函数
- 通过 register_channel() 注册到全局渠道表
- send() 依次调用所有已注册渠道
- 渠道内部自行判断是否配置完整，未配置则跳过
- 所有配置从配置文件 push 段读取，不依赖环境变量

添加新渠道示例：
    @register_channel
    def my_channel(title, content, config):
        key = config.get("my_key", "")
        if not key:
            return False
        # ... 推送逻辑 ...
        return True
"""
import json
import logging

import requests

logger = logging.getLogger(__name__)

# ========== 渠道注册表 ==========

_channels = []

# ========== 配置解析 ==========

# 渠道字段默认值（新增渠道时在此追加字段，保证推送模块自包含）
PUSH_DEFAULTS = {
    "hitokoto": False,
    "onebot_enabled": False,
    "onebot_url": "",
    "onebot_targets": "",
    "onebot_token": "",
}


def _resolve_push_config(config: dict) -> dict:
    """解析推送配置：支持嵌套（整个项目配置，含 push 段）与平铺（push 段）两种形式，并用默认值兜底。"""
    if isinstance(config, dict) and isinstance(config.get("push"), dict):
        config = config["push"]
    return {**PUSH_DEFAULTS, **(config or {})}


def register_channel(func):
    """注册一个推送渠道（可用作装饰器）。

    渠道函数签名：(title: str, content: str, config: dict) -> bool
    返回 True 表示推送成功，False 表示跳过或失败。
    """
    _channels.append(func)
    return func


# ========== 内置渠道 ==========

@register_channel
def _qmsg_push(title: str, content: str, config: dict) -> bool:
    """QMSG 酱推送。

    配置项：push.qmsg_key / push.qmsg_type
    文档：https://qmsg.zendee.cn/api
    """
    # 渠道开关：默认关闭，显式 true 才启用
    if not config.get("qmsg_enabled"):
        return False

    key = config.get("qmsg_key", "")
    qtype = config.get("qmsg_type", "send")

    if not key:
        return False

    url = f"https://qmsg.zendee.cn/{qtype}/{key}"
    logger.debug("QMSG 推送 -> %s", qtype)

    try:
        resp = requests.post(url, params={"msg": f"{title}\n\n{content}"}, timeout=(5, 10))
        data = resp.json()
    except requests.RequestException:
        logger.exception("QMSG 推送网络异常")
        return False
    except json.JSONDecodeError:
        logger.error("QMSG 响应解析失败: %s", resp.text[:200])
        return False

    if data.get("code") == 0:
        logger.info("QMSG 推送成功")
        return True
    else:
        logger.error("QMSG 推送失败: %s", data.get("reason", "未知"))
        return False


@register_channel
def _onebot_push(title: str, content: str, config: dict) -> bool:
    """OneBot 11 协议 HTTP API 推送（兼容 NapCat 等协议端）。

    配置项：push.onebot_url / push.onebot_targets / push.onebot_token
    协议：POST http://<onebot_url>/send_group_msg（群聊）或 /send_private_msg（私聊）
    适配：消息中的 @at=-1@（qmsg 的 @全员 语法）自动替换为 OneBot CQ 码 [CQ:at,qq=all]
    """
    # 渠道开关：默认关闭，显式 true 才启用
    if not config.get("onebot_enabled"):
        return False

    base_url = (config.get("onebot_url") or "").rstrip("/")
    targets = config.get("onebot_targets") or ""

    if not base_url or not targets:
        return False

    # @全员 语法适配（纯文本级转换，不绑定业务逻辑）
    text = f"{title}\n\n{content}".replace("@at=-1@", "[CQ:at,qq=all]")

    headers = {"Content-Type": "application/json"}
    token = config.get("onebot_token") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"

    success_count = 0
    for target in targets.split(","):
        target = target.strip()
        if target.startswith("group_id="):
            endpoint, payload_key = "send_group_msg", "group_id"
        elif target.startswith("user_id="):
            endpoint, payload_key = "send_private_msg", "user_id"
        else:
            logger.warning("OneBot 目标格式无效，跳过: %s", target)
            continue

        try:
            chat_id = int(target.split("=", 1)[1])
        except ValueError:
            logger.warning("OneBot 目标号码无效，跳过: %s", target)
            continue

        payload = {payload_key: chat_id, "message": text}
        try:
            resp = requests.post(
                f"{base_url}/{endpoint}",
                headers=headers,
                json=payload,
                timeout=(5, 10),
            )
            data = resp.json()
        except requests.RequestException:
            logger.exception("OneBot 推送网络异常: %s", endpoint)
            continue
        except json.JSONDecodeError:
            logger.error("OneBot 响应解析失败: %s", resp.text[:200])
            continue

        if data.get("status") == "ok" or data.get("retcode") == 0:
            logger.info("OneBot 推送成功: %s=%s", payload_key, chat_id)
            success_count += 1
        else:
            logger.error("OneBot 推送失败: %s=%s，响应: %s", payload_key, chat_id, data)

    return success_count > 0


# ========== 公共接口 ==========

def _fetch_hitokoto() -> str:
    """获取一条一言（随机句子）。

    Returns:
        句子 + 出处，失败时返回空字符串。
    """
    try:
        resp = requests.get("https://v1.hitokoto.cn/", timeout=10)
        data = resp.json()
        hitokoto = data.get("hitokoto", "")
        source = data.get("from", "")
        if hitokoto:
            return f"{hitokoto}    ----{source}"
    except Exception:
        logger.debug("获取一言失败", exc_info=True)
    return ""


def send(title: str, content: str, config: dict = None) -> None:
    """推送消息到所有已配置的渠道。

    Args:
        title: 推送标题
        content: 推送正文
        config: 推送配置字典（来自 load_config 的 push 部分）
    """
    if config is None:
        config = {}
    # 解析推送配置（嵌套/平铺兼容 + 默认值兜底）
    config = _resolve_push_config(config)

    if not content:
        logger.warning("推送内容为空，跳过推送")
        return

    # 启用一言时追加到正文末尾（兼容布尔值和字符串）
    hitokoto = config.get("hitokoto")
    if hitokoto and hitokoto != "false":
        quote = _fetch_hitokoto()
        if quote:
            content += f"\n\n{quote}"
            logger.debug("已追加一言: %s", quote[:30])

    if not _channels:
        logger.warning("无可用推送渠道")
        return

    # 打印推送信息到日志
    logger.info("推送标题: %s", title)
    logger.info("推送内容:\n%s", content)

    success_count = 0
    for channel in _channels:
        try:
            if channel(title, content, config):
                success_count += 1
        except Exception:
            logger.exception("推送渠道 %s 异常", channel.__name__)

    if success_count == 0:
        logger.warning("所有推送渠道均未成功（可能未配置或全部失败）")
    else:
        logger.info("推送完成，成功 %d/%d 个渠道", success_count, len(_channels))
