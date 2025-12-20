from math import fabs
import re
import random
import json
import sys
import cloudscraper
from lxml import etree
from config import MOODS
from typing import Dict, Optional

def load_config(path: str) -> Dict:
    """
    加载配置文件，若文件不存在则自动创建模板配置
    :param path: 配置文件路径
    :return: 配置字典
    """
    # 定义配置文件模板（按用户要求的结构）
    config_template = {
        "accounts": [
            {
                "name": "账号1",
                "cookie": "",
                "enabled": True
            },
            {
                "name": "账号2",
                "cookie": "",
                "enabled": False
            },
        ],
        "notification": {
            "enabled": False
        }
    }

    try:
        # 尝试读取配置文件
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # 配置文件不存在，创建模板文件
        try:
            with open(path, "w", encoding="utf-8") as f:
                # 用 indent=2 格式化JSON，增强可读性
                json.dump(config_template, f, ensure_ascii=False, indent=2)
            print(f"✅ 配置文件 {path} 不存在，已自动创建模板配置")
            return config_template  # 返回模板配置字典
        except PermissionError:
            print(f"❌ 无权限创建配置文件 {path}（检查文件写入权限）")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 创建配置文件 {path} 失败：{str(e)}")
            sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ 配置文件 {path} 格式错误（非合法JSON）")
        sys.exit(1)
    except Exception as e:
        # 捕获其他未知异常（如文件损坏、编码错误等）
        print(f"❌ 加载配置文件 {path} 失败：{str(e)}")
        sys.exit(1)

def check_cookie(scraper: cloudscraper.CloudScraper, url: str, cookies: dict) -> bool:
    """
    检查 Cookie 是否可用
    :param scraper: cloudscraper 实例
    :param url: 目标检测 URL
    :param cookies: Cookie 字典
    :return: 如果可用则返回 True，否则返回 False
    """
    VALID_FEATURE = "每日签到 -  ZodGame论坛"
    INVALID_FEATURE = "登录 -  ZodGame论坛"

    try:
        req = scraper.get(
            url,
            cookies=cookies,
            timeout=10 
        )
        # 打印调试信息
        # print(f"请求状态码: {req.status_code}")
        # print(f"响应内容前500个字符: {req.text[:500]}")

        # 第一步：校验状态码是否为200
        if req.status_code != 200:
            print("Cookie无效：请求状态码非200")
            return False
        # 第二步：校验页面特征（核心判断逻辑）
        if VALID_FEATURE in req.text and INVALID_FEATURE not in req.text:
            return True
        elif INVALID_FEATURE in req.text:
            return False

    except Exception as e:  # 捕获其他意外异常
        print(f"未知错误：{str(e)}")
        return False

def cookie_str_to_dict(cookie_str: str) -> dict:
    """
    将 Cookie 字符串转换为字典
    :param cookie_str: 从浏览器复制的 Cookie 字符串
    :return: 格式化后的 Cookie 字典
    """
    cookie_dict = {}
    # 按 "; " 分割每个 Cookie 键值对
    for item in cookie_str.split("; "):
        if "=" in item:
            # 按第一个 "=" 分割（避免值中包含 "=" 的情况）
            key, value = item.split("=", 1)
            cookie_dict[key] = value
    return cookie_dict


def get_formhash(scraper: cloudscraper.CloudScraper, url: str, cookies: dict) -> str:
    """
    从签到页面获取 formhash
    :param scraper: cloudscraper 实例
    :param url: 签到页面 URL
    :param cookies: Cookie 字典
    :return: formhash 字符串
    :raises ValueError: 若无法提取 formhash 时触发
    """
    req = scraper.get(url, cookies=cookies, timeout=10)
    # 使用正则表达式提取 formhash
    formhash_match = re.search(r'name="formhash" value="([a-z0-9]+)"', req.text)
    if not formhash_match:
        raise ValueError("无法提取 formhash")
    return formhash_match.group(1)
    
    
def get_random_mood() -> str:
    """
    随机获取一个签到心情
    :return: 单个签到心情字符串（如 "kx"、"shuai"）
    :raises ValueError: 若MOODS列表为空时触发
    """
    if not MOODS:
        raise ValueError("签到心情列表MOODS不能为空！")
    return random.choice(MOODS)

def send_notification(config: Dict, results: List[str]) -> None:
    """
    发送通知
    :param config: 通知配置
    :param results: 签到结果列表
    """
    if not config.get('enabled', False):
        return
    
    try:
        import notify  # 仅在通知开启时尝试导入
    except ModuleNotFoundError:
        print("❌ 缺少 notify 模块，无法发送通知（请安装/创建 notify 模块）")
        return
    except Exception as e:
        print(f"❌ 导入 notify 模块失败：{str(e)}")
        return    

    print(f"\n======== 发送通知 ========")
    
    try:
        # 构建通知内容
        title = "ZodGame 签到结果"
        content = ""
        for result in results:
            content += result + "\n"
        
        notify.send(title, content)
        print("✅ 通知发送成功")
        
    except Exception as e:
        print(f"❌ 通知发送失败: {str(e)}")

def extract_sign_info(xml_str: str) -> Dict[str, Optional[str]]:
    """
    从签到返回的XML字符串中提取签到信息
    :param xml_str: 签到接口返回的XML字符串
    :return: 结构化的签到信息字典，可直接作为通知参数
    """
    # 初始化返回结果（默认值为None，代表提取失败）
    result = {
        "sign_status": None,    # 签到状态：success(成功)/duplicate(重复签到)/failed(失败)/unknown(未知)
        "reward_item": None,    # 奖励物品：如"酱油"（仅成功时有值）
        "reward_count": None,   # 奖励数量：如"4"（仅成功时有值）
        "reward_unit": None,    # 奖励单位：如"瓶"（仅成功时有值）
        "tips_text": None,      # 原始签到提示文本
        "error_msg": None       # 错误信息：解析失败/签到失败时填充
    }

    try:
        # 1. 解析XML字符串（处理编码和空白字符）
        parser = etree.XMLParser(remove_blank_text=True, encoding="utf-8")
        root = etree.fromstring(xml_str.encode("utf-8"), parser=parser)
        
        # 2. 提取CDATA中的核心文本
        cdata_text = root.text.strip() if root.text else ""
        if not cdata_text:
            result["error_msg"] = "XML中未提取到CDATA文本"
            return result

        # 3. 定义正则匹配模式（覆盖所有场景）
        # 模式1：签到成功
        pattern_success = re.compile(
            r"恭喜你签到成功!获得随机奖励\s+(\S+)\s+(\d+)\s+(\S+)\.",
            re.UNICODE | re.MULTILINE
        )
        # 模式2：重复签到
        pattern_duplicate = re.compile(r"您今日已经签到，请明天再来！", re.UNICODE)
        # 模式3：提取原始提示文本
        pattern_tips = re.compile(r'<div class="c">\s*(.+?)\s*</div>', re.UNICODE | re.DOTALL)

        # 4. 提取原始提示文本
        tips_match = pattern_tips.search(cdata_text)
        if tips_match:
            result["tips_text"] = tips_match.group(1).strip()

        # 5. 按场景匹配并更新结果
        # 场景A：签到成功
        success_match = pattern_success.search(cdata_text)
        if success_match:
            result["sign_status"] = "success"
            result["reward_item"] = success_match.group(1)
            result["reward_count"] = success_match.group(2)
            result["reward_unit"] = success_match.group(3)
        # 场景B：重复签到（今日已签）
        elif pattern_duplicate.search(cdata_text):
            result["sign_status"] = "duplicate"
            result["error_msg"] = "今日已完成签到，无需重复操作"
        # 场景C：其他签到失败
        elif "签到失败" in cdata_text or "权限不足" in cdata_text or "参数错误" in cdata_text:
            result["sign_status"] = "failed"
            result["error_msg"] = result["tips_text"] or "签到失败，原因未知"
        # 场景D：状态未知
        else:
            result["sign_status"] = "unknown"
            result["error_msg"] = "未匹配到签到相关的关键信息"

    except etree.XMLSyntaxError as e:
        # XML语法解析错误
        result["error_msg"] = f"XML解析失败：{str(e)}"
    except Exception as e:
        # 其他未知异常
        result["error_msg"] = f"提取签到信息失败：{str(e)}"

    return result


if __name__ == "__main__":
    # 测试用例1：重复签到的XML
    xml_duplicate = """<?xml version="1.0" encoding="utf-8"?>
<root><![CDATA[<script type="text/javascript" reload="1">
setTimeout("hideWindow('qwindow')", 3000);
</script>
<div class="f_c">
<h3 class="flb">
<em id="return_win">签到提示</em>
<span>
<a href="javascript:;" class="flbc" onclick="hideWindow('qwindow')" title="关闭">关闭</a></span>
</h3>
<div class="c">
您今日已经签到，请明天再来！ </div>
</div>
]]></root>"""

    # 测试用例2：签到成功的XML
    xml_success = """<?xml version="1.0" encoding="utf-8"?>
<root><![CDATA[<script type="text/javascript" reload="1">
setTimeout("window.location.href='plugin.php?id=dsu_paulsign:sign'", 3000);
</script>
<div class="f_c">
<h3 class="flb">
<em id="return_win">签到提示</em>
<span>
<a href="javascript:;" class="flbc" onclick="hideWindow('qwindow')" title="关闭">关闭</a></span>
</h3>
<div class="c">
恭喜你签到成功!获得随机奖励 酱油 4 瓶. </div>
</div>
]]></root>"""

    # 提取重复签到的信息
    print("=== 重复签到场景 ===")
    sign_info_dup = extract_sign_info(xml_duplicate)
    for key, value in sign_info_dup.items():
        print(f"{key}: {value}")

    # 提取签到成功的信息
    print("\n=== 签到成功场景 ===")
    sign_info_succ = extract_sign_info(xml_success)
    for key, value in sign_info_succ.items():
        print(f"{key}: {value}")
        
        