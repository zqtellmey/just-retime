import os
import sys
import time
import requests
from seleniumbase import SB

# ==================== 配置项 ====================
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
LOGIN_URL = os.getenv("LOGIN_URL", "")
TARGET_URL = os.getenv("TARGET_URL", "")
USER_EMAIL = os.getenv("USER_EMAIL", "")
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD", "")

# ==================== 坐标配置 ====================
# 已验证的坐标
CHECKBOX_X = 830
CHECKBOX_Y = 640
# =================================================

def send_telegram_message(message, image_path=None):
    """发送消息到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(image_path, "rb") as photo:
                requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": message}, files={"photo": photo}, timeout=15)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=15)
    except Exception as e:
        print(f"[ERROR] Telegram 发送失败: {e}")

def handle_popup_turnstile(sb):
    """处理 Reset 弹窗验证，直接点击固定坐标"""
    try:
        # 检测是否存在 Turnstile
        if sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null'):
            print(f"[INFO] 检测到弹窗 Turnstile，点击坐标 ({CHECKBOX_X}, {CHECKBOX_Y})...")
            sb.uc_gui_click_x_y(CHECKBOX_X, CHECKBOX_Y)
            time.sleep(4)
            return True
        return True
    except Exception as e:
        print(f"[WARN] 弹窗验证点击异常: {e}")
        return False

def main():
    opts = {"uc": True, "test": True, "locale": "zh", "headed": False}

    with SB(**opts) as sb:
        sb.driver.set_window_size(1920, 1080)
        
        # 1. 登录流程
        sb.driver.get(LOGIN_URL)
        time.sleep(3)
        sb.type('input[name="Email"]', USER_EMAIL)
        sb.type('//*[@id="password"]', FIXED_PASSWORD)
        
        # 登录页使用自动穿透
        sb.uc_gui_click_captcha()
        sb.click('button[type="submit"]')
        time.sleep(5)

        # 2. 跳转并重置
        sb.driver.get(TARGET_URL)
        sb.wait_for_element('button[aria-label="Reset timer"]', timeout=20)
        sb.click('button[aria-label="Reset timer"]')
        time.sleep(3)

        # 执行弹窗固定坐标点击
        handle_popup_turnstile(sb)

        # 3. 后续操作
        sb.click('xpath://button[contains(., "Just Reset")]')
        time.sleep(3)
        
        # 尝试点击 Start
        try:
            sb.click('xpath://button[contains(normalize-space(text()), "Start")]')
        except:
            pass
            
        print("[INFO] 任务执行完毕。")
        send_telegram_message("✅ 任务已成功执行完成！")

if __name__ == "__main__":
    main()
