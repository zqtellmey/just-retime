import os
import time
import requests
from seleniumbase import SB

# ==================== 配置项（从 GitHub Secrets 环境变量读取） ====================
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

LOGIN_URL = os.getenv("LOGIN_URL")
TARGET_URL = os.getenv("TARGET_URL")

USER_EMAIL = os.getenv("USER_EMAIL")
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD")
# ======================================================================

def send_telegram_message(message, image_path=None):
    """发送消息和可选的截图到 Telegram"""
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

def handle_cloudflare_turnstile(sb, step_name):
    """处理 Cloudflare Turnstile 人机验证"""
    try:
        time.sleep(2)
        result = sb.driver.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result:
            return True
        
        print(f"[INFO] ({step_name}) 发现 Turnstile 拦截，尝试物理 GUI 点击...")
        sb.uc_gui_click_captcha()
        time.sleep(5)
        return True
    except Exception as e:
        print(f"[WARN] ({step_name}) 处理验证码异常: {e}")
        return False

def accept_cookies_if_present(sb):
    """检测并点击 Cookie 询问框的 Accept All 按钮"""
    try:
        print("[INFO] 检查是否存在 Cookie 询问框...")
        # 使用你提供的精确 CSS 选择器定位 Cookie 确认按钮
        cookie_btn = sb.find_element('button.cky-btn.cky-btn-accept', timeout=3)
        if cookie_btn:
            print("[INFO] 发现 Cookie 询问框，正在点击 'Accept All'...")
            sb.click('button.cky-btn.cky-btn-accept')
            time.sleep(1)
    except Exception:
        print("[INFO] 未检测到 Cookie 询问框或已自动关闭。")

def main():
    if not USER_EMAIL or not FIXED_PASSWORD or not LOGIN_URL or not TARGET_URL:
        print("[ERROR] 缺少必要的环境变量（USER_EMAIL, FIXED_PASSWORD, LOGIN_URL, TARGET_URL），请检查配置。")
        return

    # 使用 SeleniumBase uc 模式启动浏览器
    with SB(uc=True, test=True, locale="zh") as sb:
        screenshot_path = "step_screenshot.png"
        
        try:
            # ==================== 第一步：登录 ====================
            print("[INFO] 正在打开登录页面...")
            sb.open(LOGIN_URL)
            time.sleep(3)

            # 处理可能挡住视线的 Cookie 询问框
            accept_cookies_if_present(sb)

            # 填写账号密码（增加等待与滚动、聚焦保障，确保密码能正确填入）
            print("[INFO] 正在输入邮箱和密码...")
            sb.type('input[name="Email"]', USER_EMAIL)
            time.sleep(1)
            
            # 针对密码框做稳定性优化
            sb.wait_for_element('input[name="Password"]', timeout=10)
            sb.type('input[name="Password"]', FIXED_PASSWORD)
            time.sleep(1)
            
            # 处理登录页面的 CF 验证
            handle_cloudflare_turnstile(sb, "登录页")

            # 点击 Sign In 按钮
            print("[INFO] 正在点击登录按钮...")
            sb.click('button[type="submit"]')
            time.sleep(4)

            # 截图并发送 Telegram
            sb.save_screenshot(screenshot_path)
            send_telegram_message("【步骤 1/2】账号登录成功，已过验证并提交表单。", screenshot_path)

            # ==================== 第二步：进入后台并重置 ====================
            print(f"[INFO] 正在跳转到目标页面: {TARGET_URL}")
            sb.open(TARGET_URL)
            time.sleep(4)

            # 处理后台页面的 CF 验证
            handle_cloudflare_turnstile(sb, "后台页")

            # 点击 Reset timer 按钮
            print("[INFO] 正在点击 Reset timer...")
            sb.click('button[aria-label="Reset timer"]')
            time.sleep(2)

            # 处理可能再次出现的验证
            handle_cloudflare_turnstile(sb, "Reset弹窗")

            # 点击 Just Reset 按钮
            print("[INFO] 正在点击 Just Reset...")
            sb.click('button:has(i.bi-arrow-clockwise)')
            time.sleep(3)

            # 读取 reset 后的剩余时间
            try:
                remaining_time_elem = sb.find_element('span.hidden.sm\\:inline')
                remaining_time_text = remaining_time_elem.text
                print(f"[INFO] 当前剩余时间: {remaining_time_text}")
            except Exception:
                remaining_time_text = "未能成功获取剩余时间"
                print(f"[WARN] {remaining_time_text}")

            # 检查 Start 按钮是否存在，存在则点击
            start_clicked = False
            try:
                start_btn = sb.find_element('xpath://button[contains(normalize-space(text()), "Start")]')
                if start_btn:
                    print("[INFO] 发现 Start 按钮，正在点击...")
                    sb.click('xpath://button[contains(normalize-space(text()), "Start")]')
                    start_clicked = True
                    time.sleep(3)
            except Exception:
                print("[INFO] 未发现 Start 按钮或当前无需点击。")

            # 最终截图并发送 Telegram 通知
            sb.save_screenshot(screenshot_path)
            msg = (
                f"【步骤 2/2】操作执行完成！\n"
                f"⏱️ 剩余时间: {remaining_time_text}\n"
                f"▶️ Start按钮已点击: {'是' if start_clicked else '否'}"
            )
            send_telegram_message(msg, screenshot_path)
            print("[INFO] 所有步骤执行完毕！")

        except Exception as e:
            error_msg = f"[ERROR] 任务执行过程中发生异常: {str(e)}"
            print(error_msg)
            try:
                sb.save_screenshot(screenshot_path)
                send_telegram_message(error_msg, screenshot_path)
            except:
                send_telegram_message(error_msg)
        finally:
            if os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except:
                    pass

if __name__ == "__main__":
    main()
