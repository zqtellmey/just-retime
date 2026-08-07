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
CHECKBOX_X = 830
CHECKBOX_Y = 640
# =================================================

def send_telegram_message(message, image_path=None):
    """发送消息和截图到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[INFO] Telegram 未配置，跳过消息发送。")
        return
    
    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(image_path, "rb") as photo:
                payload = {"chat_id": TG_CHAT_ID, "caption": message}
                files = {"photo": photo}
                requests.post(url, data=payload, files=files, timeout=15)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}
            requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print(f"[ERROR] 发送 Telegram 消息失败: {e}")

def accept_cookies_if_present(sb):
    """检测并点击 Cookie 询问框的 Accept All 按钮"""
    try:
        cookie_btn = sb.find_element('button.cky-btn-accept', timeout=3)
        if cookie_btn:
            sb.click('button.cky-btn-accept')
            time.sleep(2)
    except Exception:
        pass

def main():
    if not USER_EMAIL or not FIXED_PASSWORD or not LOGIN_URL or not TARGET_URL:
        print("[ERROR] 缺少必要的环境变量，请检查配置。")
        sys.exit(1)

    opts = {
        "uc": True,
        "test": True,
        "locale": "zh",
        "headed": False,
        "timeout_multiplier": 0.5
    }

    print("🚀 正在初始化 SeleniumBase 环境...")

    try:
        with SB(**opts) as sb:
            sb.driver.set_page_load_timeout(45)
            sb.driver.set_window_size(1920, 1080)
            
            screenshot_path = "step_screenshot.png"

            # ==================== 第一步：登录 ====================
            print(f"[INFO] 正在打开登录页面: {LOGIN_URL}")
            sb.driver.get(LOGIN_URL)
            time.sleep(5)

            accept_cookies_if_present(sb)

            print("[INFO] 正在输入邮箱...")
            sb.wait_for_element('input[name="Email"]', timeout=15)
            sb.type('input[name="Email"]', USER_EMAIL)
            time.sleep(2)

            print("[INFO] 正在输入密码...")
            sb.wait_for_element('//*[@id="password"]', timeout=15)
            sb.type('//*[@id="password"]', FIXED_PASSWORD)
            time.sleep(2)

            print("[INFO] 启动登录页验证检测...")
            for cf_attempt in range(3):
                try:
                    if sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null'):
                        sb.uc_gui_click_captcha()
                        time.sleep(3)
                        cf_token = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']").value')
                        if cf_token and len(cf_token.strip()) > 0:
                            break
                except Exception:
                    pass
                time.sleep(3)

            print("[INFO] 正在点击登录按钮...")
            sb.click('button[type="submit"]')
            time.sleep(5)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("📸 【步骤 1/2】账号登录表单已提交。", screenshot_path)

            # ==================== 第二步：进入后台并重置 ====================
            print(f"[INFO] 正在跳转到目标页面: {TARGET_URL}")
            sb.driver.get(TARGET_URL)
            time.sleep(5)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("📸 【步骤 2/2】已跳转至目标后台页面。", screenshot_path)

            print("[INFO] 正在点击 Reset timer...")
            sb.wait_for_element('button[aria-label="Reset timer"]', timeout=20)
            sb.click('button[aria-label="Reset timer"]')

            print("[INFO] 等待 Reset 弹窗加载...")
            time.sleep(4)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("📸 【步骤 2/2】已点击 Reset timer 按钮，弹窗界面现场。", screenshot_path)

            # Reset 弹窗人机验证：直接点击固定坐标
            print(f"[INFO] 触发 Reset 弹窗人机验证，点击固定坐标: ({CHECKBOX_X}, {CHECKBOX_Y})")
            for cf_attempt in range(4):
                try:
                    if sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null'):
                        sb.uc_gui_click_x_y(CHECKBOX_X, CHECKBOX_Y)
                        time.sleep(3)
                        cf_token = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']").value')
                        if cf_token and len(cf_token.strip()) > 0:
                            print("[INFO] Reset 弹窗 Token 验证成功注入！")
                            break
                except Exception:
                    pass
                time.sleep(3)

            # 查找并点击 Just Reset 按钮
            print("[INFO] 正在查找 Just Reset 按钮...")
            just_reset_selector = 'xpath://button[contains(., "Just Reset")]'
            sb.wait_for_element(just_reset_selector, timeout=20)
            sb.click(just_reset_selector)
            time.sleep(3)

            # 读取剩余时间
            try:
                remaining_time_elem = sb.find_element('span.hidden.sm\\:inline')
                remaining_time_text = remaining_time_elem.text
            except Exception:
                remaining_time_text = "未能成功获取剩余时间"

            # 检查 Start 按钮是否存在
            start_clicked = False
            try:
                start_btn = sb.find_element('xpath://button[contains(normalize-space(text()), "Start")]')
                if start_btn:
                    sb.click('xpath://button[contains(normalize-space(text()), "Start")]')
                    start_clicked = True
                    time.sleep(3)
            except Exception:
                pass

            sb.save_screenshot(screenshot_path)
            msg = (
                f"🎉 【步骤 2/2】操作执行完成！\n"
                f"⏱️ 剩余时间: {remaining_time_text}\n"
                f"▶️ Start 按钮已点击: {'是' if start_clicked else '否'}"
            )
            send_telegram_message(msg, screenshot_path)
            print("[INFO] 所有步骤顺利执行完毕！")

    except Exception as e:
        error_msg = f"🚨 [ERROR] 任务执行过程中发生异常: {str(e)}"
        print(error_msg)
        screenshot_path = "step_screenshot.png"
        try:
            sb.save_screenshot(screenshot_path)
            send_telegram_message(error_msg, screenshot_path)
        except Exception:
            send_telegram_message(error_msg)
    finally:
        screenshot_path = "step_screenshot.png"
        if os.path.exists(screenshot_path):
            try:
                os.remove(screenshot_path)
            except Exception:
                pass

if __name__ == "__main__":
    main()
