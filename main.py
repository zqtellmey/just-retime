import os
import time
import requests
from PIL import Image, ImageDraw
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

def draw_red_dot_on_image(image_path, x, y, radius=8):
    """直接在生成的截图文件上画一个红点，不依赖浏览器 JS，绝对不崩溃"""
    try:
        if not os.path.exists(image_path):
            return
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        # 画红点 (带白色外边框，方便高亮)
        draw.ellipse((x - radius - 2, y - radius - 2, x + radius + 2, y + radius + 2), fill="white")
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="red")
        img.save(image_path)
        print(f"[INFO] 已在截图文件 ({x}, {y}) 位置标注红点。")
    except Exception as e:
        print(f"[WARN] 截图画红点失败: {e}")

def handle_cloudflare_turnstile(sb, step_name):
    """固定执行 3 次物理点击，每次间隔 2 秒，不判断成败直接执行后续动作"""
    print(f"[INFO] ({step_name}) 开始执行 Cloudflare Turnstile 穿透（固定尝试 3 次，间隔 2 秒）...")

    for cf_attempt in range(3):
        try:
            print(f"[INFO] ({step_name}) 尝试物理 GUI 点击验证 (第 {cf_attempt + 1}/3 次)...")
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"[WARN] ({step_name}) 第 {cf_attempt + 1} 次点击异常: {e}")
        
        print(f"[INFO] ({step_name}) 等待 2 秒...")
        time.sleep(2)
        
    print(f"[INFO] ({step_name}) 3 次固定点击完成，继续执行后续动作。")
    return True

def accept_cookies_if_present(sb):
    """检测并点击 Cookie 询问框的 Accept All 按钮"""
    try:
        print("[INFO] 检查是否存在 Cookie 询问框...")
        cookie_btn = sb.find_element('button.cky-btn-accept', timeout=3)
        if cookie_btn:
            print("[INFO] 发现 Cookie 询问框，正在点击 'Accept All'...")
            sb.click('button.cky-btn-accept')
            time.sleep(2)
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
            time.sleep(4)

            accept_cookies_if_present(sb)

            print("[INFO] 正在输入邮箱...")
            sb.wait_for_element('input[name="Email"]', timeout=15)
            sb.type('input[name="Email"]', USER_EMAIL)
            time.sleep(2)
            
            print("[INFO] 正在输入密码...")
            sb.wait_for_element('//*[@id="password"]', timeout=15)
            sb.type('//*[@id="password"]', FIXED_PASSWORD)
            time.sleep(2)
            
            handle_cloudflare_turnstile(sb, "登录页")

            print("[INFO] 正在点击登录按钮...")
            sb.click('button[type="submit"]')
            time.sleep(4)

            sb.save_screenshot(screenshot_path)
            send_telegram_message("【步骤 1/2】账号登录成功，已过验证并提交表单。", screenshot_path)

            # ==================== 第二步：进入后台并重置 ====================
            print(f"[INFO] 正在跳转到目标页面: {TARGET_URL}")
            sb.open(TARGET_URL)
            time.sleep(5)

            print("[INFO] 正在点击 Reset timer...")
            sb.wait_for_element('button[aria-label="Reset timer"]', timeout=15)
            sb.click('button[aria-label="Reset timer"]')
            time.sleep(3)

            handle_cloudflare_turnstile(sb, "Reset弹窗")

            # ==================== 使用 PyAutoGUI 绝对坐标点击 Just Reset 按钮 ====================
            TARGET_X = 590
            TARGET_Y = 795
            
            print(f"[INFO] 正在执行纯物理坐标点击 -> X: {TARGET_X}, Y: {TARGET_Y}")
            try:
                import pyautogui
                pyautogui.click(TARGET_X, TARGET_Y)
                print("[INFO] PyAutoGUI 物理坐标点击完成。")
            except Exception as e:
                print(f"[ERROR] PyAutoGUI 点击异常: {e}")

            time.sleep(3)

            # 读取 reset 后的剩余时间（纯 Selenium 选择器，不调 JS）
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

            # 截取最终图片，并在本地图片文件上标注红点
            sb.save_screenshot(screenshot_path)
            draw_red_dot_on_image(screenshot_path, TARGET_X, TARGET_Y)

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
