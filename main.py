import os
import cloudscraper
from util import (
    cookie_str_to_dict,
    get_formhash,
    check_cookie,
    get_random_mood,
    extract_sign_info,
    load_config,
    send_notification,
)
from config import *
import sys
from typing import Dict, List

CONFIG_ENV_VAR = "ZODGAME_CONFIG_PATH"
config_path = os.getenv(CONFIG_ENV_VAR, "config.json")

def create_scraper() -> cloudscraper.CloudScraper:
    """
    创建 cloudscraper 实例
    :return: cloudscraper 实例
    """
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )


def check_in(scraper: cloudscraper.CloudScraper, account: Dict) -> str:
    """
    执行签到操作
    :param scraper: cloudscraper 实例
    :param account: 账号信息
    :return: 签到结果
    """
    print(f"{account['name']}: 正在签到...")

    # 转换为 Cookie 字典
    custom_cookies = cookie_str_to_dict(account["cookie"])

    try:
        # 检查 Cookie 是否有效
        if not check_cookie(scraper, SIGN_IN_PAGE_URL, custom_cookies):
            return f"{account['name']}: ❌ Cookie 无效"

        # 获取 formhash
        formhash = get_formhash(scraper, SIGN_IN_PAGE_URL, custom_cookies)

        # 获取随机心情
        mood = get_random_mood()

        # 准备签到数据
        data = {"formhash": formhash, "qdxq": mood}

        # 发送签到请求
        response = scraper.post(
            CHECKIN_URL, headers=HEADERS, cookies=custom_cookies, data=data, timeout=10
        )

        # 处理签到结果
        result = extract_sign_info(response.text)

        if result["sign_status"] == "success":
            return f"{account['name']}: ✅ 签到成功！获得随机奖励 {result['reward_item']} {result['reward_count']} {result['reward_unit']}"
        elif result["sign_status"] == "duplicate":
            return f"{account['name']}: ✅ {result['error_msg']}"
        else:
            return (
                f"{account['name']}: ❌ 签到失败: {result.get('error_msg', '未知错误')}"
            )

    except Exception as e:
        return f"{account['name']}: ❌ 签到异常: {str(e)}"


def main():
    """
    主函数
    """
    # 加载配置
    config = load_config(config_path)

    # 检查配置
    if not config.get("accounts"):
        print("❌ 配置文件中未找到账号信息")
        sys.exit(1)

    accounts: List[Dict] = config["accounts"]
    scraper = create_scraper()

    print("\n======== 开始签到 ========")

    results = []
    for account in accounts:
        # 检查账号是否启用
        if not account.get("enabled", True):
            print(f"{account['name']}: ⚠️  账号已禁用，跳过签到")
            continue

        result = check_in(scraper, account)
        results.append(result)

    print("\n======== 签到结果 ========")
    for result in results:
        print(result)

    # 发送通知（如果启用）
    notification_config = config.get("notification", {})
    send_notification(notification_config, results)

    print("\n======== 签到完成 ========")


if __name__ == "__main__":
    main()
